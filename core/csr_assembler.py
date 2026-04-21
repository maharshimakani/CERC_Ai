"""
CSR Assembler — Layer 9
───────────────────────
Combines individually generated CSR sections into a complete,
ordered Clinical Study Report document.

Responsibilities:
  ✔ Combine sections in correct ICH E3 order
  ✔ Format output cleanly with section separators
  ✔ Generate a table of contents
  ✔ Handle missing sections gracefully
  ✔ Provide both plain-text and structured output

This module is ADDITIVE — it does not replace output_generator.py.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# ICH E3 section ordering (canonical)
ICH_E3_ORDER: List[Tuple[str, str]] = [
    ("synopsis",               "Synopsis"),
    ("introduction",           "1 Introduction"),
    ("study_objectives",       "5 Study Objectives"),
    ("ethics",                 "4 Ethics"),
    ("investigators_sites",    "6 Investigators and Study Administrative Structure"),
    ("study_design",           "9.1 Study Design"),
    ("inclusion_exclusion",    "9.3 Selection of Study Population"),
    ("treatments",             "9.4 Study Treatments"),
    ("endpoints",              "9.4.1 Efficacy and Safety Variables"),
    ("study_population",       "10.1 Subject Disposition"),
    ("demographics",           "10.1.4 Demographics and Baseline Characteristics"),
    ("efficacy_evaluation",    "10 Efficacy Evaluation"),
    ("statistical_methods",    "11 Statistical Methods"),
    ("safety_evaluation",      "12 Safety Evaluation"),
    ("adverse_events",         "12.2 Adverse Events"),
    ("discussion_conclusions", "13 Discussion and Overall Conclusions"),
]


class CSRAssembler:
    """Assembles individually generated sections into a complete CSR."""

    def __init__(self, section_order: Optional[List[Tuple[str, str]]] = None):
        """
        Args:
            section_order: Optional custom ordering as [(section_id, heading), ...].
                           Defaults to ICH_E3_ORDER.
        """
        self.order = section_order or ICH_E3_ORDER

    # ── Assembly ─────────────────────────────────────────────────────

    def assemble(
        self,
        generated_sections: Dict[str, Dict[str, Any]],
        study_title: str = "Clinical Study Report",
        protocol_number: str = "",
    ) -> str:
        """
        Assemble all generated sections into a single CSR document.

        Args:
            generated_sections: {section_id: {"final_text": "...", ...}}
            study_title: Title for the cover page.
            protocol_number: Protocol identifier.

        Returns:
            Complete CSR as plain text.
        """
        parts: List[str] = []

        # Cover block
        parts.append("=" * 72)
        parts.append(f"CLINICAL STUDY REPORT")
        parts.append(f"")
        parts.append(f"Study Title: {study_title}")
        if protocol_number:
            parts.append(f"Protocol Number: {protocol_number}")
        parts.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        parts.append(f"System: CERC — AI Clinical Document Compiler")
        parts.append("=" * 72)
        parts.append("")

        # Table of Contents
        parts.append("TABLE OF CONTENTS")
        parts.append("-" * 40)
        for section_id, heading in self.order:
            data = generated_sections.get(section_id, {})
            status = "✓" if data.get("final_text", "").strip() else "—"
            parts.append(f"  {status}  {heading}")
        parts.append("")
        parts.append("=" * 72)
        parts.append("")

        # Sections
        included = 0
        missing = 0
        for section_id, heading in self.order:
            data = generated_sections.get(section_id, {})
            text = data.get("final_text", "").strip()

            parts.append(heading)
            parts.append("-" * len(heading))
            parts.append("")

            if text:
                parts.append(text)
                included += 1
            else:
                parts.append(
                    "[This section was not generated — "
                    "insufficient source evidence or generation error.]"
                )
                missing += 1

            parts.append("")
            parts.append("=" * 72)
            parts.append("")

        logger.info(
            "CSRAssembler: assembled %d sections (%d included, %d missing)",
            len(self.order), included, missing,
        )

        return "\n".join(parts)

    def get_section_status(
        self,
        generated_sections: Dict[str, Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Return a status list showing which sections are present/missing.

        Returns:
            [{"section_id": ..., "heading": ..., "status": "generated"|"missing", "char_count": int}]
        """
        status_list = []
        for section_id, heading in self.order:
            data = generated_sections.get(section_id, {})
            text = data.get("final_text", "").strip()
            status_list.append({
                "section_id": section_id,
                "heading": heading,
                "status": "generated" if text else "missing",
                "char_count": len(text),
            })
        return status_list
