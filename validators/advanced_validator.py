"""
validators/advanced_validator.py
─────────────────────────────────
Explainable validation engine for generated CSR section text.

Returns a rich, human-readable validation report — not just a score.
Each validation dimension has its own check and explanation.

Validation dimensions:
  1. Structure check — required subsections present
  2. Tone check — formal, scientific, past-tense
  3. Completeness check — coverage of required elements
  4. Hallucination risk — speculative phrase detection
  5. Composite score (0–100)

This is ADDITIVE — it runs alongside the existing CSRValidator,
not instead of it.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional

from core.models.section_result import SectionValidation

logger = logging.getLogger(__name__)


# ── Hallucination phrase taxonomy ─────────────────────────────────────

HALLUCINATION_LOW_RISK = [
    "it is expected",
    "typically",
    "generally",
    "in general",
    "usually",
    "commonly",
]

HALLUCINATION_HIGH_RISK = [
    "we can assume",
    "presumably",
    "this is likely",
    "it can be inferred",
    "based on clinical experience",
    "as is standard practice",
    "not provided",
    "assumed",
    "unknown but probably",
]

# Present-tense patterns that should be past-tense
PRESENT_TENSE_PATTERNS = [
    (r"\bthe study is\b",         "study_status"),
    (r"\bpatients are\b",         "patient_tense"),
    (r"\bsubjects are\b",         "subject_tense"),
    (r"\bthe treatment is\b",     "treatment_tense"),
    (r"\bwe will\b",              "future_tense"),
    (r"\bwill be administered\b", "future_admin"),
    (r"\bis randomized\b",        "randomization_tense"),
]


class AdvancedValidator:
    """
    Produces an explainable, multi-dimensional validation report for
    a generated CSR section.
    """

    def __init__(
        self,
        hallucination_high_risk: Optional[List[str]] = None,
        hallucination_low_risk: Optional[List[str]] = None,
    ):
        self.high_risk = hallucination_high_risk or HALLUCINATION_HIGH_RISK
        self.low_risk = hallucination_low_risk or HALLUCINATION_LOW_RISK

    # ── Individual checks ────────────────────────────────────────────

    def _check_structure(
        self,
        text: str,
        expected_subsections: Optional[List[str]],
    ) -> tuple[bool, List[str]]:
        """Check if expected subsections are present in the output."""
        if not expected_subsections:
            return True, []

        warnings: List[str] = []
        lower = text.lower()
        missing_subs = []

        for sub in expected_subsections:
            key = sub.strip().lower()
            if key and key not in lower:
                missing_subs.append(sub)

        if missing_subs:
            warnings.append(
                f"Expected subsections not found in output: "
                f"{', '.join(missing_subs[:5])}"
            )

        ok = len(missing_subs) < len(expected_subsections) * 0.5
        return ok, warnings

    def _check_tone(self, text: str) -> tuple[bool, List[str]]:
        """Check for scientific past-tense tone."""
        warnings: List[str] = []
        lower = text.lower()

        tense_issues = []
        for pattern, label in PRESENT_TENSE_PATTERNS:
            matches = re.findall(pattern, lower)
            if matches:
                tense_issues.append(f"Present/future tense detected ({len(matches)}×): '{matches[0]}'")

        if tense_issues:
            warnings.extend(tense_issues[:3])

        ok = len(tense_issues) == 0
        return ok, warnings

    def _check_hallucination_risk(self, text: str) -> tuple[str, List[str]]:
        """
        Assess hallucination risk level and return explanatory warnings.
        Returns: ("low"|"medium"|"high", warning_list)
        """
        lower = text.lower()
        warnings: List[str] = []
        high_count = 0
        low_count = 0

        for phrase in self.high_risk:
            if phrase in lower:
                high_count += 1
                warnings.append(f"High-risk speculative phrase detected: '{phrase}'")

        for phrase in self.low_risk:
            if phrase in lower:
                low_count += 1
                warnings.append(f"Speculative phrase detected: '{phrase}'")

        if high_count >= 2:
            risk = "high"
        elif high_count == 1 or low_count >= 3:
            risk = "medium"
        else:
            risk = "low"

        return risk, warnings

    def _check_completeness(
        self,
        text: str,
        required_elements: Optional[List[str]],
        missing_elements: Optional[List[str]],
    ) -> tuple[float, List[str]]:
        """
        Heuristic coverage check — what % of required elements appear
        in the output. Evaluates using only non-missing elements.
        Returns: (coverage_pct, warnings)
        """
        if not required_elements:
            return 100.0, []

        missing = set(missing_elements or [])

        lower = text.lower()
        covered = 0
        valid_required = 0
        for el in required_elements:
            if el in missing:
                # Deliberately NOT covered because it is known to be missing.
                continue
            valid_required += 1
            val = el.strip().lower()
            if val in lower:
                covered += 1
            else:
                # Partial credit for finding major keywords
                words = [w for w in val.split() if len(w) > 4]
                if words and any(w in lower for w in words):
                    covered += 0.5

        if valid_required == 0:
            pct = 100.0
        else:
            pct = min(100.0, (covered / valid_required) * 100.0)
            
        warnings: List[str] = []

        if pct < 50:
            warnings.append(
                f"Low element coverage in output: "
                f"{covered}/{valid_required} required elements found ({pct:.0f}%)."
            )
        elif pct < 80:
            warnings.append(
                f"Moderate element coverage: "
                f"{covered}/{valid_required} elements found ({pct:.0f}%)."
            )

        return pct, warnings

    def _check_numeric_consistency(self, generated_text: str, source_evidence: str) -> tuple[bool, List[str]]:
        """
        Check if numbers generated by the LLM exist in the source evidence.
        """
        if not source_evidence:
            return True, []
            
        import re
        gen_nums = re.findall(r'\d+\.?\d*%?', generated_text)
        if not gen_nums:
            return True, []
            
        src_nums_raw = re.findall(r'\d+\.?\d*%?', source_evidence)
        
        # Convert to float for tolerance checking
        def parse_num(n):
            try: return float(n.replace('%', ''))
            except: return None
            
        src_vals = [parse_num(x) for x in src_nums_raw if parse_num(x) is not None]
        warnings = []
        is_consistent = True
        
        invalid_nums = []
        for num_str in gen_nums:
            val = parse_num(num_str)
            if val is not None:
                # Check absolute difference tolerance < 0.2
                if not any(abs(val - s) < 0.2 for s in src_vals):
                    warnings.append(f"NUMERIC INCONSISTENCY: Generated value '{num_str}' not confidently found in source.")
                    invalid_nums.append(num_str)
                    is_consistent = False
                    
        if not is_consistent:
            print(f"[NUMERIC_CHECK] mismatches found: {invalid_nums}")
        
        return is_consistent, warnings

    def _check_resource_contamination(self, text: str) -> tuple[bool, List[str]]:
        lower = text.lower()
        warnings = []
        forbidden = ["kiss", "medtronic resolute", "onyx", "ceric", "bifurcation single stenting", "617", "67.4", "75.9"]
        for f in forbidden:
            if f in lower:
                warnings.append(f"RESOURCE CONTAMINATION DETECTED: Found forbidden factual term '{f}'")
        return len(warnings) == 0, warnings

    # ── Score calculator ─────────────────────────────────────────────

    @staticmethod
    def _compute_score(
        structure_ok: bool,
        tone_ok: bool,
        hallucination_risk: str,
        coverage_pct: float,
        error_count: int,
        numeric_consistency: bool = True,
        resource_contamination: bool = False,
    ) -> int:
        """
        Compute composite score (0–100).

        Weights:
          - Coverage:       40 pts
          - Structure:      25 pts
          - Tone:           20 pts
          - Hallucination:  15 pts (penalty)
        """
        score = 0.0

        # Coverage (0–40)
        score += (coverage_pct / 100.0) * 40

        # Structure (0–25)
        if structure_ok:
            score += 25
        else:
            score += 15  # Partial credit

        # Tone (0–20)
        if tone_ok:
            score += 20
        else:
            score += 10  # Partial credit

        # Hallucination penalty (0 to -10)
        h_penalty = {"low": 0, "medium": -5, "high": -10}
        score += h_penalty.get(hallucination_risk, 0)

        # Numeric inconsistency penalty
        if not numeric_consistency:
            score -= 30

        # Resource contamination penalty
        if resource_contamination:
            score -= 40

        # Hard error penalty
        score -= error_count * 5

        return max(0, min(100, round(score)))

    # ── Public API ───────────────────────────────────────────────────

    def validate(
        self,
        section_id: str,
        generated_text: str,
        expected_subsections: Optional[List[str]] = None,
        required_elements: Optional[List[str]] = None,
        missing_elements: Optional[List[str]] = None,
        source_evidence: Optional[str] = None,
    ) -> SectionValidation:
        """
        Run all validation checks and produce a SectionValidation report.

        Args:
            section_id: Section identifier for logging.
            generated_text: The LLM-generated output to validate.
            expected_subsections: Subsections that should appear in output.
            required_elements: Required elements (for coverage check).
            missing_elements: Known missing elements from MissingDetector.

        Returns:
            SectionValidation with score, dimensions, and all warnings.
        """
        errors: List[str] = []
        warnings: List[str] = []

        # ── Empty check ───────────────────────────────────────────────
        if not generated_text or not generated_text.strip():
            return SectionValidation(
                score=0,
                structure_ok=False,
                tone_ok=False,
                hallucination_risk="low",
                errors=["Generated text is empty — no content to validate."],
                passed=False,
                coverage_pct=0.0,
            )

        # ── Length check ──────────────────────────────────────────────
        if len(generated_text.strip()) < 100:
            errors.append(
                f"Output suspiciously short ({len(generated_text.strip())} chars). "
                "Expected at least 100 characters for any CSR section."
            )

        # ── Dimension checks ──────────────────────────────────────────
        structure_ok, struct_warnings = self._check_structure(
            generated_text, expected_subsections
        )
        tone_ok, tone_warnings = self._check_tone(generated_text)
        hall_risk, hall_warnings = self._check_hallucination_risk(generated_text)
        coverage_pct, cov_warnings = self._check_completeness(
            generated_text, required_elements, missing_elements
        )
        numeric_ok, num_warnings = self._check_numeric_consistency(
            generated_text, source_evidence
        )
        contam_ok, contam_warnings = self._check_resource_contamination(generated_text)

        warnings.extend(struct_warnings)
        warnings.extend(tone_warnings)
        warnings.extend(hall_warnings)
        warnings.extend(cov_warnings)
        warnings.extend(num_warnings)
        warnings.extend(contam_warnings)

        # ── Known missing elements warnings ───────────────────────────
        if missing_elements:
            warnings.append(
                f"Evidence gaps detected: the following required elements "
                f"were not found in source documents: "
                f"{', '.join(missing_elements[:6])}"
                + (f" (+{len(missing_elements)-6} more)" if len(missing_elements) > 6 else "")
            )
        if any("statistical" in str(x).lower() for x in (missing_elements or [])):
            warnings.append("Missing statistical data")
        if any("demograph" in str(x).lower() for x in (missing_elements or [])):
            warnings.append("Incomplete demographics")

        # ── Score ─────────────────────────────────────────────────────
        score = self._compute_score(
            structure_ok=structure_ok,
            tone_ok=tone_ok,
            hallucination_risk=hall_risk,
            coverage_pct=coverage_pct,
            error_count=len(errors),
            numeric_consistency=numeric_ok,
            resource_contamination=not contam_ok,
        )

        passed = score >= 40 and not any(
            "empty" in e.lower() for e in errors
        ) and numeric_ok

        result = SectionValidation(
            score=score,
            structure_ok=structure_ok,
            tone_ok=tone_ok,
            hallucination_risk=hall_risk,
            warnings=warnings,
            errors=errors,
            passed=passed,
            coverage_pct=round(coverage_pct, 1),
            numeric_consistency=numeric_ok,
        )

        logger.info(
            "AdvancedValidator [%s]: score=%d, risk=%s, passed=%s",
            section_id, score, hall_risk, passed,
        )
        return result

    def validate_batch(
        self,
        sections: Dict[str, Dict[str, Any]],
    ) -> Dict[str, SectionValidation]:
        """
        Validate a batch of sections.

        Args:
            sections: {section_id: {"text": ..., "subsections": [...], "required": [...]}}

        Returns:
            {section_id: SectionValidation}
        """
        results = {}
        for sid, data in sections.items():
            results[sid] = self.validate(
                section_id=sid,
                generated_text=data.get("text", ""),
                expected_subsections=data.get("subsections"),
                required_elements=data.get("required"),
                missing_elements=data.get("missing"),
            )
        return results
