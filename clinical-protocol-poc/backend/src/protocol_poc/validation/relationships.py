from dataclasses import dataclass

from protocol_poc.validation.findings import Finding


@dataclass(frozen=True)
class EndpointRelationship:
    endpoint: str
    timepoint: str


@dataclass(frozen=True)
class ArmInterventionRelationship:
    arm: str
    intervention: str


def validate_relationships(claimed: list[EndpointRelationship], approved: list[EndpointRelationship]) -> list[Finding]:
    approved_by_endpoint = {item.endpoint.casefold(): item.timepoint.casefold() for item in approved}
    findings: list[Finding] = []
    for relationship in claimed:
        if approved_by_endpoint.get(relationship.endpoint.casefold()) != relationship.timepoint.casefold():
            findings.append(Finding("ENDPOINT_TIMEPOINT_MISMATCH", "blocker", "Endpoint and timepoint relationship does not match approved facts"))
    return findings


def validate_arm_interventions(
    claimed: list[ArmInterventionRelationship], approved: list[ArmInterventionRelationship]
) -> list[Finding]:
    approved_by_arm = {item.arm.casefold(): item.intervention.casefold() for item in approved}
    return [
        Finding("ARM_INTERVENTION_MISMATCH", "blocker", "Arm and intervention relationship does not match approved facts")
        for item in claimed
        if approved_by_arm.get(item.arm.casefold()) != item.intervention.casefold()
    ]
