from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from zipfile import ZipFile

from protocol_poc.reliability.manifest import (
    CorrectionSpec,
    ExpectedArtifact,
    ExpectedBlocker,
    ExpectedFact,
    PilotManifest,
)
from protocol_poc.rendering.template_map import build_template, deterministic_package


SECTIONS = ["synopsis", "objectives_endpoints", "study_design", "eligibility"]
ARTIFACTS = (
    ExpectedArtifact(
        name="protocol.docx",
        media_type=(
            "application/vnd.openxmlformats-officedocument."
            "wordprocessingml.document"
        ),
    ),
    ExpectedArtifact(name="traceability.csv", media_type="text/csv"),
    ExpectedArtifact(name="scorecard.html", media_type="text/html"),
)


@dataclass(frozen=True, slots=True)
class SynopsisSource:
    identity_heading: str
    short_title: str
    objectives_heading: str
    objective: str
    endpoints_heading: str
    endpoint: str
    arms_heading: str
    arm: str
    intervention: str
    dose: str | None
    population_heading: str
    population: str
    eligibility_heading: str
    eligibility: str
    duration: str | None

    def paragraphs(self) -> tuple[tuple[str, bool], ...]:
        arm_line = f"Arm: {self.arm}; Intervention: {self.intervention}"
        if self.dose is not None:
            arm_line += f" {self.dose} mg once daily"
        paragraphs: tuple[tuple[str, bool], ...] = (
            (self.identity_heading, True),
            (f"Short title: {self.short_title}", False),
            (self.objectives_heading, True),
            (f"Objective: {self.objective}", False),
            (self.endpoints_heading, True),
            (f"Endpoint: {self.endpoint}", False),
            (self.arms_heading, True),
            (arm_line, False),
            (self.population_heading, True),
            (f"Population: {self.population}", False),
            (self.eligibility_heading, True),
            (f"Eligibility: {self.eligibility}", False),
        )
        if self.duration is not None:
            paragraphs += ((f"Duration: {self.duration}", False),)
        return paragraphs


@dataclass(frozen=True, slots=True)
class StudyDeclaration:
    study_key: str
    study_name: str
    synopsis: SynopsisSource
    expected_facts: tuple[ExpectedFact, ...]
    expected_passages: dict[str, str]
    initial_outcome: str = "direct_success"
    initial_synopsis: SynopsisSource | None = None
    broken_template: bool = False
    expected_blockers: tuple[ExpectedBlocker, ...] = ()
    expected_next_action: str = "review_facts"
    correction: CorrectionSpec | None = None
    unsupported_edit: dict[str, str] | None = None


def _paragraph(text: str, heading: bool) -> str:
    style = '<w:pPr><w:pStyle w:val="Heading1"/></w:pPr>' if heading else ""
    return f"<w:p>{style}<w:r><w:t>{escape(text)}</w:t></w:r></w:p>"


def build_synopsis(source: SynopsisSource) -> bytes:
    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<w:body>"
        + "".join(_paragraph(text, heading) for text, heading in source.paragraphs())
        + '<w:sectPr><w:headerReference w:type="default" r:id="rId1"/>'
        '<w:footerReference w:type="default" r:id="rId2"/>'
        '<w:pgSz w:w="12240" w:h="15840"/>'
        '<w:pgMar w:top="1440" w:right="1440" w:bottom="1440" w:left="1440" '
        'w:header="708" w:footer="708" w:gutter="0"/></w:sectPr>'
        "</w:body></w:document>"
    ).encode()
    with ZipFile(BytesIO(build_template([]))) as archive:
        entries = {name: archive.read(name) for name in archive.namelist()}
    entries["word/document.xml"] = document
    return deterministic_package(entries)


def _string_fact(kind: str, value: str) -> ExpectedFact:
    return ExpectedFact(kind=kind, value={"kind": "string", "value": value})


def _facts(source: SynopsisSource) -> tuple[ExpectedFact, ...]:
    endpoint, timepoint = source.endpoint.rsplit(" at ", 1)
    facts: tuple[ExpectedFact, ...] = (
        _string_fact("study_identity", source.short_title),
        _string_fact("objective", source.objective),
        _string_fact("endpoint", endpoint),
        _string_fact("timepoint", timepoint),
        _string_fact("arm", source.arm),
        _string_fact("intervention", source.intervention),
        ExpectedFact(
            kind="dose",
            value={
                "kind": "dose",
                "value": source.dose,
                "unit": "mg",
                "frequency": "once daily",
            },
            critical=True,
        ),
        _string_fact("population", source.population),
        ExpectedFact(
            kind="eligibility",
            value={"kind": "structured_criterion", "value": {"text": source.eligibility}},
            critical=True,
        ),
    )
    if source.duration is not None:
        facts += (_string_fact("duration", source.duration),)
    return tuple(
        fact
        for critical in (True, False)
        for fact in facts
        if fact.critical is critical
    )


def _passages(source: SynopsisSource) -> dict[str, str]:
    endpoint, timepoint = source.endpoint.rsplit(" at ", 1)
    design = (
        f"{source.arm} receives {source.intervention}, {source.dose} mg once daily"
    )
    design += f", for {source.duration}." if source.duration is not None else "."
    return {
        "synopsis": (
            f"{source.short_title} is a synthetic study in {source.population}."
        ),
        "objectives_endpoints": (
            f"The objective is to {source.objective}; the endpoint is {endpoint} at {timepoint}."
        ),
        "study_design": design,
        "eligibility": f"Eligibility is limited to {source.eligibility}.",
    }


def _source(
    *,
    short_title: str,
    objective: str,
    endpoint: str,
    arm: str,
    intervention: str,
    dose: str | None,
    population: str,
    eligibility: str,
    duration: str | None,
    identity_heading: str = "Study Identity",
    objectives_heading: str = "Objectives",
    endpoints_heading: str = "Endpoints",
    arms_heading: str = "Arms and Interventions",
    population_heading: str = "Population",
    eligibility_heading: str = "Eligibility",
) -> SynopsisSource:
    return SynopsisSource(
        identity_heading=identity_heading,
        short_title=short_title,
        objectives_heading=objectives_heading,
        objective=objective,
        endpoints_heading=endpoints_heading,
        endpoint=endpoint,
        arms_heading=arms_heading,
        arm=arm,
        intervention=intervention,
        dose=dose,
        population_heading=population_heading,
        population=population,
        eligibility_heading=eligibility_heading,
        eligibility=eligibility,
        duration=duration,
    )


STANDARD = _source(
    short_title="REL-STD-01",
    objective="Evaluate synthetic symptom score change",
    endpoint="Change from baseline at Week 24",
    arm="Reference arm",
    intervention="Synthetic Compound Alpha",
    dose="10",
    population="Adults with synthetic condition Alpha",
    eligibility="Adults aged 18 through 75 years with synthetic condition Alpha",
    duration="24 weeks",
)
VOCABULARY = _source(
    short_title="REL-VOC-02",
    objective="Evaluate synthetic response durability",
    endpoint="Sustained response at Week 18",
    arm="Active arm",
    intervention="Synthetic Compound Beta",
    dose="25",
    population="Adults with synthetic condition Beta",
    eligibility="Adults aged 21 through 70 years with synthetic condition Beta",
    duration="18 weeks",
    identity_heading="  STUDY   IDENTITY  ",
    objectives_heading="OBJECTIVES",
    endpoints_heading="ENDPOINTS",
    arms_heading="ARMS / INTERVENTIONS",
    population_heading="Study Population",
    eligibility_heading="Eligibility Criteria",
)
VALUE_VARIATION = _source(
    short_title="REL-VAL-03",
    objective="Assess synthetic marker change",
    endpoint="Synthetic marker change at Week 12",
    arm="Low-dose arm",
    intervention="Synthetic Compound Gamma",
    dose="7.5",
    population="Adults with synthetic condition Gamma",
    eligibility="Adults aged 30 through 65 years with synthetic condition Gamma",
    duration="1 week",
)
MISSING_DOSE_CORRECTED = _source(
    short_title="REL-COR-04",
    objective="Evaluate synthetic correction response",
    endpoint="Correction response at Week 16",
    arm="Correction arm",
    intervention="Synthetic Compound Delta",
    dose="12",
    population="Adults with synthetic condition Delta",
    eligibility="Adults aged 25 through 68 years with synthetic condition Delta",
    duration="16 weeks",
)
MISSING_DOSE_INITIAL = _source(
    short_title="REL-COR-04",
    objective="Evaluate synthetic correction response",
    endpoint="Correction response at Week 16",
    arm="Correction arm",
    intervention="Synthetic Compound Delta",
    dose=None,
    population="Adults with synthetic condition Delta",
    eligibility="Adults aged 25 through 68 years with synthetic condition Delta",
    duration="16 weeks",
)
BROKEN_TEMPLATE = _source(
    short_title="REL-TPL-05",
    objective="Evaluate synthetic template recovery",
    endpoint="Template recovery response at Week 8",
    arm="Template arm",
    intervention="Synthetic Compound Epsilon",
    dose="8",
    population="Adults with synthetic condition Epsilon",
    eligibility="Adults aged 20 through 72 years with synthetic condition Epsilon",
    duration="8 weeks",
)
UNSUPPORTED_EDIT = _source(
    short_title="REL-EDIT-06",
    objective="Evaluate synthetic passage correction",
    endpoint="Passage correction response at Week 14",
    arm="Passage arm",
    intervention="Synthetic Compound Zeta",
    dose="14",
    population="Adults with synthetic condition Zeta",
    eligibility="Adults aged 22 through 74 years with synthetic condition Zeta",
    duration="14 weeks",
)


DECLARATIONS = (
    StudyDeclaration(
        "standard",
        "Reliability 1 - Standard synthetic study",
        STANDARD,
        _facts(STANDARD),
        _passages(STANDARD),
    ),
    StudyDeclaration(
        "vocabulary-variation",
        "Reliability 2 - Vocabulary variation",
        VOCABULARY,
        _facts(VOCABULARY),
        _passages(VOCABULARY),
    ),
    StudyDeclaration(
        "value-variation",
        "Reliability 3 - Value variation",
        VALUE_VARIATION,
        _facts(VALUE_VARIATION),
        _passages(VALUE_VARIATION),
    ),
    StudyDeclaration(
        "missing-dose",
        "Reliability 4 - Missing dose recovery",
        MISSING_DOSE_CORRECTED,
        _facts(MISSING_DOSE_CORRECTED),
        _passages(MISSING_DOSE_CORRECTED),
        initial_outcome="blocked_then_recover",
        initial_synopsis=MISSING_DOSE_INITIAL,
        expected_blockers=(
            ExpectedBlocker(
                code="SYNOPSIS_DOSE_MISSING",
                affected_area="arms_interventions",
                next_action="upload_synopsis",
            ),
        ),
        expected_next_action="upload_synopsis",
        correction=CorrectionSpec(
            kind="replace_synopsis", filename="corrected-synopsis.docx"
        ),
    ),
    StudyDeclaration(
        "broken-template",
        "Reliability 5 - Broken template recovery",
        BROKEN_TEMPLATE,
        _facts(BROKEN_TEMPLATE),
        _passages(BROKEN_TEMPLATE),
        initial_outcome="blocked_then_recover",
        broken_template=True,
        expected_blockers=(
            ExpectedBlocker(
                code="TEMPLATE_TOKEN_MISSING",
                affected_area="eligibility",
                next_action="upload_template",
            ),
        ),
        expected_next_action="upload_template",
        correction=CorrectionSpec(
            kind="upload_corrected_template", filename="corrected-template.docx"
        ),
    ),
    StudyDeclaration(
        "unsupported-passage-edit",
        "Reliability 6 - Unsupported passage edit recovery",
        UNSUPPORTED_EDIT,
        _facts(UNSUPPORTED_EDIT),
        _passages(UNSUPPORTED_EDIT),
        initial_outcome="blocked_then_recover",
        expected_blockers=(
            ExpectedBlocker(
                code="UNSUPPORTED_DOSE",
                affected_area="study_design",
                next_action="review_passages",
            ),
        ),
        expected_next_action="review_passages",
        correction=CorrectionSpec(kind="regenerate_passage", section="study_design"),
        unsupported_edit={
            "section": "study_design",
            "supported_value": "14 mg",
            "unsupported_value": "99 mg",
            "finding_code": "UNSUPPORTED_DOSE",
        },
    ),
)


def _write_pack(root: Path, declaration: StudyDeclaration) -> Path:
    directory = root / declaration.study_key
    directory.mkdir(parents=True, exist_ok=True)
    for existing in directory.iterdir():
        if existing.is_file():
            existing.unlink()

    initial_synopsis = declaration.initial_synopsis or declaration.synopsis
    files = {
        "synopsis": ("synopsis.docx", build_synopsis(initial_synopsis)),
        "template": (
            "template.docx",
            build_template(SECTIONS[:-1] if declaration.broken_template else SECTIONS),
        ),
    }
    if declaration.initial_synopsis is not None:
        files["corrected_synopsis"] = (
            "corrected-synopsis.docx",
            build_synopsis(declaration.synopsis),
        )
    if declaration.broken_template:
        files["corrected_template"] = (
            "corrected-template.docx",
            build_template(SECTIONS),
        )

    inputs: dict[str, str] = {}
    hashes: dict[str, str] = {}
    for logical_name, (filename, content) in files.items():
        (directory / filename).write_bytes(content)
        inputs[logical_name] = filename
        hashes[logical_name] = sha256(content).hexdigest()

    manifest = PilotManifest(
        schema_version=1,
        study_key=declaration.study_key,
        study_name=declaration.study_name,
        initial_outcome=declaration.initial_outcome,  # type: ignore[arg-type]
        inputs=inputs,
        input_sha256=hashes,
        expected_facts=declaration.expected_facts,
        expected_blockers=declaration.expected_blockers,
        expected_next_action=declaration.expected_next_action,
        correction=declaration.correction,
        expected_current_versions={
            "synopsis": 2 if declaration.initial_synopsis is not None else 1,
            "template": 2 if declaration.broken_template else 1,
        },
        expected_passages=declaration.expected_passages,
        unsupported_edit=declaration.unsupported_edit,
        expected_artifacts=ARTIFACTS,
    )
    manifest_path = directory / "manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest_path


def build_reliability_fixtures(root: Path) -> tuple[Path, ...]:
    root.mkdir(parents=True, exist_ok=True)
    return tuple(_write_pack(root, declaration) for declaration in DECLARATIONS)
