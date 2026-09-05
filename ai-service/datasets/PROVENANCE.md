# Dataset Provenance

All datasets here are **real, published datasets**. No synthetic or generated data
is used anywhere in VaidyaAI's ML layer, by explicit instruction.

Each entry below is scored against what the **project specification actually
requires** for that module, not against what happened to be easy to download.

---

## Module 10 — Diabetes · `raw/diabetes_prediction_dataset.csv` · ✅ PERFECT MATCH

| | |
|---|---|
| Origin | Kaggle, "Diabetes prediction dataset" (`iammustafatz/diabetes-prediction-dataset`) |
| Retrieved from | Two independent HuggingFace mirrors (no Kaggle credentials present) |
| Mirror A | `m2s6a8/diabetes_prediction_dataset` |
| Mirror B | `marianeft/diabetes_prediction_dataset` |
| Integrity | **Byte-identical across both mirrors**, re-verified: sha256 `f233fc470e904201f35310d061cb46ca0a6bc7ca5c3e428b769fb4f87f69929b` |
| Size | 3,810,356 bytes · 100,000 rows · 0 nulls |

**Spec Module 10 requires:** HbA1c, blood glucose, BMI, age, other patient information.

| Spec feature | Column | Present |
|---|---|---|
| HbA1c | `HbA1c_level` | ✅ |
| Blood glucose | `blood_glucose_level` | ✅ |
| BMI | `bmi` | ✅ |
| Age | `age` | ✅ |
| Other patient info | `gender`, `hypertension`, `heart_disease`, `smoking_history` | ✅ |

**Every spec-named feature is present.** Additionally, `smoking_history`'s categories
are *identical* to what Module 2 already stores — strong evidence this is the dataset
the project description was written against.

### Verified characteristics that shape modelling

* **Class imbalance: 91,500 negative / 8,500 positive (8.5%).** Predicting "no
  diabetes" for everyone scores **91.5% accuracy**. Accuracy is therefore close to
  meaningless — spec §11's precision, recall, F1 and confusion matrix are the
  numbers that mean anything, and PR-AUC is more informative than ROC-AUC here.
* **`bmi = 27.32` appears 25,495 times (25.5%)** — the author median-filled missing
  BMI. These are imputed, not measured.
* **Age top-coded at 80.0** (5,621 rows); infants present (0.08 years).
* **3,854 duplicate rows.** De-duplicating before vs after the split changes whether
  the test set is contaminated.
* `gender`: Female 58,552 / Male 41,430 / **Other 18**. Module 2 also allows
  `prefer_not_to_say`, which has **no dataset equivalent** — hence
  `Profile.ML_GENDER_VALUES`.
* **`hypertension` / `heart_disease` are 0/1 only — no unknown state — but Module 2's
  profile is TRI-STATE.** A patient who never answered must **not** be encoded as `0`;
  that fabricates a negative clinical finding. How the predictor handles a genuinely
  absent value is a real modelling decision and must be documented, never defaulted.

---

## Module 11 — Heart Disease · `raw/cardio_train.csv` · ✅ PERFECT MATCH

| | |
|---|---|
| Origin | Kaggle, "Cardiovascular Disease dataset" (`sulianova/cardiovascular-disease-dataset`) |
| Retrieved from | **Three independent GitHub repositories**, no Kaggle credentials needed |
| Source A | `juniorcl/cardiovascular-disease-prediction` → `database/cardio.csv` |
| Source B | `saklaniabhimanyu/Cardiovascular-Disease-Prediction` → `data/cardio_train.csv` |
| Source C | `LeadingIndiaAI/Cardiovascular-Disease-Prediction` → `cardio_train.csv` |
| Integrity | **All three BYTE-IDENTICAL**, sha256 `21a705d23381b0dfd6a6416da701b490…` |
| Size | 2,941,524 bytes · 70,000 rows · **semicolon-delimited** |

Columns: `id;age;gender;height;weight;ap_hi;ap_lo;cholesterol;gluc;smoke;alco;active;cardio`

**Spec Module 11 requires:** Age, Gender, BMI, Cholesterol, Smoking history.

| Spec feature | Column | Present |
|---|---|---|
| Age | `age` (in DAYS — divide by 365.25) | ✅ |
| Gender | `gender` (1 / 2) | ✅ |
| **BMI** | derive from `height` (cm) + `weight` (kg) | ✅ |
| Cholesterol | `cholesterol` (1 normal / 2 above / 3 well above) | ✅ |
| **Smoking history** | `smoke` (0 / 1) | ✅ |
| Other relevant | `ap_hi`, `ap_lo` (blood pressure), `gluc`, `alco`, `active` | ✅ |

**All five spec-named features present.** Blood pressure additionally supports the
rule engine's hypertension-related reasoning.

### Verified characteristics

* **Near-perfectly balanced: 35,021 negative / 34,979 positive.** Unlike the diabetes
  set, accuracy IS meaningful here — but still report the full §11 metric set.
* **Age is in DAYS** (10,798–23,713 ⇒ 29.6–64.9 years). Failing to convert would make
  every age feature nonsense.
* `gender` is `1`/`2`, NOT `male`/`female`. UCI/Kaggle documentation does not state
  which is which; infer from height/weight distributions and **document the mapping**.
* `cholesterol` and `gluc` are **ordinal categories (1/2/3), not mg/dL values.** They
  cannot be fed the same way as Module 5's numeric `cholesterol` feature — a mapping
  layer is required, and conflating the two would be a serious defect.
* **This dataset is famously dirty:** height 55–250 cm, weight 10–200 kg, giving
  derived BMI 3.5–298.7. These are data-entry errors, not real patients. Cleaning is
  required and must be documented. (Module 6's validation engine would reject these:
  its BMI possible band is 8–200.)
* `smoke`: 63,831 non-smokers / 6,169 smokers.

> **Previously here and REMOVED:** `processed.cleveland.data` (UCI Heart Disease,
> Cleveland, 303 rows) and `heart_failure_prediction.csv` (Kaggle fedesoriano, 918
> rows). **Both lack BMI and smoking history entirely** — 3 of 5 spec features at
> best. They were fetched before the spec's feature list was checked. Removed so
> nobody trains Module 11 on a dataset that cannot satisfy it.

---

## Module 12 — Kidney Disease · `raw/chronic_kidney_disease_full.csv` · ✅ PERFECT MATCH

| | |
|---|---|
| Origin | **UCI Chronic Kidney Disease (id 336) — the OFFICIAL archive, full 25-attribute version** |
| Retrieved from | `archive.ics.uci.edu/static/public/336/` (zip → `Chronic_Kidney_Disease.rar`) |
| Extraction | UCI ships ONLY a `.rar`. No `unrar`/`7z` present, but **Windows' bundled `bsdtar` (`C:/Windows/System32/tar.exe`) reads RAR via libarchive** — that is how it was extracted. |
| Converted | `chronic_kidney_disease_full.arff` → CSV; ARFF `?` preserved as **empty cells** (real missingness, never imputed at this stage) |
| sha256 (CSV) | `4cdfe028aae5a4541d46a7f2e35ba3f4…` |
| Size | 400 rows · **25 attributes** |
| Companion | `ckd_uci_info.txt` — UCI's own attribute documentation, shipped verbatim |

**Spec Module 12 requires:** Creatinine, Hemoglobin, Blood glucose, Age, Hypertension.

| Spec feature | Column | Present | Missing |
|---|---|---|---|
| Creatinine | `sc` (serum creatinine) | ✅ | 17/400 |
| Hemoglobin | `hemo` | ✅ | 52/400 |
| Blood glucose | `bgr` (blood glucose random) | ✅ | 44/400 |
| Age | `age` | ✅ | 9/400 |
| Hypertension | `htn` (yes/no) | ✅ | 2/400 |
| Other kidney params | `bp, sg, al, su, rbc, pc, pcc, ba, bu, sod, pot, pcv, wbcc, rbcc, dm, cad, appet, pe, ane` | ✅ | — |

**All five spec-named features present, plus 19 further kidney parameters.**

**This dataset is exactly what spec Module 12 describes.** It has **1,013 missing
cells** across 400 rows and a mix of numeric and categorical attributes — precisely
the pipeline the spec calls for: missing-value imputation → categorical encoding →
numerical processing → Random Forest. The missingness is genuine, not manufactured,
and it is also what makes the spec's **information-sufficiency skip** meaningful.

### Data-quality note (do NOT silently "fix")

Class values are `ckd` 250 / `notckd` 149 / **`no` 1** — one malformed label, a
known quirk of this file (stray whitespace/truncation in the original ARFF). Decide
explicitly whether to drop or repair that row and **document the choice**; do not
quietly coerce it. Several numeric columns also carry trailing-whitespace artifacts
in the source ARFF.

> **Previously here and REMOVED:** `ckd_reduced_400.csv`, a 14-column redistribution
> found on HuggingFace. It **dropped both `age` and `bgr`** — two spec-required
> features — while looking superficially complete. Removed.

---

## Rule for anyone adding a dataset here

1. **Check the spec's feature list FIRST.** A well-known dataset that omits a
   spec-required feature is the wrong dataset — this is exactly how the Cleveland
   file got fetched and then removed.
2. Use a real published dataset. **Never substitute generated data.** If a dataset
   cannot be obtained, stop and say so rather than fabricating one.
3. Verify integrity against **two independent sources** where possible, and record
   origin, checksum, row count and licence.
4. Record a per-feature match table like the ones above, so a partial match can never
   be mistaken for a complete one.
