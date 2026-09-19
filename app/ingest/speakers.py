"""Speaker attribution for single-voice recordings.

Deepgram diarization is the first choice. When it returns one speaker for the
whole call, which is what a solo take produces (DECISIONS D18), turns are
recovered by aligning the words against the script that was actually read.

The alignment is monotonic: it walks forward through the script and never jumps
back, so a repeated phrase cannot pull the pointer backwards. Word timings from
Deepgram give every recovered turn an exact start and end, which the evidence
contract needs.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from app.config import SPEAKER_MATCH_MIN_SCORE, UNKNOWN_SPEAKER_CONFIDENCE

SPEAKER_AGENT = "agent"
SPEAKER_CUSTOMER = "customer"
SPEAKER_UNKNOWN = "unknown"

SOURCE_DIARIZATION = "diarization"
SOURCE_ALIGNMENT = "script_alignment"

# A redaction token is not speech, so it never matches a script line. It belongs
# to whoever was talking, which is the turn it interrupts.
_REDACTION_TOKEN = re.compile(r"\[[A-Z_]+_\d+\]")

# Markdown noise in the script: bold, italics, check markers, stage directions.
_MARKERS = re.compile(r"\[(?:A-CRIT|B|C|G)\]")
_BOLD_ITALIC = re.compile(r"[*_]+")
_ROLE_LINE = re.compile(r"^\*{0,2}(AGENT|CUSTOMER)\*{0,2}\s*:\s*(.*)$", re.IGNORECASE)

# How far ahead the aligner may look. A turn never skips more than this many
# script lines, which stops a late line from stealing an early one.
LOOKAHEAD_LINES = 6

# Two candidate lines this close in score are a tie, broken by the word gap.
TIE_MARGIN = 4.0

# How far before a redaction token the card turn may start. The customer's card
# offer runs a few words into the digits; anything earlier is ordinary speech.
CARD_LEAD_IN_WORDS = 12


@dataclass(frozen=True)
class ScriptLine:
    """One spoken line from the read script."""

    idx: int
    speaker: str
    text: str


@dataclass
class Turn:
    """A recovered speaker turn, with the words that make it up."""

    speaker: str
    start_s: float
    end_s: float
    text: str
    confidence: float
    speaker_source: str
    script_idx: int | None = None
    match_score: float = 0.0
    words: list[dict[str, Any]] = field(default_factory=list)


def normalise(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. Matching only."""
    text = _MARKERS.sub(" ", text)
    text = _BOLD_ITALIC.sub("", text)
    text = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def parse_script(path: Path) -> list[ScriptLine]:
    """Ordered AGENT/CUSTOMER lines from the read script.

    Only lines that open with a role label are spoken. Stage directions, italic
    notes, headings, tables and the check markers are dropped.
    """
    lines: list[ScriptLine] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if not stripped or stripped.startswith(("#", "|", ">", "-", "`")):
            continue
        match = _ROLE_LINE.match(stripped)
        if match is None:
            continue
        speaker = match.group(1).lower()
        spoken = normalise(match.group(2))
        if not spoken:
            continue
        lines.append(
            ScriptLine(idx=len(lines), speaker=speaker, text=spoken)
        )
    return lines


def _score(candidate: str, script_text: str) -> float:
    """How well a run of words matches a whole script line.

    ratio is the backbone because the run should match the line end to end.
    partial_ratio and token_set_ratio rescue mishears and dropped words, but
    both score 100 on a single word inside a long line, so they are damped by
    how much of the line the run actually covers. Without that, the aligner
    happily cuts a turn after one word.
    """
    if not candidate:
        return 0.0
    expected = len(script_text.split())
    got = len(candidate.split())
    coverage = min(got / expected, 1.0) if expected else 0.0
    loose = max(
        fuzz.partial_ratio(candidate, script_text),
        fuzz.token_set_ratio(candidate, script_text),
    )
    return max(fuzz.ratio(candidate, script_text), loose * coverage)


def _best_line(
    words: list[dict[str, Any]], start: int, script: list[ScriptLine]
) -> tuple[int, float]:
    """Best script line at or after `start` for this run of words.

    Returns the script index and its score. Only looks a few lines ahead, so a
    phrase repeated later in the call cannot capture an earlier turn.
    """
    text = normalise(" ".join(w.get("punctuated_word", w["word"]) for w in words))
    best_idx, best_score = start, 0.0
    for offset in range(min(LOOKAHEAD_LINES, len(script) - start)):
        idx = start + offset
        score = _score(text, script[idx].text)
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx, best_score


def align_words_to_script(
    words: list[dict[str, Any]], script: list[ScriptLine]
) -> list[Turn]:
    """Cut a word stream into turns by walking the script forward.

    A turn ends when extending it stops improving the match against the current
    script line and the next line fits the following words better. Ties are
    broken towards the larger word gap, which is the only thing timing is used
    for here: the gaps are too small to split on alone (D18).
    """
    if not words or not script:
        return []

    turns: list[Turn] = []
    cursor = 0  # first unconsumed word
    pointer = 0  # first script line still available

    while cursor < len(words):
        # A redaction token ends a turn wherever it falls. The card digits are
        # spoken by the customer, and without a forced cut the offer, the token
        # and the agent's refusal fuse into one agent turn (D18).
        token_at = _next_redaction_token(words, cursor)
        if token_at is not None and token_at - cursor <= CARD_LEAD_IN_WORDS:
            # Only the run immediately before the token is the card turn. Words
            # further back are ordinary speech and still align normally, which
            # is why this is bounded rather than reaching back to the cursor.
            turns.append(_card_turn(words[cursor : token_at + 1]))
            cursor = token_at + 1
            # The card run may have consumed script lines, so resync the pointer
            # to whichever line the words after the token match. Still forward
            # only: the search starts at the current pointer.
            pointer = _resync_pointer(words, cursor, script, pointer)
            continue

        if pointer >= len(script):
            turns.append(_unmatched_turn(words[cursor:]))
            break

        line_idx, length, score = _claim_next_line(
            words, cursor, script, pointer, stop_before=token_at
        )

        if line_idx is None or length == 0:
            # Nothing ahead matches, so the rest is unattributable.
            turns.append(_unmatched_turn(words[cursor:]))
            break

        turns.append(_make_turn(words[cursor : cursor + length], script, line_idx, score))
        cursor += length
        pointer = line_idx + 1

    return turns


def _resync_pointer(
    words: list[dict[str, Any]],
    cursor: int,
    script: list[ScriptLine],
    pointer: int,
) -> int:
    """Best script line for the words after a forced cut, searching forward.

    Looks further ahead than the normal step because a card turn can span
    several script lines at once.
    """
    if cursor >= len(words):
        return pointer
    lookahead = words[cursor : cursor + 14]
    best_idx, best_score = pointer, 0.0
    # A card turn can swallow several script lines, and the token itself matches
    # nothing, so the pointer can be far behind. Search the rest of the script
    # rather than a fixed window, still forward only from `pointer`.
    for idx in range(pointer, len(script)):
        text = normalise(
            " ".join(w.get("punctuated_word", w["word"]) for w in lookahead)
        )
        score = _score(text, script[idx].text)
        if score > best_score:
            best_idx, best_score = idx, score
    return best_idx if best_score >= SPEAKER_MATCH_MIN_SCORE else pointer


def _next_redaction_token(words: list[dict[str, Any]], cursor: int) -> int | None:
    """Index of the next word that is a redaction token, at or after cursor."""
    for position in range(cursor, len(words)):
        word = words[position].get("punctuated_word", words[position]["word"])
        if _REDACTION_TOKEN.search(str(word)):
            return position
    return None


def _card_turn(words: list[dict[str, Any]]) -> Turn:
    """The run ending in a redaction token. Always the customer (D18).

    Card data is read out by the customer, never by the agent, so the token and
    the words leading into it belong to the customer.
    """
    text = " ".join(w.get("punctuated_word", w["word"]) for w in words).strip()
    avg_conf = sum(float(w.get("confidence", 0.0)) for w in words) / max(len(words), 1)
    return Turn(
        speaker=SPEAKER_CUSTOMER,
        start_s=float(words[0]["start"]),
        end_s=float(words[-1]["end"]),
        text=text,
        confidence=avg_conf,
        speaker_source=SOURCE_ALIGNMENT,
        script_idx=None,
        match_score=0.0,
        words=words,
    )


def _claim_next_line(
    words: list[dict[str, Any]],
    cursor: int,
    script: list[ScriptLine],
    pointer: int,
    stop_before: int | None = None,
) -> tuple[int | None, int, float]:
    """Find the script line the next run of words belongs to, and how long it is.

    Tries each line within the lookahead and each plausible run length, and
    keeps the best scoring pair. Monotonic by construction: it only ever looks
    at `pointer` onwards.
    """
    best: tuple[int | None, int, float] = (None, 0, 0.0)
    # Never run a turn past a redaction token: that boundary is not negotiable.
    limit = len(words) - cursor if stop_before is None else stop_before - cursor
    if limit <= 0:
        return (None, 0, 0.0)

    for offset in range(min(LOOKAHEAD_LINES, len(script) - pointer)):
        line_idx = pointer + offset
        line = script[line_idx]
        expected = len(line.text.split())
        # A spoken line runs roughly as long as the script line, give or take
        # disfluencies and mishears.
        lengths = range(
            max(1, expected - 4),
            min(limit, expected + 6) + 1,
        )
        for length in lengths:
            run = words[cursor : cursor + length]
            if not run:
                continue
            text = normalise(" ".join(w.get("punctuated_word", w["word"]) for w in run))
            score = _score(text, line.text)
            # A later line must beat the earlier one outright, so equal scores
            # keep the earliest line and the alignment stays in order.
            if score > best[2] + (TIE_MARGIN if offset else 0.0):
                best = (line_idx, length, score)

    if best[0] is None or best[2] < SPEAKER_MATCH_MIN_SCORE:
        # Nothing convincing. Emit the words up to the next real pause as one
        # unknown turn rather than guessing a speaker.
        length = min(_run_to_pause(words, cursor), limit)
        return (pointer, length, 0.0) if length else (None, 0, 0.0)
    return best


def _run_to_pause(words: list[dict[str, Any]], cursor: int) -> int:
    """Words up to the next noticeable pause, or all of them."""
    for position in range(cursor, len(words)):
        if words[position].get("gap_after", 0.0) >= 0.15:
            return position - cursor + 1
    return len(words) - cursor


def _unmatched_turn(words: list[dict[str, Any]]) -> Turn:
    """Words that matched no script line at all."""
    text = " ".join(w.get("punctuated_word", w["word"]) for w in words).strip()
    avg_conf = sum(float(w.get("confidence", 0.0)) for w in words) / max(len(words), 1)
    return Turn(
        speaker=SPEAKER_UNKNOWN,
        start_s=float(words[0]["start"]),
        end_s=float(words[-1]["end"]),
        text=text,
        confidence=min(avg_conf, UNKNOWN_SPEAKER_CONFIDENCE),
        speaker_source=SOURCE_ALIGNMENT,
        script_idx=None,
        match_score=0.0,
        words=words,
    )


def _make_turn(
    words: list[dict[str, Any]], script: list[ScriptLine], idx: int, score: float
) -> Turn:
    """Build one turn, sending weak matches to unknown."""
    text = " ".join(w.get("punctuated_word", w["word"]) for w in words).strip()
    confident = score >= SPEAKER_MATCH_MIN_SCORE
    speaker = script[idx].speaker if confident else SPEAKER_UNKNOWN
    avg_conf = sum(float(w.get("confidence", 0.0)) for w in words) / max(len(words), 1)
    return Turn(
        speaker=speaker,
        start_s=float(words[0]["start"]),
        end_s=float(words[-1]["end"]),
        text=text,
        # An unresolved speaker must not let a critical check PASS (hard rule 7).
        confidence=avg_conf if confident else min(avg_conf, UNKNOWN_SPEAKER_CONFIDENCE),
        speaker_source=SOURCE_ALIGNMENT,
        script_idx=idx if confident else None,
        match_score=round(float(score), 1),
        words=words,
    )


def attach_redaction_tokens(turns: list[Turn]) -> list[Turn]:
    """A turn that is only a redaction token inherits the previous speaker.

    The card digits are spoken by whoever was already talking, so the token
    belongs to that turn rather than to nobody.
    """
    for position, turn in enumerate(turns):
        if not _REDACTION_TOKEN.fullmatch(turn.text.strip().rstrip(".")):
            continue
        if position == 0:
            continue
        previous = turns[position - 1]
        turn.speaker = previous.speaker
        turn.speaker_source = previous.speaker_source
    return turns


def diarization_speaker_count(utterances: list[dict[str, Any]]) -> int:
    return len({u.get("speaker") for u in utterances if u.get("speaker") is not None})


def words_with_gaps(utterances: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every word in order, each carrying the pause that follows it."""
    words: list[dict[str, Any]] = []
    for utterance in utterances:
        words.extend(dict(w) for w in utterance.get("words", []))
    for previous, current in zip(words, words[1:], strict=False):
        previous["gap_after"] = round(float(current["start"]) - float(previous["end"]), 3)
    if words:
        words[-1]["gap_after"] = 0.0
    return words


def resolve_speakers(
    payload: dict[str, Any], script_path: Path | None = None
) -> list[Turn]:
    """Turns for a transcript, by diarization when it worked, else by alignment.

    Diarization stays the first choice: if Deepgram separated two or more
    speakers, its labels are kept and the script is not consulted at all.
    """
    utterances = payload.get("results", {}).get("utterances") or []
    if not utterances:
        return []

    if diarization_speaker_count(utterances) >= 2:
        return _turns_from_diarization(utterances)

    if script_path is None or not script_path.is_file():
        return _turns_from_diarization(utterances)

    script = parse_script(script_path)
    if not script:
        return _turns_from_diarization(utterances)

    turns = align_words_to_script(words_with_gaps(utterances), script)
    return attach_redaction_tokens(turns)


def _turns_from_diarization(utterances: list[dict[str, Any]]) -> list[Turn]:
    """Keep Deepgram's own speaker split, mapping labels to roles."""
    from app.ingest.transcribe import identify_agent_speaker

    agent = identify_agent_speaker(utterances)
    turns: list[Turn] = []
    for utterance in utterances:
        label = utterance.get("speaker")
        if label is None or agent is None:
            speaker = SPEAKER_UNKNOWN
        elif int(label) == agent:
            speaker = SPEAKER_AGENT
        else:
            speaker = SPEAKER_CUSTOMER
        turns.append(
            Turn(
                speaker=speaker,
                start_s=float(utterance.get("start", 0.0)),
                end_s=float(utterance.get("end", 0.0)),
                text=(utterance.get("transcript") or "").strip(),
                confidence=float(utterance.get("confidence", 0.0)),
                speaker_source=SOURCE_DIARIZATION,
                words=list(utterance.get("words", [])),
            )
        )
    return turns
