"""
Template Engine

Serves section-level knowledge from `pipeline/knowledge_engine.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass(frozen=True)
class SectionTemplatePackage:
    section_id: str
    title: str
    template: Dict[str, Any]
    required_elements: List[str]
    style_rules: List[str]
    formatting_rules: List[str]
    prohibited_phrases: List[str]
    example_snippets: List[str]


class TemplateEngine:
    def __init__(self, knowledge_base: Dict[str, Dict[str, Any]]):
        self.knowledge_base = knowledge_base or {}

    def get_section_knowledge(self, section_id: str) -> Dict[str, Any]:
        return self.knowledge_base.get(section_id, {})

    def get_template(self, section_id: str) -> Dict[str, Any]:
        return self.get_section_knowledge(section_id).get("template", {}) or {}

    def get_required_elements(self, section_id: str) -> List[str]:
        return self.get_section_knowledge(section_id).get("required_elements", []) or []

    def get_style_rules(self, section_id: str) -> List[str]:
        return self.get_section_knowledge(section_id).get("style_rules", []) or []

    def get_formatting_rules(self, section_id: str) -> List[str]:
        return self.get_section_knowledge(section_id).get("formatting_rules", []) or []

    def get_example_snippets(self, section_id: str) -> List[str]:
        return self.get_section_knowledge(section_id).get("example_snippets", []) or []

    def get_prohibited_phrases(self, section_id: str) -> List[str]:
        return self.get_section_knowledge(section_id).get("prohibited_phrases", []) or []

    def build_generation_package(self, section_id: str) -> SectionTemplatePackage:
        k = self.get_section_knowledge(section_id)
        template = k.get("template", {}) or {}
        return SectionTemplatePackage(
            section_id=section_id,
            title=str(k.get("title", template.get("heading", section_id)) or section_id),
            template=template,
            required_elements=self.get_required_elements(section_id),
            style_rules=self.get_style_rules(section_id),
            formatting_rules=self.get_formatting_rules(section_id),
            prohibited_phrases=self.get_prohibited_phrases(section_id),
            example_snippets=self.get_example_snippets(section_id),
        )

    def render_constraints_block(self, section_id: str) -> str:
        """
        Non-breaking helper used by older code paths.
        """
        p = self.build_generation_package(section_id)
        structure_order = p.template.get("structure_order", []) or []
        structure_lines = [f"- {x}" for x in structure_order[:12]] if structure_order else ["- None specified"]
        required_lines = [f"- {x}" for x in p.required_elements[:16]] if p.required_elements else ["- None specified"]
        style_lines = [f"- {x}" for x in p.style_rules[:12]] if p.style_rules else ["- None specified"]

        return "\n".join(
            [
                f"Section ID: {p.section_id}",
                f"Target Heading: {p.template.get('heading', p.section_id)}",
                "Structure Order:",
                *structure_lines,
                "Required Elements:",
                *required_lines,
                "Style Rules:",
                *style_lines,
            ]
        )

