# CERC Clinical AI Workbench

## Project Description
The CERC Clinical AI Workbench is a robust, production-ready system designed for automating the generation of Clinical Study Reports (CSR). It employs an evidence-constrained AI pipeline, ensuring zero hallucination, strict adherence to ICH E3 guidelines, and high traceability.

## System Architecture
The platform is built with a modular architecture:
- **Transformation Engine**: Normalizes and structures raw input data.
- **Missing Detector**: Identifies missing clinical evidence before generation.
- **Advanced Validator**: Enforces numeric validation and compliance metrics.
- **Section Pipeline**: Orchestrates section-by-section generation with fallback mechanisms.
- **Prompt Builder**: Constructs deterministic structural prompts.

## Key Features
- **Zero Hallucination**: Strict generation constrained to explicitly provided evidence.
- **Evidence-Only Generation**: Pre-verifies facts and skips generation for missing evidence (defaults to "Not specified.").
- **Numeric Validation**: Ensures statistical coherence between input data and generated text.
- **Traceability**: Comprehensive logging and traceability for auditing purposes.
- **Deterministic Pipeline**: Predictable, consistent outputs.

## Tech Stack
- **Backend**: Python, FastAPI
- **Frontend**: React (Next.js) / HTML + JS
- **AI/LLM**: Anthropic / LangChain

## Setup Instructions

### Backend
1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use `venv\Scripts\activate`
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `.env.example` to `.env` and fill in your API keys.
4. Run the API locally:
   ```bash
   uvicorn api.server:app --reload
   ```

### Frontend
1. Navigate to the frontend directory and launch the interface. Setup instructions inside `frontend/README.md` if using a build system (Vite), otherwise serve statically.
