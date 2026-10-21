from __future__ import annotations

import logging
from typing import Any, Iterator, List, Tuple

import pytest

from app.data.recommendation_catalog import (
    NOT_A_DIAGNOSIS,
    RECOMMENDATIONS,
    recommendation,
)
from app.safety import (
    APPROVE,
    APPROVE_WITH_MODIFICATION,
    MAX_TEXT_LENGTH,
    REDACTION_NOTICE,
    REJECT,
    RULES,
    SafetyContext,
    SafetyVerdict,
    UnsafeGeneratedContentError,
    assert_safe_for_patient,
    guarded_generation,
    rule_document,
    safe_fallback,
    validate_text,
)
from app.safety.policy import (
    CODE_SEVERITY,
    SAFETY_POLICY,
    Severity,
    ViolationCode,
)
from app.safety.validator import (
    MAX_REDACTED_FRACTION,
    MIN_SURVIVING_CHARACTERS,
)
from app.services.report_builder import generate_report

FRAGMENT = SafetyContext(require_referral=False)


def codes(verdict: SafetyVerdict) -> List[str]:
    return sorted(set(verdict.codes))


def has(verdict: SafetyVerdict, code: ViolationCode) -> bool:
    return code.value in verdict.codes


@pytest.mark.parametrize(
    "value",
    [
        None,
        123,
        4.5,
        True,
        b"some bytes",
        bytearray(b"x"),
        {"text": "hello"},
        ["a", "b"],
        object(),
        ("a",),
        set(),
    ],
)
def test_a_non_string_is_rejected_never_approved(value: Any) -> None:
    verdict = validate_text(value)
    assert verdict.verdict == REJECT
    assert verdict.approved_text is None
    assert verdict.fallback_required is True
    assert has(verdict, ViolationCode.UNANALYSABLE_INPUT)


def test_an_unencodable_string_is_rejected() -> None:
    verdict = validate_text("your result \udfff looks fine")
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.UNANALYSABLE_INPUT)
    assert verdict.approved_text is None


@pytest.mark.parametrize("control", ["\x00", "\x07", "\x1b", "\x7f", "\x9f"])
def test_control_characters_are_rejected_not_scanned(control: str) -> None:
    verdict = validate_text(f"An educational note{control} about your result.")
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.UNANALYSABLE_INPUT)


def test_oversized_input_is_rejected_rather_than_partially_analysed() -> None:
    verdict = validate_text("a" * (MAX_TEXT_LENGTH + 1))
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.INPUT_TOO_LARGE)


@pytest.mark.parametrize("blank", ["", "   ", "\n\n", "\t \t"])
def test_an_empty_generation_is_a_failure_not_an_approval(blank: str) -> None:
    verdict = validate_text(blank)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.EMPTY_OUTPUT)


def test_an_internal_error_rejects_instead_of_approving(monkeypatch) -> None:
    import app.safety.validator as validator_module

    def explode(*_args: Any, **_kwargs: Any):
        raise RuntimeError("the scanner is broken")

    monkeypatch.setattr(validator_module, "_scan_rules", explode)
    verdict = validate_text("A perfectly innocuous educational sentence.")
    assert verdict.verdict == REJECT
    assert verdict.approved_text is None
    assert has(verdict, ViolationCode.VALIDATOR_ERROR)
    assert verdict.fallback_required is True


def test_even_a_base_exception_rejects(monkeypatch) -> None:
    import app.safety.validator as validator_module

    def explode(*_args: Any, **_kwargs: Any):
        raise RecursionError("too deep")

    monkeypatch.setattr(validator_module, "_normalise", explode)
    verdict = validate_text("A perfectly innocuous educational sentence.")
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.VALIDATOR_ERROR)


def test_validate_text_never_raises(monkeypatch) -> None:
    import app.safety.validator as validator_module

    monkeypatch.setattr(
        validator_module,
        "_check_hedging",
        lambda *_a, **_k: (_ for _ in ()).throw(ValueError("x")),
    )
    verdict = validate_text("Anything at all.")
    assert verdict.verdict == REJECT


def test_a_rejection_never_carries_approved_text() -> None:
    verdict = validate_text("Take metformin 500 mg twice a day.")
    assert verdict.verdict == REJECT
    assert verdict.approved_text is None
    assert verdict.fallback_required is True


def test_the_error_path_never_reports_a_clean_verdict(monkeypatch) -> None:
    for code in (
        ViolationCode.UNANALYSABLE_INPUT,
        ViolationCode.EMPTY_OUTPUT,
        ViolationCode.INPUT_TOO_LARGE,
        ViolationCode.VALIDATOR_ERROR,
        ViolationCode.REDACTION_NOT_POSSIBLE,
    ):
        assert CODE_SEVERITY[code] is Severity.STRUCTURAL


@pytest.mark.parametrize(
    "text",
    [
        "The diagnosis is diabetes.",
        "Your diagnosis is chronic kidney disease.",
        "This report diagnoses type 2 diabetes.",
        "You have diabetes.",
        "You are diabetic.",
        "The patient has anaemia.",
        "These results are diagnostic of kidney disease.",
        "A diagnosis of vitamin D deficiency is established here.",
    ],
)
def test_unsupported_diagnosis_is_rejected(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.UNSUPPORTED_DIAGNOSIS)


@pytest.mark.parametrize(
    "text",
    [
        "This is an automated educational analysis, not a diagnosis.",
        "It does not diagnose anything.",
        "This tool is not a diagnostic device.",
    ],
)
def test_the_mandated_disclaiming_phrasing_is_not_a_diagnosis(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert not has(verdict, ViolationCode.UNSUPPORTED_DIAGNOSIS)


@pytest.mark.parametrize(
    "condition",
    [
        "diabetes",
        "anaemia",
        "kidney disease",
        "chronic kidney disease",
        "heart disease",
        "hypertension",
        "hypothyroidism",
        "hyperthyroidism",
        "cancer",
        "liver disease",
    ],
)
def test_the_suffering_from_carrier_rejects_every_enumerated_condition(
    condition: str,
) -> None:
    verdict = validate_text(f"You are suffering from {condition}.", FRAGMENT)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.UNSUPPORTED_DIAGNOSIS)


@pytest.mark.parametrize(
    "text,why",
    [
        ("You have kidney  disease.", "two spaces inside the condition name"),
        ("You have kidney\tdisease.", "a tab inside the condition name"),
        ("You have chronic  kidney disease.", "three-word name, doubled space"),
        ("You have heart\t disease.", "tab and space together"),
        ("You  have kidney disease.", "doubled space in the CARRIER (already held)"),
    ],
)
def test_a_multi_word_condition_name_survives_real_whitespace(
    text: str, why: str
) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT, why
    assert has(verdict, ViolationCode.UNSUPPORTED_DIAGNOSIS), why


@pytest.mark.parametrize(
    "condition,why",
    [
        ("cirrhosis of the liver", "§6r's D1, the sentence in the handover"),
        ("cirrhosis", "-osis"),
        ("leukaemia", "-aemia"),
        ("leukemia", "-emia, US spelling"),
        ("lymphoma", "-oma"),
        ("multiple myeloma", "-oma behind a modifier"),
        ("hepatitis", "-itis"),
        ("pancreatitis", "-itis"),
        ("rheumatoid arthritis", "-itis behind a modifier"),
        ("thalassaemia", "-aemia"),
        ("polycythaemia", "-aemia"),
        ("thrombocytopenia", "-penia"),
        ("tuberculosis", "-osis"),
        ("nephrotic syndrome", "head noun: syndrome"),
        ("metabolic syndrome", "head noun: syndrome"),
        ("sickle cell disease", "head noun behind two modifiers"),
        ("fatty liver disease", "head noun behind two modifiers"),
        ("coeliac disease", "head noun"),
        ("a bleeding disorder", "head noun: disorder"),
        ("a thyroid disorder", "head noun: disorder"),
        ("an iron deficiency", "head noun: deficiency"),
        ("HIV", "irregular -- enumerated, no usable suffix"),
        ("gout", "irregular"),
        ("lupus", "irregular"),
        ("sepsis", "irregular -- `-psis`, not `-osis`"),
        ("COVID-19", "irregular, and carries a numeral"),
    ],
)
def test_a_diagnosis_is_refused_even_when_nobody_enumerated_the_condition(
    condition: str, why: str
) -> None:
    verdict = validate_text(f"You have {condition}.", FRAGMENT)
    assert verdict.verdict == REJECT, why
    assert has(verdict, ViolationCode.UNSUPPORTED_DIAGNOSIS), why


@pytest.mark.parametrize(
    "text,why",
    [
        ("You have a higher risk of heart disease.", "a risk is not a diagnosis"),
        ("You have an increased risk of diabetes.", "a risk is not a diagnosis"),
        ("You have a family history of kidney disease.", "a history is not a diagnosis"),
        ("You have four results outside the reference interval.", "about the report"),
        ("You have two results that could not be assessed.", "about the report"),
        ("You have a follow-up appointment with your doctor.", "about an appointment"),
        ("You have questions about these results.", "about the reader's questions"),
        ("Cirrhosis is a condition in which the liver becomes scarred.", "education"),
        ("Anaemia is a condition in which the blood carries less oxygen.", "education"),
        ("A raised ALT is associated with liver disease.", "association, not assertion"),
        ("Screening for diabetes may be worth discussing.", "screening"),
    ],
)
def test_a_risk_or_a_history_or_the_report_itself_is_not_a_diagnosis(
    text: str, why: str
) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert not has(verdict, ViolationCode.UNSUPPORTED_DIAGNOSIS), why


@pytest.mark.parametrize(
    "text",
    [
        "You have a raised CRP. Infection is one cause among many.",
        "You have a raised ALT. Liver disease is one possibility.",
        "You have one result to discuss; anaemia is a common explanation.",
    ],
)
def test_the_diagnosis_rule_does_not_reach_across_a_sentence_boundary(
    text: str,
) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert not has(verdict, ViolationCode.UNSUPPORTED_DIAGNOSIS)


def test_the_perfect_tense_reaches_its_noun() -> None:
    verdict = validate_text("You have had a heart attack.", FRAGMENT)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.UNSUPPORTED_DIAGNOSIS)


@pytest.mark.parametrize(
    "text,why",
    [
        ("Your doctor may start you on metformin.", "enumerated by name"),
        ("Candesartan is often used for this.", "NOT enumerated -- caught by -sartan"),
        ("Bisoprolol would help here.", "NOT enumerated -- caught by -olol"),
        ("Ranolazine is worth asking about.", "NOT enumerated -- caught by -azine"),
        ("Consider budesonide for this.", "NOT enumerated -- caught by -sonide"),
        ("Furosemide-like agents reduce this.", "-semide"),
        ("A vitamin D supplement would raise this.", "supplementation"),
    ],
)
def test_medication_reference_is_rejected(text: str, why: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT, why
    assert has(verdict, ViolationCode.MEDICATION_REFERENCE), why


@pytest.mark.parametrize(
    "text",
    [
        "Take half a tablet at night.",
        "Take one capsule with food.",
        "Take 500 mg twice a day.",
        "The usual dose is two tablets.",
        "Increase the dosage every morning.",
        "You should take 10 milligrams of it.",
        "Swallow it on an empty stomach.",
    ],
)
def test_medication_dosage_is_rejected(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.MEDICATION_DOSAGE)


def test_a_laboratory_threshold_is_not_a_dosage() -> None:
    verdict = validate_text(
        "The fasting glucose threshold this tool uses is 126 mg/dL, which a "
        "qualified healthcare professional can put in context.",
        FRAGMENT,
    )
    assert not has(verdict, ViolationCode.MEDICATION_DOSAGE)


@pytest.mark.parametrize(
    "text",
    [
        "Your doctor will prescribe something for this.",
        "This condition is treated with a change of medication.",
        "The usual therapy is straightforward.",
        "You should stop taking your current medicine.",
        "A short course of treatment fixes this.",
        "Dialysis is the next step.",
    ],
)
def test_unsafe_treatment_instruction_is_rejected(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.UNSAFE_TREATMENT_INSTRUCTION)


@pytest.mark.parametrize(
    "text",
    [
        "This definitely means diabetes.",
        "The result confirms the condition.",
        "This proves your kidneys are damaged.",
        "You will develop heart disease.",
        "This is 100% conclusive.",
        "There is nothing to worry about.",
        "Your results are perfectly normal, rest assured.",
    ],
)
def test_claims_of_certainty_are_rejected(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.CERTAINTY_CLAIM)


@pytest.mark.parametrize(
    "text",
    [
        "You do not need to see a doctor about this.",
        "This report replaces a clinical consultation.",
        "There is no need to consult anyone.",
        "Use this instead of seeing a physician.",
        "This is a substitute for medical advice.",
        "It saves you a trip to the clinic.",
    ],
)
def test_replacing_professional_consultation_is_caught(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert has(verdict, ViolationCode.REPLACES_PROFESSIONAL_CONSULTATION)
    assert verdict.verdict == REJECT


def test_the_required_disclaimer_is_not_a_replacement_claim() -> None:
    verdict = validate_text(recommendation(NOT_A_DIAGNOSIS).text, FRAGMENT)
    assert verdict.verdict == APPROVE
    assert verdict.violations == ()


@pytest.mark.parametrize(
    "text",
    [
        "I recommend you get this checked.",
        "In my clinical opinion this is fine.",
        "As your doctor, I would watch this.",
        "We advise a repeat test.",
    ],
)
def test_clinician_voice_is_rejected(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.CLINICIAN_VOICE)


@pytest.mark.parametrize(
    "text",
    [
        "This means you have a kidney problem.",
        "Your result indicates diabetes.",
        "Creatinine indicates kidney disease.",
        "This finding shows a deficiency.",
    ],
)
def test_an_unhedged_interpretation_is_rejected(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM)


@pytest.mark.parametrize(
    "text",
    [
        "This may indicate that your kidneys are working harder than usual.",
        "A result in this range can sometimes mean a deficiency.",
        "This finding is often associated with a raised risk.",
    ],
)
def test_a_hedged_interpretation_is_permitted(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert not has(verdict, ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM)


@pytest.mark.parametrize(
    "text",
    [
        "Your HbA1c is 6.8%.",
        "Total cholesterol was 190 mg/dL.",
        "HbA1c means glycated haemoglobin.",
        "A reference range is the band a laboratory reports as usual.",
    ],
)
def test_a_restatement_or_a_definition_needs_no_hedge(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert not has(verdict, ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM)


@pytest.mark.parametrize(
    "verb_text",
    [
        "You should reduce your salt.",
        "You must start exercising.",
        "You need to increase your intake.",
        "You have to avoid fruit.",
    ],
)
def test_a_directive_verb_outside_the_allowlist_is_caught(verb_text: str) -> None:
    verdict = validate_text(verb_text, FRAGMENT)
    assert has(verdict, ViolationCode.UNPERMITTED_DIRECTIVE)


@pytest.mark.parametrize(
    "text",
    [
        "You should discuss this with a qualified healthcare professional.",
        "You may want to ask a doctor about it.",
        "You should consider raising it at your next appointment.",
    ],
)
def test_the_permitted_directives_are_permitted(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert not has(verdict, ViolationCode.UNPERMITTED_DIRECTIVE)


def test_a_number_absent_from_the_grounding_is_rejected() -> None:
    context = SafetyContext(
        grounding_sources=("An HbA1c at or above 6.5% is the usual threshold.",),
        permitted_numbers=(6.8,),
        require_referral=False,
    )
    grounded = validate_text(
        "Your HbA1c of 6.8% sits above the 6.5% figure this tool uses.", context
    )
    assert grounded.verdict == APPROVE

    invented = validate_text(
        "Your HbA1c of 6.8% sits above the 9.9% figure this tool uses.", context
    )
    assert invented.verdict == REJECT
    assert has(invented, ViolationCode.UNGROUNDED_NUMERIC_CLAIM)
    offending = [
        v for v in invented.violations
        if v.code is ViolationCode.UNGROUNDED_NUMERIC_CLAIM
    ]
    assert [v.excerpt for v in offending] == ["9.9"]


def test_numeric_grounding_is_inactive_without_grounding_material() -> None:
    verdict = validate_text("Your HbA1c of 6.8% is above 6.5%.", FRAGMENT)
    assert not has(verdict, ViolationCode.UNGROUNDED_NUMERIC_CLAIM)


def test_required_grounding_refuses_an_ungrounded_generation() -> None:
    verdict = validate_text(
        "A short educational note about your report.",
        SafetyContext(require_grounding=True, require_referral=False),
    )
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.GROUNDING_REQUIRED_BUT_ABSENT)


def test_approve_carries_the_text_and_no_violations() -> None:
    text = (
        "Your HbA1c sits a little above the band this tool uses. A qualified "
        "healthcare professional can say what that may mean for you."
    )
    verdict = validate_text(text)
    assert verdict.verdict == APPROVE
    assert verdict.approved_text == text
    assert verdict.violations == ()
    assert verdict.modifications == ()
    assert verdict.fallback_required is False
    assert verdict.approved is True


def test_every_violation_is_actionable_and_auditable() -> None:
    text = "Take metformin 500 mg twice a day; this confirms you have diabetes."
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT
    assert verdict.violations
    for violation in verdict.violations:
        assert violation.code in set(ViolationCode)
        assert violation.rule_id
        assert violation.reason.strip()
        assert violation.severity in set(Severity)
        assert violation.span_end >= violation.span_start
        assert (
            verdict.analysed_text[violation.span_start : violation.span_end]
            == violation.excerpt
        )
    assert {
        ViolationCode.MEDICATION_REFERENCE.value,
        ViolationCode.MEDICATION_DOSAGE.value,
        ViolationCode.CERTAINTY_CLAIM.value,
        ViolationCode.UNSUPPORTED_DIAGNOSIS.value,
    } <= set(verdict.codes)


def test_code_counts_are_machine_readable() -> None:
    verdict = validate_text("Take 500 mg. Take 250 mg.", FRAGMENT)
    counts = verdict.code_counts()
    assert counts[ViolationCode.MEDICATION_DOSAGE.value] >= 2


def test_assert_safe_for_patient_raises_on_a_rejection() -> None:
    with pytest.raises(UnsafeGeneratedContentError) as excinfo:
        assert_safe_for_patient("You definitely have diabetes.", FRAGMENT)
    assert excinfo.value.verdict.verdict == REJECT
    assert assert_safe_for_patient(
        "A qualified healthcare professional can go through this with you."
    )


def test_missing_referral_appends_catalogue_framing_and_changes_nothing_else() -> None:
    original = (
        "Your HbA1c sits above the band this tool uses. Tracking it across "
        "future reports can show whether it is changing."
    )
    verdict = validate_text(original)
    assert verdict.verdict == APPROVE_WITH_MODIFICATION
    assert has(verdict, ViolationCode.MISSING_PROFESSIONAL_REFERRAL)
    assert [m.action for m in verdict.modifications] == ["append_safety_framing"]
    assert verdict.approved_text.startswith(original)
    assert verdict.approved_text.endswith(recommendation(NOT_A_DIAGNOSIS).text)


def test_a_redaction_removes_a_whole_sentence_and_keeps_the_rest_verbatim() -> None:
    keep_first = (
        "Your creatinine sits above the band this tool uses, which a qualified "
        "healthcare professional can put in context."
    )
    keep_last = (
        "Tracking the value across future reports can show whether it is changing."
    )
    drop = "You do not need to see a doctor about it."
    verdict = validate_text(f"{keep_first} {drop} {keep_last}")

    assert verdict.verdict == APPROVE_WITH_MODIFICATION
    assert [m.action for m in verdict.modifications] == ["redact_sentence"]
    assert keep_first in verdict.approved_text
    assert keep_last in verdict.approved_text
    assert drop not in verdict.approved_text
    assert REDACTION_NOTICE in verdict.approved_text
    assert verdict.modifications[0].removed_excerpt.strip() == drop


def test_a_redaction_never_removes_the_abnormal_finding() -> None:
    finding = "Your creatinine is above the usual band for this laboratory."
    verdict = validate_text(
        f"{finding} You do not need to see a doctor or any other clinician."
    )
    assert verdict.verdict == APPROVE_WITH_MODIFICATION
    assert finding in verdict.approved_text


def test_only_instruction_codes_are_ever_redactable() -> None:
    redactable = {c for c, s in CODE_SEVERITY.items() if s is Severity.REDACTABLE}
    assert redactable == {
        ViolationCode.REPLACES_PROFESSIONAL_CONSULTATION,
        ViolationCode.UNPERMITTED_DIRECTIVE,
    }


def test_a_prohibited_violation_is_never_salvaged_by_redaction() -> None:
    verdict = validate_text(
        "Your cholesterol sits above the band a qualified healthcare "
        "professional would use. Your doctor may start atorvastatin. "
        "Tracking it over time can be useful."
    )
    assert verdict.verdict == REJECT
    assert verdict.approved_text is None
    assert has(verdict, ViolationCode.MEDICATION_REFERENCE)


def test_redaction_is_refused_when_it_would_gut_the_explanation() -> None:
    verdict = validate_text(
        "You do not need to see a doctor. There is no need to consult anyone. "
        "A qualified healthcare professional wrote this laboratory band."
    )
    assert verdict.verdict == REJECT
    assert has(verdict, ViolationCode.REDACTION_NOT_POSSIBLE)
    assert MAX_REDACTED_FRACTION <= 0.5
    assert MIN_SURVIVING_CHARACTERS > 0


def test_a_modification_cannot_launder_text_into_approval() -> None:
    import app.safety.validator as validator_module

    def fake_redact(text, sentences, violations):
        return "Take metformin 500 mg twice a day with a doctor.", [
            validator_module.SafetyModification(
                action="redact_sentence",
                code=ViolationCode.UNPERMITTED_DIRECTIVE,
                reason="planted",
                span_start=0,
                span_end=1,
                removed_excerpt="x",
            )
        ]

    monkey = pytest.MonkeyPatch()
    monkey.setattr(validator_module, "_redact", fake_redact)
    try:
        verdict = validate_text(
            "Your creatinine sits above the usual band for this laboratory. "
            "You do not need to see a doctor about it. "
            "Tracking it across future reports can be useful to review."
        )
    finally:
        monkey.undo()
    assert verdict.verdict == REJECT
    assert verdict.approved_text is None


def test_the_modification_policy_says_what_it_may_not_do() -> None:
    policy = SAFETY_POLICY["modification"]
    actions = {a["action"] for a in policy["permitted_actions"]}
    assert actions == {"append_safety_framing", "redact_sentence"}
    assert all(a["changes_existing_words"] is False for a in policy["permitted_actions"])
    forbidden = " ".join(policy["forbidden_actions"]).lower()
    assert "paraphras" in forbidden
    assert "softening" in forbidden


TREAT_WARNING = (
    "Feature 'bmi' is usable but flagged (DERIVED_VALUE); treat it with "
    "reduced confidence."
)


def test_treat_it_with_reduced_confidence_is_not_a_treatment_instruction() -> None:
    verdict = validate_text(TREAT_WARNING, FRAGMENT)
    assert verdict.verdict == APPROVE
    assert verdict.violations == ()


@pytest.mark.parametrize(
    "text",
    [
        "treat it with caution",
        "Treat this with reduced confidence.",
        "treat the value with scepticism",
        "Treat these values with care.",
    ],
)
def test_the_epistemic_treat_exemption_is_narrow(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert not has(verdict, ViolationCode.UNSAFE_TREATMENT_INSTRUCTION)


@pytest.mark.parametrize(
    "text",
    [
        "treat it with metformin",
        "Treat this with antibiotics.",
        "treat them with insulin",
        "Treat it with reduced confidence and a statin.",
    ],
)
def test_a_real_treatment_instruction_still_matches(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    assert verdict.verdict == REJECT


@pytest.mark.parametrize("code", sorted(RECOMMENDATIONS))
def test_every_catalogue_recommendation_passes_cleanly(code: str) -> None:
    verdict = validate_text(RECOMMENDATIONS[code].text, FRAGMENT)
    unexpected = [v for v in verdict.violations if v.severity is not Severity.REQUIRED]
    assert unexpected == [], f"{code}: {[v.code.value for v in unexpected]}"


def _walk_strings(obj: Any, path: str = "report") -> Iterator[Tuple[str, str]]:
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield from _walk_strings(value, f"{path}.{key}")
    elif isinstance(obj, (list, tuple)):
        for index, value in enumerate(obj):
            yield from _walk_strings(value, f"{path}[{index}]")


def test_a_generated_clinical_report_produces_no_false_positives() -> None:
    report = generate_report()
    offenders: List[Tuple[str, str, List[str]]] = []
    for path, text in _walk_strings(report.model_dump(mode="json")):
        verdict = validate_text(text, FRAGMENT)
        bad = [v for v in verdict.violations if v.severity is not Severity.REQUIRED]
        if bad:
            offenders.append((path, text, [v.code.value for v in bad]))
    assert offenders == [], f"{len(offenders)} false positives, first: {offenders[:3]}"


@pytest.mark.parametrize(
    "text",
    [
        "HbA1c reflects average blood glucose over roughly the previous three "
        "months. A qualified healthcare professional interprets it alongside "
        "other results.",
        "Creatinine is a waste product filtered by the kidneys. Laboratories "
        "report it against a reference range that varies by method.",
        "A reference range describes the band of values a laboratory reports "
        "as usual for its population; it is not a target.",
        "Vitamin D status is commonly described using a 25-hydroxyvitamin D "
        "measurement. Sunlight exposure and diet are the general topics "
        "associated with it.",
    ],
)
def test_knowledge_base_register_text_passes_cleanly(text: str) -> None:
    verdict = validate_text(text, FRAGMENT)
    unexpected = [v for v in verdict.violations if v.severity is not Severity.REQUIRED]
    assert unexpected == [], [v.code.value for v in unexpected]


def test_a_realistic_module_23_explanation_is_approved() -> None:
    text = (
        "Your HbA1c came back at 6.8%. HbA1c reflects average blood glucose "
        "over roughly the previous three months, so it can give a broader "
        "picture than a single glucose reading. A value in this range sits "
        "above the band this tool uses, which may be worth discussing with a "
        "qualified healthcare professional. A single laboratory result rarely "
        "settles a question on its own."
    )
    verdict = validate_text(
        text,
        SafetyContext(
            grounding_sources=(
                "HbA1c reflects average blood glucose over roughly 3 months. "
                "The threshold this tool uses is 6.5%.",
            ),
            permitted_numbers=(6.8,),
        ),
    )
    assert verdict.verdict == APPROVE, codes(verdict)
    assert verdict.approved_text == text


def test_the_fallback_is_useful_honest_and_catalogue_sourced() -> None:
    verdict = validate_text("Take metformin 500 mg twice a day.")
    fallback = safe_fallback(verdict)

    assert fallback.generated_explanation_available is False
    assert fallback.use_structured_report is True
    assert "unaffected" in fallback.notice
    assert "qualified healthcare professional" in fallback.notice
    assert [r["code"] for r in fallback.recommendations] == list(
        fallback.recommendation_codes
    )
    for resolved in fallback.recommendations:
        assert resolved["text"] == RECOMMENDATIONS[resolved["code"]].text
    assert ViolationCode.MEDICATION_DOSAGE.value in fallback.violation_codes


def test_the_fallback_never_leaks_the_refused_text() -> None:
    verdict = validate_text("Take metformin 500 mg twice a day.")
    rendered = " ".join(
        [fb for fb in (safe_fallback(verdict).notice,)]
        + [r["text"] for r in safe_fallback(verdict).recommendations]
    )
    assert "metformin" not in rendered.lower()
    assert "500" not in rendered


def test_the_fallback_text_itself_passes_the_safety_layer() -> None:
    fallback = safe_fallback(validate_text("You definitely have diabetes."))
    assert validate_text(fallback.notice).verdict == APPROVE
    for resolved in fallback.recommendations:
        assert validate_text(resolved["text"], FRAGMENT).verdict in (
            APPROVE,
            APPROVE_WITH_MODIFICATION,
        )


def test_the_redaction_notice_itself_passes_the_safety_layer() -> None:
    assert validate_text(REDACTION_NOTICE).verdict == APPROVE


def test_guarded_generation_returns_approved_text_when_the_output_is_clean() -> None:
    result = guarded_generation(
        lambda **_: "A qualified healthcare professional can go through this with you."
    )
    assert result.approved_text is not None
    assert result.fallback is None
    assert result.attempts == 1


def test_guarded_generation_retries_then_succeeds() -> None:
    outputs = iter(
        [
            "Take metformin 500 mg twice a day.",
            "A qualified healthcare professional can go through this with you.",
        ]
    )

    def generate(**_: Any) -> str:
        return next(outputs)

    result = guarded_generation(generate, attempts=2)
    assert result.approved_text is not None
    assert result.attempts == 2
    assert len(result.history) == 2
    assert result.history[0].verdict == REJECT


def test_guarded_generation_falls_back_rather_than_showing_nothing() -> None:
    result = guarded_generation(lambda **_: "Take 500 mg twice a day.", attempts=2)
    assert result.approved_text is None
    assert result.fallback is not None
    assert result.fallback.violation_codes
    assert result.verdict.verdict == REJECT


def test_a_generator_that_raises_is_a_failed_attempt_not_an_approval() -> None:
    def explode(**_: Any) -> str:
        raise RuntimeError("the model is down")

    result = guarded_generation(explode, attempts=1)
    assert result.approved_text is None
    assert result.fallback is not None


def test_a_generator_returning_none_is_a_failed_attempt() -> None:
    result = guarded_generation(lambda **_: None, attempts=1)
    assert result.approved_text is None
    assert result.fallback is not None
    assert ViolationCode.UNANALYSABLE_INPUT.value in result.verdict.codes


def test_a_generator_that_takes_no_feedback_keyword_still_works() -> None:
    calls: List[int] = []

    def generate() -> str:
        calls.append(1)
        return "Take 500 mg."

    result = guarded_generation(generate, attempts=2)
    assert len(calls) == 2
    assert result.approved_text is None


def test_validated_content_never_reaches_the_logs(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    marker = "ZZQUNIQUEMARKERZZ"
    validate_text(
        f"{marker} take metformin 500 mg twice a day; your HbA1c is 6.8%.",
        FRAGMENT,
    )
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert marker not in logged
    assert "metformin" not in logged.lower()
    assert "6.8" not in logged
    assert "500" not in logged
    assert "safety_validation" in logged
    assert ViolationCode.MEDICATION_REFERENCE.value in logged


def test_the_fallback_path_logs_codes_but_no_content(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    marker = "ZZOTHERMARKERZZ"
    guarded_generation(lambda **_: f"{marker} take 500 mg twice a day.", attempts=1)
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert marker not in logged
    assert ViolationCode.MEDICATION_DOSAGE.value in logged


def test_a_structural_rejection_logs_no_content(caplog) -> None:
    caplog.set_level(logging.DEBUG)
    validate_text("ZZSTRUCTURALMARKERZZ\x00")
    logged = "\n".join(record.getMessage() for record in caplog.records)
    assert "ZZSTRUCTURALMARKERZZ" not in logged
    assert ViolationCode.UNANALYSABLE_INPUT.value in logged


def test_the_rule_table_is_not_vacuous() -> None:
    canary = (
        "Take metformin 500 mg twice a day; this confirms you have diabetes "
        "and you do not need to see a doctor."
    )
    verdict = validate_text(canary, FRAGMENT)
    assert verdict.verdict == REJECT
    assert len(set(verdict.codes)) >= 5


def test_every_code_has_a_severity_so_none_is_un_actionable() -> None:
    for code in ViolationCode:
        assert code in CODE_SEVERITY


def test_every_rule_records_why_it_exists() -> None:
    for rule in RULES:
        assert rule.rule_id and rule.reason.strip() and rule.pattern is not None


def test_the_rule_document_publishes_the_blocklist_split() -> None:
    document = rule_document()
    assert document["rule_count"] == len(document["rules"])
    assert document["blocklist_rule_count"] > 0
    assert document["positive_control_rule_count"] > 0
    kinds = {r["kind"] for r in document["rules"]}
    assert kinds == {"blocklist", "positive_control", "fail_closed"}
    assert all("pattern" not in r for r in document["rules"])


def test_the_policy_publishes_its_limitations() -> None:
    limitations = SAFETY_POLICY["limitations"]
    assert len(limitations) >= 4
    joined = " ".join(limitations).lower()
    assert "blocklist" in joined
    assert "cannot enumerate everything" in joined
    assert "paraphrase" in joined


def test_the_known_gap_is_recorded_rather_than_hidden() -> None:
    bare = validate_text("Digoxin exists.", FRAGMENT)
    assert not has(bare, ViolationCode.MEDICATION_REFERENCE)

    realistic = validate_text("You should start digoxin.", FRAGMENT)
    assert realistic.verdict == REJECT
    assert has(realistic, ViolationCode.UNSAFE_TREATMENT_INSTRUCTION) or has(
        realistic, ViolationCode.UNPERMITTED_DIRECTIVE
    )


def test_a_spelled_out_concentration_is_not_a_dose() -> None:
    assert (
        validate_text(
            "Total cholesterol bands in milligrams per decilitre: below 200.",
            FRAGMENT,
        ).verdict
        == APPROVE
    )
    assert has(
        validate_text("You should take 10 milligrams of it.", FRAGMENT),
        ViolationCode.MEDICATION_DOSAGE,
    )


@pytest.mark.parametrize(
    "text",
    [
        "The body makes too little insulin, or responds poorly to it.",
        "Insulin resistance is common in this condition.",
        "The hormone insulin moves glucose into cells.",
        "Some people do not produce enough insulin.",
    ],
)
def test_insulin_the_hormone_is_not_insulin_the_injection(text: str) -> None:
    assert not has(validate_text(text, FRAGMENT), ViolationCode.MEDICATION_REFERENCE)


@pytest.mark.parametrize(
    "text",
    ["Your doctor may start insulin.", "You should inject insulin.", "Insulin 10 units."],
)
def test_insulin_as_a_medication_still_matches(text: str) -> None:
    assert validate_text(text, FRAGMENT).verdict == REJECT


def test_a_disclaiming_replacement_sentence_is_not_a_replacement_claim() -> None:
    for text in (
        "Nothing in it replaces an assessment by a qualified healthcare professional.",
        "It is the right place for questions rather than a substitute for it.",
    ):
        verdict = validate_text(text, FRAGMENT)
        assert not has(
            verdict, ViolationCode.REPLACES_PROFESSIONAL_CONSULTATION
        ), text


def test_the_negation_guard_cannot_leak_across_a_sentence_boundary() -> None:
    verdict = validate_text(
        "You do not need to see a doctor. There is no need to consult anyone. "
        "A qualified healthcare professional wrote this laboratory band.",
        FRAGMENT,
    )
    assert verdict.verdict == REJECT
    replacement_hits = [
        v
        for v in verdict.violations
        if v.code is ViolationCode.REPLACES_PROFESSIONAL_CONSULTATION
    ]
    assert len(replacement_hits) >= 2


def test_naming_an_interpretation_is_not_making_one() -> None:
    verdict = validate_text(
        "What a result means for an individual is a question for a qualified "
        "healthcare professional.",
        FRAGMENT,
    )
    assert not has(verdict, ViolationCode.UNHEDGED_INTERPRETIVE_CLAIM)


def test_a_line_wrapped_disclaimer_still_reads_as_a_disclaimer() -> None:
    assert not has(
        validate_text(
            "This material is educational and is not\na diagnosis.", FRAGMENT
        ),
        ViolationCode.UNSUPPORTED_DIAGNOSIS,
    )


def test_zero_width_characters_cannot_split_a_banned_word() -> None:
    verdict = validate_text("Your doctor may start met​formin.", FRAGMENT)
    assert has(verdict, ViolationCode.MEDICATION_REFERENCE)
