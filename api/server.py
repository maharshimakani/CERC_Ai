"""
FastAPI Backend for AI-Assisted CSR Generator
Provides REST API endpoints for the CSR generation pipeline.
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional
import json
import os
from datetime import datetime
import time
import io

# Force UTF-8 encoding for stdout/stderr to prevent emoji crashes on Windows
if hasattr(sys.stdout, 'encoding') and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if hasattr(sys.stderr, 'encoding') and sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    RESOURCES_DIR, OUTPUT_DIR, CSR_SECTIONS_DIR, USER_DOCUMENTS_DIR,
    OPENAI_API_KEY, ensure_directories, ENABLE_SECTION_PIPELINE
)
from pipeline.orchestrator import CSROrchestrator

# Initialize FastAPI app
app = FastAPI(
    title="AI CSR Generator API",
    description="Generate ICH E3-compliant Clinical Study Report sections",
    version="1.0.0"
)

# CORS middleware for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Ensure directories exist
ensure_directories()

# Global state for generation progress
generation_status = {
    "status": "idle",
    "progress": 0,
    "current_stage": "",
    "message": "",
    "results": None,
    "error": None
}
current_run_document_ids: List[str] = []


# Pydantic models
class GenerationStatus(BaseModel):
    status: str
    progress: int
    current_stage: str
    message: str
    results: Optional[Dict] = None
    error: Optional[str] = None
    sections_completed: Optional[int] = None
    total_sections: Optional[int] = None


class SectionInfo(BaseModel):
    id: str
    name: str
    csr_section_number: str
    description: str


class GenerateRequest(BaseModel):
    # Optional subset of CSR section IDs to generate.
    # If omitted/empty, the backend generates the full CSR.
    section_ids: Optional[List[str]] = None
    # Optional run-scoped document identifiers (filename IDs).
    document_ids: Optional[List[str]] = None


# API Endpoints

@app.get("/")
async def root():
    """Health check endpoint."""
    return {"status": "ok", "message": "AI CSR Generator API is running"}


@app.get("/api/sections", response_model=List[SectionInfo])
async def get_sections():
    """Get list of supported CSR sections."""
    sections_file = Path(__file__).parent.parent / "mappings" / "mvp_sections.json"
    
    if not sections_file.exists():
        raise HTTPException(status_code=404, detail="Sections configuration not found")
        
    with open(sections_file) as f:
        data = json.load(f)
        
    return [
        SectionInfo(
            id=s["id"],
            name=s["name"],
            csr_section_number=s["csr_section_number"],
            description=s["description"]
        )
        for s in data["mvp_sections"]
    ]



@app.get("/api/documents")
async def list_documents():
    """List all user-uploaded clinical source documents."""
    supported_ext = ('.pdf', '.docx', '.doc')
    docs = [
        {
            "name": f.name,
            "folder": f.parent.name if f.parent != USER_DOCUMENTS_DIR else "uploads",
            "size": f.stat().st_size
        }
        for f in USER_DOCUMENTS_DIR.rglob("*")
        if f.suffix.lower() in supported_ext
    ]
    return {"documents": docs, "count": len(docs)}


@app.post("/api/upload")
async def upload_documents(files: List[UploadFile] = File(...)):
    """Upload documents to the user documents directory."""
    global current_run_document_ids
    saved_files = []
    
    for file in files:
        if file.filename:
            file_path = USER_DOCUMENTS_DIR / file.filename
            with open(file_path, "wb") as buffer:
                content = await file.read()
                buffer.write(content)
                
            saved_files.append({
                "filename": file.filename,
                "size": len(content)
            })
            
    current_run_document_ids = [f["filename"] for f in saved_files]
    return {
        "message": f"Successfully uploaded {len(saved_files)} files",
        "files": saved_files,
        "current_run_document_ids": current_run_document_ids,
    }


@app.delete("/api/documents")
async def clear_documents():
    """Clear all documents from the user documents folder."""
    global current_run_document_ids
    count = 0
    for f in USER_DOCUMENTS_DIR.rglob("*"):
        if f.is_file() and f.name != ".gitkeep":
            try:
                f.unlink()
                count += 1
            except Exception as e:
                print(f"Failed to delete {f}: {e}")
    current_run_document_ids = []
    return {"message": f"Cleared {count} documents from resources folder", "count": count}


@app.delete("/api/documents/{filename}")
async def delete_document(filename: str):
    """
    Delete a single uploaded document from the user documents folder.
    UI uses `filename` (not full path), so we search by exact base name safely.
    """
    global current_run_document_ids
    if not filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    safe_name = Path(filename).name  # Prevent directory traversal
    supported_ext = {".pdf", ".docx", ".doc"}
    if Path(safe_name).suffix.lower() not in supported_ext:
        raise HTTPException(status_code=400, detail="Unsupported file type")

    matches = [f for f in USER_DOCUMENTS_DIR.rglob(safe_name) if f.is_file()]
    if not matches:
        raise HTTPException(status_code=404, detail="File not found")

    deleted = 0
    for f in matches:
        try:
            f.unlink()
            deleted += 1
        except Exception as e:
            print(f"Failed to delete {f}: {e}")

    current_run_document_ids = [x for x in current_run_document_ids if x != safe_name]
    return {"message": f"Deleted {deleted} file(s)", "count": deleted, "filename": safe_name}


def run_generation_pipeline(
    api_key: str,
    section_ids: Optional[List[str]] = None,
    document_ids: Optional[List[str]] = None,
):
    """Background task to run the CSR generation pipeline with async concurrent generation."""
    global generation_status
    
    try:
        generation_status["status"] = "running"
        generation_status["progress"] = 5
        generation_status["current_stage"] = "Initializing"
        
        orchestrator = CSROrchestrator(api_key=api_key)
        scoped_doc_ids = [x for x in (document_ids or []) if str(x).strip()]
        print("Generation scope (current run):")
        print(f"  Selected sections: {section_ids or []}")
        print(f"  Selected document IDs: {scoped_doc_ids}")
        
        # Stage 1: Load documents
        generation_status["current_stage"] = "Loading Documents"
        generation_status["progress"] = 10
        generation_status["message"] = "Loading and parsing documents..."
        orchestrator.load_documents(selected_filenames=scoped_doc_ids)
        
        if not orchestrator.loaded_documents:
            raise Exception(
                "No scoped documents were loaded for this run. "
                "Provide valid document_ids from current session."
            )
        print(f"Processing {len(orchestrator.loaded_documents)} documents for current run:")
        for fn in orchestrator.loaded_documents.keys():
            print(f"  - {fn}")
        
        # Stage 2: Extract text
        generation_status["current_stage"] = "Extracting Text"
        generation_status["progress"] = 25
        generation_status["message"] = "Extracting text structure..."
        orchestrator.extract_text()
        
        # Stage 3: Match sections
        generation_status["current_stage"] = "Matching Sections"
        generation_status["progress"] = 40
        generation_status["message"] = "Matching source to CSR sections..."
        orchestrator.match_sections()

        # If the UI provided a subset, limit generation to only those sections.
        if section_ids:
            filtered = {
                sid: orchestrator.matched_content[sid]
                for sid in section_ids
                if sid in orchestrator.matched_content
            }
            orchestrator.matched_content = filtered
        
        # Stage 4: Generate sections
        generation_status["current_stage"] = "Generating CSR"
        generation_status["progress"] = 45
        generation_status["sections_completed"] = 0
        generation_status["total_sections"] = len(orchestrator.matched_content)
        
        # Progress callback for per-section updates (used by async fallback)
        def on_section_progress(section_id, stage, **kwargs):
            """Update global status with per-section progress."""
            completed = kwargs.get("completed", generation_status.get("sections_completed", 0))
            total = kwargs.get("total", generation_status.get("total_sections", 1))
            
            if stage == "complete":
                generation_status["sections_completed"] = completed
                gen_progress = int(45 + (completed / max(total, 1)) * 40)
                generation_status["progress"] = min(gen_progress, 85)
                generation_status["message"] = f"Generated {completed}/{total} sections — {section_id} done"
            else:
                pretty_name = section_id.replace("_", " ").title()
                stage_names = {"extracted": "extracting", "transformed": "transforming", "written": "writing"}
                stage_label = stage_names.get(stage, stage)
                generation_status["message"] = f"Section {completed + 1}/{total}: {stage_label} {pretty_name}..."
        
        # Try Reference-Guided pipeline first, fall back to async concurrent
        guided_ok = False
        if ENABLE_SECTION_PIPELINE:
            try:
                generation_status["message"] = "AI generating CSR sections (reference-guided)..."
                orchestrator.generate_sections_guided(section_ids=section_ids)
                guided_ok = True
            except Exception as guided_err:
                print(f"Reference-guided pipeline failed ({guided_err}), falling back to async...")
        
        if not guided_ok:
            generation_status["message"] = "AI generating CSR sections concurrently..."
            import asyncio
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(
                    orchestrator.generate_sections_async(progress_callback=on_section_progress)
                )
            finally:
                loop.close()
        
        # Stage 5: Validate
        generation_status["current_stage"] = "Validating"
        generation_status["progress"] = 87
        generation_status["message"] = "Validating generated content..."
        orchestrator.validate_sections()
        
        # Stage 6: Save outputs
        generation_status["current_stage"] = "Saving Outputs"
        generation_status["progress"] = 92
        generation_status["message"] = "Saving generated documents..."
        output_files = orchestrator.save_outputs()
        
        # Generate gap analysis
        gap_analysis = None
        try:
            from pipeline.validator import CSRValidator
            gap_validator = CSRValidator()
            generated_texts = {
                sid: data.get("final_text", "")
                for sid, data in orchestrator.generated_sections.items()
                if data.get("final_text")
            }
            gap_analysis = gap_validator.generate_gap_analysis(generated_texts)
        except Exception as gap_err:
            print(f"Gap analysis failed: {gap_err}")
        
        # Complete
        generation_status["status"] = "complete"
        generation_status["progress"] = 100
        generation_status["current_stage"] = "Complete"
        generation_status["message"] = "CSR generation complete!"
        validation_by_section = {
            (r.get("section_id") or ""): r
            for r in (orchestrator.validation_results or {}).get("results", [])
            if isinstance(orchestrator.validation_results, dict) and isinstance(r, dict)
        }

        sections_out = {}
        for section_id, data in orchestrator.generated_sections.items():
            section_error = data.get("error")
            v = validation_by_section.get(section_id)
            if not v:
                # Spec-accuracy: अगर validation entry उपलब्ध नहीं है (उदा. strict Step A/B fail),
                # तो इसे FAIL माना जाएगा ताकि UI silently pass न करे।
                validation_status = "fail"
                critical_error_count = 1 if section_error else 0
                confidence_score = 0.0
                validation_issues = (
                    [
                        {
                            "type": "generation_error",
                            "severity": "error",
                            "message": str(section_error),
                        }
                    ]
                    if section_error
                    else []
                )
            else:
                critical_error_count = v.get("error_count", 0) or 0
                validation_issues = v.get("all_issues", []) or []
                confidence_score = v.get("confidence_score", 0.0)
                if critical_error_count > 0:
                    validation_status = "fail"
                else:
                    validation_status = "warning" if (v.get("total_issues", 0) or 0) > 0 else "pass"

            sections_out[section_id] = {
                "section_name": data.get("section_name", section_id),
                "status": data.get("status", "missing" if section_error else "complete"),
                "generated_text": data.get("generated_text", data.get("final_text", "")),
                "content": data.get("final_text", data.get("generated_text", "")),
                "source_documents": data.get("source_documents", data.get("sources", [])),
                "sources": data.get("source_documents", data.get("sources", [])),
                "validation": data.get("validation", {}),
                "token_usage": data.get("token_usage", {}),
                "missing_elements": data.get("missing_elements", []),
                "element_map": data.get("element_map", {}),
                "element_map_rich": data.get("element_map_rich", {}),
                "traceability_blocks": (data.get("generation_context") or {}).get("source_blocks", []),
                "error": section_error,
                "validation_status": validation_status,
                "confidence_score": confidence_score,
                "critical_error_count": critical_error_count,
                "validation_issues": validation_issues,
            }

        # region agent log
        try:
            from pathlib import Path
            log_path = Path(r"C:\Users\mahar\OneDrive\Desktop\ai_csr_generator\debug-ef7b3b.log")
            payload = {
                "sessionId": "ef7b3b",
                "runId": "pre-fix",
                "hypothesisId": "H5",
                "location": "api/server.py:run_generation_pipeline",
                "message": "Assembled /api/results section statuses",
                "data": {
                    "sections": {
                        sid: {
                            "has_error": bool((sd or {}).get("error")),
                            "validation_status": (sd or {}).get("validation_status"),
                            "critical_error_count": (sd or {}).get("critical_error_count"),
                        }
                        for sid, sd in list(sections_out.items())[:12]
                    }
                },
                "timestamp": int(time.time() * 1000),
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # endregion agent log

        generation_status["results"] = {
            "sections_generated": len(orchestrator.generated_sections),
            "validation": orchestrator.validation_results,
            "extraction_diagnostics": orchestrator.extraction_diagnostics,
            "matching_diagnostics": orchestrator.matching_diagnostics,
            "token_usage": orchestrator.csr_generator.get_usage_summary() if orchestrator.csr_generator else {},
            "gap_analysis": gap_analysis,
            "validation_by_section": validation_by_section,
            "sections": sections_out,
            # ── Reference-Guided Pipeline outputs (additive) ───────────
            "pipeline_summary": orchestrator.section_pipeline_results or {},
            "traceability": {
                sid: {k: v for k, v in trace.items() if k not in ("prompt",)}
                for sid, trace in (orchestrator.traceability or {}).items()
            },
            "basic_validation": (
                orchestrator.basic_validator.get_summary()
                if hasattr(orchestrator, "basic_validator")
                else {}
            ),
            # ── Full structured output contract (powers all UI tabs) ───
            "structured_output": (
                orchestrator.structured_output
                if hasattr(orchestrator, "structured_output") and orchestrator.structured_output
                else None
            ),
        }
        
    except Exception as e:
        generation_status["status"] = "error"
        generation_status["error"] = str(e)
        generation_status["message"] = f"Error: {str(e)}"


@app.post("/api/generate")
async def start_generation(
    background_tasks: BackgroundTasks,
    req: GenerateRequest,
    api_key: Optional[str] = None,
):
    """Start the CSR generation pipeline."""
    global generation_status, current_run_document_ids
    
    # Check if already running
    if generation_status["status"] == "running":
        raise HTTPException(status_code=400, detail="Generation already in progress")
    
    # Get API key
    key = api_key or OPENAI_API_KEY or os.getenv("OPENAI_API_KEY")
    if not key:
        raise HTTPException(
            status_code=400, 
            detail="OpenAI API key required. Set OPENAI_API_KEY environment variable."
        )
    
    # Check for documents in user documents folder
    supported_ext = ('.pdf', '.docx', '.doc')
    docs = [f for f in USER_DOCUMENTS_DIR.rglob("*") if f.suffix.lower() in supported_ext]
    if not docs:
        raise HTTPException(status_code=400, detail="No documents found in uploads")
    
    scoped_document_ids = [d for d in (req.document_ids or []) if str(d).strip()]
    if not scoped_document_ids:
        scoped_document_ids = list(current_run_document_ids)
    if not scoped_document_ids:
        raise HTTPException(
            status_code=400,
            detail=(
                "No scoped documents supplied for generation. "
                "Provide document_ids or upload files in current session."
            ),
        )

    available_names = {f.name for f in docs}
    valid_scoped = [d for d in scoped_document_ids if d in available_names]
    if not valid_scoped:
        raise HTTPException(
            status_code=400,
            detail=(
                "None of the scoped document_ids are available in uploads. "
                "Generation aborted to prevent broad fallback."
            ),
        )

    # Reset status
    generation_status = {
        "status": "starting",
        "progress": 0,
        "current_stage": "Starting",
        "message": "Initializing pipeline...",
        "results": None,
        "error": None
    }
    
    # Start background task
    background_tasks.add_task(run_generation_pipeline, key, req.section_ids, valid_scoped)
    
    return {
        "message": "Generation started",
        "status": "starting",
        "scoped_document_ids": valid_scoped,
    }


@app.get("/api/status", response_model=GenerationStatus)
async def get_status():
    """Get current generation status."""
    return generation_status


@app.get("/api/results")
async def get_results():
    """Get generation results."""
    if generation_status["status"] != "complete":
        raise HTTPException(status_code=400, detail="Generation not complete")
        
    data = generation_status["results"]
    if data and "sections" in data:
        for section_id, section in data["sections"].items():
            if not isinstance(section.get("validation"), dict):
                section["validation"] = {
                    "score": 0,
                    "structure_ok": False,
                    "tone_ok": False,
                    "hallucination_risk": "unknown",
                    "warnings": [],
                    "errors": [],
                    "passed": False,
                    "coverage_pct": 0
                }
            if not isinstance(section.get("trace"), dict):
                section["trace"] = {
                    "mapping_confidence": 0,
                    "input_char_count": 0,
                    "transformed_char_count": 0,
                    "matched_keywords": [],
                    "semantic_matches": [],
                    "numeric_values_found": [],
                    "source_priority_used": [],
                    "paragraphs_used_count": 0,
                    "relevance_validated": False
                }
            if not section.get("content"):
                section["content"] = "Not specified in provided documents."

    return data


@app.get("/api/download/{file_type}")
async def download_file(file_type: str):
    """Download generated files."""
    if file_type == "docx":
        file_path = OUTPUT_DIR / "csr_draft.docx"
    elif file_type == "pdf":
        file_path = OUTPUT_DIR / "csr_draft.pdf"
    elif file_type == "summary":
        file_path = OUTPUT_DIR / "generation_summary.txt"
    elif file_type == "log":
        file_path = OUTPUT_DIR / "generation_log.json"
    else:
        raise HTTPException(status_code=400, detail=f"Unknown file type: {file_type}")
        
    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"File not found: {file_type}")
        
    return FileResponse(
        path=str(file_path),
        filename=file_path.name,
        media_type="application/octet-stream"
    )


@app.get("/api/section/{section_id}")
async def get_section_content(section_id: str):
    """Get content of a specific generated section."""
    section_file = CSR_SECTIONS_DIR / f"{section_id}.txt"
    
    if not section_file.exists():
        raise HTTPException(status_code=404, detail=f"Section not found: {section_id}")
        
    with open(section_file, 'r', encoding='utf-8') as f:
        content = f.read()
        
    return {"section_id": section_id, "content": content}


@app.get("/api/compliance")
def get_compliance():
    """Get ICH E3 compliance gap analysis for generated sections."""
    if generation_status.get("results") and generation_status["results"].get("gap_analysis"):
        return generation_status["results"]["gap_analysis"]
    return {"message": "No gap analysis available. Generate CSR sections first."}


# Run with: uvicorn api.server:app --reload --port 8000
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
