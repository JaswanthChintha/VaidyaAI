# Module 31 — Population Distribution Provenance

Every number Module 31 can report about a population comes from the nineteen JSON
files in `distributions/`. This document says where each of them came from,
what exactly was computed, what was checked, and what the resulting statement
does **not** cover.

The project rule applies here as it does to the ML datasets in
`../PROVENANCE.md`: **no synthetic, estimated, smoothed or "reasonably
approximated" data.** A percentile shown to a patient is a factual claim about
a real, surveyed population. Where no such population is available, Module 31
returns `available: false` with a reason code — see *Not covered, and why*
below.

---

## What these tables are

**Source:** the U.S. **National Health and Nutrition Examination Survey
(NHANES)** public-use microdata, published by the National Center for Health
Statistics (NCHS), Centers for Disease Control and Prevention.

**Derivation:** every shipped table declares
`"derivation": "computed_by_vaidyaai_from_published_microdata"`. These are
**not** transcriptions of a CDC-published percentile table, and they must never
be described as such. NCHS does not publish percentile tables for all nineteen
analytes, on one consistent set of age bands, at the grid this module needs.
What NCHS *does* publish is the microdata, and a survey-weighted quantile of it
is a measurement, not an invention: deterministic, and reproducible by anyone
from the same public files.

**Build script:** `build_population_tables.py` (in this directory). Its module
docstring is the complete statement of method; there is no step that is not
written down there.

```
cd ai-service
.venv/Scripts/python.exe datasets/population/build_population_tables.py --check
```

**Reproducibility, verified 2026-09-04 for the first seven tables.** The
script was re-run against the committed `raw/*.xpt` files, writing to a
scratch directory, and all seven outputs were **byte-identical** to the
shipped `distributions/*.json`. The build is deterministic and those seven
shipped tables really are its output.

**Re-verified 2026-09-19 for all nineteen.** After the twelve
complete-blood-count tables were added, the script was re-run against the
committed `raw/*.xpt` files into a scratch directory and **all nineteen
outputs were byte-identical** to the shipped `distributions/*.json`
(`diff -r`, no differences). The determinism claim covers the CBC tables too.

---

## Analytic sample (identical for every table)

| Filter | Variable | Why |
|---|---|---|
| Interviewed **and** MEC-examined | `RIDSTATR == 2` | The exam weight is only valid for examined participants. |
| Non-zero exam weight | `WTMEC2YR > 0` | A zero weight represents nobody. |
| Adults only | `RIDAGEYR >= 20` | Paediatric distributions are age-in-months sensitive and are not derivable at this band width. A child scored against an adult table is a clinical error, so children are **not covered at all**. |
| Not pregnant | `RIDEXPRG != 1` | Pregnancy materially shifts haemoglobin, creatinine and lipids. Recorded as a limitation: a pregnant patient is compared against a **non-pregnant** cohort. |
| Analyte present | *(item non-response dropped)* | No re-weighting for item non-response is applied, and none is claimed. |

**Strata:** sex from `RIAGENDR` (1 = Male, 2 = Female, per the NHANES
codebook) × ten-year age bands 20–29 … 70–79 plus **80 and over**. NHANES
top-codes age at 80, so the top band cannot be split and is open above.

**Minimum cell size:** a (sex, age band) cell with fewer than **100** unweighted
observations is **dropped, not published** — a percentile estimated from a
handful of people is worse than no percentile. **No cell was dropped in any of
the nineteen tables**; every table publishes all 14 cells.

**Estimator:** the inverse of the survey-weighted empirical CDF (the lower /
"type 1" quantile). Sort the cell's values ascending, let `W` be the cumulative
sum of `WTMEC2YR` and `T` the cell's total weight; the *p*-th percentile is the
smallest observed value `x_i` with `W_i / T >= p/100`. **No interpolation
between observations and no distributional assumption** — so every published
number is a value some real NHANES participant actually had.

**Percentile grid (all tables):** `1, 2.5, 5, 10, 25, 50, 75, 90, 95, 97.5, 99`.
The service brackets a patient's value **between two adjacent grid points** and
never interpolates a single percentile out of them.

**Variance is NOT estimated.** A correct NHANES standard error needs
`SDMVPSU`/`SDMVSTRA` with Taylor-series linearisation, which this build does
not do. This is one of the reasons the service reports a percentile **band**
rather than a point estimate: it cannot report an interval, so it does not
report a number that would imply it has one.

---

## Source files

All `raw/*.xpt` files are permanently published by CDC at the URLs below.
sha256 digests recorded **2026-09-04** and re-verified against the on-disk files
when this document was written; the build script verifies every digest before
it reads a file, so a silently changed upstream file fails the build instead of
quietly changing a percentile.

| File | Bytes | sha256 | URL |
|---|---:|---|---|
| `DEMO_J.xpt` | 3,412,720 | `c0b46e0345ea19404928656277c8b0d10b0cca348a9b2fe4fc3c67e8b7ee73ec` | `https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/DEMO_J.xpt` |
| `BMX_J.xpt` | 1,466,000 | `8d675e42d8826ac98714b2c3dd4c5138a5e353fb4424f7eff5e6db4a01ce838a` | `.../2017/DataFiles/BMX_J.xpt` |
| `GHB_J.xpt` | 103,520 | `35f07094573a0061a03ed609a5a363b34eb1b1c7065d1623b43d72e132a8a654` | `.../2017/DataFiles/GHB_J.xpt` |
| `CBC_J.xpt` | 1,476,320 | `00f964098dc91272e415344554cbf1b627ecaeb2eda201518527446a7d81e742` | `.../2017/DataFiles/CBC_J.xpt` |
| `BIOPRO_J.xpt` | 2,106,080 | `5bcd5722c1892883b96a9d7fed0befadabacae313f800fadc0133cd5dd00c4c6` | `.../2017/DataFiles/BIOPRO_J.xpt` |
| `TCHOL_J.xpt` | 179,680 | `0291a6a4f6d82dac8392c8c992b519946824dfeda01647935520cf506ed9f4ab` | `.../2017/DataFiles/TCHOL_J.xpt` |
| `VID_J.xpt` | 604,400 | `5a688e2107758b9344a222823fbdce4838928bbec70e1fd2f34e3ef5c45a95ac` | `.../2017/DataFiles/VID_J.xpt` |
| `DEMO_H.xpt` | 3,833,200 | `f8f0cbb3085a323d4cde22349b164878fea1e64dbc404e65b5815c7816b547d7` | `.../2013/DataFiles/DEMO_H.xpt` |
| `VITB12_H.xpt` | 138,880 | `6d280479d279379a1f67278722e3b6a1f1a3566c06dfc3a1f02c9713975633ae` | `.../2013/DataFiles/VITB12_H.xpt` |

**Retrieved on:** 2026-09-04, direct from `wwwn.cdc.gov`. No mirror, no
intermediary.

### Downloaded but deliberately UNUSED

| File | Bytes | sha256 | Why it is not used |
|---|---:|---|---|
| `TRIGLY_J.xpt` | 245,040 | `3995696f9686ad84aeb008c655639387adb45df5b6bee953acde6f474fe06ffc` | Fetched before the fasting-status decision was taken. `triglycerides` is in `EXCLUDED_FEATURES` — see *Not covered* below — so no table is built from it. |
| `FASTQX_J.xpt` | 1,275,120 | `f28e3f41ab423e712c7a70c1952a1a257096b153765840f4f10929c0721e44c1` | NHANES' fasting questionnaire. It would let the *survey* side be restricted to fasting participants, but VaidyaAI has no fasting status for the *patient* side, so it cannot close the gap. Kept for the record; referenced by nothing. |

Neither file is named anywhere in `build_population_tables.py`; they are inert.

### Reference documents (for the cross-checks below)

| File | Bytes | sha256 | What it is |
|---|---:|---|---|
| `reference/sr03-046-508.pdf` | 1,318,592 | `936396720de7ce66b69e392a3b964d552f3170fc241f91fc9e93efb74c447b2d` | NCHS, *Vital and Health Statistics* **Series 3, Number 46** (January 2021), "Anthropometric Reference Data for Children and Adults: United States, 2015–2018". Tables 14 (adult females) and 15 (adult males) carry published BMI percentiles by sex and age; PDF pages 24 and 25. |
| `reference/db363-h.pdf` | 546,889 | `5a3dcb0a5184d73dcc785a757ce00d281c665fab7994576f7dcd9c9ebbf8fe8e` | NCHS **Data Brief No. 363** (April 2020), Carroll MD & Fryar CD, "Total and High-density Lipoprotein Cholesterol in Adults: United States, 2015–2018". The crude high-total-cholesterol prevalences used below are the Figure 1 notes on page 1. |

Both are committed so the transcribed comparison figures in the build script
can be re-checked without a network.

---

## Per-table detail

The shipped JSON carries all of this too, in `source`, `population`, `method`,
`counts` and `notes` — this table is the human-readable index.

| Feature | Table id | NHANES file | Variable (label) | Cycle | Eligible sample | Weight | Analytic n | Cohorts |
|---|---|---|---|---|---|---|---:|---:|
| `hba1c` | `nhanes_2017_2018_hba1c` | `GHB_J.xpt` | `LBXGH` — Glycohemoglobin (%) | 2017–2018 (J) | examined, aged 12+ | `WTMEC2YR` | 4,971 | 14 |
| `hemoglobin` | `nhanes_2017_2018_hemoglobin` | `CBC_J.xpt` | `LBXHGB` — Hemoglobin (g/dL) | 2017–2018 (J) | examined, aged 1+ | `WTMEC2YR` | 4,981 | 14 |
| `creatinine` | `nhanes_2017_2018_creatinine` | `BIOPRO_J.xpt` | `LBXSCR` — Creatinine, refrigerated serum (mg/dL) | 2017–2018 (J) | examined, aged 12+ | `WTMEC2YR` | 4,869 | 14 |
| `cholesterol` | `nhanes_2017_2018_total_cholesterol` | `TCHOL_J.xpt` | `LBXTC` — Total Cholesterol (mg/dL) | 2017–2018 (J) | examined, aged 6+ | `WTMEC2YR` | 4,890 | 14 |
| `bmi` | `nhanes_2017_2018_bmi` | `BMX_J.xpt` | `BMXBMI` — Body Mass Index (kg/m**2) | 2017–2018 (J) | examined (body measures) | `WTMEC2YR` | 5,120 | 14 |
| `vitamin_d` | `nhanes_2017_2018_vitamin_d` | `VID_J.xpt` | `LBXVIDMS` — 25OHD2+25OHD3 (nmol/L) | 2017–2018 (J) | examined, aged 1+ | `WTMEC2YR` | 4,936 | 14 |
| `vitamin_b12` | `nhanes_2013_2014_vitamin_b12` | `VITB12_H.xpt` | `LBDB12` — Vitamin B12 (pg/mL) | **2013–2014 (H)** | examined, aged 19+ | `WTMEC2YR` | 5,255 | 14 |

**Citation (all tables).** Centers for Disease Control and Prevention (CDC).
National Center for Health Statistics (NCHS). *National Health and Nutrition
Examination Survey Data*. Hyattsville, MD: U.S. Department of Health and Human
Services, CDC. Per-file and per-variable citations are recorded in each table's
`source.citation`.

### The measurand, per feature

* **`hba1c`** — glycohaemoglobin as a percentage, Tosoh HLC-723 HPLC,
  NGSP-certified. This is the **NGSP %** scale, matching the canonical unit;
  it is *not* IFCC mmol/mol.
* **`hemoglobin`** — whole-blood haemoglobin, Sysmex XN-series analyser.
* **`creatinine`** — **serum** creatinine, Roche Cobas 6000, enzymatic,
  IDMS-traceable. Urine creatinine is a different analyte and is refused
  upstream by `feature_catalog.NON_BLOOD_SPECIMEN_TOKENS`.
* **`cholesterol`** — serum **TOTAL** cholesterol, enzymatic assay. Matches
  the canonical feature, which is explicitly total cholesterol; HDL/LDL/VLDL
  are separate analytes (`feature_catalog.DISTINCT_ANALYTE_TOKENS`).
* **`bmi`** — computed by NCHS from **measured** standing height and measured
  weight, not self-report.
* **`vitamin_d`** — total serum 25-hydroxyvitamin D (25OHD2 + 25OHD3) by
  HPLC-MS/MS, standardised to the Vitamin D Standardization Program.
* **`vitamin_b12`** — serum vitamin B12 (cobalamin), Roche Elecsys
  electrochemiluminescence immunoassay.

### Cohort sizes (unweighted n per published cell)

| Cohort | hba1c | hemoglobin | creatinine | cholesterol | bmi | vitamin_d | vitamin_b12 |
|---|---|---|---|---|---|---|---|
| `male_20_29` | 355 | 356 | 346 | 346 | 371 | 352 | 435 |
| `male_30_39` | 342 | 342 | 338 | 339 | 358 | 341 | 437 |
| `male_40_49` | 340 | 341 | 332 | 334 | 366 | 338 | 439 |
| `male_50_59` | 399 | 399 | 391 | 393 | 404 | 398 | 420 |
| `male_60_69` | 515 | 516 | 505 | 508 | 527 | 511 | 416 |
| `male_70_79` | 286 | 287 | 279 | 282 | 296 | 285 | 239 |
| `male_80_plus` | 178 | 178 | 174 | 175 | 171 | 176 | 149 |
| `female_20_29` | 355 | 357 | 351 | 353 | 372 | 354 | 403 |
| `female_30_39` | 400 | 402 | 396 | 397 | 422 | 400 | 464 |
| `female_40_49` | 387 | 387 | 380 | 382 | 397 | 385 | 517 |
| `female_50_59` | 457 | 457 | 445 | 446 | 467 | 451 | 452 |
| `female_60_69` | 501 | 503 | 488 | 489 | 516 | 495 | 450 |
| `female_70_79` | 270 | 270 | 262 | 264 | 271 | 265 | 267 |
| `female_80_plus` | 186 | 186 | 182 | 182 | 182 | 185 | 167 |
| **total** | **4971** | **4981** | **4869** | **4890** | **5120** | **4936** | **5255** |

Every cell clears the 100-observation floor comfortably; the smallest is 149.
Pregnant participants excluded: **55** in the 2017–2018 tables, **65** in the
2013–2014 B12 table.

---

## Unit match against `app/data/feature_catalog.py`

Checked feature by feature. This is the check that stops a value being placed
in a distribution of the same analyte on a different scale.

| Feature | Canonical unit (`feature_catalog.py`) | Table unit | Match |
|---|---|---|---|
| `hba1c` | `%` | `%` | IDENTICAL |
| `hemoglobin` | `g/dl` | `g/dl` | IDENTICAL |
| `creatinine` | `mg/dl` | `mg/dl` | IDENTICAL |
| `cholesterol` | `mg/dl` | `mg/dl` | IDENTICAL |
| `bmi` | `kg/m2` | `kg/m2` | IDENTICAL |
| `vitamin_d` | `ng/ml` | **`nmol/l`** | **CONVERTED at lookup** |
| `vitamin_b12` | `pg/ml` | `pg/ml` | IDENTICAL |

**The one conversion.** NHANES publishes 25-hydroxyvitamin D in **nmol/L**;
VaidyaAI's canonical unit is **ng/mL**. The table is **never rescaled** — the
published numbers stay exactly as NCHS measured them. Instead the *patient's*
value is converted into nmol/L at lookup time, using the audited row in
`app/data/unit_conversions.py`:

```
vitamin_d: nmol/l -> ng/ml, factor 0.400641
   basis: MW 25-OH-D 400.64 g/mol; 1 ng/mL = 2.496 nmol/L
```

applied in the inverse direction. `app/population/tables.py` refuses at import
to load a table whose declared unit has no audited conversion for its feature,
so this cannot silently break.

**HbA1c is the other one worth stating explicitly:** the table is NGSP `%`, and
a patient value printed in IFCC `mmol/mol` reaches it through the affine NGSP/
IFCC master equation (`NGSP% = 0.09148 × IFCC + 2.152`), not a ratio. Verified
end to end: 48 mmol/mol in gives 6.543 % compared against the table.

---

## Cross-checks against numbers NCHS actually published

The estimator was validated against published NCHS statistics, not only
against itself. Both references pool **2015–2018** (two cycles) while the
shipped tables use **2017–2018** (one cycle), so this is a **method check, not
an identity check** — close agreement shows the sample definition, the exam
weights and the quantile estimator are right; exact equality is not expected
and would in fact be suspicious.

**Check 1 — BMI percentiles vs NCHS Series 3 No. 46, Tables 14/15.**
13 published cohorts × 9 percentiles (5th, 10th, 15th, 25th, 50th, 75th, 85th,
90th, 95th). Worst absolute difference across all 117 comparisons:
**1.60 kg/m²**. Median agreement per cohort:

| Cohort | Computed median | Published median | Max abs. diff (all 9 percentiles) |
|---|---:|---:|---:|
| male 20–29 | 26.6 | 26.5 | 0.50 |
| male 30–39 | 29.1 | 28.9 | 1.20 |
| male 40–49 | 29.3 | 29.1 | 1.60 |
| male 50–59 | 29.6 | 29.1 | 1.10 |
| male 60–69 | 29.1 | 28.9 | 0.40 |
| male 70–79 | 28.4 | 28.2 | 0.80 |
| female 20–29 | 26.9 | 26.2 | 1.40 |
| female 30–39 | 28.1 | 28.3 | 0.90 |
| female 40–49 | 28.7 | 28.6 | 1.30 |
| female 50–59 | 28.5 | 29.1 | 1.10 |
| female 60–69 | 28.9 | 29.2 | 0.90 |
| female 70–79 | 29.0 | 28.8 | 1.10 |
| female 80+ | 28.0 | 27.5 | 1.10 |

**Check 2 — prevalence of high total cholesterol (≥ 240 mg/dL) vs NCHS Data
Brief No. 363**, which reports crude estimates for US adults 20+, 2015–2018:

| Group | Computed (2017–2018) | Published crude (2015–2018) | Difference |
|---|---:|---:|---:|
| Total | 10.4 % | 11.5 % | 1.1 pp |
| Male | 9.5 % | 10.3 % | 0.8 pp |
| Female | 11.3 % | 12.6 % | 1.3 pp |

Both checks are reproducible with `--check`. The residual differences are of
the size a one-cycle vs two-cycle comparison would produce; neither check is
claimed to prove more than that.

---

## The complete blood count — twelve tables added 2026-09-19

All twelve come from **`CBC_J.xpt`, NHANES 2017–2018 (cycle J)** — the same
file, cycle, demographic file (`DEMO_J.xpt`), weight variable (`WTMEC2YR`) and
analytic sample that `hemoglobin` already used. **No new download, no new
cohort definition, no new cycle.** The file's sha256 is unchanged and is
recorded in the source-files table above.

| feature | NHANES column | unit | n (analytic) |
|---|---|---|---|
| `hematocrit` | `LBXHCT` | % | 4,981 |
| `rbc_count` | `LBXRBCSI` | 10^6/uL | 4,981 |
| `mcv` | `LBXMCVSI` | fL | 4,981 |
| `mch` | `LBXMCHSI` | pg | 4,981 |
| `mchc` | `LBXMC` | g/dL | 4,981 |
| `wbc_count` | `LBXWBCSI` | 10^3/uL | 4,981 |
| `neutrophils` | `LBXNEPCT` | % | 4,977 |
| `lymphocytes` | `LBXLYPCT` | % | 4,977 |
| `monocytes` | `LBXMOPCT` | % | 4,977 |
| `eosinophils` | `LBXEOPCT` | % | 4,977 |
| `basophils` | `LBXBAPCT` | % | 4,977 |
| `platelet_count` | `LBXPLTSI` | 10^3/uL | 4,981 |

14 cohorts each, none dropped.

**THE DIFFERENTIAL IS THE PERCENTAGE, NOT THE ABSOLUTE COUNT.** NHANES
publishes both (`LBXNEPCT` and `LBDNENO`). The reports this service reads print
percentages — `NEUTROPHILS 82 %` — so the percentage is the quantity that can
be matched to a patient's value. An absolute count is a **different quantity**,
not the same one in another unit, and `app/data/unit_conversions.py` therefore
lists `%` as the only accepted unit for these five and refuses the rest.

**Eyeball check against clinical expectation** (male / female, 40–49, median):
haematocrit 44.3 / 40.1 %, RBC 5.00 / 4.47, MCV 89.3 / 89.6 fL, MCH 30.2 /
30.2 pg, MCHC 34.0 / 33.5 g/dL, WBC 6.6 / 7.4, neutrophils 58.6 / 58.9 %,
lymphocytes 30.5 / 30.2 %, monocytes 8.0 / 7.1 %, eosinophils 2.3 / 2.1 %,
basophils 0.7 / 0.7 %, platelets 229 / 263. Every one lands where a haematology
reference would put it, including the sex differences in haematocrit, RBC and
platelets.

> **⚠ TIED CUT-POINTS ARE REAL IN THESE TABLES AND WERE NOT IN THE FIRST
> SEVEN.** Basophils run at roughly 0–2 % and are reported to one decimal
> place, so adjacent published percentiles can be the **same number** — the
> male 20–29 cohort publishes 0.3 at both the 1st and the 2.5th. The service
> brackets with `bisect_right` and so reports the HIGHER of the tied
> percentiles, which is correct. A test that assumed strictly-increasing grids
> was corrected rather than the behaviour.

> **⚠ ZERO IS A PUBLISHED VALUE.** The female 70–79 eosinophil cohort publishes
> 0.0 at the 1st percentile. That is a real result — a share of surveyed adults
> had no eosinophils detected — not a floor artefact or a missing value.

---

## Not covered, and why

`app/population/policy.py`'s `EXCLUDED_FEATURES` is the authoritative list and
carries the patient-facing wording. `app/population/tables.py` asserts at
import that **every** canonical feature in `feature_catalog.py` is either
backed by a table here or listed there — so a feature cannot go missing by
accident.

| Canonical feature | Reason code | Summary |
|---|---|---|
| `blood_glucose` | `NO_VERIFIED_DISTRIBUTION` | A glucose result means something different fasting vs non-fasting, and **neither this service nor the uploaded report reliably records fasting status**. NHANES has the data (`FASTQX_J.xpt` above) for the survey side; the patient side is what is missing. Comparing a random glucose against a fasting population, or the reverse, would produce a precise-looking wrong percentile. |
| `triglycerides` | `NO_VERIFIED_DISTRIBUTION` | The lipid most strongly affected by recent eating. Same missing fasting status, larger consequence. `TRIGLY_J.xpt` was downloaded before this decision and is unused. |
| `hypertension` | `FEATURE_NOT_CONTINUOUS` | Recorded as yes / no / not answered. No distribution to place a value in. |
| `heart_disease` | `FEATURE_NOT_CONTINUOUS` | As above. |
| `smoking_history` | `FEATURE_NOT_CONTINUOUS` | A category, not a measured number. |
| `gender` | `FEATURE_NOT_CONTINUOUS` | Matched **on**, not scored. |
| `age` | `FEATURE_NOT_CONTINUOUS` | Matched **on**, not scored. |

---

## Limitations — every one of these is carried into the response

The first five are shipped verbatim in every response as
`policy.GENERAL_LIMITATIONS`; the rest are recorded per table in the JSON's
`notes` and returned as `comparison.table_notes`.

1. **The reference population is the United States.** Civilian
   non-institutionalised US residents surveyed by NHANES. It is **not** matched
   to any other country, ethnicity, or health status. VaidyaAI's users are not
   assumed to be American, and this is the single largest caveat on the whole
   module.
2. **These are not "healthy" reference ranges.** The surveyed groups include
   people who have the relevant condition and people on medicines that change
   the result. The upper HbA1c percentiles are populated by treated and
   untreated diabetes; the cholesterol distribution includes people on
   lipid-lowering therapy. This describes a population **as it is**.
3. **Pregnant participants were excluded from every cell**, so a pregnant
   patient is compared against people who were not pregnant.
4. **Adults 20+ only.** No comparison is offered for children or adolescents,
   ever, under any code path.
5. **A band, not a number**, because the underlying estimates carry sampling
   uncertainty this build does not quantify (no `SDMVPSU`/`SDMVSTRA`
   linearisation, therefore no standard errors).
6. **`vitamin_b12` is a different survey cycle** — 2013–2014, not 2017–2018.
   Serum B12 was not measured in 2017–2018 and 2013–2014 is the most recent
   cycle that measured it. The cohort really is US adults *in 2013–2014*, and
   the table records that. Serum B12 also does not distinguish B12 bound to
   haptocorrin from metabolically available B12 and is raised by
   supplementation, which is common; a high percentile frequently reflects
   supplement use.
7. **`vitamin_d` is pooled across the whole year.** 25OHD has a strong seasonal
   cycle and NHANES releases only a six-month examination-period indicator
   (`RIDEXMON`), so a summer draw and a winter draw are compared against the
   same cohort. Values below the limit of detection are stored by NCHS as
   LLOD/√2.
8. **`hemoglobin` is not altitude-adjusted.** NHANES examines at sea-level and
   high-altitude locations alike.
9. **`creatinine` tracks muscle mass as well as kidney function.** A high
   percentile is not by itself a kidney finding.
10. **`cholesterol` is measured regardless of fasting status** — which is why
    it *is* covered while triglycerides is not: total cholesterol is only
    minimally fasting-dependent, and the surveyed cohort is fasting-mixed in
    the same way an arbitrary patient sample is.
11. **Item non-response is not re-weighted for.** Participants missing an
    analyte are dropped from that analyte's table; the exam weights are used
    unadjusted.
12. **Sex, not gender.** NHANES records `RIAGENDR` as male/female. Module 31
    never coerces a person's stated gender into one of those two categories:
    `other`, `prefer_not_to_say` and an absent gender all return
    `SEX_COHORT_NOT_AVAILABLE`.

---

## What a reviewer can check without re-running anything

* `GET /api/v1/population/policy` returns the policy, the exclusions, and the
  full table inventory — survey, cycle, file, **sha256**, NHANES variable,
  cohort sample sizes, grid, estimator — for every covered parameter.
* Every successful comparison carries `comparison.table` (the same provenance),
  `comparison.percentile_grid` and `comparison.cohort_percentile_values`, so
  the reported band can be re-derived by hand from the response itself.
