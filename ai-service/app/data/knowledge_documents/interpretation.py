"""Module 22 content -- GENERAL INTERPRETATION.

How to read a result at all: what a single number can and cannot support, what
borderline means, why values move, what a refused or missing value means, and
what this platform is and is not.

WHY THIS TOPIC EXISTS SEPARATELY
--------------------------------
These are the documents that should be retrievable for EVERY patient,
regardless of finding, because they are about the act of interpretation rather
than about any analyte. They are deliberately tagged with many features and
conditions (and some with none at all) so that a query built from any finding
can reach them.

They also carry most of the platform's honesty about its own limits -- the
partial view, the refused values, the absence of blood pressure, the fact that
absence of a finding is not a finding of health. Spec section 14 puts safety
before the LLM as well as after it, and grounding the model on its own limits is
part of that.
"""

from __future__ import annotations

from typing import Tuple

from app.data import conditions as C
from app.data.knowledge_types import TOPIC_INTERPRETATION, KnowledgeDocument

INTERPRETATION_DOCUMENTS: Tuple[KnowledgeDocument, ...] = (
    KnowledgeDocument(
        doc_id="interp_single_result",
        title="What a single laboratory result can and cannot support",
        topic=TOPIC_INTERPRETATION,
        features=("hba1c", "blood_glucose", "creatinine", "cholesterol", "hemoglobin"),
        conditions=(C.DIABETES, C.KIDNEY_DISEASE, C.HIGH_CHOLESTEROL, C.ANEMIA),
        keywords=(
            "one test result", "single result", "repeat test", "retest",
            "is one test enough", "abnormal result", "what does my result mean",
        ),
        summary=(
            "A single measurement is one observation of a fluctuating quantity "
            "made with an imperfect instrument, which is why guidelines "
            "generally require repetition before a result is acted on."
        ),
        body="""
Every laboratory result carries two kinds of variation. Analytical variation
comes from the measurement itself and is usually small and well characterised.
Biological variation comes from the person, and for many analytes it is
considerably larger than the analytical component.

Together these mean that two samples from the same person on the same day can
differ, and samples on different days can differ more. A change between two
reports is only meaningful once it exceeds what that variation alone would
produce.

This is why guidelines for several conditions explicitly require repetition. An
abnormal HbA1c or glucose is repeated, or paired with a second different test,
before the band is acted on. Kidney conditions require the finding to persist for
at least three months by definition.

Pre-analytical factors sit before the measurement and are a frequent
explanation for a surprising result: how long the person fasted, time of day,
posture, recent exercise, how long the sample waited before processing, and how
it was transported. None of these involve anything having changed in the person's
health.

A result should also be read against that person's own previous results where
they exist. A value that has been stable for years carries different information
from the same value reached from somewhere else, and a trend is usually more
informative than any single point.

The practical consequence is that a single out-of-range value is a reason to
look further, not a conclusion. What looking further means depends on the
analyte and the person, which is a question for a qualified healthcare
professional. This material is educational and is not a diagnosis.
""",
        basis=(
            "Standard clinical laboratory practice on analytical and biological "
            "variation and pre-analytical factors; ADA Standards of Care "
            "requirement for repeat or paired testing; KDIGO three-month "
            "persistence requirement."
        ),
    ),
    KnowledgeDocument(
        doc_id="interp_borderline",
        title="What a borderline result means",
        topic=TOPIC_INTERPRETATION,
        features=("hba1c", "blood_glucose", "cholesterol", "triglycerides", "bmi", "vitamin_d"),
        conditions=(C.DIABETES, C.HIGH_CHOLESTEROL, C.HIGH_TRIGLYCERIDES, C.OBESITY),
        keywords=(
            "borderline", "slightly high", "just above normal", "grey zone",
            "prediabetes", "marginal result", "a bit out of range",
        ),
        summary=(
            "Borderline means a value sits in a band between the usual range "
            "and the band guidelines act on; it is a prompt for attention and "
            "usually for repetition, not a finding."
        ),
        body="""
Most published bands have an intermediate zone between the range described as
usual and the range at which guidelines advise action. This platform reports
values in that zone as borderline, and the label means exactly that position and
nothing more.

Borderline is not a mild version of the flagged finding. It is a statement that
the value sits where the evidence does not clearly separate the two situations,
which is a different claim.

Because thresholds are sharp and measurements vary, a value just below a cut-off
and a value just above it are far more similar to each other than their labels
are. Repeating the measurement moves values across boundaries routinely without
anything having changed.

The intermediate zone often is where the most useful conversation happens,
because it is where change over time is most informative and where general
health measures are most often discussed. That makes borderline a reason to pay
attention rather than a reason to dismiss.

This platform reports borderline findings with the same evidence and the same
traceability as flagged ones: which value, which threshold, which guideline. A
reader can therefore see how close to a boundary a value sat rather than only
the label. This material is educational and is not a diagnosis.
""",
        basis=(
            "The BORDERLINE status semantics defined in "
            "app/schemas/decisions.py and applied by the band tables in "
            "app/data/clinical_rules.py; ADA intermediate glycaemic band; NCEP "
            "ATP III borderline-high bands."
        ),
    ),
    KnowledgeDocument(
        doc_id="interp_missing_value",
        title="Missing, unreadable and refused values",
        topic=TOPIC_INTERPRETATION,
        features=(),
        conditions=(),
        keywords=(
            "missing value", "not available", "could not read", "unreadable",
            "rejected value", "insufficient data", "blank result", "not assessed",
        ),
        summary=(
            "A value that was absent, a value that could not be read and a "
            "value that was read but refused are three different situations, "
            "and none of them means the result was normal."
        ),
        body="""
When a test does not appear in a report, the platform reports that the topic
could not be assessed. It does not report that nothing was found, because those
are different statements and only one of them is true.

This distinction is the single most dangerous one to get wrong. An absence of
findings in a report that could not be read looks identical, on a screen, to a
clean set of results. The platform therefore carries an explicit
insufficient-data outcome and an overall status of not assessed, rather than
letting silence be read as good news.

A third case sits between them: a value that was extracted but refused. This
happens when a number is physiologically implausible, is of the wrong type, or
carries a unit that could not be mapped to the canonical one. Refusing it is
safer than converting it wrongly, because a wrongly converted value produces a
confident finding that is simply false.

A refused value is reported as refused, with the reason, and never as absent.
Telling a reader that a test was not in the report when it was in fact present
and rejected would misdescribe both the report and the platform's own behaviour.

The practical reading is that a topic marked not assessed is an open question. If
it matters, the route to closing it is obtaining the test, which is a
conversation with a healthcare professional. This material is educational and is
not a diagnosis.
""",
        basis=(
            "The INSUFFICIENT_DATA decision status and the always_assessed "
            "policy in app/data/conditions.py; the valid / questionable / "
            "rejected separation in app/services/validator.py; the 'Not "
            "Assessed' fourth case in the Module 18 overall status policy."
        ),
    ),
    KnowledgeDocument(
        doc_id="interp_why_values_vary",
        title="Why laboratory values differ between reports",
        topic=TOPIC_INTERPRETATION,
        features=("hemoglobin", "creatinine", "blood_glucose", "triglycerides", "cholesterol"),
        conditions=(),
        keywords=(
            "different results", "changed since last time", "why is it different",
            "another lab", "trend", "comparing reports", "went up went down",
        ),
        summary=(
            "Differences between two reports can come from the person, the "
            "sample, the laboratory method or the reference interval used, and "
            "distinguishing them is part of interpretation."
        ),
        body="""
The most common reason two reports differ is ordinary biological variation.
Many analytes move across the day, with hydration, with recent meals, with
activity and with sleep, entirely within health.

The sample itself is the next source. Time between collection and processing,
storage temperature, posture during collection and the tube used all shift
particular analytes. Glucose falls in a tube left standing, and haemoglobin
concentration rises with dehydration without any change in red-cell number.

Laboratories differ too. Different instruments and methods can produce
systematically different values for the same sample, particularly for
immunoassays such as vitamin B12 and vitamin D. This is why each laboratory
publishes its own reference interval and why the interval printed on a report is
the right comparison for that result.

Reference intervals themselves are revised. A value unchanged between two
reports can be flagged on one and not the other simply because the interval
moved, which is a change in the comparison rather than in the person.

Because of all this, a trend across several results from the same laboratory is
usually more informative than any single comparison, and a difference is worth
interpreting only once it exceeds what these sources would produce on their own.
A healthcare professional with the full history is the one able to judge that.
This material is educational and is not a diagnosis.
""",
        basis=(
            "Standard clinical laboratory practice on pre-analytical and "
            "method-related variation and on laboratory-specific reference "
            "intervals; supports the longitudinal comparison Modules 28-30 "
            "will perform over app/services/feature_repository.py snapshots."
        ),
    ),
    KnowledgeDocument(
        doc_id="interp_what_this_platform_is",
        title="What this platform does and what it does not do",
        topic=TOPIC_INTERPRETATION,
        features=(),
        conditions=(),
        keywords=(
            "what is this", "automated analysis", "ai health report",
            "not a diagnosis", "can i trust this", "limitations",
            "scope", "disclaimer",
        ),
        summary=(
            "This platform reads a laboratory report, compares values against "
            "published guideline bands and model outputs, and explains what it "
            "compared. It does not examine anyone and it is not a diagnosis."
        ),
        body="""
What the platform does is bounded and can be stated exactly. It transcribes a
laboratory report, maps printed test names onto a fixed set of canonical
features, converts units, refuses values it cannot trust, compares the rest
against published guideline bands, runs condition-specific statistical models,
combines the two, and explains each step.

Every finding it produces carries its inputs: which value, which threshold,
which guideline, which model, and what the model was given. That traceability is
the point. A reader who disagrees with a finding can see precisely what produced
it rather than being asked to accept it.

What the platform does not do is equally definite. It does not examine anyone,
take a history, see symptoms, or know anything not in the report and profile it
was given. It holds a fixed set of features and is blind to everything outside
that set, including blood pressure, which is one of the most important inputs to
cardiovascular assessment.

It also cannot weigh the things a clinician weighs: how a person looks, what has
changed recently, what else is going on, and what the person is worried about.
Those routinely change what a number means.

An automated comparison against a band is genuinely useful for orientation and
for knowing what to ask about. It is not an assessment of a person, and it is
not a diagnosis. Decisions about health belong with a qualified healthcare
professional who can see the whole picture.

Where the platform is uncertain, it says so rather than resolving the
uncertainty quietly: unknown sex, missing values, refused values, derived
values and partial views are all reported as what they are.
""",
        basis=(
            "Spec section 14 (Medical Safety Architecture) and the Module 24 "
            "requirement that the platform never present itself as a substitute "
            "for professional care; the explainability chain Input -> Evidence "
            "-> Decision from spec section 13."
        ),
    ),
    KnowledgeDocument(
        doc_id="interp_when_to_seek_advice",
        title="When to seek professional advice about a result",
        topic=TOPIC_INTERPRETATION,
        features=("blood_glucose", "triglycerides", "creatinine", "hemoglobin", "vitamin_d"),
        conditions=(
            C.HYPOGLYCEMIA, C.HIGH_TRIGLYCERIDES, C.KIDNEY_DISEASE, C.ANEMIA,
            C.ELEVATED_VITAMIN_D,
        ),
        keywords=(
            "when to see a doctor", "urgent", "should i worry", "seek advice",
            "who do i ask", "next steps", "how soon",
        ),
        summary=(
            "Any result a person is unsure about is a reason to ask a "
            "healthcare professional, and some findings warrant asking "
            "promptly rather than at the next routine opportunity."
        ),
        body="""
The general answer is simple: a result someone does not understand, or is
worried about, is a reason to ask. That is true whether or not anything was
flagged, and being reassured by a clinician is a legitimate outcome of asking.

Some findings warrant prompt rather than routine contact. Markedly low or
markedly high glucose, very high triglycerides, substantially raised creatinine,
a markedly low haemoglobin and a markedly raised vitamin D are all in this
group. This platform flags such findings for prompt professional advice rather
than leaving them alongside routine ones.

Symptoms change the answer regardless of what any number says. Chest pain,
breathlessness at rest, confusion, fainting, or feeling seriously unwell are
reasons to seek medical help immediately and are not questions for a laboratory
report or for this platform.

For everything else, the useful next step is usually a conversation with the
clinician who requested the tests, since they know why they were requested and
what was expected. Bringing the report itself, and any previous ones, makes that
conversation more productive.

Questions worth taking to that conversation include what the value means in this
particular context, whether it should be repeated and when, whether anything
else should be measured alongside it, and what would change the plan.

Nothing in this platform is a reason to delay seeking care, and nothing in it
replaces an assessment by a qualified healthcare professional. This material is
educational and is not a diagnosis.
""",
        basis=(
            "The SEEK_PROMPT_MEDICAL_ADVICE and DISCUSS_WITH_CLINICIAN "
            "recommendation codes in app/data/recommendation_catalog.py and the "
            "clinically-extreme bands that raise them in "
            "app/data/clinical_rules.py; spec section 14."
        ),
    ),
)

__all__ = ["INTERPRETATION_DOCUMENTS"]
