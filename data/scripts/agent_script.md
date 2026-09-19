# Recording script: outbound NBN sales call

For the self-recorded test call, per DECISIONS D17. Derived from `handout/transcript.pdf` in structure and
wording, with all values invented by us. No real customer detail appears here.

## How to record

Solo, one voice, both parts, one continuous take. Target 3 to 5 minutes.

- **AGENT**: brisk, slightly higher pitch, professional call-centre pace.
- **CUSTOMER**: slower, lower, more hesitant.
- **Leave 1 to 2 seconds of silence between every speaker turn.** This is what lets nova-3 split the turns.
- Read the stage directions in brackets, do not speak them.
- One take. Do not restart on small stumbles: disfluencies are realistic and the real call is full of them.
- Save to `data/recordings/demo/call.wav`.

### The spoken card number is deliberate test behaviour

Partway through, the customer reads out a card number and the agent stops them. **This is not how a
compliant agent handles payment, and it is not us modelling bad practice as acceptable.** In the real
handout call the agent muted the recording before payment and the customer typed the details into a web
form, which is the correct behaviour and is what our agent's refusal line reflects.

We speak the number anyway for one reason: the PCI guardrail cannot be proven on audio that never contains
a card. Hard rule 4 requires Deepgram `redact=pci` plus a local Luhn pass, and a redaction path that has
only ever been exercised in unit tests is a redaction path we do not actually know works. So the script
produces the one condition the guardrail exists for, and the demo shows it being caught: masked at source,
Luhn-checked locally, violation flag raised, zero digits in the database or on screen.

The number is `4111111111111111`, the publicly published Visa test value. It belongs to no one, bills
nothing, and is safe to speak aloud and commit. Never substitute a real card number here.

When demoing, say this out loud. "The customer started reading a card number, the agent stopped them, and
the system redacted it anyway" is a stronger story than a call where the topic never arises.

## Test values used in this script

> **Superseded by the recording.** The call was read from `data/scripts/recorded_script.md`, not from this
> file, and the values below are the ones actually spoken. The CRM fixture and rate card must match this
> table. Wording differs too: the call opens "Hi, is this Jordan?", not "Good afternoon, am I speaking with
> Jordan Avery?". Speaker alignment reads `recorded_script.md` only. See DECISIONS D18.

| Field | CRM / rate card value (the truth) | What the agent says | Result |
|---|---|---|---|
| Plan | NBN 25 Mbps | NBN 25 | match |
| Promo price | 42.90 per month, first 6 months | 42.90 | match |
| Promo term | 6 months | 6 months | match |
| Ongoing price | 72.90 | **79.90, said twice** | **deliberate mismatch, Type B FAIL** |
| Download speed | 25 Mbps typical evening | 25 Mbps | match |
| Email | jordan.avery@example.com | "j dot avery at example dot com" | **deliberate mismatch, Type B FAIL** |
| DOB | 14 March 1990 | 14 March 1990 | match, see note below |
| Address | 12 Sample Street, Testville NSW 2000 | same | match |
| Modem | Netcomm CF40, free | Netcomm CF40, free | match |
| Account number | ACC44721 | ACC44721 | match |

Deepgram transcribes the spoken DOB as `03/14/1990`, US month-first order. The date normaliser must read
day-first by default and accept month-first only when the first number is above 12, which makes this one
unambiguous. Tests cover both orders.

low-confidence route to REVIEW.

---

## The script

**AGENT:** Good afternoon, am I speaking with Jordan Avery?

**CUSTOMER:** Yes, speaking.

**AGENT:** Hi Jordan, this is Sam from Econnex Comparison. Before we go any further, please be advised
that this call is being recorded for quality assurance and training purposes. Is that okay with you?
<!-- TYPE A CRITICAL: recording_disclaimer. Must appear before any data collection. Placed first
     deliberately: the real handout call put it after address confirmation, which would fail this check. -->

**CUSTOMER:** Yeah, that's fine.

**AGENT:** Thank you. We noticed you were looking for a better internet plan, so I am calling to help you
with that. Can I just confirm I am speaking with the account holder?
<!-- TYPE A CRITICAL: account_holder_confirmation -->

**CUSTOMER:** Yes, that's me. The account's in my name.

**AGENT:** Lovely. And can you confirm the service address for me?

**CUSTOMER:** It's 12 Wattle Street, Northbridge, 6003.
<!-- TYPE B: service_address vs CRM -->

**AGENT:** Thank you. I can see that address is NBN ready, fibre to the premises. Who is your internet
provider at the moment?

**CUSTOMER:** I'm with iPrimus. Paying sixty five a month.
<!-- TYPE B: current_provider and current_price, discovery capture -->

**AGENT:** And do you know what speed you are on?

**CUSTOMER:** Twenty five, I think.

**AGENT:** And how many people are using the internet at home?

**CUSTOMER:** Just me.

**AGENT:** Do you need a landline at all?

**CUSTOMER:** No, don't need one.

**AGENT:** Right. So let me tell you what I can do. I can give you twenty five megabits for forty two
dollars and ninety cents a month for your first six months.
<!-- TYPE B: promo_price 42.90, promo_term 6 months. Both match CRM. -->

**CUSTOMER:** And then what does it go up to after that?

**AGENT:** After the six months it goes to seventy nine dollars and ninety cents, which is the standard
rate.
<!-- TYPE B DELIBERATE MISMATCH: agent says 79.90, plan rate card says 72.90.
     Expect: FAIL, high confidence, both values in the reason string. This is the headline demo catch. -->

**CUSTOMER:** Hmm. That's not a huge saving really. I might just stay where I am, to be honest.

**AGENT:** I understand. Let me add something to it. I can include a brand new modem at no extra cost, and
it is yours to keep. Even if you switch providers later, you keep the modem.

**CUSTOMER:** Oh right. And it's a new one, not refurbished?

**AGENT:** Brand new, one hundred percent free, no setup fee. It is the Netcomm CF40 Wi-Fi 6 modem, and it
arrives in three to five business days.
<!-- TYPE B: modem_model. STT commonly mangles this, good fuzzy-match target. -->

**CUSTOMER:** Okay, that does sound better. Go on then.

**AGENT:** Let me read you the full plan details. This plan is month to month, there is no lock-in
contract. It provides twenty five megabits typical download speed and eight point five megabits typical
upload speed during the busy evening period, seven PM to eleven PM. The promotional price is forty two
dollars and ninety cents per month for six months, then seventy nine dollars and ninety cents ongoing. The
total minimum cost is forty two dollars and ninety cents. There is no setup fee and no additional charges.
<!-- TYPE A CRITICAL: plan_readout. The mandatory disclosure block, the internet equivalent of the DMO
     read. Note it repeats the wrong ongoing price, so the same fault surfaces twice. -->
<!-- TYPE B: download_speed, upload_speed, peak_window, total_minimum_cost -->

**CUSTOMER:** Okay. Yep, I follow.

**AGENT:** Now I need to take a few details. Can you verify your first and last name as they appear on
your ID?

**CUSTOMER:** Jordan Avery.
<!-- TYPE B: full_name vs CRM -->

**AGENT:** Thank you. And your email address?

**CUSTOMER:** It's j dot avery at example dot com.
<!-- TYPE B DELIBERATE MISMATCH, SUBTLE: CRM holds jordan.avery@example.com, customer says j.avery@...
     Expect REVIEW or FAIL, not a silent pass. Tests the span-isolation fix from D14 bug 1:
     the extractor must isolate the email span BEFORE normalising, never find-and-replace the whole line. -->

**AGENT:** And your mobile number?

**CUSTOMER:** Oh four hundred, triple zero, one one eight.
<!-- TYPE B: mobile vs CRM. Spoken-number normalisation target. -->

**AGENT:** And your date of birth?

**CUSTOMER:** Fourteenth of March, nineteen eighty two.
<!-- TYPE B: dob vs CRM. Spoken-date normalisation target. -->

**AGENT:** Thank you. Now, do you have your current iPrimus bill handy? I need the account number from it.

**CUSTOMER:** Hang on, let me find it. I think it's in the kitchen drawer.

[PAUSE HERE. STAY SILENT FOR 25 SECONDS. Do not fill the gap, do not clear your throat. Count it out.
 This is the Type C dead-air fixture and it needs to clearly exceed the 20 second threshold.]
<!-- TYPE C: dead_air. Expect NOTE, never blocks. Threshold is DEAD_AIR_THRESHOLD_S = 20.0 in config. -->

**CUSTOMER:** Sorry about that. Right, I've got it. The account number is 4 4 1 2 8 0 6.

**AGENT:** Thank you for holding. Now, to set up the account we need your preferred payment method, which
will be direct debited monthly. Are you using a credit card or a debit card?

**CUSTOMER:** Credit card. It's 4 1 1 1 1 1 1 1 1 1 1 1 1 1 1 1.
<!-- PCI TEST, DELIBERATE. See "The spoken card number is deliberate test behaviour" in the directions
     above. This is the standard Visa test number 4111111111111111: publicly published, not a real card,
     passes Luhn. The compliant handling is the agent's refusal on the next line, which mirrors the real
     call where the agent muted the recording at this point. We speak it only so the guardrail is proven
     on real audio. Expect redact=pci to mask at source, the local Luhn pass to catch any leak, and the
     PCI violation flag to raise because digits were spoken at all. Verify zero digits reach the DB or UI. -->

**AGENT:** I have to stop you there, I cannot take card details over the phone. I am sending you a secure
link by email now, and you can enter them yourself on the form.

**CUSTOMER:** Ah, okay. Got the email.

**AGENT:** Open it and click view plan, then apply now. You should see the modem at zero dollars upfront.

**CUSTOMER:** Yep, selected. Submitting now. It's given me a reference number, 8 8 2 0 4.
<!-- TYPE B: reference_number -->

**AGENT:** Thank you. That confirms the order. Your modem will arrive in three to five business days and
you can activate it yourself. Congratulations, and thank you for choosing Econnex Comparison. This is Sam,
it was a pleasure to help you today.
<!-- TYPE A: close_and_identification. Agent names themselves and the company at the close. -->

**CUSTOMER:** Great, thanks for your help.

**AGENT:** You are very welcome. Have a wonderful day.

---

## Expected scoring outcome

If the pipeline is correct, this call produces:

| Check | Type | Critical | Expected |
|---|---|---|---|
| recording_disclaimer | A | yes | PASS, and before any data collection |
| account_holder_confirmation | A | yes | PASS |
| plan_readout | A | yes | PASS on script match |
| close_and_identification | A | no | PASS |
| ongoing_price | B | yes | **FAIL**, 79.90 quoted vs 72.90 on the rate card |
| promo_price | B | yes | PASS |
| email | B | yes | **REVIEW or FAIL**, j.avery vs jordan.avery |
| mobile, dob, full_name, address | B | mixed | PASS |
| modem_model | B | no | PASS |
| dead_air | C | no | NOTE, one gap of about 25 seconds |
| talk_ratio | C | no | NOTE, agent-heavy |
| pci_violation | guardrail | yes | flag raised, zero digits stored |

Gate decision: **HELD_TL**, because a critical Type B check failed. That is the demo: the sale does not
ship, the failing check is named, and clicking it plays the audio at that second.
