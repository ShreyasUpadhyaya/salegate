# Solo call recording script (iPhone)

Target length: 4 to 5 minutes. One take. You read both roles.
All names, addresses, emails and numbers below are fictional test data.

Values this call must match (these are what the checks compare against):
| Field | CRM / rate card value | What the agent says on the call |
|---|---|---|
| Plan | NBN 25 Mbps | NBN 25 |
| Promo price | $42.90/month, first 6 months | $42.90 (correct) |
| Ongoing price | $72.90/month | **$79.90, said twice (deliberate FAIL)** |
| Modem | Netcomm CF40, free | Netcomm CF40, free (correct) |
| Email | jordan.avery@example.com | **"j dot avery at example dot com" (deliberate FAIL)** |
| DOB | 14 March 1990 | 14 March 1990 (correct) |
| Address | 12 Sample Street, Testville NSW 2000 | same (correct) |

If `data/scripts/agent_script.md` in the repo uses different values, tell Claude Code:
"Align the lead fixture and rate card to call_recording_script.md, that is what I recorded."

---

## Before you press record

1. iPhone: **Settings > Apps > Voice Memos > Audio Quality > Lossless.**
2. Quiet room, fan and AC off, phone on a table about 20 cm from your mouth. Do Not Disturb on.
3. Two voices, one person:
   - **AGENT:** calm, steady, slightly slower, lower pitch. Sit upright.
   - **CUSTOMER:** faster, more casual, a bit higher pitch. Lean slightly closer to the phone.
4. Leave a **full 2 second pause at every speaker change.** This matters more than the voice difference.
5. If you stumble, keep going. A small stumble is realistic. Only restart for a big mistake in a marked **[CHECK]** line.

Markers: **[A-CRIT]** script check, critical. **[B]** factual check. **[C]** behaviour note. **[G]** guardrail test.

---

## The script

**AGENT:** Hi, is this Jordan? My name's Sam, I'm calling from econnex about the internet plan comparison you started online yesterday.

**CUSTOMER:** Yeah, that's me. Hi.

**AGENT:** **[A-CRIT] Before we go any further, just letting you know this call will be recorded for quality assurance and training purposes.** Is that okay with you?

**CUSTOMER:** Yeah, that's fine.

*(This comes before any personal detail on purpose. The real CIMET call got this order wrong.)*

**AGENT:** **[A-CRIT] Great. And can I confirm you're the account holder for the internet service at this address?**

**CUSTOMER:** Yes, I'm the account holder.

**AGENT:** **[B] Thanks. Can you confirm your date of birth for me?**

**CUSTOMER:** Fourteenth of March, nineteen ninety.

**AGENT:** **[B] And the service address is twelve Sample Street, Testville, New South Wales, two thousand. Is that right?**

**CUSTOMER:** Yep, that's it.

**AGENT:** Lovely. So based on what you entered, the plan that suits you is our NBN twenty-five plan. It's good for streaming and working from home for one to two people.

**CUSTOMER:** Okay. What's it cost though? That's the main thing for me.

**AGENT:** **[B] For the first six months it's forty-two dollars ninety a month.** **[B] After that it goes to seventy-nine dollars ninety a month.**

*(Deliberate mismatch: rate card says 72.90.)*

**CUSTOMER:** Hmm, seventy-nine ninety after six months? That's a bit more than I was hoping.

**AGENT:** **[C]** I understand. The good news is there's no lock-in contract, so if it's not working for you, you can leave anytime. And you get the Netcomm CF40 modem included free.

**CUSTOMER:** Right. So there's no contract at all?

**AGENT:** That's right, it's month to month. Just to be clear again, **[B] it's forty-two ninety for six months, then seventy-nine ninety ongoing.**

*(Second deliberate repeat of the wrong price.)*

**CUSTOMER:** Okay, fine, let's do it.

**AGENT:** **[B] Great. I just need to confirm your email for the welcome pack. I have it as j dot avery at example dot com.**

*(Deliberate mismatch: CRM says jordan.avery@example.com.)*

**CUSTOMER:** Yep, that's right.

**AGENT:** Thanks, and I'll need the latest bill from your current provider to check the connection. Could you grab that for me?

**CUSTOMER:** Oh, give me a sec, let me find it.

**[C] SILENCE: stay completely quiet for 25 seconds. Count in your head. Don't move the phone.**

**CUSTOMER:** Sorry, got it. What do you need off it?

**AGENT:** Just the account number at the top.

**CUSTOMER:** It's A-C-C, four four seven two one.

**AGENT:** Thanks. Now I need to read you the key information for this plan, please listen carefully.

**AGENT:** **[A-CRIT] This plan is NBN twenty-five with typical evening download speeds of twenty-five megabits per second. There is no minimum term and no early exit fee. The monthly charge is forty-two dollars ninety for the first six months, then the standard monthly charge applies. The included modem is yours to keep. Your Critical Information Summary will be emailed to you and you can also find it on our website.**

*(This is the CIS read. The rate in it is left vague on purpose; the explicit wrong price was already stated twice above.)*

**CUSTOMER:** Okay.

**AGENT:** **[A-CRIT] Do you understand and agree to switch your internet service to this plan on these terms?**

**CUSTOMER:** Yes, I agree.

**CUSTOMER:** **[G]** Do you need my card now? It's four one one one, one one one one, one one one one, one one one one.

*(Say the customer's line quickly, straight after "I agree", with only a short 1 second gap. That is also your interruption beat.)*

**AGENT:** **[G] Sorry Jordan, please stop there. I can't take card details over this call. You'll get a secure payment link by email.**

*(Deliberate guardrail test: redact=pci and the Luhn pass must hide these digits. The agent's refusal is the compliant behaviour. 4111 1111 1111 1111 is the published Visa test number and bills nothing.)*

**CUSTOMER:** Oh, okay, no worries.

**AGENT:** Your connection should be active within five business days. Is there anything else I can help you with today?

**CUSTOMER:** No, that's all. Thanks Sam.

**AGENT:** Thanks Jordan, have a great day.

**Stop recording after 3 seconds of silence.**

---

## Expected result when scored

| Check                    | Expected                           | Why                         |
| ------------------------ | ---------------------------------- | --------------------------- |
| Recording disclaimer     | PASS                               | Said first, before any data |
| Account holder confirmed | PASS                               | Direct question and yes     |
| DOB, address             | PASS                               | Match CRM                   |
| Ongoing price            | **FAIL (critical)**                | 79.90 said, rate card 72.90 |
| Email read-back          | **FAIL (critical)**                | j.avery vs jordan.avery     |
| CIS read                 | PASS or REVIEW                     | Near-verbatim read          |
| Explicit consent         | PASS                               | "Yes, I agree"              |
| Card number spoken       | Violation flagged, digits redacted | Guardrail test              |
| Dead air                 | NOTE                               | 25 seconds, never blocks    |
| **Gate decision**        | **HELD_TL**                        | Two critical fails          |

---

## Getting the file onto your laptop

1. Voice Memos: tap the recording, rename it `call`.
2. Tap **... > Share > Save to Files > iCloud Drive**. On Windows open icloud.com, go to Drive, download `call.m4a`.
   (Alternative: Share > Mail, send to yourself, download the attachment. Avoid WhatsApp, it compresses audio.)
3. Put it in `C:\dev\salegate\data\recordings\demo\` and convert to wav, since the ingestion step reads wav:

```powershell
cd C:\dev\salegate
ffmpeg -i data\recordings\demo\call.m4a -ac 1 -ar 16000 data\recordings\demo\call.wav
ffprobe -hide_banner data\recordings\demo\call.wav
```

`ffprobe` should show 1 channel, 16000 Hz, and a duration of about 4 to 5 minutes.
The audio stays local: `data/` is gitignored, so it is never committed.

4. Then send Claude Code the Phase 3 prompt.
