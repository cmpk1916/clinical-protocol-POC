from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from protocol_poc.ingest.docx_parser import DocxParser
from protocol_poc.reliability.fixtures import build_reliability_fixtures
from protocol_poc.reliability.manifest import load_pilot_manifests
from protocol_poc.studies.document_contract import DocumentContract
from protocol_poc.studies.local_extractor import LocalExtractor


CHECKED_IN_FIXTURES = Path(__file__).parents[4] / "fixtures" / "reliability-pilot"


@dataclass(frozen=True)
class Evidence:
    id: str
    text: str


def _evidence(path: Path) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(f"paragraph-{index}", item.text)
        for index, item in enumerate(DocxParser().parse(path.read_bytes()))
    )


def _files(root: Path) -> dict[Path, bytes]:
    return {
        path.relative_to(root): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def test_builder_is_byte_identical_and_hashes_match_manifests(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"

    build_reliability_fixtures(first)
    build_reliability_fixtures(second)

    assert _files(first) == _files(second)
    for manifest in load_pilot_manifests(first):
        pack = first / manifest.study_key
        for logical_name, filename in manifest.inputs.items():
            assert sha256((pack / filename).read_bytes()).hexdigest() == (
                manifest.input_sha256[logical_name]
            )


def test_checked_in_packs_exactly_match_a_fresh_build(tmp_path: Path) -> None:
    rebuilt = tmp_path / "rebuilt"

    build_reliability_fixtures(rebuilt)

    assert _files(CHECKED_IN_FIXTURES) == _files(rebuilt)


def test_six_packs_have_only_the_declared_files_and_outcomes(tmp_path: Path) -> None:
    build_reliability_fixtures(tmp_path)
    manifests = {item.study_key: item for item in load_pilot_manifests(tmp_path)}

    assert {path.name for path in (tmp_path / "standard").iterdir()} == {
        "manifest.json",
        "synopsis.docx",
        "template.docx",
    }
    assert {path.name for path in (tmp_path / "missing-dose").iterdir()} == {
        "manifest.json",
        "synopsis.docx",
        "template.docx",
        "corrected-synopsis.docx",
    }
    assert {path.name for path in (tmp_path / "broken-template").iterdir()} == {
        "manifest.json",
        "synopsis.docx",
        "template.docx",
        "corrected-template.docx",
    }
    assert manifests["missing-dose"].expected_blockers[0].code == (
        "SYNOPSIS_DOSE_MISSING"
    )
    assert manifests["broken-template"].expected_blockers[0].code == (
        "TEMPLATE_TOKEN_MISSING"
    )
    assert manifests["unsupported-passage-edit"].unsupported_edit == {
        "section": "study_design",
        "supported_value": "14 mg",
        "unsupported_value": "99 mg",
        "finding_code": "UNSUPPORTED_DOSE",
    }


def test_corrected_or_valid_synopses_match_all_gold_facts(tmp_path: Path) -> None:
    build_reliability_fixtures(tmp_path)

    for manifest in load_pilot_manifests(tmp_path):
        synopsis_name = (
            manifest.inputs["corrected_synopsis"]
            if "corrected_synopsis" in manifest.inputs
            else manifest.inputs["synopsis"]
        )
        evidence = _evidence(tmp_path / manifest.study_key / synopsis_name)

        assert DocumentContract().validate_synopsis(evidence) == ()
        proposal = LocalExtractor().extract(evidence)
        assert proposal.findings == ()
        extracted = [
            {
                "kind": candidate.kind,
                "value": candidate.value_json,
                "critical": candidate.critical,
            }
            for candidate in proposal.candidates
        ]
        assert sorted(extracted, key=lambda item: not item["critical"]) == [
            fact.model_dump() for fact in manifest.expected_facts
        ]


def test_initial_mistake_documents_fail_for_only_the_declared_reason(
    tmp_path: Path,
) -> None:
    build_reliability_fixtures(tmp_path)

    missing_dose = _evidence(tmp_path / "missing-dose" / "synopsis.docx")
    assert DocumentContract().validate_synopsis(missing_dose) == ()
    assert [
        (item.code, item.field)
        for item in LocalExtractor().extract(missing_dose).findings
    ] == [("SYNOPSIS_DOSE_MISSING", "arms_interventions")]

    broken_template = _evidence(tmp_path / "broken-template" / "template.docx")
    assert [
        (item.code, item.field)
        for item in DocumentContract().validate_template(broken_template)
    ] == [("TEMPLATE_TOKEN_MISSING", "eligibility")]

    corrected_template = _evidence(
        tmp_path / "broken-template" / "corrected-template.docx"
    )
    assert DocumentContract().validate_template(corrected_template) == ()


def test_supported_variations_are_present_as_literal_user_inputs(tmp_path: Path) -> None:
    build_reliability_fixtures(tmp_path)

    vocabulary = [
        item.text
        for item in DocxParser().parse(
            (tmp_path / "vocabulary-variation" / "synopsis.docx").read_bytes()
        )
    ]
    values = [
        item.text
        for item in DocxParser().parse(
            (tmp_path / "value-variation" / "synopsis.docx").read_bytes()
        )
    ]

    assert "ARMS / INTERVENTIONS" in vocabulary
    assert "Study Population" in vocabulary
    assert "Eligibility Criteria" in vocabulary
    with ZipFile(
        BytesIO((tmp_path / "vocabulary-variation" / "synopsis.docx").read_bytes())
    ) as package:
        document_xml = package.read("word/document.xml").decode()
    assert "<w:t>  STUDY   IDENTITY  </w:t>" in document_xml
    assert "Arm: Low-dose arm; Intervention: Synthetic Compound Gamma 7.5 mg once daily" in values
    assert "Endpoint: Synthetic marker change at Week 12" in values
    assert "Duration: 1 week" in values
