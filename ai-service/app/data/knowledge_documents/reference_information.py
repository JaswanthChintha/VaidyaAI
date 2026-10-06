"""Module 22 content -- REFERENCE INFORMATION.

The published bands themselves, one document per feature that has them.

WHY THESE ARE SEPARATE FROM `lab_tests.py`
------------------------------------------
A threshold changes when a guideline is revised. A description of what a test
measures does not. Splitting them means a guideline update touches exactly one
short document per analyte, and a reviewer comparing the corpus against
`app/data/clinical_rules.py` has one place to look.

THESE NUMBERS MUST MATCH THE RULE TABLE. If they drift, the platform will tell a
reader one band and act on another -- a contradiction the reader cannot see and
has no way to resolve. `tests/test_knowledge_base.py` asserts the correspondence
for every threshold quoted here.

A band is a population statistic. It says where a value sits relative to a
published cut-off. It does not say what is happening in a person, and every
document here says so rather than leaving it implied.
"""

from __future__ import annotations

from typing import Tuple

from app.data import conditions as C
from app.data.knowledge_types import TOPIC_REFERENCE, KnowledgeDocument

BANDS_CAVEAT = (
    "Bands describe populations, not people. A value just outside a band and a "
    "value just inside it are far more alike than the labels suggest, and where "
    "a value sits is only one input to a clinical judgement. This material is "
    "educational and is not a diagnosis."
)

REFERENCE_DOCUMENTS: Tuple[KnowledgeDocument, ...] = (
    KnowledgeDocument(
        doc_id="ref_hba1c_bands",
        title="HbA1c reference bands",
        topic=TOPIC_REFERENCE,
        features=("hba1c",),
        conditions=(C.DIABETES,),
        keywords=("hba1c range", "a1c normal range", "6.5", "5.7", "prediabetes range"),
        summary=(
            "The HbA1c bands this platform applies, in NGSP percent: below "
            "5.7 %, 5.7 to 6.4 %, and 6.5 % or above."
        ),
        body="""
An HbA1c below 5.7 % sits below the band that guidelines describe as increased
risk. It is reported as nothing flagged against this cut-off.

An HbA1c from 5.7 % up to and including 6.4 % sits in the band guidelines
describe as increased risk of developing diabetes, sometimes called prediabetes.
It is reported as borderline: a prompt for discussion and usually for a repeat
measurement, not a conclusion.

An HbA1c of 6.5 % or above sits at or above the diabetes-range cut-off.
Guidelines require a repeat abnormal result, or a second different abnormal
test, before that band is acted on, because a single measurement can be
affected by sample or red-cell factors.

The cut-offs apply at the value itself. A result of exactly 6.5 % is in the
highest band; a result of exactly 5.7 % is in the middle band. This platform
implements the comparison exactly as written rather than rounding first.

These bands assume the HbA1c is reported in the NGSP percentage scale. The IFCC
scale reports the same measurement in millimoles per mole, where the numbers are
much larger, and the two must be converted before comparison rather than read
against each other.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "American Diabetes Association, Standards of Care in Diabetes, "
            "section 2. Byte-aligned with the bands of RULE_DIABETES_HBA1C in "
            "app/data/clinical_rules.py (>= 6.5 indicated, >= 5.7 borderline)."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_glucose_bands",
        title="Blood glucose reference bands",
        topic=TOPIC_REFERENCE,
        features=("blood_glucose",),
        conditions=(C.DIABETES, C.HYPOGLYCEMIA),
        keywords=(
            "glucose range", "fasting glucose normal", "126", "100", "200",
            "140", "70", "54", "low sugar range",
        ),
        summary=(
            "Glucose bands are timing-specific: fasting cut-offs of 100 and "
            "126 mg/dL, post-load and random cut-offs of 140 and 200 mg/dL, "
            "and low-glucose alert values of 70 and 54 mg/dL."
        ),
        body="""
For a sample established as fasting, a value below 100 mg/dL sits below the
impaired-fasting-glucose cut-off. From 100 up to 125 mg/dL is the
impaired-fasting-glucose band, reported as borderline. At or above 126 mg/dL is
the diabetes-range fasting band.

When the report does not establish that the sample was fasting, the fasting
cut-offs are not applied, because ordinary post-meal values would be flagged as
abnormal. The post-load and random bands are used instead: below 140 mg/dL,
140 to 199 mg/dL as borderline, and 200 mg/dL or above as the diabetes-range
band.

Low values have their own bands, applied whatever the sample timing. Below
70 mg/dL is the guideline alert value. Below 54 mg/dL is the level guidelines
describe as clinically significant low glucose. Both are reasons to speak to a
healthcare professional.

Applying the wrong timing band is the single most common misreading of a
glucose result. A value of 150 mg/dL two hours after a meal and the same value
after an overnight fast are different observations, and this platform will not
guess which one it has been given.

These bands are expressed in milligrams per decilitre. Reports using millimoles
per litre give numbers roughly eighteen times smaller, and a value of 7 mmol/L
compared against a band of 126 would look reassuringly low while representing
the same concentration.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "American Diabetes Association, Standards of Care in Diabetes, "
            "section 2; ADA/EASD hypoglycaemia classification levels 1 and 2. "
            "Byte-aligned with RULE_DIABETES_GLUCOSE_FASTING, "
            "RULE_DIABETES_GLUCOSE_UNSPECIFIED and RULE_HYPOGLYCEMIA_GLUCOSE "
            "in app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_hemoglobin_bands",
        title="Haemoglobin reference cut-offs",
        topic=TOPIC_REFERENCE,
        features=("hemoglobin",),
        conditions=(C.ANEMIA, C.ELEVATED_HEMOGLOBIN),
        keywords=(
            "haemoglobin normal range", "hemoglobin range", "13.0", "12.0",
            "anaemia cut off", "who cut off", "16.5",
        ),
        summary=(
            "WHO haemoglobin cut-offs are sex- and age-specific: 13.0 g/dL for "
            "adult men and 12.0 g/dL for non-pregnant adult women, with "
            "separate lower boundaries describing moderate and severe anaemia."
        ),
        body="""
The WHO anaemia cut-off for adult men is 13.0 g/dL and for non-pregnant adult
women is 12.0 g/dL. Below the applicable cut-off is what the term anaemia
describes. Children have their own lower cut-offs, which step up with age.

Below 11.0 g/dL is the boundary WHO uses for moderate anaemia, and below
8.0 g/dL for severe anaemia. These are descriptive severity boundaries; what
they mean for a particular person depends on how quickly the value fell and on
the cause, which the number alone does not give.

When sex has not been recorded, this platform uses the lower of the two adult
cut-offs so that it does not over-call anaemia, and reports the zone between the
two cut-offs as borderline rather than resolving it by guessing. The evidence
accompanying the finding says that this was done.

At the other end, the conventional boundary for a raised haemoglobin is
16.5 g/dL in men and 16.0 g/dL in women, with a markedly raised value above
20.0 g/dL. Where sex is unknown the higher cut-off is used, again to avoid
over-calling, and the zone between is reported as borderline.

Haemoglobin cut-offs assume sea level. Sustained residence at altitude raises
the expected value, and published adjustments exist for that reason. This
platform does not apply an altitude adjustment, so a value from a
high-altitude population may be reported as lower than its local reference
would suggest.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "WHO VMNIS 2011 Table 1 haemoglobin cut-offs at sea level; WHO 2016 "
            "haematology criterion for raised haemoglobin. Byte-aligned with "
            "RULE_ANEMIA_HEMOGLOBIN and RULE_ELEVATED_HEMOGLOBIN in "
            "app/data/clinical_rules.py, including their sex-unknown policy."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_vitamin_d_bands",
        title="Vitamin D reference bands",
        topic=TOPIC_REFERENCE,
        features=("vitamin_d",),
        conditions=(C.VITAMIN_D_DEFICIENCY, C.ELEVATED_VITAMIN_D),
        keywords=("vitamin d range", "30 ng/ml", "20 ng/ml", "insufficiency", "deficiency band"),
        summary=(
            "Vitamin D status bands in nanograms per millilitre: below 20 is "
            "described as deficiency, 20 to 29 as insufficiency, 30 and above "
            "as sufficiency."
        ),
        body="""
A 25-hydroxyvitamin D result of 30 ng/mL or above sits in the band described as
sufficiency by the guideline this platform follows.

A result from 20 up to 29 ng/mL sits in the insufficiency band and is reported
as borderline.

A result below 20 ng/mL sits in the deficiency band, and below 10 ng/mL in the
band described as severe deficiency.

Guidelines differ here more than for most analytes. Some bodies place the
adequacy boundary lower, around 20 ng/mL, on the grounds that population bone
outcomes are met there. This platform states which guideline it applies rather
than presenting one set of bands as the only one.

Reports in nanomoles per litre use numbers about two and a half times larger, so
75 nmol/L and 30 ng/mL describe the same status. Comparing across the two scales
without converting is a frequent source of alarm about results that are not
actually low.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "Endocrine Society clinical practice guideline on vitamin D (2011) "
            "status bands. Byte-aligned with RULE_VITAMIN_D_DEFICIENCY and "
            "RULE_ELEVATED_VITAMIN_D in app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_vitamin_b12_bands",
        title="Vitamin B12 reference bands",
        topic=TOPIC_REFERENCE,
        features=("vitamin_b12",),
        conditions=(C.VITAMIN_B12_DEFICIENCY,),
        keywords=("b12 range", "200 pg/ml", "300 pg/ml", "low b12 level", "cobalamin range"),
        summary=(
            "Common serum B12 reporting bands in picograms per millilitre: "
            "below 200 as low, 200 to 300 as an indeterminate zone, above 300 "
            "as unlikely to be low."
        ),
        body="""
A serum B12 above 300 pg/mL is generally reported as making a deficient state
unlikely on this test alone.

A result from 200 up to 300 pg/mL sits in an indeterminate zone. It is reported
as borderline because the serum test cannot separate an adequate state from an
early low one in this range, not because the value is mildly abnormal.

A result below 200 pg/mL sits in the band laboratories commonly report as low,
and below 150 pg/mL in the band describing a frank deficient state.

The indeterminate zone is the reason clinicians add other tests. Methylmalonic
acid and homocysteine rise when cells are actually short of B12, so they can
resolve a serum value that sits between the boundaries.

Serum B12 reference intervals vary noticeably between laboratories and between
assay platforms. The band printed on the report itself is the one that applies
to that measurement, and where it differs from these general bands, the
laboratory's own interval is the more specific reference.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "British Committee for Standards in Haematology cobalamin and "
            "folate guideline (2014) and common laboratory reporting bands. "
            "Byte-aligned with RULE_VITAMIN_B12_DEFICIENCY in "
            "app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_creatinine_bands",
        title="Serum creatinine reference limits",
        topic=TOPIC_REFERENCE,
        features=("creatinine",),
        conditions=(C.KIDNEY_DISEASE,),
        keywords=("creatinine normal range", "1.35", "1.04", "kidney reference", "upper limit"),
        summary=(
            "Adult serum creatinine upper reference limits are sex-specific, "
            "around 1.35 mg/dL for men and 1.04 mg/dL for women, with markedly "
            "raised boundaries above."
        ),
        body="""
The adult upper reference limit used by this platform is approximately
1.35 mg/dL for men and 1.04 mg/dL for women. A value exactly at the limit is
still inside the reference interval, so the comparison is strictly greater than
rather than greater than or equal to.

A value at or above 2.0 mg/dL is substantially above every adult reference
interval in either sex, and at or above 5.0 mg/dL describes severe impairment of
filtration.

Where sex is not recorded, the higher of the two limits is applied so that the
platform does not over-call, and the zone between the two limits is reported as
borderline rather than resolved by guessing.

Creatinine reference limits are not a staging system. Guidelines define and
stage chronic kidney conditions using estimated glomerular filtration rate and
urine albumin, over a period of at least three months. A creatinine value above
the reference limit is a prompt to obtain those, not a stage.

Laboratory methods differ, and reference intervals are method-specific. Reports
in micromoles per litre use numbers roughly eighty-eight times larger, so an
unconverted value would be far outside any band expressed in milligrams per
decilitre.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "Adult sex-specific serum creatinine upper reference limits; KDIGO "
            "2012/2024 for the scope note that staging uses eGFR and "
            "albuminuria. Byte-aligned with RULE_KIDNEY_CREATININE in "
            "app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_cholesterol_bands",
        title="Total cholesterol reference bands",
        topic=TOPIC_REFERENCE,
        features=("cholesterol",),
        conditions=(C.HIGH_CHOLESTEROL,),
        keywords=("cholesterol range", "200", "240", "desirable cholesterol", "lipid bands"),
        summary=(
            "Total cholesterol bands in milligrams per decilitre: below 200 is "
            "described as desirable, 200 to 239 as borderline high, and 240 or "
            "above as high."
        ),
        body="""
A total cholesterol below 200 mg/dL sits in the band described as desirable.

From 200 up to 239 mg/dL is the borderline-high band, reported as borderline.

At or above 240 mg/dL is the high band, and at or above 400 mg/dL is markedly
raised, which is a prompt for prompt professional assessment.

These bands are for TOTAL cholesterol. LDL and HDL cholesterol have their own,
different bands, and a total in the desirable band can still sit over an LDL
that a clinician would want to look at. The components are the more informative
values.

Cardiovascular risk is not read off a cholesterol band. Risk calculators combine
lipid components with age, sex, blood pressure, smoking status, diabetes status
and family history, and two people with identical cholesterol can have very
different estimated risk.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "NCEP ATP III total cholesterol classification. Byte-aligned with "
            "RULE_HIGH_CHOLESTEROL in app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_triglycerides_bands",
        title="Triglyceride reference bands",
        topic=TOPIC_REFERENCE,
        features=("triglycerides",),
        conditions=(C.HIGH_TRIGLYCERIDES,),
        keywords=("triglyceride range", "150", "200", "500", "very high triglycerides"),
        summary=(
            "Triglyceride bands in milligrams per decilitre: below 150 normal, "
            "150 to 199 borderline high, 200 to 499 high, and 500 or above "
            "very high."
        ),
        body="""
A triglyceride value below 150 mg/dL sits in the band described as normal.

From 150 up to 199 mg/dL is borderline high, reported as borderline.

From 200 up to 499 mg/dL is the high band. At or above 500 mg/dL is the very
high band, and at or above 1000 mg/dL is the level at which guidelines
specifically describe a risk of pancreatic inflammation. Values in that range
are a reason to seek professional advice promptly.

These bands assume a fasting sample. A non-fasting triglyceride can read
substantially higher without anything having changed about the person, which is
why a raised non-fasting value is normally repeated fasting before it is
interpreted against these bands.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "NCEP ATP III triglyceride classification; American Heart "
            "Association guidance on the very-high band and pancreatic risk. "
            "Byte-aligned with RULE_HIGH_TRIGLYCERIDES in "
            "app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_bmi_bands",
        title="Body mass index reference bands",
        topic=TOPIC_REFERENCE,
        features=("bmi",),
        conditions=(C.OBESITY, C.UNDERWEIGHT),
        keywords=("bmi range", "18.5", "25", "30", "overweight band", "who bmi"),
        summary=(
            "WHO adult BMI bands in kilograms per square metre: below 18.5 "
            "thinness, 18.5 to 24.9 normal range, 25.0 to 29.9 overweight, and "
            "30.0 or above obesity."
        ),
        body="""
For adults, WHO describes a BMI from 18.5 up to 24.9 kg/m2 as the normal range.

From 25.0 up to 29.9 kg/m2 is described as overweight and is reported as
borderline. At or above 30.0 kg/m2 is described as obesity, and at or above
40.0 kg/m2 as obesity class III.

Below 18.5 kg/m2 is described as thinness: mild from 17.0, moderate from 16.0,
and severe below 16.0 kg/m2.

These bands are for adults. Children and adolescents are assessed against
age- and sex-specific growth references rather than fixed numbers, so an adult
band applied to a child's BMI is simply the wrong comparison.

BMI is a ratio of weight to height squared and knows nothing about body
composition. It reads high in people with substantial muscle and can read
reassuringly ordinary in people carrying central fat with little muscle. It also
performs differently across populations, and several health bodies use lower
boundaries for people of South Asian, Chinese and other Asian descent.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "WHO adult BMI classification. Byte-aligned with RULE_OBESITY_BMI "
            "and RULE_UNDERWEIGHT_BMI in app/data/clinical_rules.py. The "
            "population caveat reflects WHO's 2004 expert consultation on "
            "Asian BMI cut-off points."
        ),
    ),
    KnowledgeDocument(
        doc_id="ref_liver_bands",
        title="Liver test limits: ALT, AST and total bilirubin",
        topic=TOPIC_REFERENCE,
        features=("alt", "ast", "bilirubin_total"),
        conditions=(C.LIVER_DISEASE,),
        keywords=(
            "alt normal range", "sgpt normal range", "ast normal range",
            "sgot normal range", "bilirubin normal range", "upper limit of normal",
            "1.2", "33", "25", "40",
        ),
        summary=(
            "ALT and AST are compared with the upper limit printed on the "
            "laboratory's own report, or the guideline limits when none is "
            "printed; total bilirubin is compared with 1.2 mg/dL."
        ),
        body="""
Laboratories set their own upper limits for ALT and AST, because methods
differ. This platform therefore compares ALT and AST with the upper limit
printed on the report itself. A value above that limit is flagged, and a value
at or above five times that limit is flagged for prompt attention.

When a report prints no upper limit, the guideline limits are used instead: for
ALT, 33 U/L for men and 25 U/L for women, and 33 U/L when sex is not recorded;
for AST, 40 U/L. A printed limit far outside the usual range is not trusted and
the guideline limit is used in its place.

Total bilirubin above 1.2 mg/dL is flagged, and at or above 3.0 mg/dL, the
range in which yellowing of the skin and eyes usually becomes visible, it is
flagged for prompt attention.

These limits apply to adults. Results in children are read against
age-specific references, and newborn bilirubin follows its own charts.

U/L and IU/L are the same unit. Bilirubin reported in micromoles per litre is
divided by 17.1 to give milligrams per decilitre.
"""
        + "\n\n" + BANDS_CAVEAT,
        basis=(
            "ACG Clinical Guideline: Evaluation of Abnormal Liver Chemistries "
            "(American Journal of Gastroenterology, 2017) for the ALT limits "
            "and grading by multiples of the upper limit; common adult "
            "reference values for AST and total bilirubin. Byte-aligned with "
            "RULE_LIVER_ALT, RULE_LIVER_AST and RULE_LIVER_BILIRUBIN in "
            "app/data/clinical_rules.py."
        ),
        last_reviewed="2026-10-04",
    ),
)

__all__ = ["REFERENCE_DOCUMENTS"]
