"""Module 22 content -- LIFESTYLE GUIDANCE (Module 26's corpus).

Spec Module 26 is explicit that this layer is "pre-approved educational
guidance rather than unrestricted AI-generated treatment advice". These
documents ARE that pre-approved material, in retrievable form.

THE HARD LINE THIS FILE HOLDS
-----------------------------
General population guidance, never personal instruction.

    ALLOWED   "General dietary guidance describes ... "
              "Population guidance suggests ... across the week"
    REFUSED   "You should eat ... ", "take ... ", any quantity of any
              substance, any named preparation

The import-time scanner enforces the refused side mechanically, and the
documents are written in the third person throughout so that an LLM grounded on
them reproduces the register as well as the content. A grounded model copies
tone; a corpus that instructs will produce a model that instructs.

Each document pairs with a code in `app/data/recommendation_catalog.py` (the
GENERAL_* family). The catalogue emits one approved SENTENCE; this corpus
supplies the paragraphs behind it, so Module 23 can explain a recommendation
without inventing the explanation. The pairing is named in each `basis`.
"""

from __future__ import annotations

from typing import Tuple

from app.data import conditions as C
from app.data.knowledge_types import TOPIC_LIFESTYLE, KnowledgeDocument

GENERAL_ONLY = (
    "This is general population guidance for education. It is not personal "
    "advice, it takes no account of any individual's circumstances or other "
    "conditions, and it is not a diagnosis. Changes relevant to a particular "
    "person are best discussed with a qualified healthcare professional."
)

LIFESTYLE_DOCUMENTS: Tuple[KnowledgeDocument, ...] = (
    KnowledgeDocument(
        doc_id="life_balanced_eating",
        title="General guidance on balanced eating",
        topic=TOPIC_LIFESTYLE,
        features=("bmi", "cholesterol", "triglycerides", "blood_glucose", "hba1c"),
        conditions=(C.OBESITY, C.HIGH_CHOLESTEROL, C.HIGH_TRIGLYCERIDES, C.DIABETES),
        keywords=(
            "diet", "healthy eating", "balanced diet", "nutrition", "food",
            "what to eat", "eating well", "mediterranean diet", "fibre",
        ),
        summary=(
            "Population dietary guidance consistently describes eating "
            "patterns built around vegetables, fruit, whole grains, pulses, "
            "nuts and fish rather than around single foods or nutrients."
        ),
        body="""
The most consistent finding across national dietary guidance is that overall
patterns matter more than individual foods. Patterns associated with better
population outcomes are built largely on vegetables, fruit, whole grains,
pulses, nuts, seeds and fish, with smaller amounts of processed meat and of
foods high in free sugars and salt.

Dietary fibre, found in whole grains, pulses, vegetables, fruit and nuts, is one
of the few components where population guidance is unusually consistent. Higher
fibre intakes are associated with better outcomes across cardiovascular,
metabolic and digestive measures, and most populations fall well short of the
amounts guidance describes.

Eating patterns described as Mediterranean, characterised by vegetables,
pulses, whole grains, fish, nuts and olive oil, have the strongest supporting
evidence for cardiovascular outcomes among named patterns. That evidence is
about the pattern as a whole rather than about any component of it.

Guidance is about populations over long periods, and the size of the effects
described is modest at an individual level. Framing any single food as harmful
or protective overstates what the evidence supports.

Circumstances change what is appropriate. Kidney conditions, coeliac disease,
food allergies, pregnancy, eating disorders and many long-term conditions all
change what general guidance means for a person, sometimes reversing it. This is
one reason general material is not personal advice.

Cost, time, culture, access and preference are real constraints, and guidance
that ignores them is not followed. A registered dietitian or a healthcare
professional can help translate general patterns into something workable.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "WHO healthy diet guidance and national dietary guidelines; "
            "PREDIMED and related evidence for Mediterranean-pattern "
            "cardiovascular outcomes. Pairs with GENERAL_BALANCED_DIET in "
            "app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_physical_activity",
        title="General guidance on physical activity",
        topic=TOPIC_LIFESTYLE,
        features=("bmi", "blood_glucose", "hba1c", "cholesterol", "triglycerides"),
        conditions=(C.OBESITY, C.DIABETES, C.HEART_DISEASE, C.HIGH_TRIGLYCERIDES),
        keywords=(
            "exercise", "physical activity", "walking", "movement", "fitness",
            "how much exercise", "sedentary", "steps", "active",
        ),
        summary=(
            "WHO guidance for adults describes 150 to 300 minutes of moderate "
            "activity across a week, or half that at vigorous intensity, plus "
            "muscle-strengthening activity on two or more days."
        ),
        body="""
WHO guidance for adults describes accumulating 150 to 300 minutes of
moderate-intensity aerobic activity across a week, or 75 to 150 minutes at
vigorous intensity, or an equivalent combination, together with
muscle-strengthening activity on two or more days.

Moderate intensity is the level at which breathing is noticeably harder but
conversation is still possible, such as brisk walking or cycling on level
ground. Vigorous intensity makes sustained conversation difficult.

The largest relative benefit in population studies comes from moving from very
little activity to some, rather than from moderate to high. This matters
practically: guidance explicitly states that some activity is better than none
for people currently doing very little, and that the targets are something to
build toward.

Time spent sitting is associated with outcomes partly independently of
structured activity, which is why current guidance also describes breaking up
long sedentary periods rather than only meeting a weekly total.

Activity is associated with better glucose handling, blood pressure, lipid
profile, weight maintenance, bone density, sleep and mood. These are population
associations over long periods and vary considerably between individuals.

Anyone with a heart or lung condition, joint problems, a recent event, or who is
currently very inactive is advised to discuss what is appropriate with a
healthcare professional before starting something substantially new.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "WHO 2020 guidelines on physical activity and sedentary behaviour "
            "for adults aged 18-64. Pairs with GENERAL_PHYSICAL_ACTIVITY in "
            "app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_hydration",
        title="General guidance on fluid intake",
        topic=TOPIC_LIFESTYLE,
        features=("creatinine", "hemoglobin"),
        conditions=(C.KIDNEY_DISEASE, C.ELEVATED_HEMOGLOBIN),
        keywords=(
            "water", "hydration", "drinking water", "dehydration", "fluids",
            "how much water", "thirst",
        ),
        summary=(
            "Adequate fluid intake supports normal kidney function and affects "
            "several laboratory values directly, though the right amount "
            "varies with climate, activity and individual conditions."
        ),
        body="""
Water makes up most of the body and is required for the kidneys to clear waste,
for circulation and for regulating temperature. Requirements vary widely with
body size, climate, activity and what else is being consumed.

There is no single figure that applies to everyone, and the widely repeated
fixed daily volumes are not well supported. National guidance gives ranges
rather than a number, and counts fluid from all drinks and from food.

Thirst is a reasonable guide for most healthy adults under ordinary conditions.
It becomes less reliable with age, during intense or prolonged exertion, and in
hot conditions, which are the situations where more deliberate attention helps.

Hydration status changes laboratory values directly and is a common reason for
an unexpected result. Because haemoglobin is a concentration, dehydration raises
the apparent value without any change in red cells. Creatinine also rises with
reduced fluid volume, which is one reason a raised value is repeated before it is
interpreted.

Some circumstances change this guidance substantially, and in the opposite
direction. People with certain kidney or heart conditions are given specific
fluid limits by their clinicians, and general guidance to drink more does not
apply to them. That instruction from a clinician takes precedence over anything
here.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "EFSA dietary reference values for water and national fluid intake "
            "guidance, which give ranges rather than fixed volumes. Pairs with "
            "GENERAL_HYDRATION in app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_iron_rich_foods",
        title="Dietary sources of iron",
        topic=TOPIC_LIFESTYLE,
        features=("hemoglobin",),
        conditions=(C.ANEMIA,),
        keywords=(
            "iron", "iron rich foods", "iron deficiency diet", "red meat",
            "spinach", "lentils", "haem iron", "non-haem iron", "vitamin c iron",
        ),
        summary=(
            "Iron in food comes in two forms that are absorbed differently, "
            "and general guidance describes which foods contain them and what "
            "helps or hinders absorption."
        ),
        body="""
Iron is required to make haemoglobin. Dietary iron comes in two forms. Haem
iron, found in meat, poultry and fish, is absorbed relatively efficiently.
Non-haem iron, found in pulses, dark green leafy vegetables, whole grains, nuts,
seeds, dried fruit and fortified cereals, is absorbed less efficiently.

Absorption of non-haem iron is strongly affected by what is eaten alongside it.
Vitamin C in the same meal increases it considerably, which is why fruit or
vegetables alongside a pulse-based meal are commonly described in guidance.

Some components reduce absorption. Tea and coffee contain compounds that bind
non-haem iron, and calcium-rich foods compete with it, so guidance often
describes separating them in time from iron-rich meals rather than avoiding
them.

People eating no meat or fish can meet iron needs, but the lower absorption of
non-haem iron means the total intake needs to be higher, and attention to the
combinations above matters more.

Diet alone does not resolve every low haemoglobin, and this is the important
caveat. Where the cause is ongoing blood loss, an absorption problem or a
condition affecting red-cell production, dietary change addresses none of them.
Establishing the cause is a clinical task, and a low haemoglobin is a reason to
speak to a healthcare professional rather than to change diet on the assumption
that iron is the issue.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "WHO and national guidance on dietary iron, haem and non-haem "
            "absorption and the effect of ascorbate, phytate, polyphenols and "
            "calcium. Pairs with GENERAL_IRON_RICH_FOODS in "
            "app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_vitamin_d_sources",
        title="Sources of vitamin D",
        topic=TOPIC_LIFESTYLE,
        features=("vitamin_d",),
        conditions=(C.VITAMIN_D_DEFICIENCY,),
        keywords=(
            "vitamin d sources", "sunlight", "oily fish", "fortified foods",
            "sun exposure", "how to get vitamin d", "egg yolk",
        ),
        summary=(
            "Vitamin D comes mainly from skin exposure to ultraviolet light, "
            "with a small contribution from a limited range of foods, and both "
            "routes have well-described limits."
        ),
        body="""
Most vitamin D in most people is made in the skin on exposure to ultraviolet B
light from sunlight. The amount made depends on latitude, season, time of day,
cloud cover, how much skin is exposed, skin pigmentation and age.

At higher latitudes the sun is too low in the sky through the winter months for
the skin to make any vitamin D at all, regardless of how much time is spent
outdoors. This is why low status is seasonal in many populations and why winter
values are commonly lower.

Skin production is self-limiting, so prolonged exposure does not push levels
into an excessive range. It does, however, carry the well-established risks of
ultraviolet exposure to the skin, which is why guidance describes short regular
exposure rather than extended time in strong sun, and why sun protection advice
is not in conflict with vitamin D guidance.

Few foods contain much vitamin D naturally. Oily fish such as salmon, mackerel,
sardines and herring are the richest sources; egg yolks, liver and some
mushrooms contain smaller amounts. Many countries fortify foods such as milk,
plant drinks, spreads and breakfast cereals, and in those countries fortified
foods contribute a meaningful share of intake.

Several groups are recognised as less able to meet needs from these routes,
including people with limited outdoor exposure, those who cover most of their
skin, those with darker skin pigmentation at higher latitudes, older adults, and
people with conditions affecting fat absorption.

What is appropriate for someone with a measured low value is a clinical
question, and it depends on how low, why, and what else is going on. That
conversation belongs with a healthcare professional.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "Endocrine Society clinical practice guideline on vitamin D (2011) "
            "and national public health guidance on sunlight exposure and "
            "fortification. Pairs with GENERAL_VITAMIN_D_SOURCES in "
            "app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_vitamin_b12_sources",
        title="Dietary sources of vitamin B12",
        topic=TOPIC_LIFESTYLE,
        features=("vitamin_b12",),
        conditions=(C.VITAMIN_B12_DEFICIENCY,),
        keywords=(
            "b12 sources", "b12 foods", "vegan b12", "vegetarian b12",
            "fortified foods b12", "nutritional yeast", "animal foods",
        ),
        summary=(
            "Vitamin B12 occurs naturally almost only in animal-derived foods, "
            "with fortified foods being the main plant-based route, and low "
            "results are often about absorption rather than intake."
        ),
        body="""
Vitamin B12 is made by microorganisms, not by plants or animals, and it
accumulates in animal tissues. In practical terms it occurs naturally almost
exclusively in meat, fish, shellfish, eggs and dairy foods.

Plant foods contain essentially none in a form the body can use. Some, such as
certain seaweeds and unfortified yeast products, contain related compounds that
appear in analyses but do not function as B12 and can even interfere with it.

Fortified foods are the reliable plant-based route. Many plant drinks,
breakfast cereals, yeast extracts and nutritional yeast products have B12 added,
and in populations eating no animal-derived foods these are the principal
dietary source.

Body stores are large relative to daily needs and take years to run down, which
is why a change in diet may not show up in blood for a long time, and why a
recent dietary change is rarely the explanation for a low result today.

The absorption point is the one most often missed. Because uptake requires
stomach acid, a stomach protein and a healthy final section of small intestine,
a low result in someone eating plenty of animal-derived food usually points to
absorption rather than to intake, and no dietary change addresses that. This is
why a low or borderline result is a reason to speak to a healthcare
professional rather than to change diet on an assumption.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "British Committee for Standards in Haematology cobalamin and "
            "folate guideline (2014) and national guidance on B12 in "
            "plant-based diets. Pairs with GENERAL_VITAMIN_B12_SOURCES in "
            "app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_added_sugar",
        title="General guidance on free and added sugars",
        topic=TOPIC_LIFESTYLE,
        features=("hba1c", "blood_glucose", "triglycerides", "bmi"),
        conditions=(C.DIABETES, C.HIGH_TRIGLYCERIDES, C.OBESITY),
        keywords=(
            "sugar", "added sugar", "free sugars", "sugary drinks", "sweets",
            "lower sugar intake", "soft drinks", "fruit juice",
        ),
        summary=(
            "WHO guidance describes keeping free sugars below ten per cent of "
            "energy intake, with further benefit below five per cent, and "
            "identifies sugary drinks as the largest single source in many "
            "populations."
        ),
        body="""
Free sugars are those added to foods and drinks, plus the sugars naturally
present in honey, syrups and fruit juices. Sugars within the structure of whole
fruit, vegetables and milk are not counted, because they behave differently in
the body.

WHO guidance describes keeping free sugars below ten per cent of total energy
intake, and describes additional benefit from going below five per cent. The
main outcomes behind this are dental caries and body weight.

Sugary drinks are the largest single source in many populations, and they are
distinctive in providing energy without the fullness that comes with solid food.
Guidance identifies them specifically for that reason. Fruit juice counts as a
free sugar even without anything added.

Sugars in the diet are not the sole cause of the conditions they are associated
with, and describing them that way misstates the evidence. Overall energy
balance, dietary pattern, activity, sleep and genetics all contribute, and the
associations for cardiovascular and metabolic outcomes are less direct than
those for dental health and weight.

For anyone using glucose-lowering preparations, changes in carbohydrate intake
interact with those preparations and need to be discussed with the clinician
managing them, not made on general advice.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "WHO guideline on sugars intake for adults and children (2015), "
            "free sugars below 10 per cent of energy with conditional "
            "recommendation below 5 per cent. Pairs with "
            "GENERAL_LIMIT_ADDED_SUGAR in app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_dietary_fat_quality",
        title="General guidance on the type of dietary fat",
        topic=TOPIC_LIFESTYLE,
        features=("cholesterol", "triglycerides"),
        conditions=(C.HIGH_CHOLESTEROL, C.HIGH_TRIGLYCERIDES, C.HEART_DISEASE),
        keywords=(
            "fat", "saturated fat", "unsaturated fat", "trans fat", "olive oil",
            "butter", "omega 3", "cooking oil", "fat quality",
        ),
        summary=(
            "Population guidance focuses on the type of fat rather than the "
            "total, describing replacement of saturated fat with unsaturated "
            "fat and the elimination of industrially produced trans fat."
        ),
        body="""
Guidance on dietary fat has shifted over decades from total amount toward
composition. The consistent current message is about which fats replace which,
rather than about reducing fat overall.

Saturated fat, found largely in fatty meat, butter, cheese, cream and some
tropical oils such as coconut and palm, raises LDL cholesterol in controlled
feeding studies. Guidance describes keeping it below around ten per cent of
energy intake.

What replaces it determines the effect. Replacing saturated fat with
unsaturated fat, particularly polyunsaturated fat from vegetable oils, nuts,
seeds and oily fish, is associated with lower cardiovascular event rates.
Replacing it with refined carbohydrate is not.

Industrially produced trans fat, formed by partial hydrogenation of oils, has
the least favourable profile of any dietary fat and WHO has called for its
elimination from the food supply. Many countries have now restricted or banned
it, and it is far less common in food than it was.

Omega-3 fats from oily fish are associated with lower triglycerides and are
part of most cardiovascular dietary guidance, generally framed as eating fish
rather than as any other route.

These are population-level effects over long periods, and individual response
varies considerably. Anyone making substantial dietary changes alongside a
condition or preparations taken under medical supervision is best doing so with a healthcare
professional or dietitian involved.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "WHO guidelines on saturated fatty acid and trans-fatty acid intake "
            "(2023) and the WHO REPLACE initiative; NCEP ATP III dietary "
            "guidance. Pairs with GENERAL_DIETARY_FAT_QUALITY in "
            "app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_smoking_cessation_support",
        title="Support for stopping smoking",
        topic=TOPIC_LIFESTYLE,
        features=("smoking_history",),
        conditions=(C.HEART_DISEASE,),
        keywords=(
            "quitting smoking", "smoking cessation", "giving up smoking",
            "nicotine", "vaping", "quitline", "support to quit",
        ),
        summary=(
            "Stopping smoking is followed by measurable reductions in "
            "cardiovascular risk over time, and structured support "
            "substantially improves the chance of stopping compared with "
            "attempting it alone."
        ),
        body="""
Stopping smoking is followed by improvements that begin quickly and continue
over years. Cardiovascular risk falls substantially over the first years after
stopping, and for several outcomes continues to fall over a longer period,
although for some it does not return fully to the never-smoked level.

Benefit is described at every age. Stopping later in life is still associated
with meaningful gains in both life expectancy and quality of life, which is why
guidance does not describe any point as too late.

Most people who stop successfully have made several attempts first. This is the
usual pattern rather than a sign of failure, and each attempt provides
information about what helps.

Structured support markedly improves success rates compared with willpower
alone. Behavioural support, telephone quitlines, group programmes and
pharmacological options available through healthcare services all have
supporting evidence, and combinations work better than any single route.

Which of those options suits a particular person, and what is available locally,
is something a healthcare professional or a national stop-smoking service can
advise on. This platform does not name or recommend any specific product or
preparation.

Support is available and is generally free through public health services in
many countries. Asking about it is a reasonable thing to raise at any routine
appointment.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "WHO Framework Convention on Tobacco Control guidance and national "
            "smoking cessation guidelines on the effectiveness of structured "
            "support. Pairs with GENERAL_SMOKING_CESSATION_SUPPORT in "
            "app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_weight_discussion",
        title="Talking about body weight with a healthcare professional",
        topic=TOPIC_LIFESTYLE,
        features=("bmi",),
        conditions=(C.OBESITY, C.UNDERWEIGHT),
        keywords=(
            "weight loss", "losing weight", "weight gain", "managing weight",
            "dieting", "weight management", "talking about weight",
        ),
        summary=(
            "Body weight is influenced by many factors outside individual "
            "control, and general guidance describes discussing it with a "
            "healthcare professional rather than following generic targets."
        ),
        body="""
Body weight is shaped by genetics, sleep, long-term conditions, preparations
taken under medical supervision, stress, food environment, activity
opportunities and social and economic circumstances. Framing it as a straightforward matter of individual
choice does not match the evidence and is not how clinical guidance approaches
it.

Where change is appropriate, population guidance consistently describes modest,
sustained change rather than rapid loss. Improvements in glucose handling, blood
pressure and lipid measures are described at losses of around five to ten per
cent of body weight, which is considerably less than most people set as a
target.

Sustained change is harder than initial change, and most approaches show weight
returning over the following years without ongoing support. Guidance therefore
describes long-term support rather than time-limited programmes.

Weight is not a reliable proxy for health on its own. Activity level, fitness,
dietary pattern, sleep and blood measurements all carry information that weight
does not, and someone can improve several of these without the number changing.

For people whose BMI sits below the usual range, unintended weight loss is the
part that warrants attention, since it can accompany conditions affecting
appetite, absorption or energy use, and eating disorders occur across all ages
and genders.

A healthcare professional can look at the whole picture, including conditions
and preparations taken under medical supervision that affect weight, and this platform's role is to
explain what was recorded rather than to set a target.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "WHO adult BMI classification and national clinical guidance on "
            "weight management, including the 5-10 per cent threshold for "
            "metabolic improvement. Pairs with GENERAL_WEIGHT_DISCUSSION in "
            "app/data/recommendation_catalog.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_sleep",
        title="General guidance on sleep",
        topic=TOPIC_LIFESTYLE,
        features=("bmi", "blood_glucose", "hba1c"),
        conditions=(C.OBESITY, C.DIABETES, C.HEART_DISEASE),
        keywords=(
            "sleep", "insomnia", "sleep apnoea", "tired", "rest",
            "how much sleep", "sleep quality", "snoring",
        ),
        summary=(
            "Population guidance describes seven to nine hours of sleep for "
            "most adults, and both short and disrupted sleep are associated "
            "with metabolic and cardiovascular measures."
        ),
        body="""
Most adult sleep guidance describes seven to nine hours per night, with
individual needs varying within and somewhat outside that range. Consistency of
timing appears to matter alongside total duration.

Short and disrupted sleep are associated in population studies with less
favourable glucose handling, higher blood pressure, weight gain and
cardiovascular measures. The associations run in both directions, since several
conditions also disrupt sleep, so cause is difficult to separate.

Obstructive sleep apnoea, in which breathing repeatedly pauses during sleep, is
common, frequently unrecognised, and specifically associated with raised blood
pressure, cardiovascular outcomes and raised haemoglobin. Loud snoring with
pauses, and marked daytime sleepiness, are the features that most often prompt
assessment.

General guidance on sleep habits describes regular sleep and waking times, a
dark and quiet environment, limiting caffeine later in the day, and reducing
bright screen light before bed. The evidence for these is modest but they carry
little downside.

Persistent difficulty sleeping, or persistent daytime sleepiness despite
adequate opportunity, is worth raising with a healthcare professional, since
both have identifiable and addressable causes that general habit advice does not
reach.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "National sleep foundation and public health guidance on adult "
            "sleep duration; established associations between obstructive sleep "
            "apnoea, cardiovascular outcomes and secondary erythrocytosis, which "
            "supports the raised-haemoglobin document."
        ),
    ),
    KnowledgeDocument(
        doc_id="life_monitoring_and_retesting",
        title="General guidance on monitoring and repeat testing",
        topic=TOPIC_LIFESTYLE,
        features=("hba1c", "blood_glucose", "cholesterol", "creatinine", "hemoglobin"),
        conditions=(C.DIABETES, C.HIGH_CHOLESTEROL, C.KIDNEY_DISEASE, C.ANEMIA),
        keywords=(
            "repeat test", "monitoring", "how often", "follow up", "recheck",
            "retest", "tracking over time", "next test",
        ),
        summary=(
            "How often a test is repeated depends on the analyte, on what the "
            "previous result was and on why it is being followed; a trend "
            "carries more information than any single value."
        ),
        body="""
Repeat testing serves two distinct purposes that are easily confused.
Confirming an unexpected result asks whether the value was real. Monitoring over
time asks whether something is changing. The appropriate interval is different
for each.

For confirmation, the interval is usually short, because the question is about
the measurement rather than about the person. Guidelines for several conditions
specify repeating an abnormal result before acting on it.

For monitoring, the interval follows the biology. HbA1c reflects roughly three
months of average glucose, so repeating it much sooner than that adds little.
Kidney function is defined over at least three months. Lipids change slowly
unless something specific has changed.

Testing more often than the biology supports produces apparent changes that are
measurement variation rather than real movement, which generates anxiety and
sometimes unnecessary follow-up. More testing is not automatically better
information.

A trend across several results carries more information than any single value,
which is why keeping previous reports and having them measured by the same
laboratory where possible makes each new result more interpretable.

The clinician who requested a test is the right person to say when it should be
repeated, because that depends on why it was requested and what else is being
followed. This platform records values over time so that a trend can be shown,
but it does not set testing intervals.
"""
        + "\n\n" + GENERAL_ONLY,
        basis=(
            "ADA Standards of Care monitoring intervals; KDIGO three-month "
            "persistence requirement; general laboratory guidance on biological "
            "variation and retesting intervals. Pairs with MONITOR_OVER_TIME "
            "and CONFIRM_WITH_REPEAT_TESTING in "
            "app/data/recommendation_catalog.py."
        ),
    ),
)

__all__ = ["LIFESTYLE_DOCUMENTS"]
