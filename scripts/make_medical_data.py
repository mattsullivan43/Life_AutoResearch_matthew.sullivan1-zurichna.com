"""Synthetic, labelled medical-report dataset for the summarisation modality.

V2 — the reports DO NOT state the structured fields verbatim. The model must
actually reason: compute BMI from height+weight, map prose to smoker status,
exclude family members' conditions and discontinued medications, and make a
clinical risk judgement. This gives the auto-research loop real headroom instead
of trivial copying. SYNTHETIC + anonymised ([PLACEHOLDER_n]); never real PII.

Run:  .venv/bin/python scripts/make_medical_data.py
"""
import os, json
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "medical")
REPORTS = os.path.join(OUT, "reports")
os.makedirs(REPORTS, exist_ok=True)

SCHEMA = {
    "age": "integer or null",
    "smoker": "one of: yes | no | ex | unknown",
    "conditions": "list of the PATIENT's current diagnosed conditions (exclude family / resolved)",
    "medications": "list of CURRENT medications (exclude discontinued)",
    "family_history": "one of: yes | no | unknown",
    "bmi": "number (compute from height & weight; 1 decimal place)",
    "risk_level": "one of: low | moderate | high (your clinical judgement)",
}

# (file, report_text, partial_gt_without_bmi, height_m, weight_kg)
DATA = [
 ("report_1",
  "GP report. Mr [NAME_1], born 1984, reviewed in clinic in 2026. Stands 1.78m and weighs 95kg. "
  "Does not smoke. Type 2 diabetes, managed on metformin 500mg twice daily. He was started on "
  "atorvastatin last year but this was discontinued due to side effects. His father had a myocardial "
  "infarction aged 58.",
  {"age": 42, "smoker": "no", "conditions": ["type 2 diabetes"], "medications": ["metformin"],
   "family_history": "yes", "risk_level": "moderate"}, 1.78, 95),

 ("report_2",
  "Consultant letter. A 35-year-old woman who has never smoked. Mild asthma, uses a salbutamol "
  "inhaler as required. She is 1.65m tall, 60kg. No family history of note. Otherwise fit and well.",
  {"age": 35, "smoker": "no", "conditions": ["asthma"], "medications": ["salbutamol"],
   "family_history": "no", "risk_level": "low"}, 1.65, 60),

 ("report_3",
  "Medical report on a 58-year-old gentleman who smokes around 20 a day and has done for 30 years. "
  "Hypertension treated with ramipril 10mg and amlodipine 5mg; raised cholesterol on atorvastatin 40mg. "
  "He had a transient ischaemic attack two years ago. Height 1.75m, weight 102kg. Both his mother and "
  "brother have had strokes.",
  {"age": 58, "smoker": "yes", "conditions": ["hypertension", "high cholesterol", "transient ischaemic attack"],
   "medications": ["ramipril", "amlodipine", "atorvastatin"], "family_history": "yes", "risk_level": "high"}, 1.75, 102),

 ("report_4",
  "29-year-old who stopped smoking three years ago, having previously smoked five a day. No ongoing "
  "medical conditions and takes no regular medication. 1.80m, 78kg. No relevant family history.",
  {"age": 29, "smoker": "ex", "conditions": [], "medications": [],
   "family_history": "no", "risk_level": "low"}, 1.80, 78),

 ("report_5",
  "Psychiatry letter regarding a 46-year-old, lifelong non-smoker. Recurrent depression, currently "
  "stable on sertraline 100mg daily. Also has an underactive thyroid, managed with levothyroxine 75mcg. "
  "Measures 1.70m and 78kg.",
  {"age": 46, "smoker": "no", "conditions": ["recurrent depression", "hypothyroidism"],
   "medications": ["sertraline", "levothyroxine"], "family_history": "unknown", "risk_level": "moderate"}, 1.70, 78),

 ("report_6",
  "Examination of a 63-year-old who still smokes about ten a day. COPD treated with tiotropium and "
  "salbutamol, and type 2 diabetes requiring insulin. He had a heart attack four years ago and a stent "
  "fitted. 1.70m, 88kg. Strong family history of cardiovascular disease.",
  {"age": 63, "smoker": "yes", "conditions": ["COPD", "type 2 diabetes", "myocardial infarction"],
   "medications": ["tiotropium", "salbutamol", "insulin"], "family_history": "yes", "risk_level": "high"}, 1.70, 88),

 ("report_7",
  "GP report. A 51-year-old non-smoker with osteoarthritis of the knee, taking ibuprofen as needed. "
  "No cardiovascular or metabolic disease. He is 1.72m and 77kg. His father is diabetic.",
  {"age": 51, "smoker": "no", "conditions": ["osteoarthritis"], "medications": ["ibuprofen"],
   "family_history": "yes", "risk_level": "low"}, 1.72, 77),

 ("report_8",
  "Cardiology letter. 39-year-old, never smoked. Atrial fibrillation, anticoagulated with apixaban. "
  "Otherwise well, no diabetes or hypertension. 1.80m, 75kg. No family history of premature cardiac death.",
  {"age": 39, "smoker": "no", "conditions": ["atrial fibrillation"], "medications": ["apixaban"],
   "family_history": "no", "risk_level": "moderate"}, 1.80, 75),

 ("report_9",
  "Medical report. A 47-year-old who smokes 15 a day. Hypertension on losartan 50mg, no diabetes. "
  "Height 1.74m, weight 94kg. His mother had breast cancer at 70.",
  {"age": 47, "smoker": "yes", "conditions": ["hypertension"], "medications": ["losartan"],
   "family_history": "yes", "risk_level": "moderate"}, 1.74, 94),

 ("report_10",
  "A fit 25-year-old who has never smoked, with no medical conditions and on no medication. "
  "1.78m, 66kg. No family history of note.",
  {"age": 25, "smoker": "no", "conditions": [], "medications": [],
   "family_history": "no", "risk_level": "low"}, 1.78, 66),
]

gt = {}
for name, text, partial, h, w in DATA:
    summary = dict(partial)
    summary["bmi"] = round(w / (h * h), 1)   # ground-truth BMI computed exactly
    with open(os.path.join(REPORTS, name + ".txt"), "w", encoding="utf-8") as f:
        f.write(text)
    gt[name] = summary

with open(os.path.join(OUT, "ground_truth_summaries.json"), "w", encoding="utf-8") as f:
    json.dump({"schema": SCHEMA, "labels": gt}, f, indent=2)

print(f"wrote {len(DATA)} inference-requiring medical reports -> {REPORTS}")
