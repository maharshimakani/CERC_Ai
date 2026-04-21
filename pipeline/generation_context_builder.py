"""
Generation Context Builder

Assembles complete validated context package before any LLM call.
"""

from __future__ import annotations

from typing import Any, Dict, List

from pipeline.template_engine import SectionTemplatePackage, TemplateEngine


class GenerationContextBuilder:
    def __init__(self, template_engine: TemplateEngine):
        self.template_engine = template_engine

    @staticmethod
    def _infer_missing_elements(required_elements: List[str], evidence_text: str) -> List[str]:
        """
        Heuristic missingness detection for required elements.
        This is candidate-level only; the validator enforces final compliance.
        """
        low = (evidence_text or "").lower()
        missing: List[str] = []
        for element in required_elements:
            k = str(element).strip().lower()
            if not k:
                continue
            # lightweight coverage proxy
            if k not in low:
                missing.append(element)
        return missing

    @staticmethod
    def _source_files_from_blocks(matched_blocks: List[Dict[str, Any]]) -> List[str]:
        files: List[str] = []
        seen = set()
        for b in matched_blocks or []:
            f = b.get("source_file")
            if f and f not in seen:
                files.append(str(f))
                seen.add(f)
        return files

    def build(
        self,
        section_id: str,
        template_package: SectionTemplatePackage,
        match_result: Dict[str, Any],
    ) -> Dict[str, Any]:
        combined = match_result.get("combined_content", "") or ""
        matched_blocks = match_result.get("matched_blocks", []) or []
        candidate_missing = match_result.get("candidate_missing_elements", []) or []

        missing_inferred = self._infer_missing_elements(template_package.required_elements, combined)
        # Union: include both candidate_missing (matcher-level) and inferred missing.
        missing = list(dict.fromkeys([*candidate_missing, *missing_inferred]))

        source_files = self._source_files_from_blocks(matched_blocks)

        # Evidence blocks are kept as raw traceability blocks (UI can render them).
        user_evidence = combined

        return {
            "section_id": section_id,
            "section_title": template_package.title,
            "template": template_package.template,
            "required_elements": template_package.required_elements,
            "style_rules": template_package.style_rules,
            "formatting_rules": template_package.formatting_rules,
            "prohibited_phrases": template_package.prohibited_phrases,
            "example_snippets": template_package.example_snippets[:4],
            "user_evidence": user_evidence,
            "source_files": source_files,
            "source_blocks": matched_blocks,
            "candidate_missing": candidate_missing,
            "missing_elements": missing,
            "strict_rules": {
                "evidence_only": True,
                "no_speculation": True,
                "missing_data_policy": "Not specified.",
            },
        }

