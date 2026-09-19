---
name: qa-console-ui
description: Use for any Streamlit page, component, theme, chart or UI copy in the CIMET QA gate. Defines the design direction, tokens, layout and banned patterns so the console does not look like a generic AI dashboard. Pair with the frontend-design plugin.
---

# QA console UI

## Who and what
Users are team leaders and QA auditors clearing a queue of held sales. Their job: see why a sale is held,
hear the exact 20 seconds, fix or challenge, move on. The design is an audit ledger for listening, not a marketing dashboard.

## The one bold element
The call timeline strip on the lead review page: a full-width horizontal bar the length of the call,
thin speaker lanes (agent above, customer below), and a marker at every check timestamp coloured by status.
Clicking a marker or a check row sets the audio start time and plays. Everything else stays quiet.
Build it with plotly and `st.plotly_chart(..., on_select="rerun")`, or a small HTML component if selection is unreliable.
Audio: `st.audio(path, start_time=seconds, autoplay=True)` driven by `st.session_state`.

## Tokens (.streamlit/config.toml plus one injected CSS block in ui/theme.py)
- Ledger `#F6F7F4` background, Sheet `#FFFFFF` panels, Rule `#D6DBD3` borders
- Ink `#1C2430` text, Muted `#5B6573`
- Pass `#1E7A4C`, Fail `#B3261E`, Review `#A15C07`, Note `#4B5B75`, Link `#2B5AA8`
- Type: Public Sans for everything (tabular numerals on), IBM Plex Mono only for timestamps and lead ids.
- Radius 6 px on panels, 3 px on chips. One subtle border, no drop shadows.
Verify which theme keys the installed Streamlit version supports (font faces, baseRadius, borderColor) before relying on them.

## Layout: lead review
```
[ Verdict sentence ................................ Decision chip ]
[ Lead 3613790 | Retailer 1 | Agent A | 30 min | Library v3 (live on call date) ]
[ ========= call timeline strip with markers ============================== ]
[ Checks (left, 45%)                 | Transcript (right, 55%)             ]
[  Failed, critical                  |  scrolls to selected utterance,     ]
[  Needs review                      |  evidence line highlighted,         ]
[  Passed (collapsed)                |  redaction shown as "card number    ]
[  Coaching notes                    |  hidden"                            ]
[ Override panel: new status, reason, auditor, Save override               ]
```
Left aligned. Verdict sentence example: `Held for TL review. 2 critical checks failed: rate quoted and email captured.`

## Copy rules
Sentence case. Plain verbs. Buttons say what happens: "Play from 14:02", "Save override", "Send back to agent".
Errors state what happened and what to do. Empty queue: "No sales waiting. New calls appear here within minutes of hangup."
No em dashes, never the word "perfect", no emoji.

## Banned (the generic AI look)
- Rows of identical metric cards with big number and small label as the page opener.
- Gradient washes, purple accents, glassmorphism, shadows under every panel.
- ALL CAPS eyebrow labels, "A · B · C" meta strings, arrows appended to buttons.
- st.balloons, st.snow, rainbow chart palettes, pie charts.
- Status shown by colour only: always pair colour with a word (Failed, Needs review, Passed).

## Dashboards page
Filters row (period, retailer, campaign, site, TL). Then: agent table with FPY, critical fail rate, score with and without fatal,
sortable. One small-multiples line chart of FPY by week. Bar chart of failing checks ranked. Repeat offender table
(same critical check failing 3+ times in rolling 7 days) with a flag column. Label seeded history as "Seeded demo data".

## Self-critique loop
After each UI change: take a screenshot (Playwright via webapp-testing skill if installed, else ask me for one),
compare against this skill and the frontend-design plugin, fix the three worst issues, stop.
