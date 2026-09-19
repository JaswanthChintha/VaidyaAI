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
    # ==================================================================
    # THE COMPLETE BLOOD COUNT
    # ==================================================================
    #
    # Twelve documents for the twelve CBC features. Every one of them says,
    # somewhere and in the reader's own language, that the value is harmful at
    # BOTH ends or that it is a proportion of a total -- because that is why
    # `app/data/trend_polarity.py` refuses to tell the reader which direction
    # is better, and a refusal the reader cannot understand reads as the tool
    # being broken.
    KnowledgeDocument(
        doc_id="lab_hematocrit",
        title="Haematocrit (PCV)",
        topic=TOPIC_LAB_TEST,
        features=("hematocrit",),
        conditions=(),
        keywords=(
            "haematocrit", "hematocrit", "pcv", "packed cell volume", "hct",
            "full blood count", "cbc", "red blood cells",
        ),
        summary=(
            "Haematocrit is the share of blood volume made up of red cells. "
            "It is often printed as PCV, and it moves closely with "
            "haemoglobin."
        ),
        body="""
Haematocrit is the proportion of whole blood that consists of red cells,
reported as a percentage. Many laboratories print it under the name PCV, short
for packed cell volume; the two names describe the same measurement.

Haematocrit moves closely with haemoglobin, and in adults the two rise and fall
together. Because they carry much the same information, a report showing one
below the usual range will usually show the other below it as well.

The usual range differs between men and women, and is also affected by age.
Altitude matters too: people living at high altitude commonly have higher
values, which is a normal adaptation rather than a finding.

A value below the usual range is the same observation that the term anaemia
describes, and a value above it may reflect reduced plasma volume, living at
altitude, smoking, or less commonly a bone-marrow condition.

Because haematocrit is a proportion of blood volume, anything that changes the
amount of plasma changes it without any change in the number of red cells.
Dehydration raises the apparent value and fluid loading lowers it, so a modest
difference between two reports need not reflect a change in the person.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement. The value can be outside the
usual range at either end, and the usual range itself depends on sex and other
factors this report may not record.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Describes the measurement and the sex, age and altitude "
            "dependence. The population distribution shipped for this feature "
            "is NHANES 2017-2018 (LBXHCT); see "
            "datasets/population/PROVENANCE.md."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_rbc_count",
        title="Red blood cell count",
        topic=TOPIC_LAB_TEST,
        features=("rbc_count",),
        conditions=(),
        keywords=(
            "rbc", "red blood cell count", "red cell count", "erythrocyte",
            "total rbc", "full blood count", "cbc",
        ),
        summary=(
            "The red blood cell count is the number of red cells in a volume "
            "of blood, reported as part of the full blood count."
        ),
        body="""
The red blood cell count reports how many red cells are present in a given
volume of blood. It is issued as part of the full blood count, alongside
haemoglobin and haematocrit.

Red cells carry oxygen from the lungs to the rest of the body. The count is one
of three related measurements describing them, and it is usually interpreted
together with haemoglobin and haematocrit rather than on its own.

The usual range differs between men and women. A count below it accompanies the
observation described by the term anaemia; a count above it can reflect reduced
plasma volume, living at altitude, or less commonly a bone-marrow condition.

The count alone does not describe the size or the haemoglobin content of the
cells. Those are reported separately as MCV and MCH, and it is the combination
that laboratories use to narrow down why a count is unusual.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because the count can be
outside the usual range at either end.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Describes the measurement and its relationship to haemoglobin "
            "and haematocrit. Population distribution: NHANES 2017-2018 "
            "(LBXRBCSI)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_mcv",
        title="MCV (mean corpuscular volume)",
        topic=TOPIC_LAB_TEST,
        features=("mcv",),
        conditions=(),
        keywords=(
            "mcv", "mean corpuscular volume", "mean cell volume",
            "red cell size", "microcytic", "macrocytic", "cbc",
        ),
        summary=(
            "MCV is the average size of a red blood cell. It is used to "
            "narrow down why a blood count is unusual, rather than to "
            "describe severity."
        ),
        body="""
MCV, the mean corpuscular volume, is the average volume of a single red blood
cell. It is calculated from the red cell count and the haematocrit and is
reported in femtolitres as part of the full blood count.

MCV is most useful as a pointer rather than as a measure of severity. When a
blood count is unusual, the average cell size helps narrow down the possible
reasons, which is why laboratories group causes by whether the cells are small,
normal or large.

Smaller than usual red cells are associated with reduced iron availability and
with inherited haemoglobin variants such as thalassaemia. Larger than usual red
cells are associated with low vitamin B12 or folate, with alcohol use, and with
certain bone-marrow conditions.

A value near the middle of the usual range does not by itself indicate that a
blood count is unremarkable, because a mixture of causes can pull the average
in opposite directions and leave it looking ordinary.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement. A move upward from a small
average and a move downward from a large one are different situations, and the
number alone does not distinguish them.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Describes MCV as a classifying index rather than a severity "
            "measure, which is the reason app/data/trend_polarity.py declares "
            "its polarity UNDECLARED. Population distribution: NHANES "
            "2017-2018 (LBXMCVSI)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_mch",
        title="MCH (mean corpuscular haemoglobin)",
        topic=TOPIC_LAB_TEST,
        features=("mch",),
        conditions=(),
        keywords=(
            "mch", "mean corpuscular haemoglobin", "mean cell hemoglobin",
            "cbc", "full blood count",
        ),
        summary=(
            "MCH is the average amount of haemoglobin carried in a single red "
            "blood cell."
        ),
        body="""
MCH, the mean corpuscular haemoglobin, is the average mass of haemoglobin in a
single red blood cell. It is calculated from the haemoglobin concentration and
the red cell count and is reported in picograms.

MCH tends to move in the same direction as MCV, because smaller cells generally
carry less haemoglobin and larger cells carry more. The two are usually read
together rather than separately.

A lower than usual MCH is associated with reduced iron availability and with
inherited haemoglobin variants. A higher than usual MCH accompanies the same
situations that enlarge red cells, including low vitamin B12 or folate.

Because MCH is calculated rather than measured directly, anything that affects
the haemoglobin concentration or the red cell count also affects it.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because the value can be
unusual at either end for different reasons.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Describes MCH as a derived index read alongside MCV. Population "
            "distribution: NHANES 2017-2018 (LBXMCHSI)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_mchc",
        title="MCHC (mean corpuscular haemoglobin concentration)",
        topic=TOPIC_LAB_TEST,
        features=("mchc",),
        conditions=(),
        keywords=(
            "mchc", "mean corpuscular haemoglobin concentration",
            "mean cell hemoglobin concentration", "cbc",
        ),
        summary=(
            "MCHC is how concentrated the haemoglobin is inside red cells. A "
            "high result is frequently caused by the sample rather than by "
            "the person."
        ),
        body="""
MCHC, the mean corpuscular haemoglobin concentration, describes how tightly
haemoglobin is packed inside red blood cells. It is calculated from the
haemoglobin concentration and the haematocrit.

MCHC varies far less between people than most other blood count values, because
there is a physical limit to how much haemoglobin a red cell can hold. That
narrow spread is why an unusual result draws attention.

A result above the usual range is frequently a measurement effect rather than a
change in the person. Fat in the blood sample, red cells that have broken down
before analysis, and proteins that make cells clump in the cold can each raise
the figure reported by the analyser.

A result below the usual range accompanies the situations that produce small,
pale red cells, most commonly reduced iron availability.

Some laboratories report this value as a percentage and others in grams per
decilitre. For this measurement the two are the same scale, so a value of 33
means the same thing in either unit.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, partly because a rise is as
likely to reflect the sample as the person.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Records the artefactual causes of a raised MCHC, which is the "
            "reason app/data/trend_polarity.py refuses a direction for it. "
            "The unit equivalence is recorded in "
            "backend/src/services/unitEquivalence.js. Population "
            "distribution: NHANES 2017-2018 (LBXMC)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_wbc_count",
        title="White blood cell count",
        topic=TOPIC_LAB_TEST,
        features=("wbc_count",),
        conditions=(),
        keywords=(
            "wbc", "white blood cell count", "total leucocyte count", "tlc",
            "white cell count", "leukocyte", "cbc", "infection",
        ),
        summary=(
            "The white blood cell count is the total number of immune cells "
            "in a volume of blood. It can be unusual at either end."
        ),
        body="""
The white blood cell count reports the total number of immune cells in a given
volume of blood. It is issued as part of the full blood count and is often
accompanied by a differential, which breaks the total down into cell types.

White cells are the part of the blood involved in responding to infection and
inflammation. The total count rises and falls in response to a wide range of
ordinary events, which is why it is read alongside other information rather
than alone.

A count above the usual range accompanies infection and inflammation, and also
follows physical stress, pregnancy and smoking. Much less commonly it reflects a
condition of the bone marrow.

A count below the usual range can follow some viral infections and conditions
affecting the bone marrow. A lower count can mean less capacity to respond to
infection.

The white cell count varies considerably within the same person from day to
day, and it is normal for it to differ between two reports without anything
having changed.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because the count can be
unusual at either end and a rise may simply mean the body is responding to
something.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Describes the total count and its wide within-person variation, "
            "which is reflected in the stability band in "
            "app/data/trend_polarity.py. Population distribution: NHANES "
            "2017-2018 (LBXWBCSI)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_neutrophils",
        title="Neutrophils",
        topic=TOPIC_LAB_TEST,
        features=("neutrophils",),
        conditions=(),
        keywords=(
            "neutrophils", "polymorphs", "differential count", "cbc",
            "white cell differential", "infection",
        ),
        summary=(
            "Neutrophils are the most numerous white cell type. This value is "
            "usually printed as a percentage of the white cell total."
        ),
        body="""
Neutrophils are the most numerous type of white blood cell and are among the
first to respond to bacterial infection. Some reports print them under the older
name polymorphs, which describes the same cells.

On most reports this value is given as a percentage: the share of all white
blood cells that are neutrophils. Some laboratories also report an absolute
count, which is the number of neutrophils rather than their share.

Reading a percentage requires care, because a share can move for two different
reasons. The number of neutrophils may have changed, or the number of some other
cell type may have changed while neutrophils stayed the same. The percentage
alone does not say which happened.

A higher share is common during bacterial infection, inflammation and physical
stress. A lower share is seen with some viral infections and with conditions
affecting the bone marrow.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because it is a share of a
total and can be unusual at either end.
"""
        + "\n\n" + CONSULT,
        basis=(
            "States explicitly that the reported quantity is a PROPORTION, "
            "which is the second reason app/data/trend_polarity.py refuses a "
            "direction for the five differentials. Population distribution: "
            "NHANES 2017-2018 (LBXNEPCT, the percentage)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_lymphocytes",
        title="Lymphocytes",
        topic=TOPIC_LAB_TEST,
        features=("lymphocytes",),
        conditions=(),
        keywords=(
            "lymphocytes", "differential count", "cbc",
            "white cell differential", "immune cells",
        ),
        summary=(
            "Lymphocytes are the white cells involved in longer-term immune "
            "responses. The value is usually a percentage of the white cell "
            "total."
        ),
        body="""
Lymphocytes are the white blood cells responsible for longer-term immune
responses, including the recognition of viruses and the production of
antibodies. They are the second most numerous white cell type in most adults.

On most reports this value is given as a percentage: the share of all white
blood cells that are lymphocytes. A share can move because lymphocytes changed
or because another cell type changed, and the percentage alone does not
distinguish the two.

A higher share is common during and after viral infections. A lower share can
follow physical stress and some conditions affecting the immune system.

Because neutrophils and lymphocytes together account for most white cells, their
percentages tend to move in opposite directions. A rise in one is frequently
accompanied by a fall in the other without either cell population having changed
in number.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because it is a share of a
total and can be unusual at either end.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Records the reciprocal relationship with neutrophils, which is "
            "why a percentage change is not attributable to one cell line. "
            "Population distribution: NHANES 2017-2018 (LBXLYPCT)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_monocytes",
        title="Monocytes",
        topic=TOPIC_LAB_TEST,
        features=("monocytes",),
        conditions=(),
        keywords=(
            "monocytes", "differential count", "cbc",
            "white cell differential",
        ),
        summary=(
            "Monocytes are a less numerous white cell type. The value is "
            "usually a percentage of the white cell total."
        ),
        body="""
Monocytes are a white blood cell type that clears debris and damaged cells and
that contributes to longer-running inflammation. They make up a small share of
the white cell total in most adults.

On most reports this value is given as a percentage: the share of all white
blood cells that are monocytes. As with the other differential values, the share
can move because monocytes changed or because another cell type did.

A higher share is associated with longer-standing infection and inflammation and
with recovery from a suppressed count. A lower share is common and is frequently
of no particular significance on its own.

Because monocytes are a small share of the total, the percentage is based on
relatively few cells and varies more between samples than the larger cell types
do.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because it is a share of a
total.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Population distribution: NHANES 2017-2018 (LBXMOPCT)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_eosinophils",
        title="Eosinophils",
        topic=TOPIC_LAB_TEST,
        features=("eosinophils",),
        conditions=(),
        keywords=(
            "eosinophils", "differential count", "cbc", "allergy",
            "white cell differential",
        ),
        summary=(
            "Eosinophils are a white cell type associated with allergic "
            "responses and parasitic infection. The value is usually a "
            "percentage of the white cell total."
        ),
        body="""
Eosinophils are a white blood cell type involved in allergic responses and in
the response to parasitic infection. They are a small share of the white cell
total in most adults.

On most reports this value is given as a percentage: the share of all white
blood cells that are eosinophils. The share can move because eosinophils changed
or because another cell type did.

A higher share is commonly associated with allergic conditions including asthma,
hay fever and eczema, and with parasitic infection. Much less commonly it
reflects a condition of the bone marrow.

Eosinophil values vary with the time of year in people with seasonal allergies,
so a difference between two reports taken months apart may reflect the season
rather than a change in health.

A share at or near zero is an ordinary result and is not by itself a concern.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because it is a share of a
total and moves with ordinary seasonal factors.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Records the seasonal variation, which is one reason the "
            "stability band for this feature is wide. Population "
            "distribution: NHANES 2017-2018 (LBXEOPCT)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_basophils",
        title="Basophils",
        topic=TOPIC_LAB_TEST,
        features=("basophils",),
        conditions=(),
        keywords=(
            "basophils", "differential count", "cbc",
            "white cell differential",
        ),
        summary=(
            "Basophils are the least numerous white cell type. The numbers "
            "involved are so small that ordinary variation looks large."
        ),
        body="""
Basophils are the least numerous of the white blood cell types, making up only a
very small share of the total. They take part in allergic and inflammatory
responses.

On most reports this value is given as a percentage: the share of all white
blood cells that are basophils. Because that share is so small, laboratories
report it on a correspondingly narrow scale.

That narrow scale has a practical consequence. The difference between one report
and the next can look large as a percentage change while representing only the
smallest step the laboratory can report, which is why a modest difference is not
reported as a trend.

A share at or near zero is an ordinary result. A persistently raised share is
uncommon and is generally investigated alongside the rest of the blood count
rather than on its own.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because it is a share of a
total and the numbers involved are very small.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Records the reporting-resolution problem that the absolute floor "
            "in app/data/trend_polarity.py exists to absorb. Population "
            "distribution: NHANES 2017-2018 (LBXBAPCT)."
        ),
    ),
    KnowledgeDocument(
        doc_id="lab_platelet_count",
        title="Platelet count",
        topic=TOPIC_LAB_TEST,
        features=("platelet_count",),
        conditions=(),
        keywords=(
            "platelets", "platelet count", "thrombocytes", "plt", "cbc",
            "clotting", "bleeding",
        ),
        summary=(
            "Platelets are the blood cells involved in clotting. The count "
            "can be unusual at either end, with different consequences."
        ),
        body="""
Platelets are small cell fragments in the blood that gather at the site of an
injury and form the initial plug that stops bleeding. The platelet count reports
how many are present in a given volume of blood.

The count is issued as part of the full blood count. It is one of the values
most often looked at before a procedure, because it relates directly to how
readily bleeding stops.

A count below the usual range can follow some viral infections, liver
conditions, and conditions affecting the bone marrow or causing platelets to be
removed faster than usual. A substantially reduced count relates to a greater
tendency to bleed or bruise.

A count above the usual range frequently accompanies inflammation, infection,
iron deficiency or recovery from a recent illness, and in those situations
reflects another process rather than a platelet condition itself. Less commonly it reflects a
condition of the bone marrow.

A low result is sometimes an effect of the sample rather than the person, as
platelets can clump together in the collection tube and be counted as fewer than
they are. Laboratories check for this when a result is unexpectedly low.

This platform reports whether the value moved between reports and by how much,
but does not say whether a move is an improvement, because the count can be
unusual at either end and a fall is not automatically good news.
"""
        + "\n\n" + CONSULT,
        basis=(
            "Describes both extremes and the clumping artefact. Population "
            "distribution: NHANES 2017-2018 (LBXPLTSI)."
        ),
    ),
)

__all__ = ["LAB_TEST_DOCUMENTS"]
