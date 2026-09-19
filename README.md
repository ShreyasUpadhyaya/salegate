# Salegate

An automated QA gate for CIMET CRM sales calls. Every sale is transcribed, scored against its
retailer's checklist, and gated before it can submit. A clean call goes through automatically.
A call with a failing critical check is held for a team leader, with the failing check, the
transcript line and the audio timestamp attached as evidence.

This is a hackathon build (see `PLAN.md` and `DECISIONS.md` for the full design history). The
checklist itself was derived from a redacted CIMET call transcript, since no check-library export
was provided (see `DECISIONS.md` D19).

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/getting-started/installation/)
- A [Deepgram](https://console.deepgram.com/signup) API key (free tier is enough; used for
  transcription with speaker diarization and word timings)
- ffmpeg, only if you want to record and score your own demo call from a phone recording in a
  container format Deepgram won't take directly (`.m4a`, `.mp4`). Not needed to run the seeded
  demo data or the test suite. Get it from [ffmpeg.org](https://ffmpeg.org/download.html) or your
  package manager.

## Setup

```bash
git clone https://github.com/ShreyasUpadhyaya/salegate.git
cd salegate
cp .env.example .env
```

Open `.env` and set `DEEPGRAM_API_KEY` to your key. `uv` will create the virtual environment and
install every dependency in `pyproject.toml` automatically the first time you run something with
`uv run`.

```bash
uv run python scripts/reset_db.py
uv run python scripts/seed_history.py
```

`reset_db.py` creates a fresh SQLite database at `data/app.db`. `seed_history.py` generates 84
synthetic scored leads across four agents and 28 days, so the queues and dashboards have
something to show. Every seeded lead's id starts with `SEED-` and its status is `SEEDED`, so it
is never mistaken for a real call (see `DECISIONS.md` D12).

## Run it

Two servers, in two terminals:

```bash
uv run uvicorn app.main:app --reload --port 8000
```

```bash
uv run streamlit run ui/Home.py --server.port 8501
```

| Port | What |
|---|---|
| 8000 | FastAPI backend. Swagger UI at `http://127.0.0.1:8000/docs`. |
| 8501 | Streamlit console. Open `http://127.0.0.1:8501` in a browser. |

The console has three pages in its sidebar: **Lead review** (pick a lead, hear the call, see
every check), **Queues** (leads grouped by gate decision, by agent), and **Dashboards** (agent
rollups, first pass yield, critical fail rate).

## Try it

### Seeded leads (work immediately, no extra setup)

Go to **Queues**. It lists agent rollups built from the 84 seeded leads. Pick any agent row, then
go to **Lead review** and type in one of that agent's lead ids (visible via the API, since there
is no list-all-leads endpoint yet):

```bash
curl -s http://127.0.0.1:8000/api/dashboards/agents
```

or query the database directly for a lead id to try:

```bash
uv run python -c "
from app.db import SessionLocal
from app.models import Score
s = SessionLocal()
for row in s.query(Score).limit(5):
    print(row.lead_id, row.decision)
"
```

Paste one of those ids into **Lead review**'s "Lead ID" field. A seeded lead already has a score,
so you will see its verdict immediately: **AUTO_SUBMIT** (cleared every critical check, not
sampled), **QA_REVIEW** (either sampled for the 5% clean-call audit, or a critical check came back
uncertain), or **HELD_TL** (a critical check failed outright). Seeded leads have no real transcript
or audio, so the timeline strip and transcript panel will be empty for them; the checks list and
override flow work the same as for a real call.

### The two self-recorded demo calls (need your own Deepgram credit)

`L-DEMO-1` and `L-DEMO-2` are the two real calls this project was built and tested against: one
call scripted to fail two checks on purpose, one call scripted clean. Their fixture data (CRM
fields, rate card, expected outcome) is tracked at `app/checks/library/lead_L-DEMO-1.json` and
`lead_L-DEMO-2.json`, and the scripts that were read are at `data/scripts/recorded_script.md` and
`data/scripts/clean_call_script.md`. **The audio itself is not in the repo** (`data/` and `cache/`
are gitignored on purpose, per `CLAUDE.md`), so a fresh clone cannot see these two calls without
recording new audio and spending a Deepgram call to transcribe it. If you want to reproduce them:

1. Record yourself reading one of the two scripts above, one voice for both parts, as `.wav`,
   `.mp3` or `.m4a`.
2. Seed the lead's CRM fields and rate card into the database (see the fixture JSON for the exact
   values `L-DEMO-1` uses).
3. `uv run python scripts/dialler_sim.py --lead L-DEMO-1 --file path/to/your.wav`
4. Open **Lead review**, type `L-DEMO-1`, click **Score this lead**.

If you skip this, everything else in the console still works end to end on the seeded data; you
just will not see the click-to-play timeline against a real recording.

### The gate proof

`POST /api/leads/{id}/submit` is the "no sale ships unscored" guarantee. Try it against a lead
that has never been scored, or a lead that is `HELD_TL`:

```bash
curl -s -X POST http://127.0.0.1:8000/api/leads/SEED-xxxx/submit
```

Both cases return `409 Conflict` with a reason in the body. Only a lead whose latest score is
`AUTO_SUBMIT` returns `200`.

## API routes

| Method | Path | Purpose |
|---|---|---|
| POST | `/api/dialler/recordings` | Dialler pushes a recording for a lead, idempotent on lead id and audio hash |
| GET | `/api/leads/{id}/score` | Latest score, every check and its evidence |
| GET | `/api/leads/{id}/transcript` | Utterances and the audio path, for the timeline and click-to-play |
| GET | `/api/leads/{id}/gate` | Gate decision and which critical checks drove it |
| POST | `/api/leads/{id}/submit` | Submits only if scored and not held (409 otherwise) |
| POST | `/api/check-results/{id}/override` | Auditor override, append-only |
| GET | `/api/check-results/{id}/overrides` | Full override history for one check result |
| GET | `/api/dashboards/agents` | Rollups by agent: total scored, decision counts, first pass yield |

## Check types

| Type | Compares | Blocks the sale |
|---|---|---|
| A, script | Transcript vs approved wording (verbatim, coverage, or a question-and-answer confirmation) | Yes if critical |
| B, factual | Transcript vs CRM fields and the plan rate card | Yes if critical |
| C, behaviour | Transcript timings only (dead air, interruptions, talk ratio) | Never |

## Tests

```bash
uv run pytest -q
```

`uv run ruff check . --fix` runs the linter.

## Known limitations, honestly

Speaker attribution on a single-voice recording is recovered by aligning the transcript against
the script that was actually read, since diarization returns one speaker for a solo take
(`DECISIONS.md` D18). This works well on short back-and-forth exchanges but can merge a long,
uninterrupted stretch of agent speech into one oversized turn, which occasionally confuses the
Type B extractor that has to tell a promo price from an ongoing price stated in the same breath
(`DECISIONS.md` D22): on the clean demo call this causes two prices to read as a mismatch that
was not actually spoken wrong. A production system would use dual-channel dialler audio instead,
which removes the whole problem. There is also no endpoint yet to list every lead or every held
lead directly; the Queues page shows agent-level rollups and Lead review takes a lead id typed by
hand. The Streamlit timeline's click-to-select relies on Plotly's selection event, which this
project has smoke-tested through Streamlit's own `AppTest` harness rather than a real browser, so
if you hit a rendering issue Streamlit's browser console is the first place to look.
