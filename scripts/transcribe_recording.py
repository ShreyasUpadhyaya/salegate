"""Transcribe a stored recording and print its utterances.

    uv run python scripts/transcribe_recording.py --recording 1

Uses the disk cache, so rerunning after the first call costs nothing. Pass
--no-cache to force a fresh Deepgram call.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.config import DEAD_AIR_THRESHOLD_S  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.ingest.transcribe import (  # noqa: E402
    TranscriptionError,
    cache_path,
    transcribe_recording,
    utterance_gaps,
)
from app.models import Recording, Utterance  # noqa: E402


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Transcribe a stored recording.")
    parser.add_argument("--recording", type=int, required=True, help="recordings.id")
    parser.add_argument("--no-cache", action="store_true", help="force a fresh Deepgram call")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    session = SessionLocal()
    try:
        recording = session.get(Recording, args.recording)
        if recording is None:
            print(f"No recording {args.recording}")
            return 1

        cached = cache_path(recording.sha256)
        print(f"Recording {recording.id}, lead {recording.lead_id}, state {recording.state}")
        print(f"Cache {'hit' if cached.is_file() else 'miss'}: {cached}")

        try:
            count = transcribe_recording(session, recording.id, use_cache=not args.no_cache)
        except TranscriptionError as exc:
            print(f"Failed: {exc}")
            return 1

        rows = session.scalars(
            select(Utterance)
            .where(Utterance.recording_id == recording.id)
            .order_by(Utterance.idx)
        ).all()

        print(f"\n{count} utterances, state now {recording.state}\n")
        print(f"{'idx':>3}  {'speaker':<9} {'start':>8} {'end':>8} {'conf':>5}  text")
        print("-" * 100)
        for row in rows:
            print(
                f"{row.idx:>3}  {row.speaker:<9} {row.start_s:>8.2f} {row.end_s:>8.2f} "
                f"{row.avg_confidence:>5.2f}  {row.text_redacted}"
            )

        speakers: dict[str, float] = {}
        for row in rows:
            speakers[row.speaker] = speakers.get(row.speaker, 0.0) + (row.end_s - row.start_s)
        total = sum(speakers.values()) or 1.0
        print("\nTalk time")
        for speaker, seconds in sorted(speakers.items(), key=lambda kv: -kv[1]):
            print(f"  {speaker:<9} {seconds:>7.1f}s  {seconds / total * 100:>5.1f}%")

        gaps = [g for g in utterance_gaps([
            {"start_s": r.start_s, "end_s": r.end_s} for r in rows
        ]) if g[1] >= 5.0]
        print(f"\nGaps of 5s or more (dead air threshold is {DEAD_AIR_THRESHOLD_S}s)")
        if not gaps:
            print("  none")
        for start, seconds in gaps:
            flag = "  <- DEAD AIR" if seconds >= DEAD_AIR_THRESHOLD_S else ""
            print(f"  at {start:>7.2f}s  {seconds:>6.2f}s{flag}")
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
