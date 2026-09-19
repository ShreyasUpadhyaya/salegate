---
name: commit-cadence
description: Use whenever a phase finishes, tests go green after a meaningful change, or 30 minutes have passed since the last commit in the CIMET hackathon repo. Defines commit timing, checks and message style.
---

# Commit cadence

## When
- End of every PLAN.md phase, and never more than 30 minutes without a commit.
- Only commit a working state: tests green, app starts.
- Never commit before 09:30 on build day. Check the clock with `Get-Date -Format HH:mm` first.

## Pre-commit checks
1. `uv run ruff check . --fix` and `uv run pytest -q` pass.
2. `git status`: no `.env`, `data/`, `cache/`, audio files, or real transcripts staged.
3. Search staged diff for key-like strings: `git diff --cached | Select-String -Pattern "sk-|AIza|api_key\s*="` plus the first 6 characters of your Deepgram key. Must be empty.

## Message style
- Plain English a person would say out loud, sentence case, describes the outcome.
- Subject max 72 characters. Optional second line max 72 characters. Never more than 2 lines.
- No conventional-commit prefixes, no emoji, no trailers, no co-author lines, no em dashes, never the word "perfect".
- Use `git commit -m "<subject>"` or `git commit -m "<subject>" -m "<second line>"`.

Good: `Compare quoted rates, email and dates with CRM and the rate card`
Good: `Hold sales on critical fails and send unsure checks to QA` / `Clean calls still get a 5% human sample`
Bad: `feat(scoring): implement gate logic`   Bad: `updates`   Bad: `WIP`

## After committing
`git push`, then suggest `/clear` if the phase is done.
