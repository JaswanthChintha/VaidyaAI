"""Module 22 content -- MEDICAL TERMINOLOGY.

The health-literacy layer. Spec Module 25 (Medical Terminology Explainer) will
read these documents directly rather than generating definitions, which is the
point: a definition an LLM invents is not auditable, and a definition retrieved
from here carries a basis a reader can check.

Documents here define WORDS. `lab_tests.py` describes TESTS and
`reference_information.py` gives NUMBERS. A reader who asks "what does eGFR
mean" and a reader who asks "what is my creatinine" want different documents,
and separating them is what lets retrieval give each the right one.
"""

from __future__ import annotations

from typing import Tuple

from app.data import conditions as C
from app.data.knowledge_types import TOPIC_TERMINOLOGY, KnowledgeDocument

TERMINOLOGY_DOCUMENTS: Tuple[KnowledgeDocument, ...] = (
    KnowledgeDocument(
        doc_id="term_reference_interval",
        title="Reference interval (the 'normal range')",
        topic=TOPIC_TERMINOLOGY,
        features=(),
        conditions=(),
        keywords=(
            "reference range", "normal range", "reference interval",
            "out of range", "flagged high", "flagged low", "h flag", "l flag",
        ),
        summary=(
            "A reference interval is the range within which most results from "
            "a healthy reference population fall, conventionally the central "
            "95 per cent, so some healthy people fall outside it by definition."
        ),
        body="""
A reference interval is built by measuring a large group of people considered
healthy and taking the range that contains the central 95 per cent of their
results. It is a statistical description of that group, not a boundary between
health and illness.

The 95 per cent convention has a direct consequence that surprises many readers:
about one healthy person in twenty falls outside the interval for any given
test, purely by arithmetic. On a panel of ten tests, a healthy person is more
likely than not to have at least one flagged value.

Intervals are specific to the laboratory and the method used. Two laboratories
measuring the same sample can legitimately report different intervals, which is
why the range printed next to a result is the one that applies to it, and why
comparing a value against a range from a different report can mislead.

Intervals are also specific to the population. Age, sex and pregnancy all shift
them, and for some analytes ancestry does too. A single interval applied to
everyone will misclassify people at the edges of those groups.

A decision limit is a different thing from a reference interval, though both
appear as numbers on a report. A decision limit comes from outcome studies and
marks where guidelines advise action, regardless of how common the value is.
Cholesterol and HbA1c bands are decision limits; a haemoglobin range is a
reference interval.

An out-of-range flag is therefore an invitation to look, not a finding. It is
read alongside how far outside the range the value sits, whether it has changed,
and everything else known about the person. This material is educational and is
not a diagnosis.
""",
        basis=(
            "Standard clinical laboratory practice for reference interval "
            "derivation (central 95 per cent of a reference population) and the "
            "distinction between reference intervals and clinical decision "
            "limits, as used throughout app/data/validation_rules.py and "
            "app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="term_units_mgdl_mmoll",
        title="Laboratory units and why they must be converted",
        topic=TOPIC_TERMINOLOGY,
        features=("blood_glucose", "cholesterol", "creatinine", "vitamin_d", "hba1c"),
        conditions=(),
        keywords=(
            "mg/dl", "mmol/l", "units", "conversion", "ng/ml", "nmol/l",
            "µmol/l", "umol/l", "pg/ml", "ifcc", "ngsp", "si units",
        ),
        summary=(
            "The same measurement is reported in different units in different "
            "countries, and comparing a value against a band expressed in "
            "another unit is one of the commonest ways a result is misread."
        ),
        body="""
Conventional units, common in the United States and much of Asia, express
concentrations as a mass per volume such as milligrams per decilitre. SI units,
common in Europe, express them as an amount of substance per volume such as
millimoles per litre. Both describe the same physical quantity.

Converting between them requires the molecular weight of the substance, so the
factor is different for every analyte. Glucose in millimoles per litre is about
eighteen times smaller than the same concentration in milligrams per decilitre;
creatinine in micromoles per litre is about eighty-eight times larger than in
milligrams per decilitre.

The danger is that unconverted values often still look plausible. A glucose of
7 mmol/L compared against a band of 126 mg/dL reads as reassuringly low while
describing a value above that cut-off. A creatinine of 884 µmol/L read as
milligrams per decilitre would look impossible, but 88 would not.

HbA1c has two scales that are not a simple ratio. The NGSP scale reports a
percentage; the IFCC scale reports millimoles per mole, and the relationship
between them includes an offset as well as a multiplier. Converting by ratio
alone gives a substantially wrong answer.

Vitamin D in nanomoles per litre is about two and a half times the value in
nanograms per millilitre, which is why results that look alarmingly high or
reassuringly adequate are worth checking against the unit printed on the report
before anything else.

This platform converts every value to one canonical unit before any comparison,
and refuses a value whose unit it cannot map rather than assuming. A refused
value is reported as refused, not as absent.
""",
        basis=(
            "IUPAC atomic weights underlying the conversion factors in "
            "app/data/unit_conversions.py, independently re-derived during the "
            "Modules 4-10 integration audit. The HbA1c NGSP/IFCC relationship "
            "is affine, not a ratio."
        ),
    ),
    KnowledgeDocument(
        doc_id="term_fasting_sample",
        title="Fasting, post-prandial and random samples",
        topic=TOPIC_TERMINOLOGY,
        features=("blood_glucose", "triglycerides"),
        conditions=(C.DIABETES,),
        keywords=(
            "fasting", "fbs", "post prandial", "pp", "random sample", "rbs",
            "before food", "after food", "8 hours fasting", "ogtt",
        ),
        summary=(
            "Sample timing is part of what a glucose or triglyceride result "
            "means, and the cut-offs used to interpret them are different for "
            "each timing."
        ),
        body="""
A fasting sample is taken after roughly eight hours with no food or caloric
drink, conventionally overnight. Water is normally allowed. This is the
condition under which the fasting glucose cut-offs were established.

A post-prandial sample is taken a defined interval after eating, most often two
hours, and in a formal glucose tolerance test after a measured glucose drink
rather than a meal. Its cut-offs are higher, because a rise after eating is
expected.

A random sample carries no timing information. It is interpreted against the
higher cut-offs, since a value that would be abnormal fasting may be entirely
ordinary an hour after lunch.

Applying the wrong band is a real and common error. It flags ordinary post-meal
values as abnormal, which generates alarm and unnecessary repeat testing. This
platform reads the timing from the printed test name where it is stated, and
where it is not stated it applies the more conservative bands rather than
assuming a fast.

Triglycerides are also timing-sensitive and rise noticeably after a meal or
alcohol. Cholesterol and HbA1c are not: HbA1c reflects months of average
glucose and does not require any fast at all.
""",
        basis=(
            "American Diabetes Association, Standards of Care in Diabetes, "
            "section 2 (timing-specific plasma glucose criteria). Matches the "
            "FASTING_TOKENS / POST_PRANDIAL_TOKENS / RANDOM_TOKENS timing "
            "detection and the only_timing rule scoping in "
            "app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="term_egfr",
        title="eGFR (estimated glomerular filtration rate)",
        topic=TOPIC_TERMINOLOGY,
        features=("creatinine", "age", "gender"),
        conditions=(C.KIDNEY_DISEASE,),
        keywords=(
            "egfr", "gfr", "glomerular filtration rate", "kidney function number",
            "ckd-epi", "mdrd", "ml/min/1.73",
        ),
        summary=(
            "eGFR estimates how much blood the kidneys filter per minute, "
            "calculated from serum creatinine together with age and sex, and "
            "it is the value guidelines use to stage kidney function."
        ),
        body="""
Glomerular filtration rate is the volume of blood the kidneys clear of waste per
minute. Measuring it directly is impractical in routine care, so it is estimated
from a blood marker using a published equation, which is what the leading e
stands for.

The current standard equations use serum creatinine together with age and sex,
and report a result standardised to a body surface area of 1.73 square metres so
that results are comparable between people of different sizes.

Because it is an estimate from creatinine, eGFR inherits creatinine's
limitations. It is less reliable in people whose muscle mass is unusual for
their age and sex, at the extremes of body size, in pregnancy, and when kidney
function is changing rapidly rather than sitting at a steady state.

Guidelines stage chronic kidney conditions using eGFR bands together with the
amount of albumin in the urine. Neither value alone gives a stage, and the
definition also requires the finding to persist for at least three months.

An alternative marker, cystatin C, is less affected by muscle mass and is used
when a creatinine-based estimate is likely to mislead. This platform calculates
eGFR itself from serum creatinine, age and sex using the CKD-EPI 2021 equation,
and only for adults whose sex is recorded. It does not receive cystatin C or
urine albumin, which is why it describes one estimate as a prompt to look
further rather than as a stage. This material is educational and is not a
diagnosis.
""",
        basis=(
            "KDIGO 2012/2024 chronic kidney disease guideline; CKD-EPI 2021 "
            "creatinine equation (Inker et al., NEJM 2021) and its stated "
            "limitations. Matches RULE_KIDNEY_EGFR and the scope limit in "
            "RULE_KIDNEY_CREATININE."
        ),
        last_reviewed="2026-10-04",
    ),
    KnowledgeDocument(
        doc_id="term_ldl_hdl",
        title="LDL, HDL and total cholesterol",
        topic=TOPIC_TERMINOLOGY,
        features=("cholesterol", "triglycerides"),
        conditions=(C.HIGH_CHOLESTEROL,),
        keywords=(
            "ldl", "hdl", "good cholesterol", "bad cholesterol", "non-hdl",
            "lipoprotein", "apob", "vldl", "lipid panel",
        ),
        summary=(
            "LDL and HDL are not different kinds of cholesterol but different "
            "particles that carry it, travelling in opposite directions, which "
            "is why total cholesterol alone is uninformative."
        ),
        body="""
Cholesterol does not dissolve in blood, so it is carried inside particles made
of protein and fat called lipoproteins. LDL and HDL name two classes of those
particles, distinguished by density. The cholesterol inside them is the same
molecule.

LDL particles carry cholesterol from the liver out to tissues, and it is LDL
particles that deposit cholesterol into artery walls. This is why LDL
cholesterol is described informally as the harmful one and why it is the value
most risk guidance focuses on.

HDL particles collect cholesterol from tissues and return it toward the liver.
Higher HDL is associated with lower cardiovascular risk in population studies,
though attempts to raise HDL directly have not reduced events, so the
association is not a simple lever.

Total cholesterol is the sum of the cholesterol in all particle classes. Because
LDL and HDL move risk in opposite directions, the same total can describe very
different situations, which is why a lipid profile reports them separately.

Non-HDL cholesterol, which is total minus HDL, captures the cholesterol in all
the particle types associated with deposits, and does not require a fasting
sample. It is increasingly reported for that reason.

This platform's `cholesterol` feature is TOTAL cholesterol. Where a report also
gives LDL and HDL, those are the more informative values and are the ones worth
raising with a healthcare professional. This material is educational and is not
a diagnosis.
""",
        basis=(
            "NCEP ATP III lipid classification and current lipid-profile "
            "reporting practice. Records the definition given for `cholesterol` "
            "in app/data/feature_catalog.py: TOTAL cholesterol, not LDL."
        ),
    ),
    KnowledgeDocument(
        doc_id="term_anaemia_word",
        title="Anaemia, deficiency and insufficiency: what these words mean",
        topic=TOPIC_TERMINOLOGY,
        features=("hemoglobin", "vitamin_d", "vitamin_b12"),
        conditions=(C.ANEMIA, C.VITAMIN_D_DEFICIENCY, C.VITAMIN_B12_DEFICIENCY),
        keywords=(
            "deficiency", "insufficiency", "anaemia meaning", "anemia meaning",
            "what does deficiency mean", "borderline low",
        ),
        summary=(
            "Deficiency, insufficiency and anaemia are threshold words: each "
            "names a position relative to a published cut-off, not a mechanism "
            "or a cause."
        ),
        body="""
Anaemia names a haemoglobin concentration below the cut-off for a person's age
and sex. It says nothing about why. Using it as though it were a cause is the
commonest misreading of the word.

Deficiency names a measured level below the band a guideline describes as
adequate. Insufficiency names the zone between deficiency and adequacy. Both are
positions on a scale, and where the boundaries sit differs between guidelines
for the same analyte.

Because they are threshold words, small measurement differences can move a
result across a boundary and change the label without anything having changed in
the person. A value one unit either side of a cut-off is far more similar than
the two labels suggest.

The words also carry no information about consequences. Many people whose values
sit in a deficiency band have no symptoms at all, and some people within an
adequate band do have relevant symptoms from another cause.

This is why the useful question about a labelled result is not what the label is
but what produced the number and whether it matters here, which is a question
for a healthcare professional rather than a reference table. This material is
educational and is not a diagnosis.
""",
        basis=(
            "WHO VMNIS 2011 (anaemia), Endocrine Society 2011 (vitamin D "
            "insufficiency and deficiency bands) and BCSH 2014 (cobalamin "
            "bands). The threshold-word framing matches the BORDERLINE status "
            "semantics in app/schemas/decisions.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="term_bmi_word",
        title="Body mass index: what the number is",
        topic=TOPIC_TERMINOLOGY,
        features=("bmi",),
        conditions=(C.OBESITY, C.UNDERWEIGHT),
        keywords=(
            "bmi", "body mass index", "quetelet", "weight height ratio",
            "how is bmi calculated", "waist to height",
        ),
        summary=(
            "Body mass index is weight in kilograms divided by height in "
            "metres squared: a single ratio that summarises size, and nothing "
            "else about the body."
        ),
        body="""
BMI is calculated as weight in kilograms divided by the square of height in
metres. Nothing else enters it. It was devised in the nineteenth century as a
way of describing populations, not individuals, and that origin explains most of
its limitations.

Because it uses only weight and height, it cannot distinguish muscle from fat,
nor say where on the body weight sits. A well-muscled person and a person with
substantial abdominal fat can share a BMI while differing considerably in
metabolic terms.

Where fat sits matters. Fat around the abdomen carries stronger associations
with metabolic and cardiovascular outcomes than fat elsewhere, which is why
waist circumference and waist-to-height ratio are often used alongside BMI.

BMI also behaves differently across populations, with associated metabolic
changes appearing at lower values in several Asian populations, and it is not
applicable in the same way to children, to pregnancy, or to people with limb
differences.

This platform derives BMI from the height and weight recorded in a patient
profile, and marks it as a derived value so that its lower reliability is
carried through rather than hidden. This material is educational and is not a
diagnosis.
""",
        basis=(
            "WHO adult BMI classification and the WHO 2004 expert consultation "
            "on Asian cut-off points. The derived-value marking reflects how "
            "`bmi` is produced in app/services/feature_engineer.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="term_risk_factor",
        title="Risk factor, risk and probability",
        topic=TOPIC_TERMINOLOGY,
        features=("age", "hypertension", "heart_disease", "smoking_history", "gender"),
        conditions=(C.HEART_DISEASE, C.DIABETES),
        keywords=(
            "risk factor", "risk score", "probability", "odds", "relative risk",
            "what does risk mean", "10 year risk", "likelihood",
        ),
        summary=(
            "A risk factor is something associated with a higher rate of an "
            "outcome in a population; a risk estimate is a probability for a "
            "group, and neither is a statement about what will happen to one "
            "person."
        ),
        body="""
A risk factor is a characteristic that occurs more often in people who go on to
experience an outcome than in people who do not. The association may or may not
be causal, and identifying one does not establish a mechanism.

A risk estimate turns a combination of factors into a probability, usually
expressed as a percentage chance of an event over a stated period. That
probability describes the rate observed among people sharing the profile, which
is why it is meaningful for a group and cannot be verified for an individual.

Relative and absolute risk are frequently confused, and the difference is
large. A change that doubles a risk sounds alarming, but if the underlying rate
was one in ten thousand, doubling it makes it two in ten thousand. The absolute
figures are what make a relative change interpretable.

A probability of 30 per cent is not a prediction, and neither is a probability
of 3 per cent. Both describe frequencies across many similar people, and any
individual either experiences the outcome or does not.

Machine-learning models used in this platform output probabilities of exactly
this kind. They are reported with the model that produced them and the features
that fed them, and they are combined with rule-based findings rather than
presented as answers on their own.

No risk estimate carries certainty, and language suggesting otherwise is
inaccurate rather than merely unhelpful. This material is educational and is not
a diagnosis.
""",
        basis=(
            "NCEP ATP III major risk factor framework and standard "
            "epidemiological definitions of absolute and relative risk. "
            "Describes how ClinicalDecision.confidence is defined in "
            "app/schemas/decisions.py."
        ),
    ),
    # ------------------------------------------------------------------
    # LIVER ENZYMES (owner, 2026-10-04). Spec Module 25 names SGPT, and the
    # corpus had nothing on it, so the term was refused. These two documents
    # describe the TESTS; the numbers live in `ref_liver_bands`.
    #
    # LATER THE SAME DAY ALT and AST became assessed features (the Liver
    # Disease topic), so these documents now carry their feature tags and are
    # the features' own "what is this test" documents. Their bodies still
    # hold no number, so a cut-off has one home.
    # ------------------------------------------------------------------
    KnowledgeDocument(
        doc_id="term_alt_sgpt",
        title="ALT (SGPT), a liver enzyme test",
        topic=TOPIC_TERMINOLOGY,
        features=("alt",),
        conditions=(C.LIVER_DISEASE,),
        keywords=(
            "alt", "sgpt", "alanine aminotransferase", "alanine transaminase",
            "serum glutamic pyruvic transaminase", "liver enzyme",
            "liver function test", "lft",
        ),
        summary=(
            "ALT, also printed as SGPT, measures an enzyme found mainly inside "
            "liver cells, which passes into the blood in larger amounts when "
            "those cells are irritated or damaged. It is usually tested as part "
            "of a liver panel to look at how the liver is coping."
        ),
        body="""
Alanine aminotransferase, shortened to ALT, is an enzyme that helps liver cells
turn food into energy. Older reports call the same test SGPT, which stands for
serum glutamic pyruvic transaminase; the two names describe one measurement.

Most ALT sits inside liver cells, so only a small amount is normally found in
the blood. When liver cells are inflamed or injured, more of the enzyme leaks
out, which is why ALT is one of the most commonly used signals of liver cell
irritation.

ALT is usually ordered together with other liver tests, such as AST, alkaline
phosphatase, bilirubin and albumin. The pattern across the panel says more than
any one enzyme, because each reflects a different part of how the liver and the
bile ducts are working.

A raised ALT on its own does not say what caused it. Many things can affect it
for a short time, including recent strenuous exercise, body weight, infections
and other substances the liver processes, and a result is often repeated before
anything is concluded from it.

ALT measures irritation of liver cells, not how well the liver is doing its
work. A liver can have a normal ALT and still need attention, and a raised ALT
can settle without any lasting problem. Reference intervals differ between
laboratories, so a result is read against the range printed by the laboratory
that measured it.

This platform compares an ALT result with the upper limit printed on the
report, and flags a value above it as worth discussing. A qualified healthcare
professional interprets it alongside the rest of the panel, symptoms and
history. This material is educational and is not a diagnosis.
""",
        basis=(
            "ACG Clinical Guideline: Evaluation of Abnormal Liver Chemistries "
            "(Kwo, Cohen and Lim; American Journal of Gastroenterology, 2017); "
            "MedlinePlus, ALT blood test (U.S. NLM). The limits applied are in "
            "ref_liver_bands and RULE_LIVER_ALT."
        ),
        last_reviewed="2026-10-04",
    ),
    KnowledgeDocument(
        doc_id="term_ast_sgot",
        title="AST (SGOT), a liver enzyme test",
        topic=TOPIC_TERMINOLOGY,
        features=("ast",),
        conditions=(C.LIVER_DISEASE,),
        keywords=(
            "ast", "sgot", "aspartate aminotransferase",
            "aspartate transaminase", "serum glutamic oxaloacetic transaminase",
            "liver enzyme", "liver function test", "lft",
        ),
        summary=(
            "AST, also printed as SGOT, measures an enzyme found in the liver "
            "and also in muscle, the heart and red blood cells, which passes "
            "into the blood when those cells are damaged. It is usually tested "
            "alongside ALT as part of a liver panel."
        ),
        body="""
Aspartate aminotransferase, shortened to AST, is an enzyme involved in how cells
process energy. Older reports call the same test SGOT, which stands for serum
glutamic oxaloacetic transaminase; the two names describe one measurement.

Unlike ALT, AST is found in several tissues: the liver, skeletal muscle, the
heart, the kidneys and red blood cells. A raised AST can therefore come from
outside the liver, for example after hard physical exercise or a muscle injury,
which is one reason it is read together with ALT rather than on its own.

AST is usually ordered as part of a liver panel with ALT, alkaline phosphatase,
bilirubin and albumin. Clinicians look at the pattern across these tests, and at
how AST and ALT compare with each other, rather than at a single value.

A raised AST on its own does not say what caused it. Short-lived changes are
common, a result is often repeated before anything is concluded from it, and
reference intervals differ between laboratories, so a result is read against the
range printed by the laboratory that measured it.

This platform compares an AST result with the upper limit printed on the
report, and flags a value above it as worth discussing. A qualified healthcare
professional interprets it alongside the rest of the panel, symptoms and
history. This material is educational and is not a diagnosis.
""",
        basis=(
            "ACG Clinical Guideline: Evaluation of Abnormal Liver Chemistries "
            "(Kwo, Cohen and Lim; American Journal of Gastroenterology, 2017); "
            "MedlinePlus, AST test (U.S. NLM). The limits applied are in "
            "ref_liver_bands and RULE_LIVER_AST."
        ),
        last_reviewed="2026-10-04",
    ),
)

__all__ = ["TERMINOLOGY_DOCUMENTS"]
