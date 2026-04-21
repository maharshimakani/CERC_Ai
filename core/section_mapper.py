"""
Section Mapper
──────────────
Takes extracted documents and returns structured, section-wise inputs
using the CSR mapping configuration.

Responsibilities:
  - Load the csr_mapping.json that links CSR sections -> document types.
  - Accept loaded/extracted document data.
  - Return a dict[section_id -> list[evidence_blocks]] so downstream
    stages know exactly which source text feeds each section.

This module is ADDITIVE — it does NOT modify or replace any existing
pipeline component.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class SectionMapper:
    """Maps extracted document content to CSR sections based on csr_mapping.json."""

    def __init__(self, mapping_path: Optional[Path] = None):
        """
        Args:
            mapping_path: Absolute path to csr_mapping.json.
                          Falls back to <project>/mappings/csr_mapping.json.
        """
        if mapping_path is None:
            mapping_path = Path(__file__).parent.parent / "mappings" / "csr_mapping.json"
        self.mapping_path = Path(mapping_path)
        self.mapping: Dict[str, Any] = self._load_mapping()

    # ── Private helpers ──────────────────────────────────────────────

    def _load_mapping(self) -> Dict[str, Any]:
        """Load and validate the mapping file."""
        if not self.mapping_path.exists():
            logger.warning("csr_mapping.json not found at %s — using empty mapping", self.mapping_path)
            return {}
        try:
            with open(self.mapping_path, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            # Strip meta key if present
            return {k: v for k, v in data.items() if not k.startswith("_")}
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Failed to load csr_mapping.json: %s", exc)
            return {}

    @staticmethod
    def _classify_document(filename: str, doc_data: Dict[str, Any]) -> str:
        """
        Infer the document_type from filename or metadata.

        Classification order:
          1. Prefer explicit 'document_type' already set by the loader.
          2. Filename keyword scan (most reliable signal).
          3. Content text scan (first 3000 chars).
          4. Fallback: 'unknown' — unknown docs are NOT forced into any section;
             they can only reach a section via content-keyword matching (Pass 2).

        Returns one of: protocol, sap, monitoring_plan, clinical_report,
                        safety_report, charter, appendix, unknown.
        """
        # 1. Prefer explicit type if the loader already assigned one
        explicit = (doc_data.get("document_type") or "").lower().strip()
        if explicit and explicit not in ("unknown", "appendix", ""):
            return explicit

        fn = filename.lower()

        # 2. Filename keyword scan — explicit priority order
        # Protocol / CIP (primary clinical investigation plan evidence)
        if any(kw in fn for kw in (
            "cip", "protocol", "investigation", "investigational_plan",
            "investigational plan", "clinical_investigation",
        )):
            return "protocol"

        # Monitoring plan
        if any(kw in fn for kw in ("monitor", "monitoring", "cmp", "cmp_")):
            return "monitoring_plan"

        # SAP
        if any(kw in fn for kw in ("sap", "statistical", "analysis_plan")):
            return "sap"

        # CEC Charter
        if any(kw in fn for kw in ("charter", "cec", "adjudication")):
            return "charter"

        # Clinical report / CSR
        if any(kw in fn for kw in (
            "clinical_investigation_report", "cir", "csr", "clinical_report",
            "clinical report", "study_report", "study report", "final_report",
        )):
            return "clinical_report"

        # Safety report
        if any(kw in fn for kw in ("safety", "dsmb", "dsur")):
            return "safety_report"

        # Appendix / Annex
        if any(kw in fn for kw in ("appendix", "annex", "attachment")):
            return "appendix"

        # 3. Content-based scan (first 3000 chars) when filename gives no signal
        text_sample = (doc_data.get("full_text") or "")[:3000].lower()
        if text_sample:
            if any(kw in text_sample for kw in (
                "clinical study protocol", "study protocol", "protocol number",
                "investigational plan", "clinical investigation plan",
                "protocol synopsis", "clinical investigation plan",
            )):
                return "protocol"
            if any(kw in text_sample for kw in (
                "statistical analysis plan", "analysis population",
                "randomization ratio", "analysis method",
            )):
                return "sap"
            if any(kw in text_sample for kw in (
                "clinical monitoring plan", "site monitoring",
                "monitoring visit", "monitor responsibilities",
            )):
                return "monitoring_plan"
            if any(kw in text_sample for kw in (
                "clinical study report", "study report", "results summary",
                "efficacy results", "primary endpoint result",
            )):
                return "clinical_report"

        # 4. Fallback: 'unknown'
        # Unknown documents are NOT silently injected into sections.
        # They can only reach a section if their text matches section keywords
        # in the content-keyword bypass (Pass 2 of map_documents).
        logger.info(
            "SectionMapper: '%s' unrecognized — classified as 'unknown'. "
            "Will reach sections only via content-keyword matching.",
            filename,
        )
        return "unknown"

    SECTION_CONTENT_KEYWORDS: Dict[str, List[str]] = {
        "synopsis": [
            "protocol synopsis", "study synopsis", "study title",
            "objective", "population", "primary endpoint", "synopsis",
            "title of study", "protocol number",
        ],
        "introduction": [
            "background", "introduction", "rationale", "disease area",
            "unmet medical need",
        ],
        "ethics": [
            "ethics", "irb", "institutional review", "informed consent",
            "good clinical practice", "gcp", "declaration of helsinki",
        ],
        "study_objectives": [
            "primary objective", "secondary objective", "exploratory objective",
            "study objective", "aim of the study", "objective of the study",
        ],
        "investigators_sites": [
            "investigator", "principal investigator", "site", "clinical site",
            "study site", "cra", "clinical research associate",
        ],
        "study_design": [
            "study design", "observational", "single-arm", "open-label",
            "multicenter", "randomized", "treatment arm", "control group",
            "double-blind", "crossover",
        ],
        "inclusion_exclusion": [
            "inclusion criteria", "exclusion criteria", "eligibility",
            "key inclusion", "key exclusion",
        ],
        "treatments": [
            "treatment", "dose", "dosage", "administration",
            "investigational product", "study drug", "ip", "comparator",
        ],
        "endpoints": [
            "primary endpoint", "secondary endpoint", "efficacy variable",
            "safety variable", "endpoint",
        ],
        "study_population": [
            "subject disposition", "enrolled", "randomized", "completed",
            "discontinued", "intent-to-treat", "itt", "per-protocol",
        ],
        "demographics": [
            "demographics", "demographic", "baseline", "age", "sex", "gender",
            "ethnicity", "race", "body weight", "bmi",
        ],
        "efficacy_evaluation": [
            "efficacy", "primary endpoint result", "response rate",
            "overall survival", "progression-free", "clinical outcome",
        ],
        "statistical_methods": [
            "statistical method", "analysis method", "sample size",
            "power calculation", "hypothesis test", "p-value",
        ],
        "safety_evaluation": [
            "safety", "adverse event", "serious adverse event", "ae", "sae",
            "tolerability", "toxicity",
        ],
        "adverse_events": [
            "adverse event", "ae", "sae", "serious adverse",
            "treatment-emergent", "teae",
        ],
        "discussion_conclusions": [
            "discussion", "conclusion", "overall conclusion", "benefit-risk",
            "clinical significance",
        ],
    }

    @classmethod
    def contains_keywords(cls, text: str, keywords: List[str]) -> bool:
        return any(k in text for k in keywords)

    _embed_cache = {}

    @classmethod
    def _get_embedding(cls, text: str) -> list[float]:
        if not text:
            return []
        # In-memory caching for embeddings
        cache_key = text[:1000]
        if cache_key in cls._embed_cache:
            print(f"[EMBED_CACHE] hit")
            return cls._embed_cache[cache_key]
            
        print(f"[EMBED_CACHE] miss")
        try:
            from openai import OpenAI
            client = OpenAI()
            emb = client.embeddings.create(
                model="text-embedding-3-small",
                input=cache_key
            ).data[0].embedding
            cls._embed_cache[cache_key] = emb
            return emb
        except Exception as e:
            # Failure safety: Pipeline must NEVER crash due to API
            print(f"[SEMANTIC] Embedding failed: {e}. Falling back to keywords.")
            return []

    @classmethod
    def _cosine_sim(cls, a: list[float], b: list[float]) -> float:
        import numpy as np
        if not a or not b:
            return 0.0
        return np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b))

    @classmethod
    def _semantic_match(cls, text: str, section_id: str) -> bool:
        SECTION_QUERIES = {
            "synopsis": "clinical study synopsis objective design population",
            "study_design": "study design randomized observational arms endpoints",
            "demographics": "baseline demographics age gender patient characteristics"
        }
        
        query = SECTION_QUERIES.get(section_id)
        if not query:
            return False

        query_emb = cls._get_embedding(query)
        text_emb = cls._get_embedding(text[:1000])

        if not query_emb or not text_emb:
            return False

        return cls._cosine_sim(query_emb, text_emb) > 0.75

    @classmethod
    def _content_keywords_match(cls, text: str, section_id: str) -> tuple[bool, list, list]:
        """
        Return (matched_bool, exact_matches, semantic_matches)
        """
        keywords = cls.SECTION_CONTENT_KEYWORDS.get(section_id, [])
        if not keywords:
            return False, [], []
            
        exact = [k for k in keywords if k in text]
        if exact:
            return True, exact, []
            
        # Semantic mapping fallback: Only run if keyword match failed AND text length > 200
        if len(text) > 200:
            if cls._semantic_match(text, section_id):
                return True, [], ["_openai_semantic_"]
                
        return False, [], []

    # ── Public API ───────────────────────────────────────────────────

    def build_resource_context(self, section_id: str, resources: List[Dict]) -> Dict[str, Any]:
        """Extract ONLY relevant structural guidance from resources."""
        relevant_paras = []
        types_used = set()
        filenames_used = set()
        
        # Priority map per section
        PRIORITY = {
            "synopsis": ["protocol_reference", "clinical_report_example", "template_reference"],
            "study_design": ["protocol_reference", "statistical_reference", "clinical_report_example"],
            "demographics": ["statistical_reference", "clinical_report_example", "protocol_reference"]
        }
        
        for r in resources:
            text = (r.get("full_text") or "").strip()
            if not text:
                continue
                
            rtype = r.get("resource_type", "")
            fname = r.get("filename", "")
            paras = [p.strip() for p in text.split("\n\n") if len(p.strip()) > 30]
            
            prio_list = PRIORITY.get(section_id, [])
            # Priority bonus helps sort ties
            prio_bonus = 0
            if rtype in prio_list:
                prio_bonus = (len(prio_list) - prio_list.index(rtype)) * 0.1
                
            for p in paras:
                p_lower = p.lower()
                score = 0
                
                # Determine negative scoring
                if any(w in p_lower for w in ["table of contents", "document history", "revision history", "confidentiality statement", "signature", "approved by", "sponsor contact details", "address", "email"]):
                    score -= 5
                
                # Determine positive scoring if not strictly negative
                if score >= 0:
                    if section_id.replace("_", " ") in p_lower:
                        score += 5
                        
                    if any(w in p_lower for w in ["objective", "methodology", "population", "endpoint", "baseline", "safety", "inclusion", "exclusion"]):
                        score += 4
                        
                    # +3 prose quality (minimum length and descriptive markers like words like 'was', 'were', 'the study')
                    if "the study" in p_lower and ("was" in p_lower or "were" in p_lower) and len(p_lower) > 100:
                        score += 3
                        
                    if "this study is designed to" in p_lower or "this investigation is" in p_lower or "the primary objective is" in p_lower:
                        score += 2
                        
                if score > 0:
                    relevant_paras.append((score + prio_bonus, p, rtype, fname))
                    
        # Select top paragraphs, bounding char count to 2500
        relevant_paras.sort(key=lambda x: x[0], reverse=True)
        selected_text = []
        current_len = 0
        
        for score, p, rtype, fname in relevant_paras:
            if current_len + len(p) <= 2500:
                selected_text.append(p)
                types_used.add(rtype)
                filenames_used.add(fname)
                current_len += len(p) + 2
                
        joined_text = "\n\n".join(selected_text)
        
        print(f"[RESOURCE MAP] section={section_id} chars={len(joined_text)}")
        print(f"[RESOURCE MAP] Resource types used: {list(types_used)}")
        print(f"[RESOURCE MAP] Resource filenames: {list(filenames_used)}")
        
        return {
            "resource_text": joined_text,
            "resource_types_used": list(types_used),
            "resource_filenames": list(filenames_used),
            "resource_char_count": len(joined_text)
        }

    def get_section_ids(self) -> List[str]:
        """Return all CSR section IDs defined in the mapping."""
        return list(self.mapping.keys())

    def get_section_config(self, section_id: str) -> Dict[str, Any]:
        """Return the raw mapping entry for a section, or empty dict."""
        return self.mapping.get(section_id, {})

    def map_documents(
        self,
        loaded_documents: Dict[str, Dict[str, Any]],
    ) -> Dict[str, Dict[str, Any]]:
        """
        Map loaded documents -> CSR sections.

        Strategy:
          0. Protocol-priority fast-path: any doc classified as 'protocol'
             is guaranteed to feed synopsis, study_design, and demographics
             before the regular type-matching pass runs. This prevents CIP
             content from being silently excluded.
          1. Primary pass: match by document_type (as before)
          2. Secondary pass: for sections that still have no evidence,
             scan each document’s text for section-relevant keywords and
             include it as secondary_evidence if keywords match.
             Also covers 'appendix'/'unknown'/'unclassified' docs.

        Args:
            loaded_documents: {filename: {full_text, document_type, ...}}

        Returns:
            {section_id: {
                "csr_section": "...",
                "primary_evidence": [{"filename": ..., "text": ..., "doc_type": ...}],
                "secondary_evidence": [{"filename": ..., "text": ..., "doc_type": ...}],
                "combined_text": "...",
                "source_count": int,
            }}
        """
        import re

        # Classify every document once
        classified: Dict[str, str] = {}
        for fname, ddata in loaded_documents.items():
            classified[fname] = self._classify_document(fname, ddata)
            print(
                f"[MAPPER] '{fname}' -> doc_type='{classified[fname]}' "
                f"(text_len={len((ddata.get('full_text') or '').strip())})"
            )

        # ── Protocol-priority fast-path ───────────────────────────────
        # Sections that MUST receive protocol/CIP content whenever available.
        PROTOCOL_PRIORITY_SECTIONS = {
            "synopsis", "study_design", "demographics",
            "study_objectives", "introduction", "endpoints",
            "inclusion_exclusion", "treatments", "study_population",
        }

        # Build pre-assigned evidence blocks keyed by section_id
        protocol_evidence_cache: Dict[str, List[Dict[str, Any]]] = {
            sid: [] for sid in PROTOCOL_PRIORITY_SECTIONS
        }
        for fname, ddata in loaded_documents.items():
            if classified[fname] != "protocol":
                continue
            raw_text = (ddata.get("full_text") or "").strip()
            if not raw_text:
                continue
            text = re.sub(r'\s+', ' ', raw_text.lower())
            block = {
                "filename": fname,
                "text": text,
                "doc_type": "protocol",
                "char_count": len(text),
                "protocol_priority": True,
            }
            for sid in PROTOCOL_PRIORITY_SECTIONS:
                protocol_evidence_cache[sid].append(block)
            print(
                f"[MAPPER] Protocol fast-path: '{fname}' pre-assigned to "
                f"{len(PROTOCOL_PRIORITY_SECTIONS)} priority sections"
            )

        result: Dict[str, Dict[str, Any]] = {}

        for section_id, sec_cfg in self.mapping.items():
            primary_types = set(sec_cfg.get("primary_sources", []))
            secondary_types = set(sec_cfg.get("secondary_sources", []))

            # Seed with pre-assigned protocol evidence (if this is a priority section)
            primary_evidence: List[Dict[str, Any]] = list(
                protocol_evidence_cache.get(section_id, [])
            )
            secondary_evidence: List[Dict[str, Any]] = []
            # Track filenames already included to avoid duplicates
            already_included: set = {b["filename"] for b in primary_evidence}

            # ── Pass 1: Standard doc-type matching ────────────────────
            for fname, ddata in loaded_documents.items():
                dtype = classified[fname]
                raw_text = (ddata.get("full_text") or "").strip()
                if not raw_text:
                    logger.debug("[MAPPER] Skipping '%s' -- empty text", fname)
                    continue

                text = re.sub(r'\s+', ' ', raw_text.lower())

                block = {
                    "filename": fname,
                    "text": text,
                    "doc_type": dtype,
                    "char_count": len(text),
                }

                if fname in already_included:
                    # Already added via protocol fast-path; do not duplicate
                    continue

                if dtype in primary_types:
                    primary_evidence.append(block)
                    already_included.add(fname)
                elif dtype in secondary_types:
                    secondary_evidence.append(block)
                    already_included.add(fname)

            # ── Pass 2: Content-keyword bypass ────────────────────────
            # For each document NOT yet matched, check if its text contains
            # section-relevant keywords. This covers appendix/unknown/protocol
            # docs that were not in primary/secondary type lists.
            for fname, ddata in loaded_documents.items():
                if fname in already_included:
                    continue
                raw_text = (ddata.get("full_text") or "").strip()
                if not raw_text:
                    continue

                text = re.sub(r'\s+', ' ', raw_text.lower())

                matched, exact, semantic = self._content_keywords_match(text, section_id)
                if matched:
                    secondary_evidence.append({
                        "filename": fname,
                        "text": text,
                        "doc_type": classified[fname],
                        "char_count": len(text),
                        "matched_via_keywords": True,
                        "semantic_matches": semantic,
                        "exact_matches": exact,
                    })
                    if semantic and "_openai_semantic_" in semantic:
                        print(f"[SEMANTIC] Match triggered for {section_id} on {fname}")
                    already_included.add(fname)
                    logger.info(
                        "[MAPPER] '%s' -> '%s' via content-keyword bypass",
                        fname, section_id,
                    )

            # ── Component 2: Source Priority Sorting ────────────────
            SOURCE_PRIORITY = {
                "synopsis": ["protocol"],
                "study_design": ["protocol"],
                "demographics": ["clinical_report", "sap", "protocol"]
            }
            default_prio = SOURCE_PRIORITY.get(section_id, [])

            def get_sort_key(block):
                dt = block.get("doc_type", "unknown")
                if dt in default_prio:
                    return default_prio.index(dt)
                return len(default_prio) + 1  # lower priority

            all_evidence = primary_evidence + secondary_evidence
            all_evidence.sort(key=get_sort_key)
            
            source_priority_used = default_prio if all_evidence and all_evidence[0].get("doc_type") in default_prio else []

            # ── Combine text from mapping ─────────────────────────────
            combined_text = "\n\n".join(b["text"] for b in all_evidence if b.get("text"))
            
            # Extract semantic matches
            semantic_matches = []
            for b in all_evidence:
                if b.get("semantic_matches"):
                    semantic_matches.extend(b["semantic_matches"])

            result[section_id] = {
                "csr_section": sec_cfg.get("name", section_id),
                "primary_evidence": primary_evidence,
                "secondary_evidence": secondary_evidence,
                "combined_text": combined_text,
                "source_count": len(all_evidence),
                "semantic_matches": list(set(semantic_matches)),
                "source_priority_used": source_priority_used,
                "template_file": sec_cfg.get("template_file"),
                "example_file": sec_cfg.get("example_file"),
            }

            # Mandatory [MAP] debug trace (per spec)
            assigned_docs = [b["filename"] for b in primary_evidence + secondary_evidence]
            # Collect which keywords actually matched in the combined text
            combined_lower = combined_text.lower()
            section_keywords = self.SECTION_CONTENT_KEYWORDS.get(section_id, [])
            matched_kw = [kw for kw in section_keywords if kw in combined_lower]
            print(f"[MAP] Section: {section_id}")
            print(f"[MAP] Assigned Docs: {assigned_docs}")
            print(f"[MAP] Combined Length: {len(combined_text)}")
            print(f"[MAP] Matched Keywords: {matched_kw}")

        logger.info(
            "SectionMapper: mapped %d documents -> %d sections",
            len(loaded_documents),
            len(result),
        )
        return result
