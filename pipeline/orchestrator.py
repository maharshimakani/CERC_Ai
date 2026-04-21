"""
Orchestrator Module
Main pipeline controller that coordinates all components.
"""

import json
import sys
import asyncio
from pathlib import Path
from typing import Dict, List, Optional, Callable

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import (
    RESOURCES_DIR, APPENDICES_DIR, EXTRACTED_TEXT_DIR, MAPPINGS_DIR,
    PROMPTS_DIR, OUTPUT_DIR, CSR_SECTIONS_DIR, RULES_DIR, KNOWLEDGE_BASE_DIR,
    OPENAI_API_KEY, OPENAI_MODEL, validate_config, ensure_directories, USER_DOCUMENTS_DIR,
    TEMPLATES_DIR, EXAMPLES_DIR, CSR_MAPPING_PATH, ENABLE_SECTION_PIPELINE
)
from pipeline.document_loader import DocumentLoader
from pipeline.text_extractor import TextExtractor
from pipeline.section_matcher import SectionMatcher
from pipeline.csr_generator import CSRGenerator
from pipeline.validator import CSRValidator
from pipeline.output_generator import OutputGenerator
from pipeline.knowledge_engine import KnowledgeEngine
from pipeline.template_engine import TemplateEngine
from pipeline.generation_context_builder import GenerationContextBuilder

# Reference-Guided Section Pipeline (additive — never breaks existing flow)
from core.section_mapper import SectionMapper
from core.resource_loader import ResourceLoader
from core.transformation_engine import TransformationEngine
from core.csr_assembler import CSRAssembler
from core.missing_detector import MissingDetector
from prompts.prompt_builder import PromptBuilder
from pipelines.section_pipeline import SectionPipeline
from validators.basic_validator import BasicValidator
from validators.advanced_validator import AdvancedValidator


class CSROrchestrator:
    """
    Main orchestrator that coordinates the entire CSR generation pipeline.
    
    Pipeline stages:
    1. Load documents from input directory
    2. Extract text and identify sections
    3. Match source sections to CSR sections
    4. Generate CSR sections using AI
    5. Validate generated content
    6. Save outputs
    """
    
    def __init__(self, api_key: str = None):
        """
        Initialize the orchestrator.
        
        Args:
            api_key: OpenAI API key (optional, uses config if not provided)
        """
        # Validate configuration
        errors = validate_config()
        if errors and not api_key:
            print("⚠ Configuration warnings:")
            for error in errors:
                print(f"  - {error}")
                
        self.api_key = api_key or OPENAI_API_KEY
        
        # Initialize components
        self.document_loader = DocumentLoader(RESOURCES_DIR)
        self.text_extractor = TextExtractor()
        self.section_matcher = SectionMatcher(MAPPINGS_DIR / "csr_section_mapping.json")
        self.validator = CSRValidator(RULES_DIR)
        self.output_generator = OutputGenerator(OUTPUT_DIR)

        # Static knowledge layer engines (resources -> structured templates/rules)
        # Static knowledge layer (resources -> structured templates/rules/required elements)
        self.knowledge_engine = KnowledgeEngine(
            resources_dir=RESOURCES_DIR,
            cache_dir=KNOWLEDGE_BASE_DIR,
        )
        self.knowledge_base = self.knowledge_engine.load_or_build()
        self.template_engine = TemplateEngine(self.knowledge_base)
        self.context_builder = GenerationContextBuilder(self.template_engine)
        
        # CSR Generator initialized when API key is confirmed
        self.csr_generator = None
        
        # State tracking
        self.loaded_documents: Dict = {}
        self.extracted_sections: Dict[str, Dict] = {}
        self.matched_content: Dict[str, Dict] = {}
        self.generated_sections: Dict[str, Dict] = {}
        self.validation_results: Dict = {}
        self.resources: List[Dict] = []
        try:
            from pathlib import Path
            res_dir = Path(RESOURCES_DIR) if isinstance(RESOURCES_DIR, str) else RESOURCES_DIR
            self.resources = self.document_loader.load_resources(res_dir)
            print(f"[RESOURCE] Total resources loaded: {len(self.resources)}")
        except Exception as e:
            print(f"[RESOURCE] Could not load resources directory: {e}")
            
        # Diagnostics tracking
        self.extraction_diagnostics: Dict[str, Dict] = {}
        self.matching_diagnostics: Dict[str, Dict] = {}

        # Reference-Guided Section Pipeline components (additive)
        self.section_mapper = SectionMapper(CSR_MAPPING_PATH)
        self.resource_loader = ResourceLoader(TEMPLATES_DIR, EXAMPLES_DIR)
        self.transformation_engine = TransformationEngine()
        self.prompt_builder = PromptBuilder()
        self.basic_validator = BasicValidator()
        self.missing_detector = MissingDetector()
        self.advanced_validator = AdvancedValidator()
        self.csr_assembler = CSRAssembler()
        self.section_pipeline = None  # Initialized lazily after generator is ready
        self.section_pipeline_results: Optional[Dict] = None
        self.structured_output: Optional[Dict] = None   # Full API contract
        self.traceability: Dict = {}  # Layer 10: full generation traceability

    def _build_generation_contexts(self) -> None:
        """
        Build strict, section-level generation contexts combining:
        - static template/rule knowledge
        - dynamic matched user evidence
        """
        if not self.matched_content:
            return
        for section_id, matched in self.matched_content.items():
            template_package = self.template_engine.build_generation_package(section_id)
            context = self.context_builder.build(section_id, template_package, matched)
            self.matched_content[section_id]["generation_context"] = context
        
    def _init_generator(self):
        """Initialize the CSR generator with API key."""
        if not self.api_key:
            raise ValueError("OpenAI API key is required. Set OPENAI_API_KEY in .env file.")
        self.csr_generator = CSRGenerator(
            api_key=self.api_key,
            model=OPENAI_MODEL,
            prompts_dir=PROMPTS_DIR
        )
        
    def load_documents(self, selected_filenames: Optional[List[str]] = None) -> Dict:
        """
        Stage 1: Load all documents from input directory.
        
        Returns:
            Dictionary of loaded documents
        """
        print("\n" + "="*60)
        print("STAGE 1: LOADING DOCUMENTS")
        print("="*60)
        
        supported_ext = {".pdf", ".docx", ".doc"}
        all_paths = [
            f
            for f in USER_DOCUMENTS_DIR.rglob("*")
            if f.is_file() and f.suffix.lower() in supported_ext
        ]
        paths = all_paths
        if selected_filenames is not None:
            selected = {str(x).strip() for x in selected_filenames if str(x).strip()}
            paths = [p for p in all_paths if p.name in selected]
            
            missing = selected - {p.name for p in paths}
            if missing:
                raise ValueError(f"Invalid document scope. Requested documents not found: {missing}")
                
            print(f"Scoped run requested: {len(selected)} document id(s)")
            print(f"Scoped run matched: {len(paths)} document file(s)")
            for p in paths:
                print(f"  - {p.name}")

        user_docs = self.document_loader.load_user_documents(paths)

        loaded: Dict[str, Dict] = {}
        for d in user_docs:
            fn = str(d.get("filename") or "")
            if not fn:
                continue
            loaded[fn] = {
                "filename": fn,
                "filepath": str(d.get("filepath") or ""),
                "document_type": d.get("document_type", "unknown"),
                "full_text": d.get("full_text", d.get("raw_text", "")) or "",
                "structure": d.get("structure", []) or [],
                "char_count": int(d.get("char_count", 0) or 0),
                "word_count": int(d.get("word_count", 0) or 0),
            }

        self.loaded_documents = loaded
        
        if not self.loaded_documents:
            print("⚠ No documents found in uploads directory!")
            print(f"  Please add PDF/DOCX/DOC files to: {USER_DOCUMENTS_DIR}")
            return {}
            
        print(f"\n✓ Loaded {len(self.loaded_documents)} document(s)")
        
        # Collect extraction diagnostics
        for filename, doc_data in self.loaded_documents.items():
            if "extraction_diagnostics" in doc_data:
                self.extraction_diagnostics[filename] = doc_data["extraction_diagnostics"]
        
        return self.loaded_documents
    
    def generate_document_inventory(self) -> Dict:
        """
        Generate an inventory of provided documents and their status.
        
        Returns:
            Dictionary with 'provided', 'expected_but_missing', 'extraction_issues'
        """
        inventory = {
            "provided": [],
            "expected_but_missing": [],
            "extraction_issues": []
        }
        
        # Expected document types
        expected_types = {"protocol", "sap", "monitoring_plan"}
        found_types = set()
        
        for filename, doc_data in self.loaded_documents.items():
            doc_type = doc_data.get("document_type", "unknown")
            quality = doc_data.get("extraction_quality") or "good"
            
            if doc_type != "unknown":
                found_types.add(doc_type)
            
            if quality == "good":
                inventory["provided"].append(f"{filename} ({doc_type})")
            elif quality == "warning":
                inventory["provided"].append(f"{filename} ({doc_type}) ⚠")
                issues = doc_data.get("extraction_issues", [])
                for issue in issues:
                    inventory["extraction_issues"].append(f"{filename}: {issue}")
            else:  # failed
                inventory["extraction_issues"].append(f"{filename}: Extraction failed")
        
        # Check for expected but missing
        for expected in expected_types:
            if expected not in found_types:
                inventory["expected_but_missing"].append(expected.upper())
        
        return inventory
    
    def extract_text(self) -> Dict[str, Dict]:
        """
        Stage 2: Extract and structure text from loaded documents.
        
        Returns:
            Dictionary mapping filenames to extracted sections
        """
        print("\n" + "="*60)
        print("STAGE 2: EXTRACTING TEXT STRUCTURE")
        print("="*60)
        
        for filename, doc_data in self.loaded_documents.items():
            full_text = doc_data.get("full_text", "")
            
            sections = self.text_extractor.extract_and_save(
                full_text,
                filename,
                EXTRACTED_TEXT_DIR
            )
            
            self.extracted_sections[filename] = sections
            
        print(f"\n✓ Extracted sections from {len(self.extracted_sections)} document(s)")
        return self.extracted_sections
    
    def match_sections(self) -> Dict[str, Dict]:
        """
        Stage 3: Match source sections to CSR sections.
        
        Returns:
            Dictionary mapping CSR section IDs to matched content
        """
        print("\n" + "="*60)
        print("STAGE 3: MATCHING SECTIONS")
        print("="*60)
        
        csr_section_ids = self.section_matcher.get_csr_section_ids()
        
        # Build vector index for semantic search
        if hasattr(self.section_matcher, "build_vector_index"):
            print("Building vector index for semantic search...")
            self.section_matcher.build_vector_index(self.extracted_sections)
        
        for section_id in csr_section_ids:
            matched = self.section_matcher.get_all_matching_content(
                section_id,
                self.loaded_documents,
                self.extracted_sections
            )
            
            self.matched_content[section_id] = matched
            
            if matched.get("total_matches", 0) > 0:
                print(f"✓ {section_id}: {matched['total_matches']} matching section(s) found")
            else:
                print(f"⚠ {section_id}: No matching sections found")
            
            # Collect matching diagnostics
            if "matching_diagnostics" in matched:
                self.matching_diagnostics[section_id] = matched["matching_diagnostics"]

        # Build context packages after evidence matching.
        self._build_generation_contexts()
        return self.matched_content
    
    def generate_sections(self) -> Dict[str, Dict]:
        """
        Stage 4: Generate CSR sections using AI.
        
        Returns:
            Dictionary of generated sections
        """
        print("\n" + "="*60)
        print("STAGE 4: GENERATING CSR SECTIONS")
        print("="*60)
        
        # Initialize generator if needed
        if not self.csr_generator:
            self._init_generator()
            
        self.generated_sections = self.csr_generator.generate_all_sections(
            self.matched_content
        )
        
        successful = sum(
            1 for s in self.generated_sections.values()
            if "error" not in s
        )
        print(f"\n✓ Generated {successful}/{len(self.generated_sections)} section(s)")
        
        return self.generated_sections

    def generate_sections_guided(
        self,
        section_ids: Optional[List[str]] = None,
    ) -> Dict[str, Dict]:
        """
        Stage 4-ALT: Reference-Guided Section Pipeline.
        
        Uses the new section_mapper → resource_loader → prompt_builder
        → LLM → validation flow. Falls back to generate_sections()
        on any error.
        
        Args:
            section_ids: Optional subset of sections to generate.
        
        Returns:
            Dictionary of generated sections
        """
        print("\n" + "="*60)
        print("STAGE 4: GENERATING CSR SECTIONS (REFERENCE-GUIDED)")
        print("="*60)
        
        # Initialize generator if needed
        if not self.csr_generator:
            self._init_generator()
        
        # Initialize section pipeline lazily (with all new layers injected)
        if not self.section_pipeline:
            self.section_pipeline = SectionPipeline(
                section_mapper=self.section_mapper,
                resource_loader=self.resource_loader,
                prompt_builder=self.prompt_builder,
                csr_generator=self.csr_generator,
                transformation_engine=self.transformation_engine,
                basic_validator=self.basic_validator,
                missing_detector=self.missing_detector,
                advanced_validator=self.advanced_validator,
            )
        
        # Map documents to sections using csr_mapping.json
        mapped = self.section_mapper.map_documents(self.loaded_documents)
        
        # Build generation contexts from the existing template engine
        # so the section pipeline can use required_elements + style_rules
        generation_contexts: Dict[str, Dict] = {}
        for sid in mapped:
            if sid in self.matched_content:
                ctx = self.matched_content[sid].get("generation_context")
                if ctx:
                    generation_contexts[sid] = ctx
        
        # Run the section pipeline
        self.generated_sections = self.section_pipeline.generate_all(
            mapped_documents=mapped,
            section_ids=section_ids,
            generation_contexts=generation_contexts,
            resources=self.resources,
        )
        
        # Store pipeline summary + full traceability (Layer 10)
        self.section_pipeline_results = self.section_pipeline.get_summary()
        self.traceability = self.section_pipeline.get_traceability()
        self.structured_output = self.section_pipeline.get_structured_output()
        
        successful = sum(
            1 for s in self.generated_sections.values()
            if "error" not in s
        )
        print(f"\n✓ Reference-Guided Pipeline: {successful}/{len(self.generated_sections)} section(s)")
        
        return self.generated_sections
    
    async def generate_sections_async(
        self,
        progress_callback: Callable = None
    ) -> Dict[str, Dict]:
        """
        Stage 4 (Async): Generate CSR sections concurrently using AI.
        Up to 4 sections are generated in parallel for ~4x speedup.
        
        Args:
            progress_callback: Optional callback(section_id, stage, **kwargs)
        
        Returns:
            Dictionary of generated sections
        """
        print("\n" + "="*60)
        print("STAGE 4: GENERATING CSR SECTIONS (ASYNC)")
        print("="*60)
        
        # Initialize generator if needed
        if not self.csr_generator:
            self._init_generator()
        
        self.generated_sections = await self.csr_generator.generate_all_sections_async(
            self.matched_content,
            max_concurrent=4,
            progress_callback=progress_callback
        )
        
        successful = sum(
            1 for s in self.generated_sections.values()
            if "error" not in s
        )
        print(f"\n✓ Generated {successful}/{len(self.generated_sections)} section(s)")
        
        return self.generated_sections
    
    def validate_sections(self) -> Dict:
        """
        Stage 5: Validate generated sections.
        
        Returns:
            Validation summary
        """
        print("\n" + "="*60)
        print("STAGE 5: VALIDATING SECTIONS")
        print("="*60)
        
        for section_id, section_data in self.generated_sections.items():
            if "error" not in section_data:
                gen_context = section_data.get("generation_context", {})
                expected_subsections = []
                if isinstance(gen_context, dict):
                    t = gen_context.get("template", {}) or {}
                    expected_subsections = t.get("structure_order", []) or t.get("subsections", []) or []
                self.validator.validate_section(
                    section_id,
                    section_data.get("final_text", ""),
                    section_data,
                    expected_subsections
                )
                
        self.validation_results = self.validator.get_validation_summary()
        return self.validation_results
    
    def save_outputs(self) -> Dict[str, Path]:
        """
        Stage 6: Save all outputs.
        
        Returns:
            Dictionary of output file paths
        """
        print("\n" + "="*60)
        print("STAGE 6: SAVING OUTPUTS")
        print("="*60)
        
        output_files = {}
        
        # Save individual section files
        txt_files = self.output_generator.save_all_sections_txt(self.generated_sections)
        output_files["section_files"] = txt_files
        
        # Generate DOCX
        try:
            docx_path = self.output_generator.generate_docx(
                self.generated_sections,
                study_title="Clinical Study Report",
                protocol_number="PROTOCOL-XXX"
            )
            output_files["docx"] = docx_path
        except ImportError as e:
            print(f"Could not generate DOCX: {e}")
        
        # Generate PDF
        try:
            pdf_path = self.output_generator.generate_pdf(
                self.generated_sections,
                study_title="Clinical Study Report",
                protocol_number="PROTOCOL-XXX"
            )
            output_files["pdf"] = pdf_path
        except ImportError as e:
            print(f"Could not generate PDF: {e}")
            
        # Save traceability log
        log_path = self.output_generator.generate_traceability_log(
            self.generated_sections,
            self.validation_results
        )
        output_files["log"] = log_path
        
        # Save summary
        summary_path = self.output_generator.generate_summary_report(
            self.generated_sections,
            self.validation_results
        )
        output_files["summary"] = summary_path
        
        # Save validation report
        if self.validation_results:
            self.validator.save_validation_report(OUTPUT_DIR / "validation_report.json")
            
        return output_files
    
    def run(self) -> Dict:
        """
        Run the complete CSR generation pipeline.
        
        Returns:
            Dictionary with all results and output paths
        """
        print("\n" + "="*60)
        print("AI-ASSISTED CSR GENERATOR")
        print("="*60)
        print("Starting pipeline...")
        
        ensure_directories()
        
        # Run all stages
        self.load_documents()
        
        from pathlib import Path
        resources_path = Path("resources")
        if resources_path.exists():
            self.resources = self.document_loader.load_resources(resources_path)
        
        if not self.loaded_documents:
            return {"error": "No documents loaded"}
        
        # Generate document inventory early
        inventory = self.generate_document_inventory()
            
        self.extract_text()
        self.match_sections()

        # Use Reference-Guided pipeline if enabled, with fallback
        if ENABLE_SECTION_PIPELINE:
            try:
                self.generate_sections_guided()
            except Exception as e:
                print(f"\n⚠ Section pipeline failed ({e}), falling back to standard pipeline...")
                self.generate_sections()
        else:
            self.generate_sections()

        self.validate_sections()
        
        # Pass inventory to output generator
        self.output_generator.set_document_inventory(inventory)
        
        output_files = self.save_outputs()
        
        print("\n" + "="*60)
        print("PIPELINE COMPLETE")
        print("="*60)
        print(f"Output directory: {OUTPUT_DIR}")
        
        return {
            "documents_loaded": len(self.loaded_documents),
            "sections_generated": len(self.generated_sections),
            "validation": self.validation_results,
            "output_files": output_files,
            "extraction_diagnostics": self.extraction_diagnostics,
            "matching_diagnostics": self.matching_diagnostics
        }


def main():
    """Main entry point for command-line execution."""
    orchestrator = CSROrchestrator()
    results = orchestrator.run()
    
    if "error" in results:
        print(f"\n❌ Error: {results['error']}")
        return 1
        
    print(f"\n✓ Pipeline completed successfully!")
    print(f"  Documents processed: {results['documents_loaded']}")
    print(f"  Sections generated: {results['sections_generated']}")
    
    return 0


if __name__ == "__main__":
    exit(main())
