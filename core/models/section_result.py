"""
core/models/section_result.py
─────────────────────────────
Canonical data model for a single CSR section result.

Every generated section is represented as a SectionResult —
a self-contained, auditable, serializable object that carries:
  ✔ the generated text
  ✔ the status determination (complete / partial / missing)
  ✔ the source documents used
  ✔ template and example references
  ✔ missing elements (with criticality flag)
  ✔ full validation report
  ✔ full trace object for the Trace tab

This is the single source of truth for the frontend data contract.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ── Status definitions ────────────────────────────────────────────────

class SectionStatus:
    """Deterministic status codes for a CSR section."""
    COMPLETE = "complete"   # All required inputs present, generation succeeded
    PARTIAL  = "partial"    # Non-critical elements missing, generation allowed
    MISSING  = "missing"    # Critical inputs absent, generation blocked


# ── Trace object ──────────────────────────────────────────────────────

@dataclass
class SectionTrace:
    """
    Full generation trace for one CSR section (powers Trace tab).

    Every field is populated during the generation pipeline.
    None values indicate the step was skipped or not applicable.
    """
    mapping_summary: str = ""
    transformation_summary: str = ""
    prompt_logic_summary: str = ""
    execution_timestamp: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))
    input_sources: List[str] = field(default_factory=list)
    template_used: Optional[str] = None
    example_used: Optional[str] = None
    input_char_count: int = 0
    transformed_char_count: int = 0
    prompt_char_count: int = 0
    generation_blocked: bool = False
    block_reason: Optional[str] = None
    
    # Traceability upgrades
    matched_keywords: List[str] = field(default_factory=list)
    semantic_matches: List[str] = field(default_factory=list)
    numeric_values_found: List[str] = field(default_factory=list)
    source_priority_used: List[str] = field(default_factory=list)
    extraction_confidence: str = "UNKNOWN"
    paragraphs_used_count: int = 0
    
    # Traceability upgrades (Regulated Level)
    semantic_used: bool = False
    numeric_values_detected: bool = False
    mapping_confidence: int = 0
    relevance_validated: bool = False
    
    # Static Knowledge Layer
    resource_used: bool = False
    resource_types_used: List[str] = field(default_factory=list)
    resource_filenames: List[str] = field(default_factory=list)
    resource_char_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mapping_summary": self.mapping_summary or "",
            "transformation_summary": self.transformation_summary or "",
            "prompt_logic_summary": self.prompt_logic_summary or "",
            "execution_timestamp": self.execution_timestamp or "",
            "input_sources": self.input_sources or [],
            "template_used": self.template_used or "",
            "example_used": self.example_used or "",
            "input_char_count": self.input_char_count or 0,
            "transformed_char_count": self.transformed_char_count or 0,
            "prompt_char_count": self.prompt_char_count or 0,
            "generation_blocked": self.generation_blocked or False,
            "block_reason": self.block_reason or "",
            "matched_keywords": self.matched_keywords or [],
            "semantic_matches": self.semantic_matches or [],
            "numeric_values_found": self.numeric_values_found or [],
            "source_priority_used": self.source_priority_used or [],
            "extraction_confidence": self.extraction_confidence or "UNKNOWN",
            "paragraphs_used_count": self.paragraphs_used_count or 0,
            "semantic_used": self.semantic_used or False,
            "numeric_values_detected": self.numeric_values_detected or False,
            "mapping_confidence": self.mapping_confidence or 0,
            "relevance_validated": self.relevance_validated or False,
            "resource_used": self.resource_used or False,
            "resource_types_used": self.resource_types_used or [],
            "resource_filenames": self.resource_filenames or [],
            "resource_char_count": self.resource_char_count or 0,
        }


# ── Validation report ─────────────────────────────────────────────────

@dataclass
class SectionValidation:
    """
    Explainable validation report for one CSR section (powers Validation tab).
    """
    score: int = 0                         # 0–100 composite score
    structure_ok: bool = False
    tone_ok: bool = False
    hallucination_risk: str = "unknown"    # "low", "medium", "high"
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)
    passed: bool = False
    coverage_pct: float = 0.0             # % of required elements present
    numeric_consistency: bool = True      # True unless ungrounded numericals found

    def to_dict(self) -> Dict[str, Any]:
        return {
            "score": self.score or 0,
            "structure_ok": self.structure_ok,
            "tone_ok": self.tone_ok,
            "hallucination_risk": self.hallucination_risk or "unknown",
            "numeric_consistency": self.numeric_consistency,
            "warnings": self.warnings or [],
            "errors": self.errors or [],
            "passed": self.passed,
            "coverage_pct": self.coverage_pct or 0.0,
        }


# ── Main model ────────────────────────────────────────────────────────

@dataclass
class SectionResult:
    """
    Canonical, auditable result for a single CSR section.

    This is the central data contract between backend and frontend.
    Every panel in the Regulated AI Workbench maps to fields here.
    """

    # ── Identity ─────────────────────────────────────────────────────
    section_id: str
    section_name: str      # Human-readable ICH E3 heading
    status: str            # SectionStatus.COMPLETE / PARTIAL / MISSING

    # ── Sources Tab ──────────────────────────────────────────────────
    source_documents: List[str] = field(default_factory=list)  # filenames

    # ── Resource references ───────────────────────────────────────────
    template_id: Optional[str] = None    # template filename used
    example_id: Optional[str] = None     # example filename used

    # ── Missing element analysis ──────────────────────────────────────
    missing_elements: List[str] = field(default_factory=list)
    critical_missing: bool = False

    # ── Generated Tab ─────────────────────────────────────────────────
    generated_text: str = ""
    generation_time_s: float = 0.0

    # ── Validation Tab ────────────────────────────────────────────────
    validation: SectionValidation = field(default_factory=SectionValidation)

    # ── Element Mapping (For UI Traceability Panel) ───────────────────
    element_map_rich: Dict[str, Any] = field(default_factory=dict)
    token_usage: Dict[str, Any] = field(default_factory=dict)

    # ── Trace Tab ─────────────────────────────────────────────────────
    trace: SectionTrace = field(default_factory=SectionTrace)

    # ── Error (if any) ────────────────────────────────────────────────
    error: Optional[str] = None

    # ── Serialization ─────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """
        Serialize to a JSON-safe dict for the API response.

        Maps to all frontend tab data contracts.
        """
        content = self.generated_text if self.generated_text else ""
        if not content.strip():
            content = "Not specified in provided documents."

        try:
            raw_conf = min(
                (self.validation.score if self.validation else 0) or 0,
                getattr(self.trace, 'mapping_confidence', 0) or 0,
                getattr(self.validation, 'coverage_pct', 0.0) or 0.0
            ) / 100.0
            import math
            confidence_score = float(raw_conf)
            if math.isnan(confidence_score):
                confidence_score = 0.0
        except Exception:
            confidence_score = 0.0

        val_dict = self.validation.to_dict() if self.validation else {
            "score": 0,
            "structure_ok": False,
            "tone_ok": False,
            "hallucination_risk": "unknown",
            "warnings": [],
            "errors": [],
            "passed": False,
            "coverage_pct": 0.0
        }
        val_dict["completeness"] = self.status or "missing"

        trace_dict = self.trace.to_dict() if self.trace else {
            "mapping_confidence": 0,
            "input_char_count": 0,
            "transformed_char_count": 0,
            "matched_keywords": [],
            "semantic_matches": [],
            "numeric_values_found": [],
            "source_priority_used": [],
            "paragraphs_used_count": 0,
            "relevance_validated": False
        }

        return {
            # Identity
            "section_id": self.section_id or "",
            "section_name": self.section_name or "",
            "status": self.status or "missing",

            # Generated Tab
            "content": content,
            "generated_text": content,
            "generation_time_s": self.generation_time_s or 0.0,

            # Sources Tab
            "source_documents": self.source_documents or [],
            "sources": self.source_documents or [],

            # Resources
            "template_id": self.template_id or "",
            "example_id": self.example_id or "",

            # Missing elements
            "missing_elements": self.missing_elements or [],
            "critical_missing": self.critical_missing or False,
            "element_map_rich": self.element_map_rich or {},
            "token_usage": self.token_usage or {},

            # Validation Tab
            "validation": val_dict,
            "confidence_score": confidence_score,
            "validation_status": (
                "pass" if (self.validation and self.validation.passed)
                else ("fail" if self.status == SectionStatus.MISSING
                      else "warning")
            ),
            "validation_issues": (
                [{"severity": "error", "type": "validation", "message": e} for e in (self.validation.errors if self.validation else [])] +
                [{"severity": "warning", "type": "validation", "message": w} for w in (self.validation.warnings if self.validation else [])]
            ) if self.validation else [],

            # Trace Tab
            "trace": trace_dict,

            # Error
            "error": self.error or None,
        }

    @classmethod
    def make_blocked(
        cls,
        section_id: str,
        section_name: str,
        missing_elements: List[str],
        reason: str,
    ) -> "SectionResult":
        """
        Factory: build a MISSING-status section (generation was blocked).
        """
        val = SectionValidation(
            score=0,
            passed=False,
            hallucination_risk="low",   # blocked = no hallucination possible
            errors=[f"Generation blocked: {reason}"],
            warnings=[f"Missing critical elements: {', '.join(missing_elements)}"],
        )
        trace = SectionTrace(
            generation_blocked=True,
            block_reason=reason,
            mapping_summary=f"No usable source evidence found for {section_name}.",
            prompt_logic_summary="LLM call skipped — insufficient inputs.",
        )
        return cls(
            section_id=section_id,
            section_name=section_name,
            status=SectionStatus.MISSING,
            missing_elements=missing_elements,
            critical_missing=True,
            generated_text="",
            validation=val,
            trace=trace,
        )
