"""
Golden/contract-style tests for spec-accuracy enforcement.
These tests validate that the system does NOT silently pass on template/JSON/Not-specified violations.
"""

from pathlib import Path
import re

import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from pipeline.validator import CSRValidator
from pipeline.csr_generator import CSRGenerator


def _base_generation_context(expected_heading: str, required_elements: list[str], prohibited_phrases: list[str]):
    return {
        "template": {"heading": expected_heading, "structure_order": ["A", "B"]},
        "required_elements": required_elements,
        "prohibited_phrases": prohibited_phrases,
        "section_title": expected_heading,
    }


class TestStructureExactEnforcement:
    def test_subsection_order_violation_fails(self):
        v = CSRValidator()
        expected_heading = "9.1 Study Design"
        expected_subsections = ["A", "B"]

        content = "\n".join(
            [
                expected_heading,
                "1. B",
                "This is content under B.",
                "2. A",
                "This is content under A.",
            ]
        )

        r = v.validate_structure("study_design", content, expected_subsections, expected_heading=expected_heading)
        assert r["passed"] is False
        assert any(i["severity"] == "error" for i in r.get("issues", []))

    def test_extra_subsection_detected_as_error(self):
        v = CSRValidator()
        expected_heading = "9.1 Study Design"
        expected_subsections = ["A", "B"]

        content = "\n".join(
            [
                expected_heading,
                "1. A",
                "Content A.",
                "2. B",
                "Content B.",
                "3. Extra",
                "Extra content.",
            ]
        )

        r = v.validate_structure("study_design", content, expected_subsections, expected_heading=expected_heading)
        assert r["passed"] is False
        assert any(i["type"] in {"structure_subsections_extra", "structure_subsections_order"} for i in r.get("issues", []))


class TestNotSpecifiedPolicyEnforcement:
    def test_missing_element_without_not_specified_fails(self):
        v = CSRValidator()
        expected_heading = "9.1 Study Design"
        expected_subsections = ["A", "B"]

        content = "\n".join(
            [
                expected_heading,
                "1. A",
                "Evidence is present for A.",
                "2. B",
                "B is missing evidence but no fallback used.",
            ]
        )

        source_data = {
            "generation_context": _base_generation_context(
                expected_heading=expected_heading,
                required_elements=["element_b"],
                prohibited_phrases=[],
            ),
            "missing_elements": ["element_b"],
        }

        r = v.validate_section(
            section_id="study_design",
            content=content,
            source_data=source_data,
            expected_subsections=expected_subsections,
        )
        assert r["overall_passed"] is False
        assert r["error_count"] >= 1
        assert any(i["type"].startswith("not_specified") for i in r.get("all_issues", []))

    def test_not_specified_forbidden_when_no_missing_fails(self):
        v = CSRValidator()
        expected_heading = "9.1 Study Design"
        expected_subsections = ["A", "B"]

        content = "\n".join(
            [
                expected_heading,
                "1. A",
                "Evidence is present for A.",
                "2. B",
                "B was present, but model still wrote Not specified.",
                "Not specified.",
            ]
        )

        source_data = {
            "generation_context": _base_generation_context(
                expected_heading=expected_heading,
                required_elements=["element_a", "element_b"],
                prohibited_phrases=[],
            ),
            "missing_elements": [],
        }

        r = v.validate_section(
            section_id="study_design",
            content=content,
            source_data=source_data,
            expected_subsections=expected_subsections,
        )
        assert r["overall_passed"] is False
        assert any(
            i.get("severity") == "error" and i.get("type", "").startswith("not_specified")
            for i in r.get("all_issues", [])
        )

    def test_wrong_subsection_placement_fails_element_linked(self):
        v = CSRValidator()
        expected_heading = "9.1 Study Design"
        expected_subsections = ["A", "B"]

        # Element A is missing and linked to subsection A, but "Not specified." is placed in subsection B.
        content = "\n".join(
            [
                expected_heading,
                "1. A",
                "A has content but does not include fallback.",
                "2. B",
                "Not specified.",
            ]
        )

        source_data = {
            "generation_context": _base_generation_context(
                expected_heading=expected_heading,
                required_elements=["element_a"],
                prohibited_phrases=[],
            ),
            "missing_elements": ["element_a"],
            "element_map_rich": {
                "element_a": {"status": "missing", "value": None, "subsection": "A", "source_phrase": None}
            },
        }

        r = v.validate_section(
            section_id="study_design",
            content=content,
            source_data=source_data,
            expected_subsections=expected_subsections,
        )
        assert r["overall_passed"] is False
        assert any(i.get("type") == "not_specified_wrong_subsection" for i in r.get("all_issues", []))

    def test_both_missing_not_specified_pollution_fails(self):
        v = CSRValidator()
        expected_heading = "9.1 Study Design"
        expected_subsections = ["A", "B"]

        # Two elements missing, both linked to different subsections, but both fallbacks are placed in A only.
        content = "\n".join(
            [
                expected_heading,
                "1. A",
                "Not specified. Not specified.",
                "2. B",
                "B has no fallback.",
            ]
        )

        source_data = {
            "generation_context": _base_generation_context(
                expected_heading=expected_heading,
                required_elements=["element_a", "element_b"],
                prohibited_phrases=[],
            ),
            "missing_elements": ["element_a", "element_b"],
            "element_map_rich": {
                "element_a": {"status": "missing", "value": None, "subsection": "A", "source_phrase": None},
                "element_b": {"status": "missing", "value": None, "subsection": "B", "source_phrase": None},
            },
        }

        r = v.validate_section(
            section_id="study_design",
            content=content,
            source_data=source_data,
            expected_subsections=expected_subsections,
        )
        assert r["overall_passed"] is False
        assert any(i.get("type") == "not_specified_wrong_subsection" for i in r.get("all_issues", []))


class TestProhibitedPhrasesEnforcement:
    def test_prohibited_phrase_is_blocking_error(self):
        v = CSRValidator()
        expected_heading = "9.1 Study Design"
        expected_subsections = ["A", "B"]

        content = "\n".join(
            [
                expected_heading,
                "1. A",
                "This contains will be which must fail.",
                "2. B",
                "More content.",
            ]
        )

        source_data = {
            "generation_context": _base_generation_context(
                expected_heading=expected_heading,
                required_elements=["element_a"],
                prohibited_phrases=["will be"],
            ),
            "missing_elements": [],
        }

        r = v.validate_section(
            section_id="study_design",
            content=content,
            source_data=source_data,
            expected_subsections=expected_subsections,
        )
        assert r["overall_passed"] is False
        assert r["error_count"] >= 1
        assert any(i["type"] == "prohibited_phrase" for i in r.get("all_issues", []))


class TestStrictJSONParsing:
    def test_strict_array_fails_on_extra_text(self):
        with pytest.raises(ValueError):
            CSRGenerator._parse_json_array_response_strict('[{"x":1}] trailing')

    def test_strict_object_fails_when_not_pure_json(self):
        with pytest.raises(ValueError):
            CSRGenerator._parse_json_object_response_strict('prefix {"x": 1}')


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

