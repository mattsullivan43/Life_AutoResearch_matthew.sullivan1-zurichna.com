# Ground-Truth Label Review — 8 Broker Submissions

**Why you're getting this:** these labels are the answer key the auto-research demo
scores itself against. The ones marked ⚠ are inferences from reading the emails, not
verified facts — a wrong label here becomes a wrong "correct answer" in the demo.
Please confirm or correct the ⚠ rows. Labels come from `data/submissions/ground_truth_submissions.csv`;
edit that file (or reply with corrections).

Legend: ✅ = from the verified seed mapping · ⚠ = inferred from the documents, needs a look

---

## 1. PolyFab Corporation (Reading Plastic & Metal Advanced Machining)
| Field | Label | Basis |
|---|---|---|
| Type | New Business ✅ | seed; cover: "new business to our agency", currently with Sentry |
| Industry | Manufacturing ✅ | seed; precision plastic/metal machining, PA |
| Structure | Single site ✅ | seed |
| Lines | Property, GL, Auto, WC, Umbrella ⚠ | "All Lines" ACORDs + ~$95k package/$55k WC in cover |
| Routing | Standard–Middle Market ⚠ | nothing suggesting referral/CAT/specialty |
| Risk flags | equipment breakdown ⚠ | machine shop; critical machinery — judgment call, could be none |

## 2. The Expo Group
| Field | Label | Basis |
|---|---|---|
| Type | Endorsement ✅ | seed; "previously logged submission… add umbrella as a line" |
| Industry | Events/Hospitality ✅ | seed; trade-show/exhibition company |
| Structure | Single entity multi-site ⚠ | national trade-show operator — weakest inference in the set |
| Lines | Umbrella/Excess ⚠ | the endorsement itself is only "+$10M umbrella"; original PC lines exist but this ask is umbrella-only |
| Routing | Standard–Middle Market ⚠ | US Middle Market – Dallas desk in the chain |
| Risk flags | (none) ⚠ | nothing flagged in the email |

## 3. Gemini Power Systems
| Field | Label | Basis |
|---|---|---|
| Type | New Business ✅ | seed; "our new business submission" |
| Industry | Distribution/Wholesale ✅ | seed |
| Structure | Single entity multi-site ✅ | seed ("5-site") |
| Lines | Property, GL, Auto, WC, Umbrella ⚠ | cover: "quote the Property/GL/Auto/Umb/WC lines" |
| Routing | CAT-Exposed ✅ | seed; AmRISC SOV (CAT wholesale market) supports it |
| Risk flags | (none) ⚠ | CAT captured in routing; nothing else flagged |

## 4. Alliance Group Holdings, LLC
| Field | Label | Basis |
|---|---|---|
| Type | **Renewal** ✅* | seed says Renewal — but the subject line says "New Business - Alliance Group Holdings". If Renewal is the intended decoy (renewal info gathered for a resubmission), confirm; otherwise this should be New Business. **Please confirm.** |
| Industry | Events/Hospitality ✅* | seed — but the docs read more like multi-location services/logistics (vehicles parked at ~40 locations). **Please confirm.** |
| Structure | Multi-entity/subsidiaries ⚠ | "Group Holdings", many locations |
| Lines | Property, GL, Auto, WC ⚠ | Pkg + WC ACORDs; heavy vehicle schedule |
| Routing | Referral–High Hazard ⚠ | seed's "heavy auto" mapped here — could equally be Standard–MM |
| Risk flags | heavy fleet exposure ⚠ | large vehicle/driver schedule dominates the submission |

## 5. Beverly Wilcox Properties / Sol Hoff
| Field | Label | Basis |
|---|---|---|
| Type | New Business ✅ | seed |
| Industry | Real Estate (LRO) ✅ | seed; rent rolls, tenant lists |
| Structure | Multi-entity/subsidiaries ⚠ | two named entities (Sol Hoff Co / Beverly Wilcox), CA + AZ properties |
| Lines | General Liability ⚠ | cover asks only for "competitive GL terms" |
| Routing | Clean/Fast-track ✅ | seed ("clean DECOY"); incumbent quote $14,483 |
| Risk flags | (none) ✅ | seed — deliberately clean |

## 6. Moda Operandi, Inc.
| Field | Label | Basis |
|---|---|---|
| Type | **Renewal** ✅* | seed says Renewal — but the subject says "New Business Submission" (new to Zurich, renewal term 8/15/26–27 elsewhere). Deliberate decoy? **Please confirm.** |
| Industry | Retail/E-commerce ✅ | seed; luxury fashion e-commerce |
| Structure | Multi-national (US + foreign) ✅ | seed (US-UK-HK); "foreign package quote with an admitted UK EL underlyer" |
| Lines | Property, GL, Auto, WC, Umbrella, Foreign Package, Stock Throughput, Jewelers Block, HNOA ⚠ | seed named JB+STP+Foreign; the rest from Hartford loss runs (AUTO/UMB/PKGINT/WC) + HNOA supplemental app |
| Routing | Standard–Middle Market ⚠ | no referral/specialty signal — judgment call |
| Risk flags | high-value inventory & transit ✅ | seed; jewelry/luxury stock |

## 7. Tryon Medical Partners, LLC
| Field | Label | Basis |
|---|---|---|
| Type | New Business ✅ | seed |
| Industry | Healthcare/Medical ✅ | seed; multi-specialty physician group |
| Structure | Multi-entity/subsidiaries ⚠ | Named-insured schedule: Tryon Medical Partners + Tryon Management Group (MSO); 2 separate WC policies |
| Lines | Property, GL, Auto, WC, Umbrella ⚠ | loss runs by line: PROP/CGL/BAUT/WORK/CUMB |
| Routing | Specialty–PE/M&A ✅ | seed; WTW "(M&A)" practice on the submission |
| Risk flags | needlestick/medical ✅ | seed |

## 8. Elsner Engineering Works, Inc
| Field | Label | Basis |
|---|---|---|
| Type | Renewal ✅ | seed; subject: "8/1/2026 Renewal" |
| Industry | Manufacturing ✅ | seed; SIC 3559, custom machinery |
| Structure | Single site ⚠ | single PA plant per SOV |
| Lines | Property, GL, Auto, Umbrella, Inland Marine ⚠ | cover: "LOBs: Auto, GL, Inland Marine, Property and Umbrella" |
| Routing | Referral–Adverse Loss ⚠ | seed's "product-loss" mapped here |
| Risk flags | large product-liability loss, adverse loss ratio ⚠ | seed: "product-loss+firearms" — note **firearms** has no flag in the seed taxonomy; add one? |

---

## Attachment doc-type index (63 files)

High-confidence from file contents/names: 27 Loss run · 12 ACORD form · 6 SOV ·
5 Driver/vehicle schedule · 6 Supplemental questionnaire · 2 Narrative/risk write-up · 5 Other.

Only these were judgment calls (full list in `data/submissions/ground_truth_doctypes.csv`):
- Tryon "Property & Casualty Submission.pdf" (WTW packet) → **Narrative/risk write-up** (prose submission story)
- Alliance "Insurance Policy1/2.docx" (umbrella coverage specifications) → **Other**
- Moda "P&C Request for Renewal Information" workbook, Elsner "Exposure Spreadsheet", Tryon "Exposure Workbook" → **SOV** (each contains a Statement of Values schedule)
- Loss *summaries* (PolyFab "Loss Summary.xlsx", Alliance "Combined LSS.xlsx") → **Loss run** (broker-compiled rather than carrier-valued)
- Moda "NOV By Category" (revenue breakdown), "NY Mod" (experience mod), "Coverage Specifications", Beverly Wilcox "Rent Rolls" → **Other**
