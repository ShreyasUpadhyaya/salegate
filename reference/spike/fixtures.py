from models import CheckDefinition, Lead, Transcript, Utterance

# Mirrors the PDF's "Lead 3613790" worked example: rate mismatch (28.6c vs 31.9c)
# and email mismatch (gmail.com vs gmial.com), plus a 47s dead air at 18:30.

lead_3613790 = Lead(
    lead_id="3613790",
    retailer="Retailer 1",
    plan_peak_rate_c_per_kwh=31.9,
    crm_email="j.smith@gmial.com",  # CRM has the typo per the PDF
    call_started_at="2026-09-01",
)

transcript_3613790 = Transcript(utterances=[
    Utterance(0, "agent", 12, 20, "This call is being recorded for quality and training purposes, is that okay with you", 0.97),
    Utterance(1, "customer", 20, 22, "Yes that's fine", 0.95),
    Utterance(2, "agent", 161, 168, "Can you confirm you are the account holder on this energy account", 0.96),
    Utterance(3, "customer", 168, 170, "Yes I am", 0.95),
    Utterance(4, "agent", 595, 640, "the Default Market Offer disclosure text goes here in full as required by the regulator", 0.94),
    Utterance(5, "agent", 842, 846, "so just to confirm peak is 28.6 cents", 0.96),
    Utterance(6, "customer", 846, 848, "okay sounds good", 0.9),
    Utterance(7, "agent", 1330, 1335, "and your email is j dot smith at gmail dot com", 0.93),
    Utterance(8, "customer", 1335, 1336, "that's right", 0.9),
    Utterance(9, "agent", 1373, 1375, "great, one more thing", 0.9),
])

check_library_retailer1_v3 = [
    CheckDefinition("recording_disclaimer", 3, "A", critical=True, fatal=False,
                     label="Recording disclaimer",
                     script_text="This call is being recorded for quality and training purposes"),
    CheckDefinition("account_holder_confirmed", 3, "A", critical=True, fatal=False,
                     label="Account holder confirmed",
                     script_text="Can you confirm you are the account holder on this energy account"),
    CheckDefinition("dmo_verbatim", 3, "A", critical=True, fatal=False,
                     label="DMO read verbatim",
                     script_text="the Default Market Offer disclosure text goes here in full as required by the regulator"),
    CheckDefinition("rates_and_charges", 3, "B", critical=True, fatal=True,
                     label="Rates and charges", field_name="peak_rate_c_per_kwh"),
    CheckDefinition("email_captured", 3, "B", critical=True, fatal=False,
                     label="Email captured", field_name="email"),
    CheckDefinition("dead_air", 3, "C", critical=False, fatal=False, label="Dead air"),
]
