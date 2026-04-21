"""
Text Extractor Module
Extracts and structures text from loaded documents, identifying sections and headings.
"""

import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import json


class TextExtractor:
    """Extracts and structures text from clinical documents."""
    
    # Common section heading patterns in clinical documents
    HEADING_PATTERNS = [
        # Numbered sections (1. Section, 1.1 Subsection, etc.)
        r'^(\d+(?:\.\d+)*)\s+([A-Z][A-Za-z\s]+)',
        # All caps headings
        r'^([A-Z][A-Z\s]{3,})$',
        # Title case with colon
        r'^([A-Z][A-Za-z\s]+):\s*$',
        # Underlined (followed by === or ---)
        r'^([A-Za-z][A-Za-z\s]+)\n[=\-]{3,}',
    ]
    
    # Keywords indicating section boundaries
    SECTION_KEYWORDS = [
        "introduction", "background", "objectives", "study design",
        "methods", "methodology", "population", "eligibility",
        "inclusion criteria", "exclusion criteria", "endpoints",
        "primary endpoint", "secondary endpoints", "statistical",
        "analysis", "safety", "adverse events", "results",
        "discussion", "conclusion", "references", "appendix",
        "synopsis", "study synopsis", "protocol synopsis",
        "demographics", "treatments", "efficacy", "ethics",
        "investigators", "study population"
    ]
    
    def __init__(self):
        self.sections: Dict[str, Dict] = {}
        
    def identify_headings(self, text: str) -> List[Dict]:
        """
        Identify section headings in the document text.
        
        Args:
            text: The full document text
            
        Returns:
            List of heading dictionaries with position and level info
        """
        headings = []
        lines = text.split('\n')
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
                
            # Check for numbered headings (e.g., "9.1 Study Design")
            numbered_match = re.match(r'^(\d+(?:\.\d+)*)\s+(.+)$', line)
            if numbered_match:
                number = numbered_match.group(1)
                title = numbered_match.group(2).strip()
                level = len(number.split('.'))
                
                headings.append({
                    "line_number": i,
                    "text": line,
                    "number": number,
                    "title": title,
                    "level": level,
                    "type": "numbered"
                })
                continue
                
            # Check for all-caps headings
            if line.isupper() and len(line) > 3 and len(line.split()) <= 6:
                headings.append({
                    "line_number": i,
                    "text": line,
                    "number": None,
                    "title": line.title(),
                    "level": 1,
                    "type": "caps"
                })
                continue
            
            # Check for colon-pattern headings (e.g., "Study Title: A Phase III...")
            colon_match = re.match(r'^([A-Z][A-Za-z\s]{2,40}):\s+(.+)$', line)
            if colon_match:
                label = colon_match.group(1).strip()
                label_lower = label.lower()
                # Only treat as heading if label matches known section keywords
                if any(kw in label_lower for kw in self.SECTION_KEYWORDS) or len(label.split()) <= 3:
                    headings.append({
                        "line_number": i,
                        "text": line,
                        "number": None,
                        "title": label,
                        "level": 2,
                        "type": "colon"
                    })
                    continue
                
            # Check for keyword-based headings
            line_lower = line.lower()
            for keyword in self.SECTION_KEYWORDS:
                if line_lower.startswith(keyword) and len(line) < 100:
                    headings.append({
                        "line_number": i,
                        "text": line,
                        "number": None,
                        "title": line,
                        "level": 2,
                        "type": "keyword"
                    })
                    break
                    
        return headings
    
    def extract_sections(self, text: str) -> Dict[str, Dict]:
        """
        Extract document into sections based on headings.
        
        Args:
            text: The full document text
            
        Returns:
            Dictionary of sections with their content
        """
        headings = self.identify_headings(text)
        lines = text.split('\n')

        # Precompute provenance helpers for SourceRef creation.
        # - page mapping: if `full_text` includes " --- Page N ---" markers, map line -> N.
        page_for_line: List[int] = []
        current_page = 1
        for line in lines:
            m = re.search(r"---\s*Page\s+(\d+)\s*---", line, flags=re.IGNORECASE)
            if m:
                current_page = int(m.group(1))
            page_for_line.append(current_page)

        # - char offsets: build starting char index per line
        line_char_start: List[int] = []
        line_char_end: List[int] = []
        cursor = 0
        for line in lines:
            line_char_start.append(cursor)
            cursor_end = cursor + len(line)
            line_char_end.append(cursor_end)
            cursor = cursor_end + 1  # +1 for '\n'
        sections = {}
        
        if not headings:
            # No headings found, return entire text as one section
            return {
                "full_document": {
                    "title": "Full Document",
                    "number": None,
                    "content": text,
                    "start_line": 0,
                    "end_line": len(lines)
                }
            }
        
        for i, heading in enumerate(headings):
            start_line = heading["line_number"]
            
            # Find end of this section (start of next heading or end of document)
            if i < len(headings) - 1:
                end_line = headings[i + 1]["line_number"]
            else:
                end_line = len(lines)
                
            # Extract content (excluding the heading line itself)
            content_lines = lines[start_line + 1:end_line]
            content = '\n'.join(content_lines).strip()

            # Approximate character boundaries in original text.
            content_start_line_idx = min(max(start_line + 1, 0), len(lines) - 1)
            content_end_line_idx = min(max(end_line - 1, 0), len(lines) - 1)
            char_start = line_char_start[content_start_line_idx] if lines else 0
            char_end = line_char_end[content_end_line_idx] if lines else 0

            # Approximate page boundaries from line mapping.
            start_page = page_for_line[content_start_line_idx] if page_for_line else 1
            end_page = page_for_line[content_end_line_idx] if page_for_line else 1
            
            # Create section key
            section_key = self._create_section_key(heading)
            
            sections[section_key] = {
                "title": heading["title"],
                "number": heading["number"],
                "heading_text": heading["text"],
                "content": content,
                "start_line": start_line,
                "end_line": end_line,
                "level": heading["level"],
                "word_count": len(content.split()),
                "source": {
                    "file": "",
                    "start_page": int(start_page),
                    "end_page": int(end_page),
                    "char_start": int(char_start),
                    "char_end": int(char_end),
                },
            }
            
        self.sections = sections
        return sections
    
    def _create_section_key(self, heading: Dict) -> str:
        """Create a unique key for a section."""
        if heading["number"]:
            return f"{heading['number']}_{heading['title'][:30]}".lower().replace(' ', '_')
        return heading["title"][:40].lower().replace(' ', '_')
    
    def find_sections_by_keywords(self, sections: Dict[str, Dict], keywords: List[str]) -> List[Dict]:
        """
        Find sections that match given keywords.
        Searches full content (up to 3000 chars) instead of just first 500.
        
        Args:
            sections: Dictionary of extracted sections
            keywords: List of keywords to search for
            
        Returns:
            List of matching sections sorted by keyword hit count (best first)
        """
        matching = []
        
        for key, section in sections.items():
            title_lower = section["title"].lower()
            # Expanded from 500 to 3000 chars to catch content buried deeper
            content_preview = section["content"][:3000].lower()
            
            hits = 0
            first_keyword = None
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in title_lower:
                    hits += 2  # Title match counts double
                    if not first_keyword:
                        first_keyword = keyword
                elif keyword_lower in content_preview:
                    hits += 1
                    if not first_keyword:
                        first_keyword = keyword
            
            if hits > 0:
                matching.append({
                    "key": key,
                    "matched_keyword": first_keyword,
                    "keyword_hits": hits,
                    **section
                })
        
        # Sort by keyword hits (best matches first)
        matching.sort(key=lambda x: x.get("keyword_hits", 0), reverse=True)
        return matching
    
    def count_keyword_hits(self, text: str, keywords: List[str]) -> int:
        """
        Count how many distinct keywords appear in a text block.
        
        Args:
            text: Text to search
            keywords: List of keywords
            
        Returns:
            Number of distinct keyword hits
        """
        text_lower = text.lower()
        return sum(1 for kw in keywords if kw.lower() in text_lower)
    
    def get_section_hierarchy(self, sections: Dict[str, Dict]) -> Dict:
        """
        Build a hierarchical representation of sections.
        
        Args:
            sections: Dictionary of extracted sections
            
        Returns:
            Hierarchical dictionary of sections
        """
        hierarchy = {"root": [], "children": {}}
        
        for key, section in sections.items():
            if section["level"] == 1:
                hierarchy["root"].append(key)
            else:
                # Find parent
                parent_key = self._find_parent_section(key, sections)
                if parent_key:
                    if parent_key not in hierarchy["children"]:
                        hierarchy["children"][parent_key] = []
                    hierarchy["children"][parent_key].append(key)
                else:
                    hierarchy["root"].append(key)
                    
        return hierarchy
    
    def _find_parent_section(self, section_key: str, sections: Dict[str, Dict]) -> Optional[str]:
        """Find the parent section for a given section."""
        section = sections[section_key]
        if not section["number"]:
            return None
            
        parts = section["number"].split('.')
        if len(parts) <= 1:
            return None
            
        parent_number = '.'.join(parts[:-1])
        
        for key, sec in sections.items():
            if sec["number"] == parent_number:
                return key
                
        return None
    
    def extract_and_save(self, text: str, filename: str, output_dir: Path) -> Dict[str, Dict]:
        """
        Extract sections and save to JSON file.
        
        Args:
            text: The full document text
            filename: Original filename
            output_dir: Directory to save extracted data
            
        Returns:
            Dictionary of extracted sections
        """
        sections = self.extract_sections(text)
        
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        
        # Fill provenance file field for each section
        for _, sec in sections.items():
            if isinstance(sec, dict):
                src = sec.get("source")
                if isinstance(src, dict):
                    src["file"] = filename

        output_data = {
            "source_file": filename,
            "total_sections": len(sections),
            "sections": [
                {
                    "title": sec.get("title"),
                    "content": sec.get("content"),
                    "heading_level": sec.get("level"),
                    "word_count": sec.get("word_count"),
                    "source": sec.get("source"),
                }
                for sec in sections.values()
            ],
        }

        output_file = output_dir / f"{Path(filename).name}.json"
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, indent=2, ensure_ascii=False)
            
        print(f"✓ Extracted {len(sections)} sections from {filename}")
        return sections


def extract_text_structure(text: str) -> Dict[str, Dict]:
    """Convenience function to extract text structure."""
    extractor = TextExtractor()
    return extractor.extract_sections(text)
