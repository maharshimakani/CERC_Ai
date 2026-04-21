"""
Tests for CSR Content Retrieval Improvements
Covers extraction quality, heading normalization, fuzzy matching,
keyword fallback, assumption language detection, and synonym coverage.
"""

import json
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================
# Test 1: Extraction Quality Validation
# ============================================================

class TestExtractionQuality:
    """Tests for enhanced extraction quality validation."""
    
    def setup_method(self):
        from pipeline.document_loader import DocumentLoader
        from config import RESOURCES_DIR
        self.loader = DocumentLoader(RESOURCES_DIR)
    
    def test_failed_quality_empty_doc(self):
        """Empty/near-empty extraction should be FAILED."""
        doc_data = {
            "char_count": 50,
            "word_count": 10,
            "full_text": "x" * 50,
            "structure": [{"page_number": 1, "text": "x" * 50}]
        }
        result = self.loader.validate_extraction(doc_data)
        assert result["extraction_quality"] == "failed"
        assert result["extraction_diagnostics"]["quality_level"] == "FAILED"
        assert any("CRITICAL" in i for i in result["extraction_issues"])
    
    def test_poor_quality_low_density(self):
        """Very low chars/page should be POOR."""
        doc_data = {
            "char_count": 200,
            "word_count": 40,
            "full_text": "a " * 100,
            "structure": [{"page_number": i} for i in range(1, 11)]  # 10 pages, 20 chars/page
        }
        result = self.loader.validate_extraction(doc_data)
        assert result["extraction_quality"] == "poor"
        assert result["extraction_diagnostics"]["quality_level"] == "POOR"
    
    def test_warning_quality_moderate_density(self):
        """Moderate density should be WARNING."""
        doc_data = {
            "char_count": 500,
            "word_count": 80,
            "full_text": "a " * 250,
            "structure": [{"page_number": i} for i in range(1, 11)]  # 10 pages, 50 chars/page
        }
        result = self.loader.validate_extraction(doc_data)
        assert result["extraction_quality"] == "warning"
    
    def test_good_quality_normal_doc(self):
        """Normal document should be GOOD."""
        text = "The study was a randomized controlled trial. " * 100
        doc_data = {
            "char_count": len(text),
            "word_count": len(text.split()),
            "full_text": text,
            "structure": [{"page_number": i} for i in range(1, 6)]  # 5 pages
        }
        result = self.loader.validate_extraction(doc_data)
        assert result["extraction_quality"] == "good"
        assert result["extraction_diagnostics"]["quality_level"] == "GOOD"
    
    def test_diagnostics_structure(self):
        """Diagnostics dict should have all required fields."""
        text = "Normal document text here. " * 50
        doc_data = {
            "char_count": len(text),
            "word_count": len(text.split()),
            "full_text": text,
            "structure": [{"page_number": 1}]
        }
        result = self.loader.validate_extraction(doc_data)
        diag = result["extraction_diagnostics"]
        assert "char_count" in diag
        assert "word_count" in diag
        assert "page_count" in diag
        assert "chars_per_page" in diag
        assert "alpha_ratio" in diag
        assert "quality_level" in diag
        assert "issues" in diag


# ============================================================
# Test 2: Heading Normalization
# ============================================================

class TestHeadingNormalization:
    """Tests for _normalize_heading."""
    
    def setup_method(self):
        from pipeline.section_matcher import SectionMatcher
        mapping_path = Path("mappings/csr_section_mapping.json")
        if mapping_path.exists():
            self.matcher = SectionMatcher(mapping_path)
        else:
            self.matcher = None
    
    def test_strip_leading_numbers(self):
        if not self.matcher:
            return
        assert self.matcher._normalize_heading("1. Study Objectives") == "study objectives"
        assert self.matcher._normalize_heading("9.1 Study Design") == "study design"
        assert self.matcher._normalize_heading("3.1.2 Randomization") == "randomization"
    
    def test_normalize_case(self):
        if not self.matcher:
            return
        assert self.matcher._normalize_heading("STUDY DESIGN") == "study design"
        assert self.matcher._normalize_heading("Study Objectives") == "study objectives"
    
    def test_strip_section_label(self):
        if not self.matcher:
            return
        result = self.matcher._normalize_heading("Section 3: Methods")
        assert "section" not in result
        assert "methods" in result
    
    def test_remove_punctuation(self):
        if not self.matcher:
            return
        result = self.matcher._normalize_heading("Study Design (Overall)")
        assert "(" not in result
        assert ")" not in result


# ============================================================
# Test 3: Fuzzy Matching
# ============================================================

class TestFuzzyMatching:
    """Tests for _fuzzy_match."""
    
    def setup_method(self):
        from pipeline.section_matcher import SectionMatcher
        mapping_path = Path("mappings/csr_section_mapping.json")
        if mapping_path.exists():
            self.matcher = SectionMatcher(mapping_path)
        else:
            self.matcher = None
    
    def test_exact_match(self):
        if not self.matcher:
            return
        assert self.matcher._fuzzy_match("study design", "study design")
    
    def test_substring_match(self):
        if not self.matcher:
            return
        assert self.matcher._fuzzy_match("study design", "overall study design and methods")
    
    def test_numbered_heading_match(self):
        if not self.matcher:
            return
        assert self.matcher._fuzzy_match("study objectives", "1. Study Objectives")
    
    def test_plural_singular_match(self):
        if not self.matcher:
            return
        assert self.matcher._fuzzy_match("endpoint", "endpoints")
        assert self.matcher._fuzzy_match("objective", "objectives")
    
    def test_no_match(self):
        if not self.matcher:
            return
        assert not self.matcher._fuzzy_match("adverse events", "study objectives")


# ============================================================
# Test 4: Assumption Language Detection
# ============================================================

class TestAssumptionDetection:
    """Tests for expanded assumption language detection."""
    
    def setup_method(self):
        from pipeline.validator import CSRValidator
        self.validator = CSRValidator()
    
    def test_original_phrases_caught(self):
        """All original assumption phrases should be detected."""
        phrases = ["assumed", "presumably", "it can be inferred", "we believe"]
        for phrase in phrases:
            result = self.validator.validate_assumptions(f"The therapy was {phrase} effective.")
            assert not result["passed"], f"Failed to catch: {phrase}"
    
    def test_new_phrases_caught(self):
        """All newly added assumption phrases should be detected."""
        new_phrases = [
            "it is expected", "would likely", "it is possible",
            "we speculate", "it is plausible", "we anticipate",
            "implying that", "it is inferred", "most likely"
        ]
        for phrase in new_phrases:
            result = self.validator.validate_assumptions(f"The study {phrase} showed results.")
            assert not result["passed"], f"Failed to catch: {phrase}"
    
    def test_severity_is_error(self):
        """Assumption language should have error severity, not warning."""
        result = self.validator.validate_assumptions("It is assumed the drug was effective.")
        assert any(i["severity"] == "error" for i in result["issues"])
    
    def test_clean_text_passes(self):
        """Text without assumption language should pass."""
        clean = "The study was designed to evaluate the efficacy of the treatment."
        result = self.validator.validate_assumptions(clean)
        assert result["passed"]
    
    def test_not_specified_passes(self):
        """'Not specified' text should pass assumption check."""
        text = "The dosage was not specified in source documents."
        result = self.validator.validate_assumptions(text)
        assert result["passed"]


# ============================================================
# Test 5: Synonym Coverage
# ============================================================

class TestSynonymCoverage:
    """Verify minimum pattern counts in csr_section_mapping.json."""
    
    def setup_method(self):
        mapping_path = Path("mappings/csr_section_mapping.json")
        if mapping_path.exists():
            with open(mapping_path) as f:
                self.mappings = json.load(f)
        else:
            self.mappings = None
    
    def test_study_design_patterns(self):
        if not self.mappings:
            return
        patterns = self.mappings["study_design"]["source_mappings"][0]["section_patterns"]
        assert len(patterns) >= 8, f"study_design has only {len(patterns)} patterns"
    
    def test_statistical_methods_patterns(self):
        if not self.mappings:
            return
        # Count total patterns across all source mappings
        total = sum(
            len(sm["section_patterns"])
            for sm in self.mappings["statistical_methods"]["source_mappings"]
        )
        assert total >= 12, f"statistical_methods has only {total} patterns"
    
    def test_keywords_present(self):
        """Every section should have a keywords array for fallback search."""
        if not self.mappings:
            return
        for section_id, mapping in self.mappings.items():
            assert "keywords" in mapping, f"{section_id} missing keywords array"
            assert len(mapping["keywords"]) >= 5, f"{section_id} has too few keywords"
    
    def test_all_sections_present(self):
        """All 5 CSR sections should be in mapping."""
        if not self.mappings:
            return
        expected = ["study_design", "study_objectives", "endpoints", 
                     "inclusion_exclusion", "statistical_methods"]
        for section in expected:
            assert section in self.mappings, f"Missing section: {section}"


# ============================================================
# Run tests
# ============================================================

if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
