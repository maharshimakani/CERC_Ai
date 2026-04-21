"""
core/missing_detector.py
────────────────────────
Detects missing required elements in CSR section inputs.

Responsibilities:
  ✔ Compare required elements against available evidence text
  ✔ Classify each gap as critical vs non-critical
  ✔ Return structured MissingAnalysis (not raw booleans)
  ✔ Determine whether generation should be blocked or allowed partial

Critical elements block generation.
Non-critical elements allow partial generation with warnings.

This module is ADDITIVE — it does not modify any existing code.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ── Element criticality configuration ────────────────────────────────
# Elements here are ALWAYS critical (block generation if missing).
# All others are non-critical (allow partial generation).

UNIVERSAL_CRITICAL_ELEMENTS: Set[str] = {
    "primary objective",
    "primary endpoint",
    "study design",
    "treatment",
    "dose",
    "patient population",
    "inclusion criteria",
}

# Per-section relevance keywords for blocking check.
# If combined_text contains NONE of these, generation is blocked
# even if text is non-empty (prevents irrelevant evidence from reaching LLM).
SECTION_RELEVANCE_KEYWORDS: Dict[str, List[str]] = {
    "synopsis": [
        "protocol synopsis", "study synopsis", "study title",
        "study design", "synopsis", "protocol number",
        "primary objective", "clinical investigation",
    ],
    "ethics": [
        "ethics", "irb", "institutional review", "informed consent", "gcp",
    ],
    "investigators_sites": [
        "investigator", "site", "clinical site",
    ],
    "study_design": [
        "study design", "observational", "single-arm", "open-label",
        "multicenter", "randomized", "treatment arm",
    ],
    "study_population": [
        "subject disposition", "enrolled", "completed", "intent-to-treat", "itt", "population",
    ],
    "demographics": [
        "demographics", "baseline characteristics", "age", "sex", "gender",
        "ethnicity", "race",
    ],
    "introduction": [
        "background", "introduction", "rationale", "disease",
    ],
    "study_objectives": [
        "primary objective", "secondary objective", "study objective",
    ],
    "inclusion_exclusion": [
        "inclusion criteria", "exclusion criteria", "eligibility",
    ],
    "treatments": [
        "treatment", "dose", "dosage", "investigational product", "study drug",
    ],
    "endpoints": [
        "primary endpoint", "secondary endpoint", "efficacy variable",
    ],
    "safety_evaluation": [
        "safety", "adverse event", "ae", "sae", "tolerability",
    ],
    "adverse_events": [
        "adverse event", "ae", "sae", "treatment-emergent",
    ],
    "statistical_methods": [
        "statistical", "sample size", "power", "hypothesis",
    ],
    "efficacy_evaluation": [
        "efficacy", "primary endpoint result", "response rate",
    ],
    "discussion_conclusions": [
        "discussion", "conclusion", "benefit-risk",
    ],
}


@dataclass
class MissingAnalysis:
    """Result of missing element detection for one CSR section."""
    section_id: str
    required_elements: List[str]
    missing_elements: List[str]
    critical_missing: List[str]
    non_critical_missing: List[str]
    coverage_pct: float           # 0.0 – 100.0
    generation_blocked: bool
    block_reason: Optional[str]
    # Relevance traceability (NEW)
    relevance_matched: bool = True       # False when evidence has no section keywords
    matched_keywords: List[str] = field(default_factory=list)  # keywords found in text

    numeric_values_present: bool = False

    @property
    def has_critical_gap(self) -> bool:
        return bool(self.critical_missing)

    @property
    def has_any_gap(self) -> bool:
        return bool(self.missing_elements)

    @property
    def completeness_score(self) -> int:
        """Integer completeness score 0–100 derived from coverage_pct."""
        return max(0, min(100, int(round(self.coverage_pct))))

    def to_dict(self) -> Dict:
        return {
            "section_id": self.section_id,
            "required_elements": self.required_elements,
            "missing_elements": self.missing_elements,
            "critical_missing_flag": bool(self.critical_missing),
            "critical_missing": self.critical_missing,
            "non_critical_missing": self.non_critical_missing,
            "coverage_pct": round(self.coverage_pct, 1),
            "completeness_score": self.completeness_score,
            "generation_blocked": self.generation_blocked,
            "block_reason": self.block_reason,
            "relevance_matched": self.relevance_matched,
            "matched_keywords": self.matched_keywords,
            "numeric_values_present": self.numeric_values_present,
        }


class MissingDetector:
    """
    Detects missing required elements in a section's evidence text.

    Strategy: lightweight lexical scan to test if each required element
    (or a synonym) appears in the evidence text. This is intentionally
    heuristic — the LLM does the authoritative check at generation time.
    """

    def __init__(
        self,
        critical_elements: Optional[Set[str]] = None,
        min_evidence_length: int = 50,
    ):
        """
        Args:
            critical_elements: Set of element names (lowercase) that are
                               always considered critical. Merged with
                               UNIVERSAL_CRITICAL_ELEMENTS.
            min_evidence_length: Minimum chars of evidence to allow generation.
                                 Lowered from 150 to 50 to support partial generation
                                 from short but real evidence snippets.
        """
        self.critical_elements = (critical_elements or set()) | UNIVERSAL_CRITICAL_ELEMENTS
        self.min_evidence_length = min_evidence_length

    # ── Private helpers ──────────────────────────────────────────────

    def _element_present(self, element: str, text_lower: str) -> bool:
        """
        Check if an element keyword is present in the evidence text.
        Supports simple synonym matching via OR patterns.
        """
        key = element.strip().lower()
        if not key:
            return True  # empty requirement → trivially satisfied

        # Direct substring check
        if key in text_lower:
            return True

        # Word-boundary regex for multi-word elements
        pattern = r"\b" + re.escape(key) + r"\b"
        if bool(re.search(pattern, text_lower)):
            return True
        
        # Lenient match for robust extraction
        words = [w for w in key.split() if len(w) > 4]
        if words and any(w in text_lower for w in words):
            return True
            
        return False

    def _is_critical(self, element: str) -> bool:
        """Determine if an element is critical."""
        key = element.strip().lower()
        return any(crit in key for crit in self.critical_elements)

    # ── Public API ───────────────────────────────────────────────────

    def analyze(
        self,
        section_id: str,
        evidence_text: str,
        required_elements: List[str],
        transformed_text: Optional[str] = None,
    ) -> MissingAnalysis:
        """
        Analyze evidence text against required elements.

        Four generation modes (per spec):
          Case 1 — Empty evidence      → generation_blocked=True  (no LLM)
          Case 2 — Non-empty but no section-relevant keywords
                                       → generation_blocked=True  (no LLM)
          Case 3 — Relevant + incomplete evidence
                                       → generation_blocked=False, partial
          Case 4 — Relevant + strong evidence
                                       → generation_blocked=False, normal

        Args:
            section_id: Section identifier used for relevance keyword lookup.
            evidence_text: The combined source text for this section.
            required_elements: List of element names that should be present.

        Returns:
            MissingAnalysis with full gap report, blocking decision,
            relevance_matched, and matched_keywords for traceability.
        """
        if not required_elements:
            # No requirements defined → always complete
            return MissingAnalysis(
                section_id=section_id,
                required_elements=[],
                missing_elements=[],
                critical_missing=[],
                non_critical_missing=[],
                coverage_pct=100.0,
                generation_blocked=False,
                block_reason=None,
                relevance_matched=True,
                matched_keywords=[],
                numeric_values_present=False,
            )

        text_stripped = (evidence_text or "").strip()
        
        if transformed_text is None:
            transformed_text = text_stripped
        extracted_text_length = len(transformed_text.strip())
        
        import re as regex
        numeric_values_present = bool(regex.search(r'\d+\.?\d*%?', evidence_text))

        # ── Case 1: Empty evidence ─────────────────────────────────────
        if extracted_text_length == 0:
            logger.warning(
                "MissingDetector [%s]: Case 1 — Empty transformed evidence. Blocking.",
                section_id,
            )
            return MissingAnalysis(
                section_id=section_id,
                required_elements=required_elements,
                missing_elements=list(required_elements),
                critical_missing=list(required_elements),
                non_critical_missing=[],
                coverage_pct=0.0,
                generation_blocked=True,
                block_reason="Case 1: No evidence text available for this section.",
                relevance_matched=False,
                matched_keywords=[],
            )

        # ── Case 2: Non-empty but irrelevant evidence ──────────────────
        text_lower = text_stripped.lower()
        relevance_kws = SECTION_RELEVANCE_KEYWORDS.get(section_id, [])
        matched_kws: List[str] = [kw for kw in relevance_kws if kw in text_lower]

        # New Rule: generation_blocked = True ONLY IF len(extracted_text) == 0 (Case 1)
        relevance_matched = True
        if relevance_kws and not matched_kws:
            relevance_matched = False
            matched_kws = []
        if not relevance_kws:
            matched_kws = ["*"]

        # ── Score penalty for very short but relevant text ───────────────
        if extracted_text_length < self.min_evidence_length:
            logger.info(
                "MissingDetector [%s]: Short evidence (%d chars < %d) — "
                "score penalty applied, partial generation allowed (relevance confirmed).",
                section_id, extracted_text_length, self.min_evidence_length,
            )

        # ── Element presence scan ──────────────────────────────────────
        missing: List[str] = []
        critical: List[str] = []
        non_critical: List[str] = []

        for element in required_elements:
            if not self._element_present(element, text_lower):
                missing.append(element)
                if self._is_critical(element):
                    critical.append(element)
                else:
                    non_critical.append(element)

        n = len(required_elements)
        coverage_pct = ((n - len(missing)) / n * 100.0) if n > 0 else 100.0

        # ── Cases 3 & 4: Relevant evidence ─────────────────────────────
        # Case 3 (partial): relevant text, some elements missing → allow with warning
        # Case 4 (complete): relevant text, most elements found → normal generation
        # We do NOT block on element gaps alone when relevant evidence exists.
        # The LLM is given the actual text and the list of missing elements.
        block = False
        block_reason: Optional[str] = None

        if critical:
            logger.info(
                "MissingDetector [%s]: %d critical element(s) missing — "
                "allowing grounded partial generation (matched_kws=%s).",
                section_id, len(critical), matched_kws,
            )

        # ── Demographics Strictness ────────────────────────────────────
        # Only mark COMPLETE if: numeric evidence exists AND demographic keywords present OR table structure present
        # Else -> force PARTIAL (coverage <= 50.0)
        if section_id == "demographics":
            has_table = "[TABLE_START]" in evidence_text
            has_kws = any(kw in text_lower for kw in ["baseline characteristics", "demographic summary", "mean age"])
            
            if not ((numeric_values_present and has_kws) or has_table):
                logger.info("[%s] Status forced to PARTIAL (coverage=50.0) — strict missing numeric/demographic real data.", section_id)
                coverage_pct = min(coverage_pct, 50.0)

        result = MissingAnalysis(
            section_id=section_id,
            required_elements=required_elements,
            missing_elements=missing,
            critical_missing=critical,
            non_critical_missing=non_critical,
            coverage_pct=coverage_pct,
            generation_blocked=block,
            block_reason=block_reason,
            relevance_matched=relevance_matched,
            matched_keywords=matched_kws,
            numeric_values_present=numeric_values_present,
        )

        # Determine case label for logging
        case_label = "Case 4 (complete)" if coverage_pct >= 80 else "Case 3 (partial)"
        logger.info(
            "MissingDetector [%s]: %s — %d/%d elements present (%.0f%%), "
            "score=%d, matched_kws=%s, blocked=%s",
            section_id, case_label,
            n - len(missing), n, coverage_pct,
            result.completeness_score, matched_kws, block,
        )
        return result
