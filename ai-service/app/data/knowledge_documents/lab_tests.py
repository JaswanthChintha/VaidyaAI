"""Module 22 content -- LABORATORY TESTS.

One document per laboratory feature in `app/data/feature_catalog.py`. Each
answers the four questions spec Module 25 lists: what the test measures, why it
is performed, what the value represents, and why the parameter may matter.

REVIEWER NOTES
--------------
* `features` and `conditions` are checked against the shared catalogues at
  import. Do not invent a name here.
* The reference bands quoted in `reference_information.py` are the ones the
  Module 8 rule table actually applies. THESE documents describe the test;
  those describe the numbers. Keeping them apart means a threshold change
  touches one document, not fifteen.
* Every paragraph is a retrieval chunk, so each must stand on its own. A
  paragraph beginning "It is also..." is a bug, not a style choice.
* Nothing here may name a medication, quantify an intake, assert a finding
  about a reader, or express certainty. The import-time scanner enforces it.
"""

from __future__ import annotations

from typing import Tuple

from app.data import conditions as C
from app.data.knowledge_types import TOPIC_LAB_TEST, KnowledgeDocument

CONSULT = (
    "A single laboratory number is one observation, not a conclusion. Results "
    "are interpreted by a qualified healthcare professional alongside symptoms, "
    "history and other tests. This material is educational and is not a "
    "diagnosis."
)

LAB_TEST_DOCUMENTS: Tuple[KnowledgeDocument, ...] = (
    KnowledgeDocument(
        doc_id="lab_hba1c",
        title="HbA1c (glycated haemoglobin)",
        topic=TOPIC_LAB_TEST,
        features=("hba1c",),
        conditions=(C.DIABETES,),
        keywords=(
            "hba1c", "a1c", "glycated haemoglobin", "glycated hemoglobin",
            "glycosylated haemoglobin", "hb a1c", "average blood sugar",
            "three month sugar", "ngsp", "long term sugar control",
        ),
        summary=(
            "HbA1c reports the proportion of haemoglobin in the blood that has "
            "sugar attached to it, which reflects average blood glucose over "
            "roughly the previous two to three months."
        ),
        body="""
Haemoglobin is the protein inside red blood cells that carries oxygen. When
glucose circulates in the blood, a small proportion of it attaches to
haemoglobin and stays attached for the life of the cell. HbA1c measures what
share of haemoglobin carries that attached glucose, reported in the NGSP
percentage scale.

Because red blood cells live for around three months, HbA1c reflects average
glucose exposure across that whole period rather than the moment of the blood
draw. That is the main reason it is used: it does not change if someone ate
shortly before the sample, and it does not need a fasting sample at all.

A higher HbA1c corresponds to higher average glucose over the preceding weeks.
Guideline bands describe where a value sits relative to published population
cut-offs; they describe a range, not a person, and the same number can arise
from very different day-to-day patterns.

HbA1c can be misleading in some circumstances, which is why it is read
alongside other information. Conditions that shorten or lengthen red-cell
survival, recent significant blood loss, pregnancy and some inherited
haemoglobin variants can all move the number independently of glucose. A
laboratory or clinician who knows the wider picture is the one who can judge
whether the value can be taken at face value.

HbA1c and a blood glucose measurement answer different questions and are often
read together. Glucose is a snapshot of one moment; HbA1c is an average across
months. Agreement between the two is informative, and so is disagreement.
"""
        + "\n\n" + CONSULT,
        basis=(
            "American Diabetes Association, Standards of Care in Diabetes, "
            "section 2 (NGSP-aligned HbA1c). Matches RULE_DIABETES_HBA1C in "
            "app/data/clinical_rules.py and the canonical unit '%' in "
            "app/data/feature_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_blood_glucose",
        title="Blood glucose",
        topic=TOPIC_LAB_TEST,
        features=("blood_glucose",),
        conditions=(C.DIABETES, C.HYPOGLYCEMIA),
        keywords=(
            "blood glucose", "blood sugar", "fasting glucose", "fbs", "fpg",
            "random blood sugar", "rbs", "post prandial", "pp glucose",
            "plasma glucose", "sugar test", "ogtt", "glucose tolerance",
        ),
        summary=(
            "Blood glucose measures the concentration of sugar in the blood at "
            "the moment the sample was taken, and its interpretation depends "
            "heavily on when the person last ate."
        ),
        body="""
Glucose is the body's main circulating fuel. A blood glucose test measures how
much of it is present in the sample at the instant the blood was drawn. Unlike
HbA1c, it is a snapshot and can change substantially within an hour.

Timing changes what the number means, which is why laboratory reports usually
label the sample. A fasting sample is taken after roughly eight hours without
food or caloric drink. A post-prandial sample is taken a set interval after a
meal or a measured glucose drink, most often two hours. A random sample carries
no timing information at all.

The published cut-offs are timing-specific and are not interchangeable. Applying
a fasting cut-off to a sample taken after a meal would flag ordinary
post-meal values as abnormal, so when a report does not establish that the
sample was fasting, the more conservative post-load and random bands are the
appropriate comparison.

Glucose values below the usual range are also meaningful and are described
separately under low blood glucose. Low readings in a person who is not taking
glucose-lowering preparations have a different significance from low readings in
someone who is, and both are questions for a clinician rather than for a
reference table.

Many everyday circumstances move a single glucose reading: acute illness,
physical stress, a poor night's sleep, some preparations taken under medical supervision, and simple
sample handling delays. This is one reason a single out-of-range value is
usually repeated before anything is concluded from it.
"""
        + "\n\n" + CONSULT,
        basis=(
            "American Diabetes Association, Standards of Care in Diabetes, "
            "section 2 (fasting, 2-hour post-load and random plasma glucose "
            "bands) and the ADA/EASD hypoglycaemia classification. Matches "
            "RULE_DIABETES_GLUCOSE_FASTING, RULE_DIABETES_GLUCOSE_UNSPECIFIED "
            "and RULE_HYPOGLYCEMIA_GLUCOSE in app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_hemoglobin",
        title="Haemoglobin",
        topic=TOPIC_LAB_TEST,
        features=("hemoglobin",),
        conditions=(C.ANEMIA, C.ELEVATED_HEMOGLOBIN),
        keywords=(
            "haemoglobin", "hemoglobin", "hb", "hgb", "blood count",
            "full blood count", "cbc", "red blood cells", "oxygen carrying",
            "low blood", "iron test",
        ),
        summary=(
            "Haemoglobin measures the concentration of the oxygen-carrying "
            "protein in red blood cells, and is the value used to describe "
            "anaemia and raised red-cell states."
        ),
        body="""
Haemoglobin is the iron-containing protein inside red blood cells that binds
oxygen in the lungs and releases it in the tissues. The test reports its
concentration in blood, usually as grams per decilitre, and it is normally
issued as part of a full blood count.

A concentration below the population cut-off is what the term anaemia
describes. Anaemia is a finding, not a cause: reduced iron availability, low
vitamin B12 or folate, ongoing blood loss, long-standing inflammation, kidney
conditions and inherited haemoglobin variants can each produce it, and the
routes to telling them apart are further tests rather than the haemoglobin
number alone.

The cut-offs genuinely differ by sex and by age, which is why a report read
without that context can mislead. Where sex is not recorded, this platform
deliberately uses the cut-off that avoids over-calling and says so, rather than
guessing.

A concentration above the usual range is a separate observation with its own
possible explanations, including reduced plasma volume from dehydration, living
at altitude, smoking, sleep-disordered breathing and, less commonly, primary
bone-marrow conditions. It is described in its own document.

Haemoglobin is a concentration, so anything that changes the volume of plasma
changes it without any change in the number of red cells. Dehydration can raise
the apparent value and fluid loading can lower it. Sample timing and posture
also introduce small shifts, so a modest change between two reports is not
necessarily a change in the person.
"""
        + "\n\n" + CONSULT,
        basis=(
            "WHO Vitamin and Mineral Nutrition Information System (VMNIS) 2011 "
            "haemoglobin cut-offs at sea level, and the WHO 2016 haematology "
            "classification for raised haemoglobin. Matches "
            "RULE_ANEMIA_HEMOGLOBIN and RULE_ELEVATED_HEMOGLOBIN in "
            "app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_vitamin_d",
        title="Vitamin D (25-hydroxyvitamin D)",
        topic=TOPIC_LAB_TEST,
        features=("vitamin_d",),
        conditions=(C.VITAMIN_D_DEFICIENCY, C.ELEVATED_VITAMIN_D),
        keywords=(
            "vitamin d", "25-oh vitamin d", "25 hydroxyvitamin d", "calcidiol",
            "vit d", "sunshine vitamin", "bone health", "25(oh)d",
        ),
        summary=(
            "The 25-hydroxyvitamin D test measures the main circulating store "
            "of vitamin D and is the standard way of describing whether the "
            "body's vitamin D status is low, adequate or high."
        ),
        body="""
Vitamin D is made in the skin on exposure to ultraviolet light and is also
obtained from a small number of foods. The liver converts it to
25-hydroxyvitamin D, which circulates for weeks and is therefore the form
measured to describe status. The active hormone form is much shorter-lived and
is not what this test reports.

Vitamin D helps the gut absorb calcium and phosphate, which is why long-standing
low status is associated with weaker bone mineralisation, and in children with
the bone-softening condition rickets. Muscle function and several other systems
are also affected, though the strength of those associations varies.

Low status is common and is often explained by ordinary circumstances: limited
outdoor time, higher latitudes and winter months, routine sun protection,
clothing that covers most skin, darker skin pigmentation, older age, and
conditions that reduce fat absorption. A low value describes the measurement,
not the reason for it.

Values well above the usual range are uncommon and generally arise from very
high intakes over time rather than from sunlight, since skin production is
self-limiting. Because vitamin D increases calcium absorption, a markedly high
value is a reason to speak to a clinician rather than something to interpret
from a table.

Laboratories report this test in either nanograms per millilitre or nanomoles
per litre, and the two scales differ by roughly two and a half times. Comparing
a value against a band expressed in the other unit is a common source of
confusion, which is why this platform converts to one canonical unit before
anything is compared.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Endocrine Society clinical practice guideline on vitamin D (2011) "
            "status bands, and the conventional upper boundary above which "
            "specialist review is advised. Matches RULE_VITAMIN_D_DEFICIENCY "
            "and RULE_ELEVATED_VITAMIN_D in app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_vitamin_b12",
        title="Vitamin B12 (cobalamin)",
        topic=TOPIC_LAB_TEST,
        features=("vitamin_b12",),
        conditions=(C.VITAMIN_B12_DEFICIENCY,),
        keywords=(
            "vitamin b12", "b12", "cobalamin", "serum b12", "vit b12",
            "pernicious anaemia", "nerve tingling", "vegetarian diet",
        ),
        summary=(
            "Serum vitamin B12 measures the amount of cobalamin circulating in "
            "the blood, a vitamin needed for red blood cell formation and for "
            "the normal function of the nervous system."
        ),
        body="""
Vitamin B12, also called cobalamin, is required to make DNA, to form red blood
cells and to maintain the insulating sheath around nerves. The body cannot make
it, so all of it comes from the diet, principally from animal-derived foods.

Absorbing B12 takes several steps: stomach acid releases it from food, a
stomach protein called intrinsic factor binds it, and the last part of the small
intestine takes it up. A problem at any of those steps can lower the level even
when intake is adequate, which is why a low result does not by itself point to
diet.

Low B12 status can show up as a particular pattern of anaemia in which red
blood cells are larger than usual, and separately as nerve-related symptoms such
as tingling, numbness or unsteadiness. The two do not always appear together,
and nerve symptoms can appear while the blood count still looks ordinary.

The serum test measures total B12, most of which is bound to a carrier protein
that does not deliver it to cells. That is one reason results in the lower part
of the range can be ambiguous, and why a clinician may add tests such as
methylmalonic acid or homocysteine when the picture is unclear.

Higher-than-usual B12 results are also seen and are usually explained by recent
intake. Because they are occasionally associated with other conditions, a
markedly high value is interpreted by a clinician in context rather than read
off a reference band.
"""
        + "\n\n" + CONSULT,
        basis=(
            "British Committee for Standards in Haematology cobalamin and "
            "folate guideline (2014) and common laboratory reporting bands. "
            "Matches RULE_VITAMIN_B12_DEFICIENCY in app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_creatinine",
        title="Serum creatinine",
        topic=TOPIC_LAB_TEST,
        features=("creatinine",),
        conditions=(C.KIDNEY_DISEASE,),
        keywords=(
            "creatinine", "serum creatinine", "kidney function test",
            "renal function", "egfr", "kidney test", "rft", "kft",
        ),
        summary=(
            "Serum creatinine measures a waste product of normal muscle "
            "activity that the kidneys filter out, and it is used as an "
            "indirect indicator of how well filtration is working."
        ),
        body="""
Creatinine is produced continuously as muscle uses energy, enters the blood at a
fairly steady rate, and is removed almost entirely by the kidneys. If filtration
slows, creatinine accumulates, so a rising concentration in blood suggests
falling filtration.

The relationship is indirect and not proportional. Filtration can fall
substantially before creatinine leaves the reference interval, so a value inside
the interval does not establish that kidney function is normal, particularly in
someone with low muscle mass.

Because the creatinine a person generates depends on their muscle, the same
concentration means different things in different people. Sex, age, body build
and ethnicity all shift the expected value, which is why reference limits are
sex-specific and why a single number is never read in isolation.

For that reason laboratories usually report an estimated glomerular filtration
rate alongside it. eGFR is calculated from creatinine together with age and sex
and is the value guidelines actually use to define and stage chronic kidney
conditions. Creatinine alone flags that filtration may warrant a closer look; it
does not stage anything.

Several ordinary things move creatinine over days without any change in the
kidneys: a large meat meal, intense exercise shortly before the sample,
dehydration, and certain preparations taken under medical supervision that alter how creatinine is
handled without altering filtration. Repeat sampling is how a real change is
distinguished from a transient one.
"""
        + "\n\n" + CONSULT,
        basis=(
            "KDIGO 2012/2024 chronic kidney disease guideline (which defines "
            "and stages by eGFR and albuminuria, not by creatinine alone) and "
            "adult sex-specific serum creatinine upper reference limits. "
            "Matches RULE_KIDNEY_CREATININE in app/data/clinical_rules.py, "
            "including its scope note."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_cholesterol",
        title="Total cholesterol",
        topic=TOPIC_LAB_TEST,
        features=("cholesterol",),
        conditions=(C.HIGH_CHOLESTEROL, C.HEART_DISEASE),
        keywords=(
            "cholesterol", "total cholesterol", "lipid profile", "lipids",
            "ldl", "hdl", "good cholesterol", "bad cholesterol", "fats in blood",
        ),
        summary=(
            "Total cholesterol measures all the cholesterol carried in the "
            "blood added together, across every type of particle that carries "
            "it."
        ),
        body="""
Cholesterol is a fatty substance the body needs to build cell membranes and to
make certain hormones and bile acids. It does not dissolve in blood, so it
travels inside particles called lipoproteins. Total cholesterol is the sum of
what all of those particles carry.

Because it is a sum, total cholesterol hides the composition. LDL particles are
the ones associated with fatty deposits building up in artery walls, while HDL
particles are associated with the opposite direction of transport. Two people
with the same total can have very different LDL and HDL splits and therefore
very different cardiovascular pictures.

This is why a full lipid profile reports the components separately, usually LDL
cholesterol, HDL cholesterol and triglycerides alongside the total, and why
cardiovascular risk scores use the components rather than the total.

Total cholesterol is still useful as an initial screen and is what many basic
panels report. A raised total is a prompt to look at the components rather than
a finding in itself.

Fasting is no longer required for a lipid profile in most circumstances,
although it can still be requested when triglycerides are the value of
interest. Sample timing, acute illness, recent significant weight change and
pregnancy all shift lipid results, so an unexpected value is usually rechecked
before anything follows from it.
"""
        + "\n\n" + CONSULT,
        basis=(
            "NCEP ATP III total cholesterol classification (desirable, "
            "borderline high, high) and current lipid-profile sampling "
            "practice. Matches RULE_HIGH_CHOLESTEROL in "
            "app/data/clinical_rules.py. Note that feature_catalog.py defines "
            "`cholesterol` as TOTAL cholesterol, not LDL."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_triglycerides",
        title="Triglycerides",
        topic=TOPIC_LAB_TEST,
        features=("triglycerides",),
        conditions=(C.HIGH_TRIGLYCERIDES, C.HEART_DISEASE),
        keywords=(
            "triglycerides", "tg", "trigs", "lipid profile", "blood fats",
            "fasting lipids", "hypertriglyceridaemia",
        ),
        summary=(
            "Triglycerides are the main form in which fat is carried in the "
            "blood and stored in the body, and the blood level responds "
            "strongly to recent food and alcohol."
        ),
        body="""
Triglycerides are the chemical form of most fat in food and most fat stored in
the body. After a meal they are carried in the blood from the gut to tissues
that use or store them, so the circulating level rises and falls across the day
far more than cholesterol does.

That sensitivity to recent intake is the practical point. A sample taken a few
hours after a substantial meal, or after alcohol, can read considerably higher
than the same person's fasting value, which is why a raised result is often
repeated with a fasting sample before it is interpreted.

Persistently raised triglycerides are associated with cardiovascular risk and
frequently appear alongside other findings such as raised blood glucose,
central weight and lower HDL cholesterol. They are read as part of that pattern
rather than on their own.

Very high triglyceride values are a distinct situation. Above the levels that
guidelines describe as very high, the concern shifts to the pancreas, and this
is a prompt for prompt professional assessment rather than for watchful waiting.

Poorly controlled glucose, low thyroid activity, kidney conditions, pregnancy,
significant alcohol intake and some preparations taken under medical supervision all raise
triglycerides. Identifying which of these applies is a clinical question, not
something a laboratory value answers.
"""
        + "\n\n" + CONSULT,
        basis=(
            "NCEP ATP III triglyceride classification (normal, borderline high, "
            "high, very high) and the American Heart Association pancreatitis "
            "risk level. Matches RULE_HIGH_TRIGLYCERIDES in "
            "app/data/clinical_rules.py."
        ),
    ),
)

__all__ = ["LAB_TEST_DOCUMENTS"]
