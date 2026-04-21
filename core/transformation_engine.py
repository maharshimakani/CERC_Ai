"""
Transformation Engine — Layer 4
────────────────────────────────
Prepares section-level input text for LLM consumption.

Responsibilities:
  - Clean section input text further
  - Remove irrelevant fragments (table of contents, headers, etc.)
  - Normalize language artifacts
  - Chunk long content safely for token limits
  - Return LLM-ready text

This module is ADDITIVE — it sits between mapping and prompt building.
"""

from __future__ import annotations

import logging
import re
from typing import List, Optional
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Default max characters per section input
DEFAULT_MAX_CHARS = 4000

SECTION_CONFIG = {
    "synopsis": {
        "keywords": ["objective", "study design", "population", "endpoint"],
        "anchors": ["objective", "study design"],
        "priority_weight": 3
    },
    "study_design": {
        "keywords": ["study design", "method", "treatment", "endpoint", "randomized", "observational"],
        "anchors": ["study design", "method"],
        "priority_weight": 4
    },
    "demographics": {
        "keywords": ["age", "gender", "sex", "baseline", "demographic"],
        "anchors": ["age", "baseline"],
        "priority_weight": 5
    }
}

class TransformationEngine:
    """Cleans and prepares mapped section text for LLM prompt injection."""

    def __init__(self, max_chars: int = DEFAULT_MAX_CHARS):
        self.max_chars = max_chars

    @staticmethod
    def is_section_relevant(paragraph: str, section_id: str) -> bool:
        SECTION_KEYWORDS = {
            "synopsis": ["objective", "population", "endpoint"],
            "study_design": ["study design", "randomized", "arm"],
            "demographics": ["age", "gender", "baseline", "bmi"]
        }
        if section_id not in SECTION_KEYWORDS:
            return True
        
        p_lower = paragraph.lower()
        if any(k in p_lower for k in SECTION_KEYWORDS[section_id]):
            return True
            
        import difflib
        for k in SECTION_KEYWORDS[section_id]:
            for word in p_lower.split():
                if difflib.SequenceMatcher(None, k, word).ratio() > 0.65:
                    return True
        return False

    # ── Cleaning passes ──────────────────────────────────────────────

    @staticmethod
    def remove_toc_lines(text: str) -> str:
        """Remove table-of-contents–style lines (dotted leaders)."""
        lines = text.split("\n")
        cleaned = []
        for line in lines:
            # Lines like "3.1 Study Design .............. 12"
            if re.search(r"\.{4,}", line):
                continue
            # Lines that are just page numbers
            if re.match(r"^\s*\d{1,3}\s*$", line):
                continue
            cleaned.append(line)
        return "\n".join(cleaned)

    @staticmethod
    def remove_repeated_headers(text: str) -> str:
        """Remove likely repeated document headers/footers."""
        lines = text.split("\n")
        if len(lines) < 20:
            return text

        # Find lines that repeat > 3 times (likely headers/footers)
        from collections import Counter
        stripped = [l.strip() for l in lines if l.strip()]
        counts = Counter(stripped)
        repeated = {l for l, c in counts.items() if c > 3 and len(l) < 120}

        if not repeated:
            return text

        cleaned = [l for l in lines if l.strip() not in repeated]
        return "\n".join(cleaned)

    @staticmethod
    def normalize_whitespace(text: str) -> str:
        """Collapse excessive whitespace while preserving paragraph structure."""
        # Collapse 3+ newlines
        text = re.sub(r"\n{3,}", "\n\n", text)
        # Collapse inline whitespace
        text = re.sub(r"[ \t]{2,}", " ", text)
        return text.strip()

    @staticmethod
    def remove_boilerplate(text: str) -> str:
        """Remove common boilerplate phrases that add no clinical value."""
        patterns = [
            r"(?i)this document is confidential.*?\n",
            r"(?i)for internal use only.*?\n",
            r"(?i)do not distribute.*?\n",
            r"(?i)all rights reserved.*?\n",
            r"(?i)proprietary and confidential.*?\n",
        ]
        for pat in patterns:
            text = re.sub(pat, "", text)
        return text

    # ── Chunking ─────────────────────────────────────────────────────

    def chunk_text(self, text: str, max_chars: Optional[int] = None) -> List[str]:
        """
        Split long text into manageable chunks on paragraph boundaries.

        Args:
            text: Full section text.
            max_chars: Override for max characters per chunk.

        Returns:
            List of text chunks.
        """
        limit = max_chars or self.max_chars
        if len(text) <= limit:
            return [text]

        chunks: List[str] = []
        paragraphs = text.split("\n\n")
        current = ""

        for para in paragraphs:
            if len(current) + len(para) + 2 > limit and current:
                chunks.append(current.strip())
                current = para
            else:
                current = current + "\n\n" + para if current else para

        if current.strip():
            chunks.append(current.strip())

        logger.debug("Chunked text into %d pieces (avg %d chars)",
                      len(chunks), sum(len(c) for c in chunks) // max(len(chunks), 1))
        return chunks

    # ── Main transform API ───────────────────────────────────────────

    def transform(self, text: str, section_id: str = None) -> str:
        """
        Apply all cleaning passes to section input text.

        Cleaning order:
          0. Whitespace normalization — re.sub(r'\\s+', ' ', text) across the
             full string.
          1. Pre-normalize whitespace (collapses PDF multi-column garbling)
          2. Remove boilerplate phrases
          3. Remove TOC lines
          4. Remove repeated headers/footers
          5. Final whitespace normalization + Priority-based Retentive Truncation

        Args:
            text: Raw mapped section text.
            section_id: Current CSR section identifier.

        Returns:
            Cleaned, normalized text ready for prompt injection.
        """
        if not text or not text.strip():
            return ""

        result = text

        # Step 0: Pre-clean typical spacing but preserve paragraph breaks.
        result = re.sub(r'[ \t]{2,}', ' ', result)

        # Step 1: Filter general noise
        result = self.remove_boilerplate(result)
        result = self.remove_toc_lines(result)
        result = self.remove_repeated_headers(result)
        result = self.normalize_whitespace(result)

        # STEP 2 — ADVANCED PARAGRAPH SPLITTING
        paragraphs_raw = re.split(r"\n{2,}|\r\n{2,}", result)
        paragraphs = []
        for p in paragraphs_raw:
            p_clean = re.sub(r"\s+", " ", p).strip()
            if p_clean:
                paragraphs.append(p_clean)

        if len(paragraphs) < 2 and result.count(".") > 5:
            sentences = [s.strip() + "." for s in re.split(r'\.\s+', result) if s.strip()]
            paragraphs = []
            chunk = []
            for s in sentences:
                chunk.append(s)
                if len(chunk) == 3:
                    paragraphs.append(" ".join(chunk))
                    chunk = []
            if chunk:
                paragraphs.append(" ".join(chunk))

        if not paragraphs:
            return ""

        # STEP 3 — MULTI-DIMENSION SCORING SYSTEM
        scored_paragraphs = []
        cfg = SECTION_CONFIG.get(section_id, {})
        keywords = cfg.get("keywords", [])
        priority_weight = cfg.get("priority_weight", 0)

        for i, paragraph in enumerate(paragraphs):
            score = 0
            p_lower = paragraph.lower()
            is_numeric = False

            # 3.1 & 3.2 & 3.3
            for kw in keywords:
                if kw in p_lower:
                    score += 2
                    score += priority_weight

                matcher = SequenceMatcher(None, p_lower, kw)
                match = matcher.find_longest_match(0, len(p_lower), 0, len(kw))
                if matcher.ratio() > 0.65 and match.size > 20:
                    score += 2

            # MINIMUM QUALITY FILTER & SMART FILTER
            if len(paragraph) < 40:
                continue
                
            uppers = sum(1 for c in paragraph if c.isupper())
            if uppers / max(len(paragraph), 1) > 0.5:
                continue
                
            if any(rej in p_lower for rej in ["cra", "monitoring", "sop", "signature", "version", "confidential", "page x of y", "page", "copyright"]):
                continue  # Reject entirely

            # 3.4 & 3.5 NUMERIC & KEYWORD PRIORITY WITH RELEVANCE CHECK
            force_include = False
            is_numeric = False
            
            is_num_match = bool(re.search(r'\d|%|n=', p_lower))
            
            kw_score = 0
            if "study design" in p_lower:
                kw_score = max(kw_score, 15)
            if "objective" in p_lower:
                kw_score = max(kw_score, 14)
            if "endpoint" in p_lower:
                kw_score = max(kw_score, 13)
            if any(signal in p_lower for signal in ["population", "arm", "randomized"]):
                kw_score = max(kw_score, 8)
                
            if is_num_match:
                kw_score = max(kw_score, 10)
                
            if is_num_match or kw_score > 0:
                if TransformationEngine.is_section_relevant(paragraph, section_id):
                    score += kw_score
                    force_include = True
                    if is_num_match:
                        is_numeric = True
                else:
                    score -= 5

            scored_paragraphs.append({
                "text": paragraph,
                "score": score,
                "is_numeric": is_numeric,
                "force_include": force_include,
                "index": i
            })

        # STEP 4 — SMART ANCHOR SELECTION (CRITICAL)
        anchors = cfg.get("anchors", [])
        anchor_paragraphs = []
        anchor_indices = set()

        for anchor in anchors:
            best_p = None
            best_score = -9999
            for p_dict in scored_paragraphs:
                if anchor in p_dict["text"].lower() and p_dict["score"] > best_score:
                    best_score = p_dict["score"]
                    best_p = p_dict

            if best_p and best_p["index"] not in anchor_indices:
                anchor_paragraphs.append(best_p)
                anchor_indices.add(best_p["index"])

        # STEP 5 — GLOBAL PARAGRAPH RANKING
        sorted_paragraphs = sorted(scored_paragraphs, key=lambda x: x["score"], reverse=True)

        # STEP 6 — GUARANTEED STRUCTURAL COVERAGE
        min_structure = {"synopsis": 3, "study_design": 4, "demographics": 3}
        required_min = min_structure.get(section_id, 1)

        # STEP 7 & 8 & 9 — BUILD FINAL TEXT
        selected_items = []
        total_chars = 0
        MAX_LIMIT = 4000

        # 1. Selected anchor paragraphs
        for act_item in anchor_paragraphs:
            selected_items.append(act_item)
            total_chars += len(act_item["text"])

        # We can still add if it is numeric or needed for min structure
        # but we will strictly trim it back in the next step anyway
        for item in sorted_paragraphs:
            if item["index"] in anchor_indices:
                continue

            # STEP 8 — DEDUPLICATION (STRICT)
            is_dup = False
            for sel in selected_items:
                if SequenceMatcher(None, item["text"], sel["text"]).ratio() > 0.85:
                    is_dup = True
                    break
            if is_dup:
                continue

            selected_items.append(item)

        # HARD CAP ENFORCEMENT
        def get_chars(items):
            return sum(len(x["text"]) for x in items) + max(0, len(items) - 1) * 2

        current_chars = get_chars(selected_items)
        while current_chars > MAX_LIMIT and len(selected_items) > 1:
            # Drop lowest priority item
            lowest_item = None
            lowest_val = (999, 999999)
            for item in selected_items:
                # ANCHOR GUARANTEE: NEVER REMOVE FORCED ITEMS
                if item["index"] in anchor_indices or item.get("force_include"):
                    continue
                val = (0, item["score"])
                if val < lowest_val:
                    lowest_val = val
                    lowest_item = item
            
            if lowest_item:
                selected_items.remove(lowest_item)
            else:
                break
            current_chars = get_chars(selected_items)

        # STEP 10 — FINAL VALIDATION (MANDATORY)
        has_anchor = len(anchor_paragraphs) > 0
        has_keyword = any(item.get("force_include") for item in selected_items)
        has_numeric = any(item["is_numeric"] for item in selected_items)
        
        # We NO LONGER invalidate purely based on missing anchors if strong evidence is present.
        # But we do want to ensure we don't output totally arbitrary text.
        is_valid = True
        if len(anchors) > 0 and not has_anchor and not has_keyword:
            is_valid = False
        if section_id == "demographics" and not has_numeric:
            is_valid = False
        if not selected_items:
            is_valid = False
            
        # Enforce minimum paragraph thresholds per section
        if len(selected_items) < required_min:
            is_valid = False
            
        if not is_valid:
            return ""  # HARD RULE: Must be empty if no relevant evidence
            
        # Re-sort to original order
        selected_items.sort(key=lambda x: x["index"])
        selected = [item["text"] for item in selected_items]

        final_text = "\n\n".join(selected)

        # Absolute hard cap on character count if even a single paragraph exceeds limits
        if len(final_text) > MAX_LIMIT:
            final_text = final_text[:MAX_LIMIT]
            last_period = final_text.rfind('.')
            if last_period > MAX_LIMIT * 0.8:
                final_text = final_text[:last_period+1]

        # STEP 11 — DEBUG LOGGING (MANDATORY)
        print(f"[TRANSFORM] Section: {section_id}")
        print(f"[TRANSFORM] Total paragraphs: {len(paragraphs)}")
        print(f"[TRANSFORM] Anchors selected: {len(anchor_paragraphs)}")
        print(f"[TRANSFORM] Final selected: {len(selected)}")
        print(f"[TRANSFORM CAP] Section: {section_id} | Final chars: {len(final_text)} | Cap: {MAX_LIMIT}")

        return final_text
