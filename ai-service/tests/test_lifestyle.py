from __future__ import annotations

from pathlib import Path


def test_guidance_is_resolved_by_code_from_the_reviewed_catalogue():
    from app.data.recommendation_catalog import RECOMMENDATIONS
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(conditions=("Diabetes",), features=("hba1c",))

    assert result.items
    for item in result.items:
        assert item.code in RECOMMENDATIONS
        assert item.text == RECOMMENDATIONS[item.code].text


def test_the_spec_s_own_guidance_categories_are_covered():
    from app.services.lifestyle import lifestyle_guidance

    eating = lifestyle_guidance(conditions=("Diabetes",))
    assert "GENERAL_BALANCED_DIET" in {i.code for i in eating.items}
    assert "GENERAL_PHYSICAL_ACTIVITY" in {i.code for i in eating.items}

    hydration = lifestyle_guidance(conditions=("Kidney Disease",))
    assert "GENERAL_HYDRATION" in {i.code for i in hydration.items}

    assert "MONITOR_OVER_TIME" in {i.code for i in eating.items}
    assert "DISCUSS_WITH_CLINICIAN" in {i.code for i in eating.items}


def test_every_response_carries_the_professional_referral_and_the_disclaimer():
    from app.services.lifestyle import ALWAYS_INCLUDED, lifestyle_guidance

    for request in (
        {},
        {"conditions": ("Anemia",)},
        {"features": ("vitamin_d",)},
        {"conditions": ("Diabetes", "Obesity"), "features": ("bmi",)},
    ):
        result = lifestyle_guidance(**request)
        codes = {i.code for i in result.items}
        assert set(ALWAYS_INCLUDED) <= codes


def test_the_output_passes_module_24():
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(conditions=("Diabetes",), features=("hba1c",))
    assert result.safety_verdict in ("approve", "approve_with_modification")
    assert result.text
    assert result.fallback is None


def test_every_condition_and_feature_produces_safe_guidance():
    from app.data.conditions import CONDITIONS
    from app.data.feature_catalog import FEATURES
    from app.services.lifestyle import lifestyle_guidance

    for condition in CONDITIONS:
        result = lifestyle_guidance(conditions=(condition,))
        assert result.text, condition
        assert result.safety_verdict != "reject", condition
    for feature in FEATURES:
        result = lifestyle_guidance(features=(feature,))
        assert result.text, feature
        assert result.safety_verdict != "reject", feature


def test_further_reading_is_curated_and_carries_its_basis():
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(conditions=("Anemia",), features=("hemoglobin",))
    assert result.further_reading
    for reading in result.further_reading:
        assert reading.doc_id.startswith("life_")
        assert reading.basis
        assert reading.last_reviewed


def test_each_item_records_why_it_was_selected():
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(conditions=("Diabetes",), features=("hba1c",))
    diet = next(i for i in result.items if i.code == "GENERAL_BALANCED_DIET")
    assert "Diabetes" in diet.because_of_conditions
    assert "hba1c" in diet.because_of_features


def test_the_payload_says_it_was_not_generated():
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(conditions=("Diabetes",))
    assert result.generated is False
    assert result.source == "recommendation_catalog"


def test_module_26_contains_no_generation_path():
    source = Path("app/services/lifestyle.py").read_text(encoding="utf-8")
    for forbidden in (
        "generate_text",
        "gemini",
        "guarded_generation",
        "prompts.explanation_prompt",
        "GeminiTextClient",
    ):
        assert forbidden not in source, forbidden


def test_the_guidance_route_takes_no_llm_dependency():
    import inspect

    from app.api.routes_explain import guidance

    parameters = inspect.signature(guidance).parameters
    assert "llm" not in parameters


def test_the_published_policy_states_that_no_model_is_used():
    from app.services.lifestyle import guidance_policy_document

    document = guidance_policy_document()
    assert document["module"] == 26
    assert document["uses_llm"] is False


def test_no_caller_supplied_text_can_reach_the_output():
    import inspect

    from app.services.lifestyle import lifestyle_guidance

    parameters = set(inspect.signature(lifestyle_guidance).parameters)
    assert parameters == {"conditions", "features", "codes"}


def test_an_unknown_code_is_reported_not_served():
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(codes=("NOT_A_REAL_CODE", "'; DROP TABLE --"))
    assert "NOT_A_REAL_CODE" in result.unknown_codes
    assert all(i.code != "NOT_A_REAL_CODE" for i in result.items)


def test_a_non_educational_code_is_refused():
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(codes=("INPUT_QUALITY_CAVEAT",))
    assert "INPUT_QUALITY_CAVEAT" in result.unknown_codes
    assert all(i.code != "INPUT_QUALITY_CAVEAT" for i in result.items)


def test_an_unknown_condition_is_reported_rather_than_silently_dropped():
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(conditions=("diabetes", "Diabetes"))
    assert result.unknown_conditions == ("diabetes",)
    assert result.conditions == ("Diabetes",)


def test_an_unknown_feature_is_reported():
    from app.services.lifestyle import lifestyle_guidance

    result = lifestyle_guidance(features=("tsh", "hba1c"))
    assert result.unknown_features == ("tsh",)


def test_band_specific_recommendations_are_unreachable():
    from app.data.conditions import CONDITIONS
    from app.data.feature_catalog import FEATURES
    from app.services.lifestyle import guidance_codes, lifestyle_guidance

    reachable = set()
    reachable |= set(
        guidance_codes(conditions=tuple(CONDITIONS), features=tuple(FEATURES))
    )
    for code in ("SEEK_PROMPT_MEDICAL_ADVICE", "UNREADABLE_DOCUMENT_RECHECK"):
        assert code not in reachable, code
        result = lifestyle_guidance(codes=(code,))
        assert all(i.code != code for i in result.items)


def test_the_guidance_never_instructs_or_prescribes():
    from app.data.conditions import CONDITIONS
    from app.services.lifestyle import lifestyle_guidance

    for condition in CONDITIONS:
        text = (lifestyle_guidance(conditions=(condition,)).text or "").lower()
        for forbidden in (
            " mg ",
            "dose",
            "dosage",
            "prescrib",
            "you must",
            "stop taking",
            "you should take",
        ):
            assert forbidden not in text, (condition, forbidden)


def test_guidance_takes_no_patient_value_of_any_kind():
    import inspect

    from app.services.lifestyle import lifestyle_guidance

    for name in inspect.signature(lifestyle_guidance).parameters:
        assert "value" not in name
        assert "result" not in name


def test_the_same_request_always_produces_the_same_guidance():
    from app.services.lifestyle import lifestyle_guidance

    first = lifestyle_guidance(conditions=("Diabetes", "Obesity"), features=("bmi",))
    second = lifestyle_guidance(conditions=("Diabetes", "Obesity"), features=("bmi",))
    assert first.model_dump() == second.model_dump()


def test_no_phi_is_logged(caplog):
    import logging

    from app.services.lifestyle import lifestyle_guidance

    caplog.set_level(logging.DEBUG)
    lifestyle_guidance(conditions=("Diabetes",), features=("hba1c",))
    logged = "\n".join(r.getMessage() for r in caplog.records)
    assert "balanced" not in logged.lower()
