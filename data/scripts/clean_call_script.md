# Clean call script (lead L-DEMO-2, Priya Shah)

Synthetic customer. Target 3 to 4 minutes. Every Type A line matches v1 library approved text
closely. No deliberate faults, no card number. Dead air under 10 seconds.

Fixture values: promo 42.90 (6 months), ongoing 72.90, NBN 25, Netcomm CF40, email
priya.shah@example.com, DOB 22 July 1988, address 7 Example Road, Testville NSW 2000.

---

**AGENT:** Hi, is this Priya? My name's Sam, I'm calling from Econnex Comparison about the internet plan comparison you started online yesterday.

**CUSTOMER:** Yes, that's me.

**AGENT:** Please be advised that this call will be recorded for quality assurance and training purposes. Is that okay with you?

**CUSTOMER:** Yeah, that's fine.

**AGENT:** Great. And this will be under your name, am I correct?

**CUSTOMER:** Yes, that's correct.

**AGENT:** Can you confirm your date of birth for me?

**CUSTOMER:** Twenty second of July, nineteen eighty eight.

**AGENT:** And the service address is 7 Example Road, Testville, New South Wales 2000. Is that right?

**CUSTOMER:** Yep, that's it.

**AGENT:** Lovely. So based on what you entered, the plan that suits you is our NBN 25 plan. It's good for streaming and working from home for one to two people.

**CUSTOMER:** Okay, what does it cost?

**AGENT:** For the first six months it's forty two dollars and ninety a month.

**CUSTOMER:** And after that?

**AGENT:** Seventy two dollars and ninety, that's the regular price.

**CUSTOMER:** Okay, that sounds reasonable.

**AGENT:** This value plan comes with a month to month contract only and provides twenty five Mbps typical download speed and eight point five Mbps typical upload speed from seven PM to eleven PM. The original plan cost is seventy two dollars and ninety per month, but we have an offer ongoing where you will get this plan at forty two dollars and ninety per month for the first six months and then seventy two dollars and ninety. The modem that you will receive is the Netcomm CF40 Wi-Fi six modem, it is one hundred percent free, no extra cost.

**CUSTOMER:** Okay, sounds good.

**AGENT:** And the total minimum cost will be forty two dollars and ninety only, no setup fee, no any additional cost.

**CUSTOMER:** Great, let's do it.

**AGENT:** Can you please verify your first and last name as per ID?

**CUSTOMER:** Priya Shah.

**AGENT:** And your email address?

**CUSTOMER:** It's priya dot shah at example dot com.

**AGENT:** Thanks. And do you understand and agree to switch your internet service to this plan on these terms?

**CUSTOMER:** Yes, I agree.

**AGENT:** Thank you, and I'll need the latest bill from your current provider to check the connection. Could you grab that for me?

**CUSTOMER:** Sure, one moment.

[PAUSE: stay quiet for about 6 to 8 seconds, well under 10.]

**CUSTOMER:** Okay, got it. The account number is ACC90112.

**AGENT:** Thanks. This is Sam from Econnex Comparison, it was a pleasure to help you today.

**CUSTOMER:** Thanks, bye.

**AGENT:** Have a great day.

---

## Expected scoring outcome

All Type A checks should PASS: disclaimer before any personal data, account holder confirmed,
plan key information read near verbatim, total minimum cost disclosed, explicit consent
obtained. No Type B mismatches: all values match the L-DEMO-2 rate card and CRM fixture below.
Dead air NOTE only, well under the 20s threshold.

| Field                   | Value                              |
| ----------------------- | ---------------------------------- |
| Full name               | Priya Shah                         |
| Email                   | priya.shah@example.com             |
| DOB                     | 1988-07-22                         |
| Service address         | 7 Example Road, Testville NSW 2000 |
| Previous account number | ACC90112                           |
| Promo price             | 42.90 / 6 months                   |
| Ongoing price           | 72.90                              |
| Modem                   | Netcomm CF40                       |
