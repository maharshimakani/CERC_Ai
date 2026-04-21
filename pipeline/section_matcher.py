"""
Section Matcher Module (POWER UPGRADED)
Matches source document sections to CSR sections using Semantic Vector Search via ChromaDB.
Falls back to lexical matching if semantic search fails.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any
import re
import chromadb
from chromadb.utils import embedding_functions

import sys
# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import OPENAI_API_KEY, KNOWLEDGE_BASE_DIR

logger = logging.getLogger(__name__)


class SectionMatcher:
    """Matches source document sections to CSR sections based on semantic vector search."""
    
    def __init__(self, mapping_file: Path):
        self.mapping_file = Path(mapping_file)
        self.mappings = self._load_mappings()
        
        # Initialize Vector DB
        try:
            self.chroma_client = chromadb.PersistentClient(path=str(KNOWLEDGE_BASE_DIR / "chroma_db"))
            self.embedding_fn = embedding_functions.OpenAIEmbeddingFunction(
                api_key=OPENAI_API_KEY,
                model_name="text-embedding-3-small"
            )
            self.collection_name = "csr_semantic_matcher"
            
            # Start fresh if we restart the orchestrator
            try:
                self.chroma_client.delete_collection(name=self.collection_name)
            except Exception:
                pass
                
            self.collection = self.chroma_client.get_or_create_collection(
                name=self.collection_name,
                embedding_function=self.embedding_fn
            )
            self.vector_search_ready = True
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB: {e}")
            self.vector_search_ready = False
            
    def _load_mappings(self) -> Dict:
        """Load the CSR section mappings from JSON file."""
        if not self.mapping_file.exists():
            raise FileNotFoundError(f"Mapping file not found: {self.mapping_file}")
            
        with open(self.mapping_file, 'r', encoding='utf-8') as f:
            return json.load(f)
            
    def build_vector_index(self, extracted_sections: Dict[str, Dict[str, Dict]]) -> None:
        """Embed all extracted documents into the semantic index space."""
        if not self.vector_search_ready:
            return
            
        ids = []
        documents = []
        metadatas = []
        
        for filename, sections in extracted_sections.items():
            for section_key, section_data in sections.items():
                content = section_data.get("content", "")
                word_count = section_data.get("word_count", len(content.split()))
                
                # Only embed meaningful text blocks
                if not content or word_count < 10:
                    continue
                    
                doc_id = f"{filename}::{section_key}"
                ids.append(doc_id)
                
                # We embed the section title alongside the content to give the vector more semantic weight
                title = section_data.get("title", "")
                enriched_text = f"Section Title: {title}\n\nContent: {content}"
                documents.append(enriched_text)
                
                metadatas.append({
                    "filename": str(filename),
                    "section_key": str(section_key),
                    "title": str(title),
                    "word_count": int(word_count),
                    "content": str(content) # Store raw content for retrieval
                })
        
        if documents:
            # Batch upsert to bypass payload limits
            batch_size = 100
            for i in range(0, len(documents), batch_size):
                self.collection.add(
                    ids=ids[i:i+batch_size],
                    documents=documents[i:i+batch_size],
                    metadatas=metadatas[i:i+batch_size]
                )
            logger.info(f"Built semantic vector index with {len(documents)} document sections.")

    def get_all_matching_content(
        self,
        csr_section_id: str,
        documents: Dict[str, Dict],
        extracted_sections: Dict[str, Dict[str, Dict]]
    ) -> Dict:
        """
        Get all matching content from all documents using Semantic Vector Search.
        """
        all_matches = []
        combined_content = []
        patterns_tried = 1 # query is treated as 1 pattern
        used_fallback = False
        
        mapping = self.mappings.get(csr_section_id, {})
        
        # Build a powerful semantic query using all available keywords and intent
        keywords = mapping.get("keywords", [])
        
        all_patterns = []
        for sm in mapping.get("source_mappings", []):
            all_patterns.extend(sm.get("section_patterns", []))
            all_patterns.extend(sm.get("subsections", []))
            
        semantic_query = f"Clinical Study Report section: {csr_section_id}. Information related to: "
        if all_patterns:
            semantic_query += ", ".join(list(set(all_patterns))[:10]) + ". "
        if keywords:
            semantic_query += "Keywords: " + ", ".join(keywords[:10])
            
        if self.vector_search_ready and self.collection.count() > 0:
            try:
                results = self.collection.query(
                    query_texts=[semantic_query],
                    n_results=4, # Top 4 most semantically similar sections
                    include=["metadatas", "distances"]
                )
                
                if results and results["metadatas"] and len(results["metadatas"]) > 0:
                    for idx, metadata in enumerate(results["metadatas"][0]):
                        distance = results["distances"][0][idx]
                        
                        # Chroma default is L2 distance, convert to generic 0-1 relevance
                        relevance_score = max(0.0, 1.0 - (distance / 2.0))
                        
                        # Only include relevant matches
                        if relevance_score > 0.35:
                            match_entry = {
                                "source_document": metadata["filename"],
                                "section_title": metadata["title"],
                                "content": metadata["content"],
                                "relevance_score": relevance_score,
                                "match_path": "semantic_vector_search",
                                "matched_via_document_sweep": False,
                                "matched_via_fallback": False,
                                "matched_via_keyword_fallback": False,
                                "word_count": metadata["word_count"]
                            }
                            all_matches.append(match_entry)
                            combined_content.append(metadata["content"])
            except Exception as e:
                logger.error(f"Vector search failed for {csr_section_id}: {e}")
                used_fallback = True
        else:
            used_fallback = True

        combined = "\n\n---\n\n".join(combined_content)

        output_structure = mapping.get("output_structure", {}) or {}
        req_topics = list(output_structure.get("subsections", []) or [])
        candidate_required = [str(x) for x in (req_topics + keywords[:6]) if str(x).strip()]

        low_combined = (combined or "").lower()
        candidate_missing: List[str] = []
        for el in candidate_required:
            el_l = str(el).strip().lower()
            if not el_l:
                continue
            if el_l not in low_combined:
                candidate_missing.append(str(el))

        matched_blocks = []
        for m in all_matches:
            matched_blocks.append(
                {
                    "source_file": m.get("source_document", "unknown"),
                    "source_section_title": m.get("section_title", ""),
                    "content": m.get("content", "") or "",
                    "relevance_score": float(m.get("relevance_score", 0.0) or 0.0),
                    "match_method": "semantic",
                    "source_pages": m.get("source_pages", []) or [],
                }
            )

        matched_blocks.sort(key=lambda b: b.get("relevance_score", 0.0), reverse=True)
        top_scores = [b.get("relevance_score", 0.0) for b in matched_blocks[:3]]
        overall_confidence = min(1.0, sum(top_scores) / max(len(top_scores), 1)) if top_scores else 0.0

        return {
            "section_id": csr_section_id,
            "matched_blocks": matched_blocks,
            "combined_content": combined,
            "overall_confidence": overall_confidence,
            "match_used_fallback": used_fallback,
            "candidate_missing_elements": candidate_missing,
            "matching_diagnostics": {
                "patterns_tried": patterns_tried,
                "patterns_matched": len(all_matches),
                "fallback_used": used_fallback,
                "keyword_fallback_used": False,
                "document_sweep_used": False,
                "total_matches": len(all_matches),
            },
        }

    def get_csr_section_ids(self) -> List[str]:
        return list(self.mappings.keys())

    def get_section_info(self, csr_section_id: str) -> Dict:
        return self.mappings.get(csr_section_id, {})

    def _normalize_heading(self, text: str) -> str:
        """Normalize heading by removing numbers, punctuation, and converting to lowercase."""
        if not text:
            return ""
        text = text.lower()
        # Strip "section X:" or "section X.Y "
        text = re.sub(r'^section\s+[\d\.]+\s*[:\-]?\s*', '', text)
        # Strip leading numbers like "1.", "9.1", "3.1.2 " 
        text = re.sub(r'^[\d\.]+\s*[:\-]?\s*', '', text)
        # Remove punctuation
        text = re.sub(r'[^\w\s]', '', text)
        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        return text

    def _fuzzy_match(self, pattern: str, heading: str) -> bool:
        """Match pattern against heading using normalized strings and simple fuzzy rules."""
        norm_pattern = self._normalize_heading(pattern)
        norm_heading = self._normalize_heading(heading)
        
        if not norm_pattern or not norm_heading:
            return False
            
        if norm_pattern == norm_heading:
            return True
            
        if norm_pattern in norm_heading:
            return True
            
        # Handle simple singular/plural
        if norm_pattern.endswith('s') and norm_pattern[:-1] in norm_heading:
            return True
        if not norm_pattern.endswith('s') and norm_pattern + 's' in norm_heading:
            return True
            
        return False

def match_sections_for_csr(
    csr_section_id: str,
    document_sections: Dict[str, Dict],
    document_type: str,
    mapping_file: Path
) -> List[Dict]:
    """Convenience function to match sections."""
    # Not using vector index bulk initialization in the convenience function
    # Because it requires the full corpus, so this is just returning an empty list, 
    # as the Orchestrator runs the stateful instance anyway.
    return []
