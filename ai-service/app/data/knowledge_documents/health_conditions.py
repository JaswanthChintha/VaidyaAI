"""Module 22 content -- HEALTH CONDITIONS.

Exactly one document per entry in `app/data/conditions.py::CONDITIONS`. The
import-time check in `knowledge_base.py` fails if any condition is left
uncovered, so this file and that vocabulary move together.

A CONDITION NAME HERE IS A TOPIC, NOT A FINDING -- the same rule
`conditions.py` states for the vocabulary itself. "Diabetes" names what was
assessed. Whether anything was found lives in the decision's status, never in
the corpus. Every document is therefore written to be equally true whether the
reader's own result was flagged or not, which is what makes it safe to retrieve
for any patient with that condition in scope.
"""

from __future__ import annotations

from typing import Tuple

from app.data import conditions as C
from app.data.knowledge_types import TOPIC_CONDITION, KnowledgeDocument

NOT_A_FINDING = (
    "This document explains a topic that was assessed. It does not state what "
    "was found for any particular person, and it is not a diagnosis. What a "
    "result means for an individual is a question for a qualified healthcare "
    "professional."
)

CONDITION_DOCUMENTS: Tuple[KnowledgeDocument, ...] = (
    KnowledgeDocument(
        doc_id="cond_diabetes",
        title="Diabetes: what the term describes",
        topic=TOPIC_CONDITION,
        features=("hba1c", "blood_glucose", "bmi", "age", "smoking_history"),
        conditions=(C.DIABETES,),
        keywords=(
            "diabetes", "type 2 diabetes", "type 1 diabetes", "prediabetes",
            "sugar disease", "high blood sugar", "insulin resistance",
            "glycaemic control", "diabetes mellitus",
        ),
        safety_exemptions=(
            (
                "medication_name",
                "The word 'insulin' is unavoidable here: it is the hormone the "
                "body makes, and diabetes is DEFINED by its shortage or by poor "
                "response to it. Explaining the condition without naming it "
                "would be vague to the point of uselessness, and Module 25 "
                "exists precisely to explain such words. The noun is used only "
                "in its physiological sense; the document names no product and "
                "gives no instruction, which `scan_administration` enforces.",
            ),
        ),
        summary=(
            "Diabetes is the term for a group of conditions in which blood "
            "glucose stays higher than the usual range, because the body makes "
            "too little of the hormone insulin, responds poorly to it, or both."
        ),
        body="""
The hormone insulin lets glucose move out of the blood and into cells. When too
little of it is available, or when cells respond poorly to it, glucose stays in
the blood at higher concentrations than usual. That sustained elevation is what
the word diabetes describes.

The main forms are distinguished by why that hormone is short. In type 1 the
body's own immune system damages the cells that make it, usually beginning
earlier in life and developing quickly. In type 2, which is far more common,
cells respond poorly to it and the supply eventually falls behind demand,
usually developing gradually over years. Diabetes that appears during pregnancy
is a third, distinct situation.

Because type 2 develops slowly, it is often present before it is noticed. When
symptoms do appear they can include increased thirst, passing urine more often,
tiredness, blurred vision, and slow healing. Their absence does not establish
that glucose is in the usual range, which is why laboratory measurement is used
rather than symptoms alone.

Sustained high glucose over years is associated with changes in small blood
vessels, affecting the eyes, kidneys and nerves, and with a higher rate of
cardiovascular events. These are associations across populations over long
periods, not predictions about an individual.

Between the usual range and the diabetes range there is an intermediate band
often called prediabetes. This platform reports it as a borderline finding on
the diabetes topic rather than as a separate condition, because it is the same
question being asked, answered in the middle of the scale.

Guidelines do not rest this on one measurement. An abnormal HbA1c or glucose is
repeated, or paired with a second different test, before it is acted on,
because sample handling, illness and red-cell factors can each move a single
result.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "American Diabetes Association, Standards of Care in Diabetes, "
            "section 2 (classification and testing) and WHO classification of "
            "diabetes. Condition name matches conditions.DIABETES."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_hypoglycemia",
        title="Low blood glucose: what the term describes",
        topic=TOPIC_CONDITION,
        features=("blood_glucose",),
        conditions=(C.HYPOGLYCEMIA,),
        keywords=(
            "hypoglycaemia", "hypoglycemia", "low blood sugar", "low sugar",
            "sugar crash", "shaky hungry sweaty", "hypo",
        ),
        summary=(
            "Hypoglycaemia is the term for blood glucose below the level at "
            "which guidelines advise attention, conventionally 70 mg/dL, with "
            "a lower level at 54 mg/dL described as clinically significant."
        ),
        body="""
Glucose is the brain's main fuel and the brain cannot store it, so the body
defends the circulating level closely. When it falls below the usual range the
term used is hypoglycaemia.

Guidelines describe two levels. Below 70 mg/dL is an alert value, the point at
which attention is warranted. Below 54 mg/dL is described as clinically
significant, because at that level the body's own warning responses become
unreliable.

Early effects come from the body's attempt to correct the fall and can include
shakiness, sweating, a fast heartbeat, hunger and anxiety. If the level falls
further, effects on the brain itself can include difficulty concentrating,
confusion, altered behaviour and drowsiness.

What a low reading means depends heavily on the context. In someone using
glucose-lowering preparations it is a recognised and expected situation with a
well-established response. In someone who is not, a genuinely low value is
uncommon and is investigated rather than assumed.

Not every low reading is a low person. Delays between drawing a sample and
separating it allow blood cells to consume glucose in the tube, which lowers the
measured value without anything having been low in the body. This is a common
explanation for an isolated low result in someone with no symptoms.

Repeated or symptomatic low readings are a reason to contact a healthcare
professional rather than to interpret at home, because the useful next step
depends entirely on the cause.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "ADA/EASD hypoglycaemia classification (level 1 glucose alert value "
            "< 70 mg/dL, level 2 clinically significant < 54 mg/dL). Condition "
            "name matches conditions.HYPOGLYCEMIA."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_anemia",
        title="Anaemia: what the term describes",
        topic=TOPIC_CONDITION,
        features=("hemoglobin", "vitamin_b12", "gender", "age"),
        conditions=(C.ANEMIA,),
        keywords=(
            "anaemia", "anemia", "low haemoglobin", "low hemoglobin",
            "iron deficiency", "low blood", "pale tired", "low hb",
        ),
        summary=(
            "Anaemia is the term for a haemoglobin concentration below the "
            "cut-off for a person's age and sex; it is a finding with many "
            "possible causes rather than a condition in itself."
        ),
        body="""
Anaemia means the blood carries less haemoglobin, and therefore less oxygen,
than expected for a person's age and sex. It is defined by a measurement, not by
a cause, which is why establishing that anaemia is present is the beginning of
an assessment rather than the end of one.

Common routes to it include reduced iron availability, low vitamin B12 or
folate, ongoing blood loss from any site, long-standing inflammation or kidney
conditions, and inherited differences in haemoglobin such as thalassaemia
traits. Several can be present at once.

The size of the red blood cells is one of the first things used to narrow this
down, and it is reported on the same full blood count. Smaller-than-usual cells
point in a different direction from larger-than-usual cells, which is why the
haemoglobin number is read alongside the rest of the count rather than alone.

Effects, when present, tend to reflect reduced oxygen delivery and can include
tiredness, breathlessness on exertion, pallor, dizziness and headache. They
depend far more on how quickly the level fell than on the number itself: a
slowly developing anaemia is often well tolerated at a level that would cause
marked symptoms if it appeared over days.

Because the cut-offs differ by sex and age, the same haemoglobin can be inside
the reference range for one person and below it for another. Where sex is not
recorded, this platform uses the cut-off that avoids over-calling and says so in
the evidence rather than guessing.

The useful next step is decided by the cause, so a low haemoglobin is a reason
to speak to a healthcare professional who can look for it.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "WHO VMNIS 2011 anaemia definition and cut-offs at sea level. "
            "Condition name matches conditions.ANEMIA."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_elevated_hemoglobin",
        title="Raised haemoglobin: what the term describes",
        topic=TOPIC_CONDITION,
        features=("hemoglobin", "smoking_history"),
        conditions=(C.ELEVATED_HEMOGLOBIN,),
        keywords=(
            "high haemoglobin", "high hemoglobin", "polycythaemia",
            "polycythemia", "thick blood", "raised hb", "erythrocytosis",
        ),
        summary=(
            "A haemoglobin above the usual range can reflect a genuine "
            "increase in red cells or simply a reduced plasma volume, and the "
            "two have quite different explanations."
        ),
        body="""
Haemoglobin is reported as a concentration, so it rises either when there are
genuinely more red blood cells or when there is less plasma for the same number
of cells to sit in. Distinguishing those two is the first question a raised
value raises.

Reduced plasma volume is the commoner and more mundane explanation.
Dehydration, and sometimes prolonged use of fluid-removing preparations, can
raise the apparent concentration without any change in red-cell production. A
repeat sample taken when well hydrated often settles the question.

A genuine increase in red cells is usually the body responding to lower oxygen
availability. Living at altitude, smoking, chronic lung conditions and
sleep-disordered breathing all drive it. Less commonly, the bone marrow produces
too many red cells on its own account, which is a specific haematological
condition assessed with further tests.

The conventional boundaries are around 16.5 g/dL for men and 16.0 g/dL for
women, with markedly raised values above 20.0 g/dL. As with the anaemia
cut-offs, where sex is unknown this platform applies the boundary that avoids
over-calling and reports the intervening zone as borderline.

A raised haemoglobin is generally investigated rather than acted on directly,
because what matters is which of these situations produced it. That
investigation belongs with a healthcare professional.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "WHO 2016 haematology classification criterion for raised "
            "haemoglobin. Condition name matches "
            "conditions.ELEVATED_HEMOGLOBIN."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_vitamin_d_deficiency",
        title="Low vitamin D status: what the term describes",
        topic=TOPIC_CONDITION,
        features=("vitamin_d",),
        conditions=(C.VITAMIN_D_DEFICIENCY,),
        keywords=(
            "vitamin d deficiency", "low vitamin d", "insufficiency",
            "bone pain", "rickets", "osteomalacia", "vit d low",
        ),
        summary=(
            "Low vitamin D status means the circulating store measured as "
            "25-hydroxyvitamin D sits below the band a guideline describes as "
            "sufficient; it is common and often has ordinary explanations."
        ),
        body="""
Vitamin D status is described by the amount of 25-hydroxyvitamin D circulating
in blood. When it sits below the band a guideline describes as sufficient, the
terms used are insufficiency and, lower still, deficiency.

Low status is common in many populations and usually has straightforward
explanations. Skin makes vitamin D only when exposed to sufficient ultraviolet
light, so latitude, season, time spent indoors, routine sun protection,
clothing coverage and skin pigmentation all matter. Very few foods contain much
of it naturally.

Other routes exist. Conditions that reduce fat absorption limit uptake from
food, since vitamin D is fat-soluble. Some long-term conditions and older age
also lower it. Body composition matters too, as vitamin D distributes into fat
tissue.

Sustained low status reduces calcium absorption and, over long periods, is
associated with softer bone mineralisation, which in children is called rickets
and in adults osteomalacia. Most people with a low measured value have no bone
symptoms at all.

Whether a particular low value warrants any action, and what that action would
be, depends on how low it is, why, and on the rest of the picture including
calcium and bone health. Those are clinical questions, and this platform's role
is to explain what was measured rather than to recommend a response.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "Endocrine Society clinical practice guideline on vitamin D (2011). "
            "Condition name matches conditions.VITAMIN_D_DEFICIENCY."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_elevated_vitamin_d",
        title="Raised vitamin D: what the term describes",
        topic=TOPIC_CONDITION,
        features=("vitamin_d",),
        conditions=(C.ELEVATED_VITAMIN_D,),
        keywords=("high vitamin d", "vitamin d toxicity", "hypercalcaemia", "excess vitamin d"),
        summary=(
            "A 25-hydroxyvitamin D value well above the usual range is "
            "uncommon and almost always reflects a high intake over time "
            "rather than sun exposure."
        ),
        body="""
Skin production of vitamin D is self-limiting: prolonged sun exposure does not
push the circulating level into the range described as excessive. A markedly
raised value therefore points to intake taken in over an extended period.

The conventional boundary above which specialist review is advised is around
100 ng/mL. Values above it are described as potential toxicity, a term about
the measurement rather than a statement that harm has occurred.

The concern with a genuinely high vitamin D level is calcium. Vitamin D
increases calcium absorption from the gut, so a sustained excess can raise blood
calcium, which can produce nausea, increased thirst and urination, confusion,
and effects on the kidneys.

A raised value is checked against the units on the report before anything else,
because a result in nanomoles per litre read as though it were nanograms per
millilitre looks about two and a half times higher than it is. Unit confusion is
a more frequent explanation for an alarming vitamin D number than genuine
excess.

A value in this range is a reason to speak to a healthcare professional
promptly, who can check calcium and review what has been taken in.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "Endocrine Society clinical practice guideline on vitamin D (2011), "
            "conventional potential-toxicity boundary above 100 ng/mL. "
            "Condition name matches conditions.ELEVATED_VITAMIN_D."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_vitamin_b12_deficiency",
        title="Low vitamin B12 status: what the term describes",
        topic=TOPIC_CONDITION,
        features=("vitamin_b12", "hemoglobin"),
        conditions=(C.VITAMIN_B12_DEFICIENCY,),
        keywords=(
            "b12 deficiency", "low b12", "pernicious anaemia",
            "macrocytic anaemia", "tingling hands feet", "numbness",
            "vegan diet b12",
        ),
        summary=(
            "Low vitamin B12 status can arise from limited intake or from any "
            "of several absorption problems, and can affect blood cell "
            "formation, the nervous system, or both."
        ),
        body="""
Vitamin B12 comes entirely from the diet, principally from animal-derived
foods, and reaching the bloodstream requires several steps in the stomach and
small intestine. A shortfall can therefore come from intake, from absorption, or
from both.

Intake is the explanation in people eating little or no animal-derived food over
a long period, since body stores take years to run down. Absorption is the
explanation more often in older adults and after operations or conditions
affecting the stomach or the last part of the small intestine. An autoimmune
process that removes the stomach protein needed to bind B12 produces the
situation historically called pernicious anaemia.

The effects fall into two groups that do not always appear together. In blood,
red cells are produced larger than usual and haemoglobin can fall. In the
nervous system, the insulating sheath around nerves is affected, which can
produce tingling, numbness, unsteadiness and, over longer periods, effects on
memory and mood.

The order matters for interpretation: nerve effects can appear while the blood
count still looks entirely ordinary. A normal haemoglobin therefore does not
settle the question.

Serum B12 in the indeterminate band between the low and adequate boundaries is
common and does not resolve the question on its own. Methylmalonic acid and
homocysteine, which rise when cells are genuinely short of B12, are the usual
way of clarifying it.

Because the useful next step depends entirely on whether intake or absorption is
the issue, a low or borderline result is a reason to speak to a healthcare
professional.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "British Committee for Standards in Haematology cobalamin and "
            "folate guideline (2014). Condition name matches "
            "conditions.VITAMIN_B12_DEFICIENCY."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_high_cholesterol",
        title="Raised cholesterol: what the term describes",
        topic=TOPIC_CONDITION,
        features=("cholesterol", "bmi", "age", "smoking_history", "hypertension"),
        conditions=(C.HIGH_CHOLESTEROL,),
        keywords=(
            "high cholesterol", "hyperlipidaemia", "dyslipidaemia",
            "raised lipids", "familial hypercholesterolaemia", "blocked arteries",
            "atherosclerosis",
        ),
        summary=(
            "Raised cholesterol describes a blood level above a published "
            "band; its significance depends on which cholesterol-carrying "
            "particles are raised and on the rest of a person's risk picture."
        ),
        body="""
Cholesterol itself is essential. The question a raised value raises is not
whether cholesterol is present but how much is being carried in the particles
associated with fatty deposits building up inside artery walls, a process called
atherosclerosis.

LDL particles are the ones that association is strongest for. HDL particles
carry cholesterol in the opposite direction and higher HDL is associated with
lower risk. Total cholesterol adds all of them together, which is why it is a
screen rather than an answer.

Atherosclerosis develops silently over decades, and narrowing of arteries
becomes clinically apparent only late in that process. This is why raised
cholesterol is looked for by measurement rather than waiting for symptoms.

Levels reflect a mixture of inherited and everyday factors. Some people carry
gene variants that raise LDL substantially from birth, a situation called
familial hypercholesterolaemia, which is much commoner than generally assumed
and tends to run visibly through a family. Diet composition, body weight,
physical activity, thyroid activity, kidney and liver conditions and some
preparations taken under medical supervision all move the numbers too.

A cholesterol value on its own does not give a risk. Clinicians combine it with
age, sex, blood pressure, smoking status, diabetes status and family history in
a risk estimate, and decisions follow from that combination rather than from any
single number.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "NCEP ATP III classification and current cardiovascular risk "
            "assessment practice. Condition name matches "
            "conditions.HIGH_CHOLESTEROL."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_high_triglycerides",
        title="Raised triglycerides: what the term describes",
        topic=TOPIC_CONDITION,
        features=("triglycerides", "bmi", "blood_glucose"),
        conditions=(C.HIGH_TRIGLYCERIDES,),
        keywords=(
            "high triglycerides", "hypertriglyceridaemia", "raised tg",
            "metabolic syndrome", "pancreatitis risk", "fatty blood",
        ),
        summary=(
            "Raised triglycerides describe a blood fat level above the "
            "published band; moderate elevations sit within a wider metabolic "
            "picture, while very high levels raise a separate concern about "
            "the pancreas."
        ),
        body="""
Triglycerides rise and fall with recent food and alcohol far more than
cholesterol does, so the first question about a raised value is whether the
sample was fasting. A raised non-fasting result is commonly repeated fasting
before it is interpreted.

Moderately raised triglycerides rarely appear alone. They cluster with central
weight, raised blood glucose, raised blood pressure and lower HDL cholesterol, a
grouping often called metabolic syndrome, and it is the cluster rather than the
single number that carries the cardiovascular association.

Several identifiable situations raise triglycerides substantially, including
poorly controlled glucose, reduced thyroid activity, some kidney conditions,
pregnancy, significant alcohol intake and certain preparations taken under medical supervision.
Looking for these is part of assessing a raised value.

At very high levels the concern changes character. Above the very-high band,
and particularly above 1000 mg/dL, guidelines describe a risk of inflammation of
the pancreas, which is an acute situation. A value in that range warrants prompt
professional advice rather than watchful waiting.

Some people carry inherited differences in how triglycerides are cleared from
the blood, which can produce very high levels without any of the usual
explanations. Family history is part of the picture a clinician will consider.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "NCEP ATP III triglyceride classification; American Heart "
            "Association guidance on very high triglycerides and pancreatic "
            "risk. Condition name matches conditions.HIGH_TRIGLYCERIDES."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_kidney_disease",
        title="Kidney conditions: what the term describes",
        topic=TOPIC_CONDITION,
        features=("creatinine", "age", "hypertension"),
        conditions=(C.KIDNEY_DISEASE,),
        keywords=(
            "kidney disease", "chronic kidney disease", "ckd", "renal failure",
            "kidney function", "egfr", "kidney failure", "nephropathy",
        ),
        summary=(
            "Chronic kidney conditions are defined by reduced filtration or "
            "signs of kidney damage persisting for at least three months, and "
            "are staged using eGFR and urine albumin rather than creatinine "
            "alone."
        ),
        body="""
The kidneys filter blood continuously, removing waste and surplus water while
retaining what the body needs, and they also help regulate blood pressure, red
blood cell production and bone minerals. A chronic kidney condition is one in
which that work is reduced, or in which there are signs of damage, persisting
for at least three months.

The formal definition and staging use estimated glomerular filtration rate,
which describes how much blood the kidneys clear per minute, together with the
amount of albumin appearing in the urine. Both are needed: filtration can be
preserved while albumin is raised, and that combination carries its own
significance.

Serum creatinine is the input from which eGFR is usually calculated, but it is
not itself a stage. Filtration can fall considerably before creatinine leaves
the reference interval, particularly in people with less muscle, so a creatinine
inside the interval does not establish normal function.

Early reductions in kidney function usually produce no symptoms at all, which is
why the condition is looked for by measurement in people with risk factors
rather than waited for. Raised blood pressure and diabetes are the two commonest
routes to it worldwide.

When symptoms do appear later they are non-specific and easily attributed to
other things: tiredness, poor appetite, swelling of the ankles, changes in how
often urine is passed, and disturbed sleep.

A single raised creatinine is not a chronic condition. Dehydration, a large meat
meal, intense exercise and some preparations taken under medical supervision all raise it
temporarily, which is why persistence over at least three months is part of the
definition and why repeat measurement is the usual next step.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "KDIGO 2012/2024 clinical practice guideline for the evaluation and "
            "management of chronic kidney disease (definition, three-month "
            "persistence, eGFR and albuminuria staging). Condition name matches "
            "conditions.KIDNEY_DISEASE. Note the scope limit recorded in "
            "RULE_KIDNEY_CREATININE: this platform sees creatinine only."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_heart_disease",
        title="Cardiovascular risk: what the term describes",
        topic=TOPIC_CONDITION,
        features=(
            "cholesterol", "triglycerides", "bmi", "age", "hypertension",
            "heart_disease", "smoking_history", "gender",
        ),
        conditions=(C.HEART_DISEASE,),
        keywords=(
            "heart disease", "cardiovascular", "cvd", "heart attack",
            "coronary artery disease", "risk factors", "stroke risk",
            "atherosclerosis", "cardiac risk",
        ),
        summary=(
            "Cardiovascular risk describes how likely heart and blood vessel "
            "events are over a period, estimated from a combination of factors "
            "rather than from any single measurement."
        ),
        body="""
Cardiovascular conditions are those affecting the heart and blood vessels, most
often through atherosclerosis, in which fatty material accumulates inside artery
walls over decades and gradually narrows them. The process is silent for most of
its course.

Risk is estimated rather than measured. Established calculators combine age,
sex, blood pressure, cholesterol components, smoking status, diabetes status and
sometimes family history and ethnicity, and produce an estimated probability of
an event over a defined period, commonly ten years.

Because it is a combination, no single input decides it. A person with one
raised value and nothing else can carry lower estimated risk than a person whose
individual values all sit just inside their bands. This is why a risk-factor
count and a risk estimate are different things.

Some factors can change and some cannot. Age, sex and family history are fixed
inputs. Blood pressure, lipid levels, glucose, weight, physical activity and
smoking are the ones interventions address, which is why they receive the
attention.

This platform assesses a risk-factor context rather than the presence of
cardiovascular disease. It counts recognised factors that are visible in the
data it has been given. It does not have blood pressure, which is one of the
strongest inputs to every published calculator, so its view is deliberately
partial and is described that way.

An estimate is not a forecast for an individual. It describes what happens on
average to people sharing a profile, and the useful conversation about it is
with a healthcare professional who has the rest of the picture.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "NCEP ATP III major risk factor definitions (including the age "
            "threshold of 45 years for men and 55 for women) and general "
            "cardiovascular risk-estimation practice. Condition name matches "
            "conditions.HEART_DISEASE. The partial-view paragraph records the "
            "documented absence of blood pressure from feature_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_obesity",
        title="Obesity: what the term describes",
        topic=TOPIC_CONDITION,
        features=("bmi",),
        conditions=(C.OBESITY,),
        keywords=(
            "obesity", "overweight", "high bmi", "excess weight",
            "body mass index high", "central obesity", "waist circumference",
        ),
        summary=(
            "Obesity is defined by WHO for adults as a body mass index of 30.0 "
            "kg/m2 or above, a population classification based on a ratio of "
            "weight to height."
        ),
        body="""
Body mass index is weight in kilograms divided by height in metres squared. WHO
classifies adults with a BMI of 30.0 kg/m2 or above as obesity and from 25.0 to
29.9 as overweight. These are population classifications derived from
statistical associations with health outcomes.

Higher BMI is associated at population level with higher rates of type 2
diabetes, raised blood pressure, several lipid abnormalities, obstructive sleep
apnoea, joint problems and some cancers. Associations describe groups; they do
not determine what happens to any individual.

BMI has real limitations as an individual measure because it says nothing about
what the weight is made of or where it sits. Substantial muscle raises it
without the associated risks. Fat carried centrally around the abdomen carries
stronger associations than fat carried elsewhere at the same BMI, which is why
waist measurement is often used alongside it.

The cut-offs also perform differently across populations. Several health bodies
apply lower boundaries for people of South Asian, Chinese and other Asian
descent, because the associated metabolic changes appear at lower BMI values in
those groups.

Body weight is influenced by genetics, sleep, long-term conditions, preparations
taken under medical supervision, food environment, activity and social
circumstances. Framing it as
a simple matter of individual choice does not match the evidence, and a
conversation with a healthcare professional is more useful than a number.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "WHO adult BMI classification and the WHO 2004 expert consultation "
            "on Asian BMI cut-off points. Condition name matches "
            "conditions.OBESITY."
        ),
    ),
    KnowledgeDocument(
        doc_id="cond_underweight",
        title="Low body mass index: what the term describes",
        topic=TOPIC_CONDITION,
        features=("bmi",),
        conditions=(C.UNDERWEIGHT,),
        keywords=(
            "underweight", "low bmi", "thinness", "unintentional weight loss",
            "malnutrition", "too thin",
        ),
        summary=(
            "WHO describes an adult body mass index below 18.5 kg/m2 as "
            "thinness, graded mild, moderate and severe, and it can reflect "
            "build, intake, or an underlying condition."
        ),
        body="""
WHO describes an adult BMI below 18.5 kg/m2 as thinness, with mild from 17.0,
moderate from 16.0 and severe below 16.0 kg/m2. As with the higher bands, these
are population classifications rather than statements about an individual.

A low BMI can simply reflect a person's natural build, and a lifelong stable low
BMI in someone who is well has a very different significance from the same
number reached recently.

Weight loss that was not intended is the part that matters most. It can
accompany conditions affecting appetite, absorption or the body's use of energy,
including thyroid overactivity, coeliac and other gut conditions, long-term
infections, and some cancers. Eating disorders are also an important and
treatable route to it, and they occur across all ages and genders.

Sustained very low weight is associated with reduced bone density, weakened
immune response, disrupted menstrual cycles and difficulty maintaining muscle.
These associations relate to sustained states rather than to any single
measurement.

Because build and change over time are what distinguish these situations, and a
BMI figure captures neither, a low value in this range is a reason for a
conversation with a healthcare professional rather than an interpretation from a
table.
"""
        + "\n\n" + NOT_A_FINDING,
        basis=(
            "WHO adult BMI classification, thinness grades. Condition name "
            "matches conditions.UNDERWEIGHT."
        ),
    ),
)

__all__ = ["CONDITION_DOCUMENTS"]
