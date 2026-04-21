"""
Basic Validator — Layer 8
─────────────────────────
Lightweight validation for generated CSR section outputs.

Checks:
  ✔ Output not empty
  ✔ Output length is reasonable
  ✔ No hallucination marker phrases
  ✔ Past tense usage (basic heuristic)
  ✔ No prohibited speculative language

This is a fast, rule-based validator that runs BEFORE the full
pipeline.validator.CSRValidator. It catches obvious issues early.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

# Minimum acceptable output length per section (in characters)
MIN_OUTPUT_LENGTH = 100

# Phrases that signal hallucination or speculation
HALLUCINATION_MARKERS = [
    "not provided",
    "assumed",
    "unknown",
    "typically",
    "generally",
    "it is expected",
    "usually",
    "commonly",
    "in most cases",
    "as is standard practice",
    "based on clinical experience",
    "it can be inferred",
    "presumably",
    "we can assume",
    "this is likely",
]

# Present-tense verbs that should be past-tense in a completed study
PRESENT_TENSE_MARKERS = [
    r"\bthe study is\b",
    r"\bpatients are\b",
    r"\bsubjects are\b",
    r"\bthe treatment is\b",
    r"\bwe will\b",
    r"\bthe investigators will\b",
]


@dataclass
class ValidationResult:
    """Result of basic validation for a single section."""
    section_id: str
    passed: bool
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metrics: Dict[str, any] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "section_id": self.section_id,
            "passed": self.passed,
            "issues": self.issues,
            "warnings": self.warnings,
            "metrics": self.metrics,
        }


class BasicValidator:
    """Fast rule-based validator for generated CSR sections."""

    def __init__(
        self,
        min_length: int = MIN_OUTPUT_LENGTH,
        hallucination_markers: Optional[List[str]] = None,
    ):
        self.min_length = min_length
        self.markers = hallucination_markers or HALLUCINATION_MARKERS
        self.results: Dict[str, ValidationResult] = {}

    # ── Individual checks ────────────────────────────────────────────

    @staticmethod
    def check_empty(text: str) -> Optional[str]:
        """Check if output is empty or whitespace-only."""
        if not text or not text.strip():
            return "Output is empty."
        return None

    def check_length(self, text: str) -> Optional[str]:
        """Check if output meets minimum length requirement."""
        if len(text.strip()) < self.min_length:
            return (
                f"Output too short ({len(text.strip())} chars, "
                f"minimum {self.min_length})."
            )
        return None

    def check_hallucination_markers(self, text: str) -> List[str]:
        """Detect hallucination-indicating phrases."""
        lower = text.lower()
        found = []
        for marker in self.markers:
            if marker in lower:
                found.append(f"Hallucination marker detected: '{marker}'")
        return found

    @staticmethod
    def check_tense(text: str) -> List[str]:
        """Detect present-tense usage that should be past-tense."""
        warnings = []
        lower = text.lower()
        for pattern in PRESENT_TENSE_MARKERS:
            matches = re.findall(pattern, lower)
            if matches:
                warnings.append(
                    f"Present tense detected ({len(matches)}x): "
                    f"'{matches[0]}' — should be past tense."
                )
        return warnings

    @staticmethod
    def check_coverage(text: str) -> Dict[str, any]:
        """Compute basic coverage metrics."""
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        total = len(lines)
        not_specified = sum(
            1 for l in lines if "not specified" in l.lower()
        )
        coverage_pct = round(((total - not_specified) / max(total, 1)) * 100, 1)
        return {
            "total_lines": total,
            "not_specified_lines": not_specified,
            "coverage_pct": coverage_pct,
            "char_count": len(text.strip()),
            "word_count": len(text.split()),
        }

    # ── Main validation API ──────────────────────────────────────────

    def validate_section(self, section_id: str, text: str) -> ValidationResult:
        """
        Run all validation checks on a single section.

        Args:
            section_id: CSR section identifier.
            text: Generated text to validate.

        Returns:
            ValidationResult with pass/fail, issues, and metrics.
        """
        issues: List[str] = []
        warnings: List[str] = []

        # Check 1: Empty
        empty_issue = self.check_empty(text)
        if empty_issue:
            result = ValidationResult(
                section_id=section_id,
                passed=False,
                issues=[empty_issue],
                metrics={"char_count": 0},
            )
            self.results[section_id] = result
            return result

        # Check 2: Length
        length_issue = self.check_length(text)
        if length_issue:
            issues.append(length_issue)

        # Check 3: Hallucination markers
        hall_issues = self.check_hallucination_markers(text)
        issues.extend(hall_issues)

        # Check 4: Tense
        tense_warnings = self.check_tense(text)
        warnings.extend(tense_warnings)

        # Metrics
        metrics = self.check_coverage(text)

        # Low coverage warning
        if metrics["coverage_pct"] < 40:
            warnings.append(
                f"Very low evidence coverage: {metrics['coverage_pct']}% "
                f"({metrics['not_specified_lines']}/{metrics['total_lines']} "
                f"lines contain 'not specified')."
            )

        # Determine pass/fail — hallucination markers are hard fails
        passed = not any("Hallucination" in i for i in issues)
        # Empty or too-short is also a hard fail
        if any("empty" in i.lower() or "too short" in i.lower() for i in issues):
            passed = False

        result = ValidationResult(
            section_id=section_id,
            passed=passed,
            issues=issues,
            warnings=warnings,
            metrics=metrics,
        )
        self.results[section_id] = result

        logger.info(
            "BasicValidator [%s]: %s — %d issues, %d warnings",
            section_id,
            "PASS" if passed else "FAIL",
            len(issues),
            len(warnings),
        )
        return result

    def validate_all(self, sections: Dict[str, str]) -> Dict[str, ValidationResult]:
        """
        Validate all generated sections.

        Args:
            sections: {section_id: generated_text}

        Returns:
            {section_id: ValidationResult}
        """
        for sid, text in sections.items():
            self.validate_section(sid, text)
        return self.results

    def get_summary(self) -> Dict:
        """Return a summary of all validation results."""
        passed = sum(1 for r in self.results.values() if r.passed)
        failed = sum(1 for r in self.results.values() if not r.passed)
        return {
            "total": len(self.results),
            "passed": passed,
            "failed": failed,
            "sections": {
                sid: r.to_dict() for sid, r in self.results.items()
            },
        }
