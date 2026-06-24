"""Synthetic labelled samples for the call-transcript and complaint channels — V2.

Realistic, HARDER data of the kind a real back office would upload: multi-turn
transcripts with verification noise and small talk; formal complaint letters with
reference numbers. The vulnerability / escalation / regulatory signals are mostly
IMPLICIT, and several items are DECOYS (frustration that is not a complaint, a
casual mention of the Ombudsman, positive feedback) so the model must judge, not
keyword-match. SYNTHETIC + anonymised ([PLACEHOLDER_n]).

Run:  .venv/bin/python scripts/make_channel_data.py
"""
import os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SCHEMA = {
    "vulnerability": "yes | no — is a vulnerable-customer indicator present (even if implicit)?",
    "vulnerability_type": "bereavement | financial_hardship | health | mental_health | age_capacity | none",
    "escalation": "yes | no — complaint / dissatisfaction / manager / threat to leave / FOS",
    "regulatory_trigger": "yes | no — DISP complaint, possible mis-selling, Consumer Duty vulnerable customer",
    "regulatory_type": "complaint_DISP | mis_selling | consumer_duty_vulnerable | none",
}

CALLS = [
 ("call_1",
  "AGENT: Thanks for calling, can I take the first line of your address and your date of birth to verify? "
  "CALLER: Yes, it's [LOCATION_1], and [DATE_1]. Sorry, I'm a bit all over the place — since I lost my husband "
  "back in the spring I've not really been keeping on top of the post. AGENT: I'm so sorry to hear that. "
  "CALLER: There's a letter here about his policy and honestly I don't know what I'm supposed to do with it.",
  {"vulnerability": "yes", "vulnerability_type": "bereavement", "escalation": "no",
   "regulatory_trigger": "yes", "regulatory_type": "consumer_duty_vulnerable"}),

 ("call_2",
  "CALLER: I've phoned four times now. Every time someone promises a callback and I hear nothing back. "
  "AGENT: I do apologise, let me look. CALLER: I'm not being funny but this is the last time I'm asking nicely "
  "before I take it further. AGENT: Take it further how, sorry? CALLER: The Ombudsman. I've had enough.",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "complaint_DISP"}),

 ("call_3",
  "CALLER: Ugh, honestly, this website. I've been trying to download my policy documents for half an hour and it "
  "keeps timing out. AGENT: I can email those across to you now if that's easier? CALLER: Oh brilliant, yes please. "
  "AGENT: Done. CALLER: Perfect, you've been far more use than that website — thanks ever so much!",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "no",
   "regulatory_trigger": "no", "regulatory_type": "none"}),

 ("call_4",
  "CALLER: I wanted to ask about maybe pausing my payments for a bit. Things have got really tight since I was "
  "made redundant and I'm trying to cut everything back to the bone. AGENT: Let me see what options we have. "
  "CALLER: I really don't want to cancel the cover, I just can't manage the full amount at the minute.",
  {"vulnerability": "yes", "vulnerability_type": "financial_hardship", "escalation": "no",
   "regulatory_trigger": "yes", "regulatory_type": "consumer_duty_vulnerable"}),

 ("call_5",
  "CALLER: I've been signed off work for a while now — stress, and my head's just not been in a good place. "
  "The forms you posted out, I keep starting them and I can't seem to get to the end of them. AGENT: That's "
  "completely understandable. CALLER: Is there someone who could just go through it with me slowly?",
  {"vulnerability": "yes", "vulnerability_type": "mental_health", "escalation": "no",
   "regulatory_trigger": "yes", "regulatory_type": "consumer_duty_vulnerable"}),

 ("call_6",
  "CALLER: I'm reading the paperwork and it says critical illness isn't covered. But when I sat down with the "
  "adviser in the branch, I'm absolutely certain he told me it was — that was the whole reason I took it out. "
  "AGENT: Let me check the policy. CALLER: So either he got it wrong or I was misled, and either way I'm not happy "
  "about it.",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "mis_selling"}),

 ("call_7",
  "CALLER: Hello dear, I'm ringing on behalf of my mum — she's 86 and gets in a bit of a muddle with these "
  "things, she's sitting right next to me. AGENT: I can speak with her directly with her permission. CALLER: "
  "She's got a letter she can't make head nor tail of and we just want to understand what it means.",
  {"vulnerability": "yes", "vulnerability_type": "age_capacity", "escalation": "no",
   "regulatory_trigger": "yes", "regulatory_type": "consumer_duty_vulnerable"}),

 ("call_8",
  "CALLER: Hiya, I'm just after a quick quote to add my partner onto the policy. AGENT: No problem — can I take "
  "their date of birth? CALLER: [DATE_1]. AGENT: Lovely, I'll run those figures and send them over. CALLER: "
  "Great stuff, no rush at all, cheers.",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "no",
   "regulatory_trigger": "no", "regulatory_type": "none"}),

 ("call_9",
  "CALLER: I'll be honest with you, I've had a terminal diagnosis and I'm trying to get my affairs in order while "
  "I still can. I put a claim in about six weeks ago and I've heard absolutely nothing. AGENT: I'm very sorry. "
  "CALLER: I haven't got time to be chased around — I want this looked at today and I want to know why nobody has "
  "called me back.",
  {"vulnerability": "yes", "vulnerability_type": "health", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "complaint_DISP"}),

 ("call_10",
  "CALLER: Bit of a manic week, work's been stressful, but anyway — I just need to change the address on my "
  "policy. AGENT: Sure, what's the new one? CALLER: [LOCATION_1]. AGENT: All updated. CALLER: Smashing, that's "
  "all I needed.",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "no",
   "regulatory_trigger": "no", "regulatory_type": "none"}),
]

COMPLAINTS = [
 ("complaint_1",
  "Ref: [NUMERICAL_PII_1]. I am writing to formally complain about the handling of the claim I submitted on "
  "[DATE_1]. Despite three separate follow-up calls I have received no substantive update in over four months. "
  "I consider this wholly unacceptable and, if it is not resolved within eight weeks, I intend to refer the "
  "matter to the Financial Ombudsman Service. Yours faithfully, [NAME_1].",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "complaint_DISP"}),

 ("complaint_2",
  "When I took out this policy in [DATE_1], the adviser assured me that pre-existing conditions would be covered "
  "after a two-year qualifying period. My claim has now been declined on the grounds of a pre-existing condition. "
  "I believe the product was mis-sold to me and I am requesting a full review of the original sales call recording.",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "mis_selling"}),

 ("complaint_3",
  "I am writing regarding my late wife's policy, reference [NUMERICAL_PII_1]. I have now provided her death "
  "certificate on two occasions and have today been asked for it a third time. Having to deal with this while "
  "grieving has been genuinely distressing and I expected a good deal more compassion. Please treat this as a "
  "formal complaint.",
  {"vulnerability": "yes", "vulnerability_type": "bereavement", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "complaint_DISP"}),

 ("complaint_4",
  "Hello, could you kindly confirm whether my premium is collected annually or monthly? I'd also be grateful if "
  "you could update the email address on my file to the one I'm writing from. Many thanks for your help, [NAME_1].",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "no",
   "regulatory_trigger": "no", "regulatory_type": "none"}),

 ("complaint_5",
  "I rely on this income protection policy because of my long-term disability. The most recent letter you sent was "
  "so confusing that I genuinely could not tell whether my cover had changed, and when I rang, the adviser was "
  "unable to explain it either. I have been left anxious and none the wiser, and frankly this is not good enough.",
  {"vulnerability": "yes", "vulnerability_type": "health", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "complaint_DISP"}),

 ("complaint_6",
  "I just wanted to pass on some feedback — the claims handler I dealt with, [NAME_1], was absolutely excellent "
  "and made a difficult time much easier. The only very minor thing was that the online portal was a little "
  "clunky to navigate, but the service itself was first class. Thank you.",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "no",
   "regulatory_trigger": "no", "regulatory_type": "none"}),

 ("complaint_7",
  "Since my heart surgery I have been under considerable financial strain, and I wrote to ask whether my premiums "
  "could be reduced. I was told flatly that nothing could be done, and the tone of the response was dismissive. "
  "For someone in my circumstances that is simply not acceptable, and I would like the matter formally reviewed.",
  {"vulnerability": "yes", "vulnerability_type": "financial_hardship", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "complaint_DISP"}),

 ("complaint_8",
  "I am disappointed that nobody made it clear to me that my policy would lapse if I missed a single payment. I "
  "have now lost my cover over one late payment and I think that is unfair and poorly communicated. I would like "
  "this reviewed.",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "complaint_DISP"}),

 ("complaint_9",
  "A friend of mine mentioned the Financial Ombudsman when I said my claim was taking a little while to come "
  "through. I want to be clear I'm not complaining at all — I was just curious roughly how long claims usually "
  "take to process? There's no rush on my end. Thanks, [NAME_1].",
  {"vulnerability": "no", "vulnerability_type": "none", "escalation": "no",
   "regulatory_trigger": "no", "regulatory_type": "none"}),

 ("complaint_10",
  "I have struggled with my mental health for a number of years and find dealing with paperwork like this quite "
  "overwhelming. I also don't recall being told, when I took the policy out, that mental-health-related claims "
  "were excluded — which feels wrong given my circumstances. I would like someone to look into how it was sold.",
  {"vulnerability": "yes", "vulnerability_type": "mental_health", "escalation": "yes",
   "regulatory_trigger": "yes", "regulatory_type": "mis_selling"}),
]

def write(channel, subdir, items):
    base = os.path.join(ROOT, "data", channel)
    docs = os.path.join(base, subdir)
    os.makedirs(docs, exist_ok=True)
    gt = {}
    for name, text, labels in items:
        with open(os.path.join(docs, name + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)
        gt[name] = labels
    with open(os.path.join(base, "ground_truth.json"), "w", encoding="utf-8") as f:
        json.dump({"schema": SCHEMA, "task": "extract", "labels": gt}, f, indent=2)
    print(f"{channel}: wrote {len(items)} docs -> {docs}")

write("calls", "transcripts", CALLS)
write("complaints", "records", COMPLAINTS)
