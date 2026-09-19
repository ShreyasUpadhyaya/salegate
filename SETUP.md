# SETUP.md: tonight and tomorrow morning

Goal for tonight: keys working, tools installed, packages cached, skills installed. No project code, no repo commits.

## 1. Deepgram key (transcription, free credit)
1. Go to console.deepgram.com and sign up (Google sign-in is fine). No card is needed for the free credit.
2. Confirm the Billing/Usage page shows the $200 starting credit.
3. Do not add a card. Without a card there is no auto top-up, so you cannot be charged.
4. Open your project (one is created for you) -> API Keys -> Create a new API key.
   Name `cimet-hackathon`, role Member, set an expiry of a few days if offered.
5. Copy the key once into a password manager or a local text file outside any repo.

## 2. Gemini key (optional LLM for unresolved semantic checks, free tier)
1. Go to aistudio.google.com -> Get API key -> Create API key (new project is fine).
2. Do not enable billing. Free tier only.
3. In AI Studio, check which Flash-Lite model shows free quota and note its exact model id. Free Flash-Lite
   has far more requests per day than free Flash, which matters. Put that id in `GEMINI_MODEL`.
4. Only synthetic data goes to it. Free-tier prompts may be used by Google to improve products; that is fine for test data only.

## 3. Expected spend
Deepgram: one 30 minute call costs well under 1 USD of the free credit, even with add-ons. Transcripts are cached, so reruns cost nothing.
Gemini: free tier. Claude Code: already on Pro. Total out of pocket: 0.

## 4. `.env` template (create in the project folder on the day, never commit)
```
DEEPGRAM_API_KEY=
DEEPGRAM_MODEL=nova-3
DEEPGRAM_LANGUAGE=en
GEMINI_API_KEY=
GEMINI_MODEL=
LLM_ENABLED=true
DB_PATH=data/app.db
AUDIO_DIR=data/recordings
CACHE_DIR=cache
QA_SAMPLE_PERCENT=5
```

## 5. Install tools (PowerShell)
```
winget install --id astral-sh.uv -e
winget install --id Gyan.FFmpeg -e
winget install --id GitHub.cli -e
winget install --id Git.Git -e        # skip if installed
uv python install 3.12
gh auth login
claude update
```
Restart the terminal after installs so PATH updates.

## 6. System readiness prompt for Claude Code (run tonight in a scratch folder, e.g. C:\hack-check)
Put the two keys in `C:\hack-check\.env` first, then paste this into Claude Code:

```
This is a readiness check for a hackathon tomorrow on Windows. Do not create a git repo.
Run each check, then print one table: item, expected, found, status, fix.
1. OS version, CPU, RAM, free disk on C: (need 5 GB free).
2. Versions: git, gh (and gh auth status), uv, python via uv (3.12), ffmpeg and ffprobe, docker (and whether the engine is running), node (optional).
3. Ports 8000 and 8501 are free.
4. Network: HTTPS reachability of api.deepgram.com, generativelanguage.googleapis.com, pypi.org, github.com, fonts.googleapis.com.
5. Create a uv project here and add: fastapi uvicorn[standard] sqlalchemy pydantic httpx rapidfuzz pandas streamlit plotly pytest ruff python-dotenv google-genai. This warms the uv cache for tomorrow.
6. Deepgram test: load DEEPGRAM_API_KEY from .env with python-dotenv without printing it. POST the public sample https://dpgr.am/spacewalk.wav to https://api.deepgram.com/v1/listen with model=nova-3, smart_format=true, diarize=true, utterances=true, redact=pci. Print only: HTTP status, duration, number of utterances, first utterance text, and whether words carry start, end, confidence and speaker.
7. Gemini test: with google-genai, send "Reply with the word ready" to GEMINI_MODEL from .env. Print status and reply only.
8. Streamlit smoke test: confirm `uv run streamlit version` works, report the version, and list which theme options that version supports (font faces, baseRadius, borderColor) and whether st.audio supports start_time and autoplay and st.plotly_chart supports on_select.
Never print the keys. At the end list anything I must fix tonight.
```
After it passes, keep `C:\hack-check` until tomorrow (the uv cache is global, so tomorrow's installs are fast either way).

## 7. Claude Code plugins and skills (tonight)
Inside Claude Code:
```
/plugin install frontend-design@claude-plugins-official
/plugin marketplace add anthropics/skills
/plugin install example-skills@anthropic-agent-skills
```
From example-skills you mainly want `webapp-testing` (Playwright screenshots for UI self-critique). If Playwright setup is slow, skip it and screenshot manually.

Copy the three custom skills to your user folder so they work in any project:
```
Copy-Item -Recurse .\.claude\skills\* "$env:USERPROFILE\.claude\skills\"
```
Then run `/skills` (or ask "what skills do you have") to confirm qa-check-engine, qa-console-ui and commit-cadence are listed.

## 8. Usage window trick (Pro plan)
The 5 hour session window starts with your first message. Send one tiny message in Claude Code around 07:30 tomorrow.
That window ends around 12:30, and a fresh one starts with your next message, carrying you through to the end.
Verify the reset time in Settings -> Usage. Do not use claude.ai chat during the build; it shares the pool.

## 9. Tomorrow 09:00 to 09:30 (no commits)
1. Connect to the venue wifi, run: `gh auth status`, and a one-line Deepgram curl or the step 6 checks 6 and 7 again.
2. Create the empty project folder. Copy in: CLAUDE.md, PLAN.md, DECISIONS.md, README.md (template), .claude/settings.json, and your .env.
3. Create `.gitignore` content ready to paste:
```
.env
data/
cache/
handout/
*.wav
*.mp3
*.m4a
__pycache__/
.venv/
.pytest_cache/
.ruff_cache/
```
4. Copy the CIMET handout files into `handout/` when they are given out.

## 10. First prompt at 09:30 (in Claude Code, plan mode)
```
Read CLAUDE.md, PLAN.md and DECISIONS.md fully. Then inspect every file in ./handout: the call recording
(use ffprobe for duration, channels, sample rate), the synthetic lead dataset, the check-library export
and the scoring sandbox payload. Do not write application code yet.
Write docs/data_notes.md with: a file inventory, formats and fields, how the check-library export maps
to our CheckDefinition model (type A/B/C, critical, weight, fatal, versions), what the sandbox payload
expects, whether transcripts have timestamps and speakers, and a list of gaps and assumptions.
Then propose any changes to PLAN.md as a short list and wait for my OK.
After I approve: git init, create the public GitHub repo with gh, add .gitignore, and make the first commit
using the commit-cadence skill.
```
