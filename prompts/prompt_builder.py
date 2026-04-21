"""
Prompt Builder (CRITICAL)
─────────────────────────
Builds structured prompts for the section-wise CSR generation pipeline.

Each prompt is assembled from three controlled inputs:
  1. Extracted input (evidence text from source documents)
  2. Template (structural guidance — what the output MUST look like)
  3. Reference example (style guidance ONLY — NEVER content)

The builder enforces:
  ✔ Past tense
  ✔ Scientific / regulatory tone
  ✔ Strict template structure adherence
  ✔ Zero hallucination
  ✔ Example used ONLY for style, NOT content copying

This module is ADDITIVE — it does not modify existing prompt files.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Strict Anti-Hallucination System Prompt ──────────────────────────

SYSTEM_PROMPT = (
    "You are an expert clinical regulatory writer producing content for "
    "an ICH E3-compliant Clinical Study Report.\n\n"
    "ABSOLUTE RULES — VIOLATION IS UNACCEPTABLE:\n"
    "1. Use ONLY information explicitly stated in the SOURCE TEXT below. If ANY relevant evidence exists, you MUST generate factual statements using ONLY that evidence.\n"
    "2. NEVER invent, infer, assume, extrapolate, or generalize ANY fact beyond the evidence.\n"
    "3. Do NOT reject the entire section if partial data exists. NEVER generate a completely empty section if any factual evidence is present.\n"
    "4. For missing elements, explicitly state: 'Not specified in provided documents.' — but ONLY for those elements.\n"
    "5. DO NOT use reference guidance as a factual source.\n"
    "6. NEVER use speculative phrases: 'typically', 'generally', 'it is expected', 'usually', 'commonly', 'likely'.\n"
    "7. Every number, date, dose, and statistic must come verbatim from the source.\n"
    "8. Use past tense throughout — the study has been completed.\n"
    "9. Use formal, neutral, scientific language. Do NOT include promotional or subjective language.\n"
    "10. Follow the provided TEMPLATE STRUCTURE exactly. If a STYLE EXAMPLE is provided, mimic its tone only.\n"
)


class PromptBuilder:
    """Assembles controlled, auditable prompts for section generation."""

    def __init__(self):
        self.system_prompt = SYSTEM_PROMPT

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _truncate(text: str, max_chars: int = 12000) -> str:
        """Safely truncate text, preserving paragraph boundaries."""
        if not text or len(text) <= max_chars:
            return text or ""
        # Cut on paragraph boundary
        cut = text[:max_chars]
        last_break = cut.rfind("\n\n")
        if last_break > max_chars * 0.6:
            cut = cut[:last_break]
        return cut + "\n\n[... source text truncated for token limits ...]"

    @staticmethod
    def _format_list(items: List[str], prefix: str = "-") -> str:
        """Format a list of strings as bulleted lines."""
        if not items:
            return "  (none specified)"
        return "\n".join(f"  {prefix} {item}" for item in items)

    @staticmethod
    def _sanitize_resource_text(text: str, section_id: str) -> str:
        """Strips factual and numeric content from resources to prevent leakage."""
        if not text:
            return ""
        import re
        
        orig_len = len(text)
        cleaned_lines = []
        forbidden_terms = [
            "kiss", "medtronic", "resolute", "onyx", "ceric",
            "acurate neo 2", "acurate neo2", "clinical investigation report"
        ]
        
        for line in text.split("\n"):
            line_lower = line.lower()
            if any(term in line_lower for term in forbidden_terms):
                continue
            if re.search(r"\d", line):
                continue
            stripped = line.strip()
            if stripped:
                cleaned_lines.append(stripped)
                
        sanitized = "\n".join(cleaned_lines)
        print(f"[RESOURCE SANITIZE] Section: {section_id} | Original chars: {orig_len} | Sanitized chars: {len(sanitized)}")
        return sanitized

    # ── Public API ───────────────────────────────────────────────────

    def build_extraction_prompt(
        self,
        section_id: str,
        section_title: str,
        source_text: str,
        required_elements: Optional[List[str]] = None,
    ) -> str:
        """
        Build the extraction prompt (Stage A).

        Instructs the LLM to extract structured facts from the source
        text specific to the CSR section's required elements.
        """
        elements_block = ""
        if required_elements:
            elements_block = (
                "\nREQUIRED ELEMENTS TO EXTRACT:\n"
                + self._format_list(required_elements)
                + "\n"
            )

        return (
            f"=== EXTRACTION TASK ===\n"
            f"Section: {section_title} (ID: {section_id})\n"
            f"{elements_block}\n"
            f"Extract ALL relevant information for the above section from "
            f"the SOURCE TEXT below.\n"
            f"Output structured facts as key-value pairs.\n"
            f"If a required element is not found, output: "
            f"\"<element>: Not specified in source documents.\"\n\n"
            f"=== SOURCE TEXT ===\n"
            f"{self._truncate(source_text)}\n"
            f"=== END SOURCE TEXT ===\n\n"
            f"Extract now:"
        )

    def build_generation_prompt(
        self,
        section_id: str,
        section_title: str,
        extracted_input: str,
        template: Optional[str] = None,
        example: Optional[str] = None,
        required_elements: Optional[List[str]] = None,
        style_rules: Optional[List[str]] = None,
        resource_text: Optional[str] = None,
    ) -> str:
        """
        Build the generation prompt (main Stage C call).

        Combines:
          - Extracted evidence (FACTS — mandatory)
          - Template structure (STRUCTURE — used if available)
          - Example text (STYLE — used if available, never for content)
          - Required elements (CHECKLIST)
          - Style rules (TONE)

        Returns a single, self-contained prompt string.
        """
        blocks: List[str] = [
            f"=== CSR SECTION GENERATION ===",
            f"Section: {section_title} (ID: {section_id})",
            "",
        ]

        # ── Template block (structural guidance) ─────────────────────
        if template:
            blocks.extend([
                "=== TEMPLATE STRUCTURE (FOLLOW EXACTLY) ===",
                template,
                "=== END TEMPLATE ===",
                "",
            ])

        # ── Style example block (tone guidance only) ─────────────────
        if example:
            blocks.extend([
                "=== STYLE REFERENCE (TONE AND FORMAT ONLY — DO NOT COPY CONTENT) ===",
                "The following is a REFERENCE EXAMPLE for writing style.",
                "Use its tone, sentence structure, and formatting conventions.",
                "DO NOT USE ANY of its factual content — it is from a different study.",
                "",
                self._truncate(example, max_chars=4000),
                "=== END STYLE REFERENCE ===",
                "",
            ])

        # ── Required elements ────────────────────────────────────────
        if required_elements:
            blocks.extend([
                "REQUIRED ELEMENTS (must be addressed in output):",
                self._format_list(required_elements),
                "",
            ])

        # ── Style rules ──────────────────────────────────────────────
        if style_rules:
            blocks.extend([
                "WRITING STYLE RULES:",
                self._format_list(style_rules),
                "",
            ])

        evidence_strength = len([p for p in extracted_input.split('\n\n') if p.strip()])

        # ── System Rules ─────────────────────────────────────────────
        blocks.extend([
            "1. SYSTEM RULES",
            "CRITICAL CONSTRAINTS:",
            f"  - EVIDENCE STRENGTH: {evidence_strength} paragraph(s) provided.",
            "  - EVIDENCE DENSITY CONTROL: If evidence_strength < 2, FORCE concise output and do not over-expand.",
            "  - Do NOT reinterpret or generalize beyond explicit evidence.",
            "  - Use ONLY the extracted input below as your factual source.",
            "  - If ANY relevant evidence exists, you MUST generate factual statements using ONLY that evidence.",
            "  - Do NOT reject the entire section if partial data exists.",
            "  - For missing elements, explicitly state: 'Not specified in provided documents.' — but ONLY for those elements.",
            "  - NEVER generate a completely empty section if any factual evidence is present.",
            "  - DO NOT infer, assume, or generalize beyond the evidence.",
            "  - Use past tense throughout.",
            "  - Use plain text formatting only (no Markdown symbols).",
            "  - Every claim must trace back to the extracted input.",
            "  - DO NOT use reference guidance as a factual source.",
            "",
            "When partial evidence is available, structure output as follows:",
            "1. Begin with factual statement derived directly from evidence",
            "2. Follow with clarifications for missing elements",
            "3. Use formal clinical tone and past tense",
            "",
            "Example format:",
            "'The study is described as a randomized, multicenter investigation.",
            "However, details regarding treatment arms and blinding were not specified in the provided documents.'",
            "",
        ])

        # ── Structural Guidance ──────────────────────────────────────
        if resource_text:
            resource_sanitized = self._sanitize_resource_text(resource_text, section_id)
            blocks.extend([
                "2. REFERENCE GUIDANCE (resources/)",
                "Reference guidance is for writing structure only. It is not a factual source. Do not reuse study names, devices, statistics, dates, or results from reference guidance.",
                "If a fact is not present in EVIDENCE, write 'Not specified in provided documents.'",
                self._truncate(resource_sanitized, max_chars=4000),
                "=== END REFERENCE GUIDANCE ===",
                "",
            ])

        # ── Extracted factual input (the ONLY truth) ─────────────────
        blocks.extend([
            "3. EVIDENCE (uploaded documents)",
            self._truncate(extracted_input),
            "=== END EVIDENCE ===",
            "",
            # ── Final Instruction ─────────────────────────────────────────
            "4. FINAL INSTRUCTION:",
            f"Generate section: {section_id}",
            "If ANY relevant evidence exists, you MUST generate factual statements using ONLY that evidence.",
            "Do NOT reject the entire section if partial data exists.",
            "For missing elements, explicitly state: 'Not specified in provided documents.' — but ONLY for those elements.",
            "NEVER generate a completely empty section if any factual evidence is present.",
            "DO NOT infer, assume, or generalize beyond the evidence.",
            "DO NOT use reference guidance as a factual source.",
        ])

        return "\n".join(blocks)

    def build_validation_prompt(
        self,
        section_title: str,
        generated_text: str,
        source_text: str,
    ) -> str:
        """
        Build a lightweight validation prompt to check for hallucinations.

        This is an optional verification step — the existing validator.py
        handles the main compliance checks.
        """
        return (
            f"=== HALLUCINATION CHECK ===\n"
            f"Section: {section_title}\n\n"
            f"Compare the GENERATED TEXT against the SOURCE TEXT.\n"
            f"List any claims in the generated text that are NOT "
            f"supported by the source text.\n"
            f"If everything is supported, respond with: "
            f"\"PASS — all claims verified.\"\n\n"
            f"=== GENERATED TEXT ===\n"
            f"{self._truncate(generated_text, max_chars=6000)}\n"
            f"=== END GENERATED TEXT ===\n\n"
            f"=== SOURCE TEXT ===\n"
            f"{self._truncate(source_text, max_chars=8000)}\n"
            f"=== END SOURCE TEXT ===\n\n"
            f"List unsupported claims (or PASS):"
        )
