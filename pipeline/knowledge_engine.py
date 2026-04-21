"""
Knowledge Engine

Builds and caches a structured internal knowledge base from `resources/`.

Caching logic (spec-aligned):
  - Compute hash of all file mtimes in resources/
  - Store hash in data/knowledge_base/.cache_hash
  - If match: load data/knowledge_base/sections.json
  - Else: rebuild and overwrite sections.json

Note: This knowledge layer is used for structure/rules/style only.
It is NEVER used as factual evidence for the current study.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from config import DATA_DIR, MAPPINGS_DIR, RESOURCES_DIR, FORCE_REBUILD_KNOWLEDGE
from pipeline.document_loader import DocumentLoader


class KnowledgeEngine:
    """
    Transforms `resources/` into a cached structured knowledge base.
    """

    SECTION_IDS: List[str] = [
        "synopsis",
        "introduction",
        "ethics",
        "study_objectives",
        "investigators_sites",
        "study_design",
        "inclusion_exclusion",
        "treatments",
        "endpoints",
        "study_population",
        "demographics",
        "efficacy_evaluation",
        "statistical_methods",
        "safety_evaluation",
        "adverse_events",
        "discussion_conclusions",
    ]

    # Prohibited phrases list for generation (also used as validator inputs later).
    DEFAULT_PROHIBITED_PHRASES: List[str] = [
        # future / advisory signals
        "will be",
        "is expected",
        "should",
        "likely",
        "presumably",
        "probably",
        "possibly",
        "may have",
        "it is possible",
        "it appears",
        "it is expected",
        "expected to",
        "would likely",
        "it seems",
        "generally",
        "typically",
        # first-person/promo signals
        "we believe",
        "we assume",
        "our study",
        # marketing-ish
        "superior",
        "best-in-class",
        "excellent results",
    ]

    def __init__(self, resources_dir: Path, cache_dir: Path):
        self.resources_dir = Path(resources_dir)
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.section_mapping_file = Path(MAPPINGS_DIR) / "csr_section_mapping.json"
        self.mvp_sections_file = Path(MAPPINGS_DIR) / "mvp_sections.json"

        self.cache_hash_file = self.cache_dir / ".cache_hash"
        self.sections_file = self.cache_dir / "sections.json"

    def _load_json(self, path: Path, default: Any) -> Any:
        if not path.exists():
            return default
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def _save_json(self, path: Path, payload: Any) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _compute_resources_hash(self) -> str:
        """
        Compute a hash of all file mtimes in `resources/`.
        """
        h = hashlib.sha256()
        if not self.resources_dir.exists():
            return h.hexdigest()

        for f in sorted(self.resources_dir.rglob("*")):
            if not f.is_file():
                continue
            rel = str(f.relative_to(self.resources_dir))
            st = f.stat()
            h.update(rel.encode("utf-8", errors="ignore"))
            h.update(str(st.st_mtime_ns).encode("utf-8", errors="ignore"))
            h.update(str(st.st_size).encode("utf-8", errors="ignore"))
        return h.hexdigest()

    def _is_cache_valid(self) -> bool:
        if not self.sections_file.exists() or not self.cache_hash_file.exists():
            return False
        try:
            cached = self.cache_hash_file.read_text(encoding="utf-8").strip()
        except Exception:
            return False
        current = self._compute_resources_hash()
        return cached == current

    def load_or_build(self) -> Dict[str, Dict[str, Any]]:
        """
        Load cached sections.json or build it from `resources/`.
        """
        force = bool(FORCE_REBUILD_KNOWLEDGE)
        if not force and self._is_cache_valid():
            return self._load_json(self.sections_file, {})

        knowledge = self._build_knowledge_base()
        self._save_json(self.sections_file, knowledge)
        self.cache_hash_file.write_text(self._compute_resources_hash(), encoding="utf-8")
        return knowledge

    def _get_baseline_knowledge(self, section_id: str, csr_section: str, section_mapping: Dict[str, Any]) -> Dict[str, Any]:
        """
        Baseline ICH E3 fallback for all 16 sections.
        Ensures the pipeline works even with sparse resources.
        """
        output_structure = section_mapping.get("output_structure", {}) or {}
        structure_order = output_structure.get("subsections", []) or []
        keywords = section_mapping.get("keywords", []) or []

        # Required elements: start from structure topics + initial keyword coverage.
        # Keep stable, deterministic order.
        required: List[str] = []
        for item in structure_order:
            it = str(item).strip()
            if it and it not in required:
                required.append(it)
        for kw in keywords[:12]:
            it = str(kw).strip()
            if it and it not in required:
                required.append(it)

        style_rules = [
            "Use formal neutral regulatory tone.",
            "Prefer past tense for study conduct/results statements.",
            "Do not speculate or infer unsupported facts.",
            "When evidence is missing, state 'Not specified in source documents.'",
            "Use section-focused concise narrative structure.",
            "Avoid first-person language.",
        ]

        formatting_rules = [
            "Use paragraph format, not bullet lists, unless the template explicitly requires enumerations.",
            "Section headings must match ICH E3 numbering exactly.",
            "Do not use Markdown syntax (#, ##, **, bullets).",
        ]

        return {
            "section_id": section_id,
            "title": section_mapping.get("description", section_id),
            "template": {
                "heading": csr_section,
                "structure_order": structure_order,
                "subsections": [],
            },
            "required_elements": required,
            "style_rules": style_rules,
            "formatting_rules": formatting_rules,
            "example_snippets": [],
            "prohibited_phrases": self.DEFAULT_PROHIBITED_PHRASES,
        }

    def _detect_sections_covered(self, text_lower: str, section_mapping: Dict[str, Any]) -> List[str]:
        """
        Heuristic detection of which ICH E3 sections a resource document covers.
        """
        covered: List[str] = []
        for sid in self.SECTION_IDS:
            mapping = section_mapping.get(sid, {}) or {}
            csr_section = mapping.get("csr_section", "")
            keywords = mapping.get("keywords", []) or []

            # number pattern: match the csr section identifier (e.g. "9.1", "10.1")
            csr_mark = str(csr_section).split(" ")[0].strip() if csr_section else ""
            hits = 0
            if csr_mark and csr_mark in text_lower:
                hits += 1
            for kw in keywords[:8]:
                kw_l = str(kw).lower().strip()
                if kw_l and kw_l in text_lower:
                    hits += 1
            if hits >= 2:
                covered.append(sid)
        return covered

    def _extract_section_example_snippets(self, full_text: str, covered_section_ids: List[str], section_mapping: Dict[str, Any]) -> Dict[str, List[str]]:
        """
        Extract compact 2-3 snippets per section as style/structure references ONLY.
        """
        snippets: Dict[str, List[str]] = {sid: [] for sid in covered_section_ids}
        text = full_text or ""
        text_lower = text.lower()
        for sid in covered_section_ids:
            mapping = section_mapping.get(sid, {}) or {}
            keywords = [str(k).lower() for k in (mapping.get("keywords", []) or [])[:10]]
            hit_idx = -1
            for kw in keywords:
                if kw and kw in text_lower:
                    hit_idx = text_lower.find(kw)
                    break
            if hit_idx < 0:
                # last resort: near start (still style reference)
                snippet = text[:900].strip()
                if snippet:
                    snippets[sid].append(snippet)
                continue

            # Extract context window around the first hit.
            start = max(0, hit_idx - 420)
            end = min(len(text), hit_idx + 780)
            snippet = text[start:end].strip()
            if snippet:
                snippets[sid].append(snippet)

        # De-duplicate and cap to 2-3 per section.
        for sid in list(snippets.keys()):
            uniq: List[str] = []
            seen = set()
            for s in snippets[sid]:
                ss = s.strip()
                if ss and ss not in seen:
                    uniq.append(ss)
                    seen.add(ss)
            snippets[sid] = uniq[:3]
        return snippets

    def _build_knowledge_base(self) -> Dict[str, Dict[str, Any]]:
        """
        Build the full structured knowledge base.
        """
        section_mapping = self._load_json(self.section_mapping_file, {})
        mvp = self._load_json(self.mvp_sections_file, {}).get("mvp_sections", [])
        mvp_meta = {s.get("id"): s for s in mvp if s.get("id")}

        # Baseline for all 16 sections.
        knowledge: Dict[str, Dict[str, Any]] = {}
        for sid in self.SECTION_IDS:
            mapping = section_mapping.get(sid, {}) or {}
            csr_section = mapping.get("csr_section", "")
            if not csr_section:
                csr_section = mvp_meta.get(sid, {}).get("csr_section_number", sid)
            base = self._get_baseline_knowledge(sid, str(csr_section), mapping)
            knowledge[sid] = base
            # Prefer MVP title/description if present.
            if mvp_meta.get(sid, {}).get("name"):
                knowledge[sid]["title"] = mvp_meta[sid]["name"]

        # If resources exists, mine example snippets and enrich.
        try:
            loader = DocumentLoader(self.resources_dir)
            docs = loader.load_all_documents()
            for _, doc in docs.items():
                full_text = (doc.get("full_text") or "").strip()
                if not full_text:
                    continue
                lower = full_text.lower()
                covered = self._detect_sections_covered(lower, section_mapping)
                if not covered:
                    continue
                mined = self._extract_section_example_snippets(full_text, covered, section_mapping)
                for sid in covered:
                    ex = knowledge[sid].get("example_snippets", [])
                    for s in mined.get(sid, [])[:3]:
                        if s not in ex:
                            ex.append(s)
                    knowledge[sid]["example_snippets"] = ex[:3]
        except Exception:
            # Keep pipeline robust: knowledge build must not hard-fail.
            pass

        return knowledge

