from protocol_poc.validation.relationships import (
    ArmInterventionRelationship,
    EndpointRelationship,
    validate_arm_interventions,
    validate_relationships,
)


def test_endpoint_timepoint_mismatch_is_blocker() -> None:
    findings = validate_relationships(
        [EndpointRelationship("primary endpoint", "Week 24")],
        [EndpointRelationship("primary endpoint", "Week 12")],
    )
    assert [(finding.code, finding.severity) for finding in findings] == [
        ("ENDPOINT_TIMEPOINT_MISMATCH", "blocker")
    ]


def test_arm_intervention_mismatch_is_blocker() -> None:
    findings = validate_arm_interventions(
        [ArmInterventionRelationship("Arm A", "Drug Y")],
        [ArmInterventionRelationship("Arm A", "Drug X")],
    )
    assert [item.code for item in findings] == ["ARM_INTERVENTION_MISMATCH"]
