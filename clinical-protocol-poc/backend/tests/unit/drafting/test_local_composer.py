from protocol_poc.drafting.local_composer import LocalComposer


def approved_fact_inputs() -> dict[str, dict[str, object]]:
    return {
        "identity-a": {"kind": "study_identity", "value": "SYN-1"},
        "population-a": {"kind": "population", "value": "Adults with synthetic condition"},
        "objective-a": {"kind": "objective", "value": "Evaluate response"},
        "endpoint-a": {"kind": "endpoint", "value": "Response"},
        "timepoint-a": {"kind": "timepoint", "value": "Week 24"},
        "arm-a": {"kind": "arm", "value": "Arm A"},
        "intervention-a": {"kind": "intervention", "value": "Synthetic Intervention A"},
        "dose-a": {"kind": "dose", "value": "10", "unit": "mg", "frequency": "once daily"},
        "duration-a": {"fact_kind": "duration", "kind": "string", "value": "24 weeks"},
        "eligibility-a": {"fact_kind": "eligibility", "kind": "structured_criterion", "value": {"text": "Age 18 years or older"}},
    }


def test_local_composer_uses_only_approved_fact_values() -> None:
    output = LocalComposer().compose("study_design", approved_fact_inputs())

    assert output.text == "Arm A receives Synthetic Intervention A, 10 mg once daily, for 24 weeks."
    assert set(output.fact_ids) == {"arm-a", "intervention-a", "dose-a", "duration-a"}
    assert "20 mg" not in output.text
    assert output.claims == ({"text": output.text, "fact_ids": ["arm-a", "intervention-a", "dose-a", "duration-a"]},)


def test_local_composer_uses_fixed_templates_for_every_scoped_section() -> None:
    composer = LocalComposer()
    facts = approved_fact_inputs()

    assert composer.compose("synopsis", facts).text == "SYN-1 is a synthetic study in Adults with synthetic condition."
    assert composer.compose("objectives_endpoints", facts).text == "The objective is to Evaluate response; the endpoint is Response at Week 24."
    assert composer.compose("eligibility", facts).text == "Eligibility is limited to Age 18 years or older."


def test_local_composer_fails_closed_when_required_fact_is_absent() -> None:
    facts = approved_fact_inputs()
    facts.pop("duration-a")

    output = LocalComposer().compose("study_design", facts)

    assert output.text == "[[REQUIRED: study duration]]"
    assert output.placeholders == ("[[REQUIRED: study duration]]",)
    assert output.claims == ()
    assert output.fact_ids == ()
