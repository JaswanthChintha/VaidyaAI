from __future__ import annotations

from typing import Tuple

from app.data import conditions as C
from app.data.knowledge_types import TOPIC_EDUCATION, KnowledgeDocument

EDUCATIONAL = (
    "This explains what the platform recorded and why it was used. It is "
    "educational, it describes no individual, and it is not a diagnosis."
)

PROFILE_DOCUMENTS: Tuple[KnowledgeDocument, ...] = (
    KnowledgeDocument(
        doc_id="profile_age",
        title="Why age is used in health assessment",
        topic=TOPIC_EDUCATION,
        features=("age",),
        conditions=(C.HEART_DISEASE, C.KIDNEY_DISEASE, C.ANEMIA),
        keywords=(
            "age", "how old", "older adults", "age related", "years",
            "age adjusted", "paediatric", "elderly",
        ),
        summary=(
            "Age changes both what counts as an expected laboratory value and "
            "the background rate of many conditions, so it enters both "
            "reference comparisons and risk estimates."
        ),
        body="""
Age enters health assessment in two quite different ways, and conflating them
causes confusion. First, it changes what an expected value is: haemoglobin
cut-offs step up through childhood, and kidney filtration estimates are
calculated with age in the equation. Second, it changes the background rate of
outcomes, which is why every cardiovascular risk calculator weights it heavily.

Reference intervals derived from adults do not apply to children. This platform
records age partly so that a paediatric haemoglobin cut-off is applied where it
belongs rather than an adult one, and it says in the evidence when it has done
so.

In cardiovascular risk frameworks, age past a threshold is itself counted as a
recognised factor: conventionally 45 years for men and 55 for women. That is a
population convention, not a birthday at which anything changes in a body.

Age is the clearest example of a factor that cannot be altered, which is why
risk conversations focus on the factors that can be. A higher estimated risk
driven mostly by age carries a different practical meaning from the same
estimate driven by blood pressure or smoking.

Where age has not been recorded, this platform applies the adult comparison and
records that assumption rather than hiding it, because an unstated assumption in
a reference comparison is invisible to the reader.
"""
        + "\n\n" + EDUCATIONAL,
        basis=(
            "WHO VMNIS 2011 paediatric haemoglobin cut-offs; NCEP ATP III major "
            "risk factor age thresholds (45 male / 55 female), implemented as "
            "CVD_AGE_THRESHOLD in app/data/clinical_rules.py; CKD-EPI age term."
        ),
    ),
    KnowledgeDocument(
        doc_id="profile_gender",
        title="Why recorded sex or gender affects reference values",
        topic=TOPIC_EDUCATION,
        features=("gender",),
        conditions=(C.ANEMIA, C.ELEVATED_HEMOGLOBIN, C.KIDNEY_DISEASE, C.HEART_DISEASE),
        keywords=(
            "gender", "sex", "male", "female", "sex specific range",
            "different range for men and women", "why does sex matter",
        ),
        summary=(
            "Several reference cut-offs genuinely differ between men and "
            "women, so where this information is missing the platform uses the "
            "cut-off that avoids over-calling and says that it has done so."
        ),
        body="""
Haemoglobin, creatinine and several other analytes have reference limits that
differ between adult men and adult women, reflecting real average differences in
red-cell mass and muscle mass. Applying one sex's limit to the other
misclassifies people at the edges of the range.

Cardiovascular risk frameworks also use sex, both as a direct input and in the
age thresholds they apply. This is a population-level statistical input, not a
statement about any individual.

Gender identity and the biological variables these reference intervals were
derived from are not the same thing, and for some people they differ. Published
intervals were largely derived from populations recorded by sex assigned at
birth, and guidance for people whose recorded gender differs from that is still
developing. A clinician who knows the person is the right one to decide which
interval applies.

When this information has not been recorded, this platform does not guess. For
each affected cut-off it applies whichever boundary avoids over-calling a
finding, reports the intervening zone as borderline rather than resolving it,
and states in the evidence that the conservative choice was made.

That conservatism has a cost worth naming: a finding that would have been
flagged for one sex may be reported as borderline instead. Recording the
information removes the ambiguity.
"""
        + "\n\n" + EDUCATIONAL,
        basis=(
            "WHO VMNIS 2011 sex-specific haemoglobin cut-offs; adult "
            "sex-specific creatinine reference limits; NCEP ATP III. Describes "
            "the ContextualThreshold unknown-sex policy and its "
            "`unknown_note` in app/data/clinical_rules.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="profile_hypertension",
        title="Recorded high blood pressure and why a blank is not a 'no'",
        topic=TOPIC_EDUCATION,
        features=("hypertension",),
        conditions=(C.HEART_DISEASE, C.KIDNEY_DISEASE),
        keywords=(
            "hypertension", "high blood pressure", "bp", "blood pressure",
            "not recorded", "unknown", "blank answer",
        ),
        summary=(
            "A recorded history of high blood pressure is counted as a "
            "cardiovascular factor; an unanswered question is recorded as "
            "unknown and is never counted as an answer of no."
        ),
        body="""
Blood pressure is the force blood exerts against artery walls. Sustained high
pressure is one of the strongest and most consistently recognised contributors
to cardiovascular and kidney outcomes, which is why a recorded history of it is
counted wherever cardiovascular factors are tallied.

High blood pressure usually produces no symptoms at all over years, which is why
it is found by measurement rather than by how someone feels, and why a person
can carry it for a long time without knowing.

This platform records the answer as one of three states: yes, no, or not
recorded. That third state is deliberate and is carried through the entire
pipeline. A blank is not turned into a no at any point, and the value refuses to
be read as a true-or-false at all.

The distinction matters because the two possible readings of a blank point in
opposite directions. Counting an unknown as a no would quietly lower every
cardiovascular tally built on it, and the reader would have no way to see that it
had happened.

This platform does not receive an actual blood pressure measurement, only the
recorded yes-no-unknown history. Its cardiovascular view is partial for that
reason, and it describes it that way rather than implying completeness.
"""
        + "\n\n" + EDUCATIONAL,
        basis=(
            "NCEP ATP III major risk factor definitions. The tri-state "
            "behaviour is the ABSENT sentinel in app/services/feature_engineer.py, "
            "which refuses bool(), float(), int() and comparison, verified in "
            "the Modules 4-10 integration audit."
        ),
    ),
    KnowledgeDocument(
        doc_id="profile_heart_disease_history",
        title="Recorded heart condition history and what it is used for",
        topic=TOPIC_EDUCATION,
        features=("heart_disease",),
        conditions=(C.HEART_DISEASE,),
        keywords=(
            "heart disease history", "existing heart condition", "past heart attack",
            "known heart problem", "cardiac history", "not recorded",
        ),
        summary=(
            "A recorded history of an existing heart condition is used as "
            "context for cardiovascular assessment, and as with blood "
            "pressure, an unanswered question is recorded as unknown."
        ),
        body="""
An already-established heart condition changes the nature of the question being
asked. Risk calculators estimate the chance of a first event in people who have
not had one; in someone with an established condition, the relevant question is
about what happens next, which is a different assessment entirely.

This platform records the answer as yes, no, or not recorded, and uses it as
context for its cardiovascular assessment. As with blood pressure, an unanswered
question is never converted into an answer of no.

The recorded history is a self-reported field, not a clinical record. It
captures what the person entered, which may be incomplete or may use different
terms from a clinician's. It is used as context rather than as an established
fact about the person.

This platform assesses a cardiovascular risk-factor context rather than the
presence or absence of a heart condition. Where a machine-learning model also
produces a likelihood for the same topic, the two are fused and both are shown
with their sources, rather than one being presented as the answer.

Anyone with a known heart condition has a clinician already involved, and that
relationship is the right place for questions this platform raises rather than a
substitute for it.
"""
        + "\n\n" + EDUCATIONAL,
        basis=(
            "NCEP ATP III risk factor framework and the general distinction "
            "between primary and secondary prevention. Records the tri-state "
            "handling of `heart_disease` in app/data/feature_catalog.py and the "
            "condition-vs-topic rule in app/data/conditions.py."
        ),
    ),
    KnowledgeDocument(
        doc_id="profile_smoking_history",
        title="Recorded smoking history and its categories",
        topic=TOPIC_EDUCATION,
        features=("smoking_history",),
        conditions=(C.HEART_DISEASE, C.DIABETES, C.ELEVATED_HEMOGLOBIN),
        keywords=(
            "smoking", "smoker", "former smoker", "never smoked", "tobacco",
            "quit smoking", "ex smoker", "cigarettes",
        ),
        summary=(
            "Smoking status is recorded in fixed categories and is counted as "
            "a cardiovascular factor; the categories distinguish never, "
            "former and current because the associated risk differs between "
            "them."
        ),
        body="""
Smoking is one of the most consistently established contributors to
cardiovascular outcomes, and it also raises the rate of many respiratory and
other conditions. It is counted wherever this platform tallies cardiovascular
factors.

The categories recorded are fixed rather than free text: never, former, current,
ever, not current, and no information. Fixed categories exist so that the same
answer means the same thing every time it is counted, which free text cannot
ensure.

The distinction between former and current matters because the associated risk
falls after stopping, substantially over the first years and continuing over a
longer period, though for some outcomes it does not return fully to the
never-smoked level. A former category is therefore not equivalent to current,
and neither is equivalent to never.

Smoking also affects some laboratory values directly rather than only through
long-term risk. It is one recognised reason for a haemoglobin above the usual
range, because reduced oxygen availability drives increased red-cell production.

A category of no information means the question was not answered. As with the
other profile fields, it is recorded as unknown rather than being counted as
never. Support for stopping is available through healthcare services, and a
healthcare professional is the right person to discuss it with.
"""
        + "\n\n" + EDUCATIONAL,
        basis=(
            "NCEP ATP III major risk factor definitions; the category list is "
            "the one in app/data/feature_catalog.py, which matches the Kaggle "
            "diabetes dataset categories Module 10 was trained on."
        ),
    ),
    KnowledgeDocument(
        doc_id="profile_bmi_derived",
        title="How body mass index is derived here, and what that implies",
        topic=TOPIC_EDUCATION,
        features=("bmi",),
        conditions=(C.OBESITY, C.UNDERWEIGHT),
        keywords=(
            "bmi calculated", "derived value", "height and weight",
            "self reported weight", "how bmi is worked out",
        ),
        summary=(
            "The BMI used here is calculated from the height and weight in a "
            "patient profile rather than measured, and it is marked as a "
            "derived value so that its lower reliability travels with it."
        ),
        body="""
BMI is not a laboratory measurement. This platform calculates it from the height
and weight recorded in a patient profile, dividing weight in kilograms by height
in metres squared.

Because those inputs are usually self-reported, the result inherits their
accuracy. Self-reported height tends to be slightly over-stated and weight
slightly under-stated in population studies, which pushes a calculated BMI
slightly low. The effect is small for most people but is real.

This platform marks the value as derived rather than measured, and that marking
travels with it through validation and into any finding that rests on it. A
finding built on a derived value is reported with lower confidence than one built
on a directly measured one, and the evidence says which it was.

Height and weight recorded at different times can also produce a BMI that
describes neither moment accurately. Where a profile has not been updated, a
calculated BMI is a statement about the recorded figures rather than about the
person today.

The limitations of BMI as a measure are separate from these and are described in
its own documents: it says nothing about body composition or where weight sits.
Both sets of limitations apply at once.
"""
        + "\n\n" + EDUCATIONAL,
        basis=(
            "WHO adult BMI classification for the bands; the derived-value "
            "marking and its confidence effect are the DERIVED_VALUE flag "
            "raised in app/services/feature_engineer.py and carried by "
            "app/services/validator.py."
        ),
    ),
)

__all__ = ["PROFILE_DOCUMENTS"]
