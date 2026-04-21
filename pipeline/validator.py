"""
Validator Module
Validates generated CSR sections for compliance, structure, and quality.
"""

import re
import json
import time
from pathlib import Path
from typing import Dict, List, Tuple, Any, Optional


class CSRValidator:
    """Validates CSR sections for compliance and quality."""
    
    # Past tense indicators for validation
    PAST_TENSE_VERBS = [
        "was", "were", "had", "did", "aimed", "evaluated", "assessed",
        "enrolled", "randomized", "received", "completed", "demonstrated"
    ]
    
    # Present/future tense that should be avoided
    FORBIDDEN_TENSE_PATTERNS = [
        r'\bwill be\b',
        r'\bwill\s+\w+\b',
        r'\bis designed to\b',
        r'\bare expected to\b',
        r'\bsubjects are\b',
        r'\bpatients are\b',
        r'\bthe study is\b',
        r'\baims to\b',
        r'\bintends to\b'
    ]
    
    # Promotional language to flag
    PROMOTIONAL_PHRASES = [
        "groundbreaking", "revolutionary", "breakthrough", "best-in-class",
        "superior", "excellent results", "very effective", "highly successful",
        "remarkable", "unprecedented", "exceptional", "outstanding"
    ]
    
    # Assumption language that poses regulatory risk
    ASSUMPTION_PHRASES = [
        "assumed", "presumably", "likely", "it can be inferred",
        "it is assumed", "none were required", "probably",
        "it appears that", "it seems", "we believe", "we assume",
        "it is expected", "expected to", "would likely", "should be",
        "it is possible", "possibly", "may have been", "could have been",
        "presumably because", "one might assume", "it is reasonable to assume",
        "in all likelihood", "it stands to reason", "based on assumptions",
        "we speculate", "it is plausible", "most likely", "it is conceivable",
        "we expect", "we anticipate", "we predict", "we suggest",
        "suggested that", "implying that", "it is inferred"
    ]
    
    def __init__(self, rules_dir: Path = None):
        """
        Initialize the validator.
        
        Args:
            rules_dir: Path to rules directory
        """
        self.rules_dir = Path(rules_dir) if rules_dir else Path("rules")
        self.validation_results: List[Dict] = []
        
    def validate_structure(
        self,
        section_id: str,
        content: str,
        expected_subsections: List[str] = None,
        expected_heading: Optional[str] = None,
    ) -> Dict:
        """
        Validate that the section follows expected structure.
        
        Args:
            section_id: The CSR section ID
            content: The generated section text
            expected_subsections: List of expected subsection headings
            
        Returns:
            Validation result dictionary
        """
        issues = []
        
        # Check if content is empty
        if not content or len(content.strip()) < 50:
            issues.append({
                "type": "structure",
                "severity": "error",
                "message": "Section content is empty or too short"
            })
            
        # Check for section heading (spec: plain numbered headings, not Markdown '#')
        heading_ok = False
        if expected_heading:
            # Step C spec: template heading should be written on the first non-empty line.
            lines = content.splitlines() if content else []
            first_nonempty = next((ln for ln in lines if ln.strip()), "").strip()
            heading_ok = first_nonempty == expected_heading.strip()
            if not heading_ok:
                issues.append(
                    {
                        "type": "structure_heading",
                        "severity": "error",
                        "message": "Section heading mismatch (expected exact template heading)",
                        "suggestion": f"Expected heading: {expected_heading}",
                    }
                )
        else:
            if section_id == "synopsis":
                heading_ok = re.search(r'^\s*Synopsis\b', content, re.MULTILINE | re.IGNORECASE) is not None
            else:
                heading_ok = re.search(r'^\s*\d+(\.\d+)*\s+', content, re.MULTILINE) is not None

            if not heading_ok:
                issues.append(
                    {
                        "type": "structure_heading",
                        "severity": "warning",
                        "message": "Section may be missing proper heading numbering",
                    }
                )
            
        # Check for expected subsections
        if expected_subsections:
            # Extract numbered subsection titles: "1. Title"
            # Important: dot के बाद कम-से-कम one whitespace होना चाहिए ताकि "9.1 Study Design" section heading
            # गलत तरीके से subsection न बन जाए।
            subsections = re.findall(r'^\s*\d+\.\s+(.+?)\s*$', content or "", re.MULTILINE)

            def norm(s: str) -> str:
                s0 = (s or "").strip()
                s0 = re.sub(r"\s+", " ", s0)
                s0 = s0.rstrip(".")
                return s0.lower()

            expected_norm = [norm(s) for s in expected_subsections]
            actual_norm = [norm(s) for s in subsections]

            if len(actual_norm) > len(expected_norm):
                issues.append(
                    {
                        "type": "structure_subsections_extra",
                        "severity": "error",
                        "message": f"Extra subsections detected (expected {len(expected_norm)}, got {len(actual_norm)})",
                    }
                )

            if actual_norm != expected_norm:
                issues.append(
                    {
                        "type": "structure_subsections_order",
                        "severity": "error",
                        "message": "Subsection order mismatch vs template structure_order",
                        "suggestion": f"Expected: {expected_subsections}",
                    }
                )

        # Optional: required element coverage (strict evidence policy)
        # We keep this additive and non-breaking: it only adds warnings/errors
        # if generate() provided template expectations via source_data.
        required_elements = None
        if isinstance(content, dict):
            # defensive: not expected, but keep pipeline robust
            required_elements = content.get("required_elements")

        return {
            "check": "structure",
            "passed": len([i for i in issues if i["severity"] == "error"]) == 0,
            "issues": issues
        }
    
    def validate_tense(self, content: str) -> Dict:
        """
        Validate that content uses past tense appropriately.
        
        Args:
            content: The generated section text
            
        Returns:
            Validation result dictionary
        """
        issues = []
        
        for pattern in self.FORBIDDEN_TENSE_PATTERNS:
            matches = re.findall(pattern, content, re.IGNORECASE)
            if matches:
                for match in matches[:3]:  # Limit to first 3 occurrences
                    issues.append({
                        "type": "tense",
                        "severity": "warning",
                        "message": f"Future/present tense detected: '{match}'",
                        "suggestion": "Convert to past tense"
                    })
                    
        # Count past tense verbs as positive indicator
        past_tense_count = sum(
            len(re.findall(rf'\b{verb}\b', content, re.IGNORECASE))
            for verb in self.PAST_TENSE_VERBS
        )
        
        return {
            "check": "tense",
            "passed": len(issues) == 0,
            "issues": issues,
            "past_tense_indicators": past_tense_count
        }
    
    def validate_tone(self, content: str) -> Dict:
        """
        Validate that content uses appropriate scientific/regulatory tone.
        
        Args:
            content: The generated section text
            
        Returns:
            Validation result dictionary
        """
        issues = []
        
        # Check for promotional language
        content_lower = content.lower()
        for phrase in self.PROMOTIONAL_PHRASES:
            if phrase in content_lower:
                issues.append({
                    "type": "tone",
                    "severity": "error",
                    "message": f"Promotional language detected: '{phrase}'",
                    "suggestion": "Remove or replace with neutral language"
                })
                
        # Check for first person (generally avoided in CSR)
        first_person_matches = re.findall(r'\b(I|we|our|my)\b', content, re.IGNORECASE)
        if first_person_matches:
            issues.append({
                "type": "tone",
                "severity": "warning",
                "message": "First person language detected",
                "suggestion": "Use third person (e.g., 'the investigators')"
            })
            
        return {
            "check": "tone",
            "passed": len([i for i in issues if i["severity"] == "error"]) == 0,
            "issues": issues
        }
    
    def validate_completeness(
        self,
        content: str,
        source_data: Dict = None
    ) -> Dict:
        """
        Validate that key information from source is included.
        
        Args:
            content: The generated section text
            source_data: Original extracted/transformed data
            
        Returns:
            Validation result dictionary
        """
        issues = []
        
        # Check for "not specified" markers
        not_specified_count = content.lower().count("not specified")
        
        if not_specified_count > 3:
            issues.append({
                "type": "completeness",
                "severity": "warning",
                "message": f"Multiple items marked as 'not specified' ({not_specified_count})",
                "suggestion": "Review source documents for missing information"
            })
            
        # Check minimum word count
        word_count = len(content.split())
        if word_count < 100:
            issues.append({
                "type": "completeness",
                "severity": "warning",
                "message": f"Section appears short ({word_count} words)",
                "suggestion": "Ensure all relevant information is included"
            })
            
        return {
            "check": "completeness",
            "passed": len([i for i in issues if i["severity"] == "error"]) == 0,
            "issues": issues,
            "word_count": word_count,
            "not_specified_count": not_specified_count
        }
    
    def validate_assumptions(self, content: str) -> Dict:
        """
        Validate that content does not contain assumption language.
        
        Args:
            content: The generated section text
            
        Returns:
            Validation result dictionary
        """
        issues = []
        content_lower = content.lower()
        
        for phrase in self.ASSUMPTION_PHRASES:
            if phrase in content_lower:
                issues.append({
                    "type": "assumption",
                    "severity": "error",
                    "message": f"Assumption language detected: '{phrase}'",
                    "suggestion": "Replace with 'Not specified in source documents' or remove"
                })
                
        return {
            "check": "assumptions",
            "passed": len(issues) == 0,
            "issues": issues
        }
    
    def validate_section(
        self,
        section_id: str,
        content: str,
        source_data: Dict = None,
        expected_subsections: List[str] = None
    ) -> Dict:
        """
        Run all validations on a section.
        
        Args:
            section_id: The CSR section ID
            content: The generated section text
            source_data: Original source data (optional)
            expected_subsections: Expected subsection headings (optional)
            
        Returns:
            Complete validation report
        """
        print(f"Validating section: {section_id}")
        
        # expected_subsections is additive: if present, strengthens template conformity checks.
        expected_heading: Optional[str] = None
        if isinstance(source_data, dict):
            gen_ctx = source_data.get("generation_context")
            if isinstance(gen_ctx, dict):
                expected_heading = (gen_ctx.get("template", {}) or {}).get("heading") or gen_ctx.get("section_title")

        structure_result = self.validate_structure(
            section_id,
            content,
            expected_subsections,
            expected_heading=expected_heading,
        )
        tense_result = self.validate_tense(content)
        tone_result = self.validate_tone(content)
        completeness_result = self.validate_completeness(content, source_data)
        assumptions_result = self.validate_assumptions(content)
        compliance_result = self.score_compliance(section_id, content)

        # Optional required-element coverage check (heuristic, non-breaking).
        # Source_data is expected to include generation_context from the generator.
        required_elements: List[str] = []
        confirmed_missing_elements: List[str] = []
        prohibited_phrases: List[str] = []
        element_map_rich: Dict[str, Any] = {}
        template_structure_order: List[str] = []

        if isinstance(source_data, dict):
            gen_ctx = source_data.get("generation_context")
            if isinstance(gen_ctx, dict):
                required_elements = gen_ctx.get("required_elements", []) or []
                prohibited_phrases = gen_ctx.get("prohibited_phrases", []) or []
                template_structure_order = (gen_ctx.get("template", {}) or {}).get("structure_order", []) or []
            confirmed_missing_elements = source_data.get("missing_elements", []) or []
            element_map_rich = source_data.get("element_map_rich", {}) or {}

        required_issues: List[Dict[str, Any]] = []
        if required_elements:
            content_lower = (content or "").lower()
            for element in required_elements[:24]:
                el = str(element).strip().lower()
                if not el:
                    continue
                # Coverage heuristic:
                # - treat as present if full phrase exists, OR enough meaningful tokens exist.
                present = el in content_lower
                if not present:
                    tokens = [t for t in el.replace("-", " ").split() if len(t) >= 4]
                    if tokens:
                        hit_count = sum(1 for t in tokens if t in content_lower)
                        present = (hit_count / max(len(tokens), 1)) >= 0.5

                if not present:
                    required_issues.append(
                        {
                            "type": "required_element",
                            "severity": "warning",
                            "message": f"Required element likely missing: {element}",
                            "suggestion": "Review evidence and consider re-extracting or adding 'Not specified in source documents.' when data is absent.",
                        }
                    )

        # Spec-aligned confirmed missing coverage (from element mapping step)
        confirmed_missing_issues: List[Dict[str, Any]] = []
        if confirmed_missing_elements and required_elements:
            req_set = set(str(x).strip().lower() for x in required_elements if str(x).strip())
            for m in confirmed_missing_elements[:40]:
                ml = str(m).strip().lower()
                if not ml:
                    continue
                if ml in req_set:
                    confirmed_missing_issues.append(
                        {
                            "type": "missing_element",
                            "severity": "warning",
                            "message": f"Required element missing (confirmed): {m}",
                            "location": "Mapped element null → generation must use 'Not specified.'",
                        }
                    )

        # Spec-aligned strict "Not specified." policy
        not_specified_issues: List[Dict[str, Any]] = []
        body = content or ""
        # "Not specified." count: '.' के बाद word-boundary नहीं चाहिए,
        # क्योंकि '.' non-word है और end/newline non-word boundary नहीं बनता।
        not_specified_exact = re.findall(r"\bNot specified\.", body, flags=re.IGNORECASE)
        not_specified_wrong_variants = []
        if re.search(r"\bNot specified\b(?!\.)", body):
            not_specified_wrong_variants.append("Not specified (missing period)")
        if "Not specified in source documents" in body.lower():
            not_specified_wrong_variants.append("Not specified in source documents")

        missing_count = len(confirmed_missing_elements or [])
        not_specified_count = len(not_specified_exact)

        if not_specified_wrong_variants:
            not_specified_issues.append(
                {
                    "type": "not_specified_invalid_usage",
                    "severity": "error",
                    "message": f"Invalid 'Not specified.' usage detected: {', '.join(not_specified_wrong_variants)}",
                    "location": "Section body",
                }
            )

        # Enforce: if missing elements exist, only allow correct fallback and exact count match.
        if missing_count > 0:
            if not_specified_count != missing_count:
                not_specified_issues.append(
                    {
                        "type": "not_specified_missing_element_not_marked",
                        "severity": "error",
                        "message": (
                            f"Missing elements detected ({missing_count}) but 'Not specified.' count is {not_specified_count}. "
                            "Each missing element must use exactly one 'Not specified.' fallback."
                        ),
                        "location": "Section body",
                    }
                )
        else:
            if not_specified_count > 0:
                not_specified_issues.append(
                    {
                        "type": "not_specified_forbidden_when_present",
                        "severity": "error",
                        "message": "'Not specified.' must not appear when no missing elements were mapped.",
                        "location": "Section body",
                    }
                )

        # Element-linked enforcement (upgrade): enforce "Not specified." placement in the correct subsection.
        element_link_issues: List[Dict[str, Any]] = []
        if element_map_rich and expected_subsections:
            # Build subsection -> body mapping using exact template subsection titles.
            # Assumes Step C format: "1. <subsection title>" then a paragraph.
            subsection_text: Dict[str, str] = {}
            current: Optional[str] = None
            lines = (content or "").splitlines()

            def norm_title(s: str) -> str:
                s0 = (s or "").strip()
                s0 = re.sub(r"\s+", " ", s0)
                s0 = s0.rstrip(".")
                return s0.lower()

            expected_norm_to_title = {norm_title(t): t for t in expected_subsections}
            buf: List[str] = []

            def flush():
                nonlocal buf, current
                if current is not None:
                    subsection_text[current] = "\n".join(buf).strip()
                buf = []

            for ln in lines:
                m = re.match(r"^\s*(\d+)\.\s+(.+?)\s*$", ln)
                if m:
                    title = m.group(2)
                    nt = norm_title(title)
                    if nt in expected_norm_to_title:
                        flush()
                        current = expected_norm_to_title[nt]
                        continue
                if current is not None:
                    buf.append(ln)
            flush()

            for element, meta in element_map_rich.items():
                if not isinstance(meta, dict):
                    continue
                status = (meta.get("status") or "").lower()
                subsection = meta.get("subsection")
                if not subsection:
                    # If missing linkage, treat as warning (schema not fully provided).
                    element_link_issues.append(
                        {
                            "type": "element_link_missing_subsection",
                            "severity": "warning",
                            "message": f"Element missing subsection linkage: {element}",
                            "location": "element_map_rich",
                        }
                    )
                    continue

                block = subsection_text.get(subsection, "")
                has_ns = bool(re.search(r"\bNot specified\.", block, flags=re.IGNORECASE))

                if status == "missing":
                    if not has_ns:
                        element_link_issues.append(
                            {
                                "type": "not_specified_wrong_subsection",
                                "severity": "error",
                                "message": f"Missing element not marked in correct subsection: {element} -> {subsection}",
                                "location": f"Subsection: {subsection}",
                            }
                        )
                elif status == "present":
                    if has_ns:
                        element_link_issues.append(
                            {
                                "type": "not_specified_present_element_subsection",
                                "severity": "error",
                                "message": f"Not specified used in present element subsection: {element} -> {subsection}",
                                "location": f"Subsection: {subsection}",
                            }
                        )

        # Spec-aligned prohibited phrase scan (from knowledge base)
        prohibited_issues: List[Dict[str, Any]] = []
        if prohibited_phrases:
            content_lower = (content or "").lower()
            for phrase in prohibited_phrases[:200]:
                ph = str(phrase).strip()
                if not ph:
                    continue
                ph_l = ph.lower()
                idx = content_lower.find(ph_l)
                if idx >= 0:
                    start = max(0, idx - 40)
                    end = min(len(content), idx + len(ph) + 40)
                    snippet = (content or "")[start:end].replace("\n", " ")
                    prohibited_issues.append(
                        {
                            "type": "prohibited_phrase",
                            "severity": "error",
                            "message": f"Prohibited phrase detected: {ph}",
                            "location": snippet[:120],
                        }
                    )
        
        all_issues = (
            structure_result.get("issues", []) +
            tense_result.get("issues", []) +
            tone_result.get("issues", []) +
            completeness_result.get("issues", []) +
            assumptions_result.get("issues", []) +
            required_issues +
            confirmed_missing_issues +
            not_specified_issues +
            element_link_issues +
            prohibited_issues
        )

        critical_errors = [i for i in all_issues if i.get("severity") == "error"]
        all_passed = len(critical_errors) == 0
        
        # region agent log
        try:
            from pathlib import Path
            log_path = Path(r"C:\Users\mahar\OneDrive\Desktop\ai_csr_generator\debug-ef7b3b.log")
            payload = {
                "sessionId": "ef7b3b",
                "runId": "pre-fix",
                "hypothesisId": "H4",
                "location": "pipeline/validator.py:validate_section",
                "message": "Validation summary",
                "data": {
                    "section_id": section_id,
                    "overall_passed": all_passed,
                    "error_count": len([i for i in all_issues if i.get("severity") == "error"]),
                    "warning_count": len([i for i in all_issues if i.get("severity") == "warning"]),
                    "error_types": sorted(
                        list(
                            {
                                str(i.get("type"))
                                for i in all_issues
                                if i.get("severity") == "error" and i.get("type")
                            }
                        )
                    )[:20],
                },
                "timestamp": int(time.time() * 1000),
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # endregion agent log

        # Calculate new advanced confidence score
        element_map_rich = source_data.get("element_map_rich", {}) if isinstance(source_data, dict) else {}
        total_elements = len(element_map_rich)
        confirmed_missing_count = len(confirmed_missing_elements or [])
        mapped_count = max(0, total_elements - confirmed_missing_count)
        
        # Completeness: % required elements filled
        completeness = mapped_count / total_elements if total_elements > 0 else 1.0
        
        # Match Quality: avg relevance score or presence of verified source mappings
        match_quality = 1.0
        if mapped_count > 0:
            traced = sum(1 for v in element_map_rich.values() if v.get("source"))
            match_quality = traced / mapped_count
            
        # Validation Score: based on validator result from constraints engine
        validation_score_component = max(0.0, compliance_result["score"] / 100.0)
        
        # New formula: confidence = (match_quality * 0.4) + (completeness * 0.3) + (validation_score * 0.3)
        confidence_score = round((match_quality * 0.4) + (completeness * 0.3) + (validation_score_component * 0.3), 3)

        result = {
            "section_id": section_id,
            "overall_passed": all_passed,
            "confidence_score": confidence_score,
            "total_issues": len(all_issues),
            "error_count": len([i for i in all_issues if i["severity"] == "error"]),
            "warning_count": len([i for i in all_issues if i["severity"] == "warning"]),
            "compliance_score": compliance_result["score"],
            "compliance_grade": compliance_result.get("grade", "N/A"),
            "compliance_missing": compliance_result.get("missing", []),
            "checks": {
                "structure": structure_result,
                "tense": tense_result,
                "tone": tone_result,
                "completeness": completeness_result,
                "compliance": compliance_result
            },
            "all_issues": all_issues
        }
        
        self.validation_results.append(result)
        
        status = "PASSED" if all_passed else "ISSUES FOUND"
        print(f"  {status} ({result['error_count']} errors, {result['warning_count']} warnings) | Compliance: {compliance_result['score']}% ({compliance_result.get('grade', 'N/A')})")
        
        return result
    
    def get_validation_summary(self) -> Dict:
        """Get summary of all validations performed."""
        if not self.validation_results:
            return {"message": "No validations performed"}
            
        return {
            "total_sections_validated": len(self.validation_results),
            "sections_passed": sum(1 for r in self.validation_results if r["overall_passed"]),
            "total_errors": sum(r["error_count"] for r in self.validation_results),
            "total_warnings": sum(r["warning_count"] for r in self.validation_results),
            "results": self.validation_results
        }
    
    def save_validation_report(self, output_file: Path) -> None:
        """Save validation results to JSON file."""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.get_validation_summary(), f, indent=2)
    
    # ─── ICH E3 Compliance Scoring ───────────────────────────────────
    
    # Required elements per ICH E3 section
    ICH_E3_REQUIRED_ELEMENTS = {
        "synopsis": [
            "study title", "protocol", "phase", "design", "objectives",
            "subjects", "diagnosis", "treatment", "duration", "results", "conclusions"
        ],
        "introduction": [
            "disease", "background", "rationale", "investigational product"
        ],
        "ethics": [
            "ethics committee", "informed consent", "good clinical practice"
        ],
        "study_objectives": [
            "primary objective", "secondary objective"
        ],
        "investigators_sites": [
            "sites", "investigators", "countries"
        ],
        "study_design": [
            "design", "randomization", "blinding", "duration",
            "treatment groups", "visit schedule"
        ],
        "inclusion_exclusion": [
            "inclusion criteria", "exclusion criteria"
        ],
        "treatments": [
            "investigational product", "dose", "administration",
            "comparator", "concomitant"
        ],
        "endpoints": [
            "primary endpoint", "secondary endpoint", "assessment"
        ],
        "study_population": [
            "screened", "enrolled", "randomized", "completed",
            "discontinued", "analysis population"
        ],
        "demographics": [
            "age", "sex", "race", "baseline", "medical history"
        ],
        "efficacy_evaluation": [
            "primary endpoint", "statistical", "p-value", "confidence interval"
        ],
        "statistical_methods": [
            "analysis population", "sample size", "primary analysis",
            "missing data", "significance"
        ],
        "safety_evaluation": [
            "adverse event", "exposure", "laboratory", "vital signs"
        ],
        "adverse_events": [
            "adverse event", "serious adverse event", "death",
            "discontinuation", "treatment-related"
        ],
        "discussion_conclusions": [
            "efficacy", "safety", "benefit-risk", "conclusion"
        ]
    }
    
    def score_compliance(self, section_id: str, content: str) -> Dict:
        """
        Score ICH E3 compliance for a generated section.
        
        Args:
            section_id: The CSR section ID
            content: Generated section text
            
        Returns:
            Compliance scoring result with 0-100 score
        """
        required = self.ICH_E3_REQUIRED_ELEMENTS.get(section_id, [])
        if not required:
            return {"score": 100, "missing": [], "present": [], "details": "No specific requirements defined"}
        
        content_lower = content.lower()
        present = []
        missing = []
        
        for element in required:
            if element.lower() in content_lower:
                present.append(element)
            else:
                missing.append(element)
        
        score = round((len(present) / len(required)) * 100) if required else 100
        
        return {
            "score": score,
            "grade": self._score_to_grade(score),
            "present": present,
            "missing": missing,
            "total_required": len(required),
            "total_present": len(present)
        }
    
    @staticmethod
    def _score_to_grade(score: int) -> str:
        """Convert a numeric score to a letter grade."""
        if score >= 90: return "A"
        if score >= 80: return "B"
        if score >= 70: return "C"
        if score >= 60: return "D"
        return "F"
    
    # ─── Cross-Section Consistency Checks ────────────────────────────
    
    def check_cross_section_consistency(
        self,
        generated_sections: Dict[str, str]
    ) -> Dict:
        """
        Check consistency across multiple generated sections.
        
        Verifies that key data points (study title, subject counts, 
        drug names, dates) are consistent across all sections.
        
        Args:
            generated_sections: Dict mapping section_id to generated text
            
        Returns:
            Consistency check result
        """
        issues = []
        
        # Extract key entities from each section
        study_drugs = {}
        subject_counts = {}
        
        for section_id, content in generated_sections.items():
            # Check for "N=" patterns (subject counts)
            n_matches = re.findall(r'[Nn]\s*=\s*(\d+)', content)
            if n_matches:
                subject_counts[section_id] = set(n_matches)
            
            # Check for drug name patterns (words before mg/dose/tablet)
            drug_matches = re.findall(
                r'(\b[A-Z][a-z]+(?:mab|nib|tide|zole|pril|sartan|statin|olol|dipine)\b)',
                content
            )
            if drug_matches:
                study_drugs[section_id] = set(drug_matches)
        
        # Check subject count consistency
        if len(subject_counts) > 1:
            all_counts = set()
            for counts in subject_counts.values():
                all_counts.update(counts)
            
            for section_id, counts in subject_counts.items():
                diff = all_counts - counts
                if diff and len(diff) < 3:  # Only flag if small differences
                    issues.append({
                        "type": "consistency",
                        "severity": "warning",
                        "sections": list(subject_counts.keys()),
                        "message": f"Subject count inconsistency in {section_id}: "
                                   f"found N={','.join(sorted(counts))} but other sections mention N={','.join(sorted(diff))}"
                    })
        
        # Check drug name consistency
        if len(study_drugs) > 1:
            all_drugs = set()
            for drugs in study_drugs.values():
                all_drugs.update(drugs)
            
            for section_id, drugs in study_drugs.items():
                if drugs != all_drugs:
                    missing = all_drugs - drugs
                    if missing:
                        issues.append({
                            "type": "consistency",
                            "severity": "info",
                            "message": f"Drug name '{', '.join(missing)}' mentioned in other sections but not in {section_id}"
                        })
        
        return {
            "check": "cross_section_consistency",
            "passed": len([i for i in issues if i["severity"] == "error"]) == 0,
            "issue_count": len(issues),
            "issues": issues
        }
    
    # ─── Gap Analysis Report ─────────────────────────────────────────
    
    def generate_gap_analysis(
        self,
        generated_sections: Dict[str, str]
    ) -> Dict:
        """
        Generate a comprehensive ICH E3 compliance gap analysis.
        
        Scores each section and identifies missing required elements,
        then produces an overall compliance report.
        
        Args:
            generated_sections: Dict mapping section_id to generated text
            
        Returns:
            Gap analysis report
        """
        section_scores = {}
        all_missing = []
        
        for section_id, content in generated_sections.items():
            score_result = self.score_compliance(section_id, content)
            section_scores[section_id] = score_result
            
            for element in score_result.get("missing", []):
                all_missing.append({
                    "section": section_id,
                    "element": element,
                    "severity": "high" if score_result["score"] < 60 else "medium"
                })
        
        # Calculate overall score
        scores = [s["score"] for s in section_scores.values()]
        overall_score = round(sum(scores) / len(scores)) if scores else 0
        
        # Identify fully missing sections (all 16 expected)
        all_expected = list(self.ICH_E3_REQUIRED_ELEMENTS.keys())
        missing_sections = [s for s in all_expected if s not in generated_sections]
        
        # Cross-section check
        consistency = self.check_cross_section_consistency(generated_sections)
        
        return {
            "overall_score": overall_score,
            "overall_grade": self._score_to_grade(overall_score),
            "sections_generated": len(generated_sections),
            "sections_expected": len(all_expected),
            "missing_sections": missing_sections,
            "section_scores": section_scores,
            "missing_elements": all_missing,
            "consistency_check": consistency,
            "recommendations": self._generate_recommendations(
                overall_score, missing_sections, all_missing
            )
        }
    
    def _generate_recommendations(
        self,
        overall_score: int,
        missing_sections: List[str],
        missing_elements: List[Dict]
    ) -> List[str]:
        """Generate actionable recommendations based on gap analysis."""
        recommendations = []
        
        if missing_sections:
            recommendations.append(
                f"Generate {len(missing_sections)} missing sections: "
                f"{', '.join(missing_sections[:5])}"
                + (f" and {len(missing_sections) - 5} more" if len(missing_sections) > 5 else "")
            )
        
        # Group missing elements by severity
        high_priority = [m for m in missing_elements if m["severity"] == "high"]
        if high_priority:
            sections_needing_work = set(m["section"] for m in high_priority)
            recommendations.append(
                f"High priority: {len(high_priority)} critical elements missing "
                f"in sections: {', '.join(sections_needing_work)}"
            )
        
        if overall_score < 70:
            recommendations.append(
                "Overall compliance is below 70%. Consider providing more detailed "
                "source documents or reviewing extraction prompts."
            )
        elif overall_score >= 90:
            recommendations.append(
                "Excellent compliance score. Review any remaining gaps and "
                "finalize for submission."
            )
        
        return recommendations
