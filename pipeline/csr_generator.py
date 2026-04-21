"""
CSR Generator Module
Generates CSR sections using OpenAI API with the 3-stage prompt pipeline.
Includes retry logic, chain-of-thought prompting, and smart document chunking.
Supports async concurrent generation for ~4x speedup.
"""

import json
import time
import asyncio
import random
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any, Callable
import os

logger = logging.getLogger(__name__)

try:
    from openai import OpenAI, AsyncOpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False


# Token pricing per 1K tokens (USD) — update if model changes
# Source: https://openai.com/pricing
TOKEN_COSTS = {
    "gpt-4o": {"input": 0.0025, "output": 0.01},
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4-turbo": {"input": 0.01, "output": 0.03},
    "gpt-4": {"input": 0.03, "output": 0.06},
    "gpt-3.5-turbo": {"input": 0.0005, "output": 0.0015},
}


# Retry and chunking constants
MAX_RETRIES = 5
RETRY_BASE_DELAY = 1.0  # seconds
RETRY_MAX_DELAY = 60.0  # seconds
MAX_TOKENS_PER_CHUNK = 6000  # approx chars per chunk (~1500 tokens)

# Chain-of-thought system prompt with strict anti-hallucination grounding
COT_SYSTEM_PROMPT = """You are an expert clinical regulatory writer specialising in ICH E3 Clinical Study Reports for the KISS clinical investigation.

CRITICAL RULES — STRICTLY ENFORCED:
1. ONLY use information explicitly stated in the provided source document text.
2. NEVER invent, infer, extrapolate, or assume ANY fact, number, date, dose, endpoint, subject count, or conclusion.
3. If a piece of information is not present in the source text, you MUST write: "Not specified in source documents."
4. NEVER use phrases like "typically", "generally", "it is expected", "usually", or "commonly" — these signal invented content.
5. Do NOT fill gaps with clinical domain knowledge — only use what is explicitly in the source.
6. Every material claim must be traceable to the source documents provided.
7. If you are uncertain whether something is in the source, treat it as NOT specified.

Think through the task step-by-step in a <thinking> block:
1. What specific information is requested?
2. What does the source text EXPLICITLY state? (quote exact phrases)
3. What is NOT in the source text? (mark as "Not specified")
4. Compile only verified, source-backed information into the output.

Provide your reasoning in <thinking>...</thinking>, then provide your final output after </thinking>."""


class CSRGenerator:
    """Generates CSR sections using a 3-stage AI pipeline with retry, CoT, and chunking."""
    
    # Mapping of section IDs to prompt files
    SECTION_PROMPTS = {
        "study_design": {
            "extractor": "study_design.txt",
            "writer": "study_design_writer.txt"
        },
        "study_objectives": {
            "extractor": "objectives.txt",
            "writer": "objectives_writer.txt"
        },
        "endpoints": {
            "extractor": "endpoints.txt",
            "writer": "endpoints_writer.txt"
        },
        "inclusion_exclusion": {
            "extractor": "inclusion_exclusion.txt",
            "writer": "inclusion_exclusion_writer.txt"
        },
        "statistical_methods": {
            "extractor": "statistical_methods.txt",
            "writer": "statistical_methods_writer.txt"
        },
        "synopsis": {
            "extractor": "synopsis.txt",
            "writer": "synopsis_writer.txt"
        },
        "introduction": {
            "extractor": "introduction.txt",
            "writer": "introduction_writer.txt"
        },
        "ethics": {
            "extractor": "ethics.txt",
            "writer": "ethics_writer.txt"
        },
        "investigators_sites": {
            "extractor": "investigators_sites.txt",
            "writer": "investigators_sites_writer.txt"
        },
        "study_population": {
            "extractor": "study_population.txt",
            "writer": "study_population_writer.txt"
        },
        "treatments": {
            "extractor": "treatments.txt",
            "writer": "treatments_writer.txt"
        },
        "efficacy_evaluation": {
            "extractor": "efficacy_evaluation.txt",
            "writer": "efficacy_evaluation_writer.txt"
        },
        "safety_evaluation": {
            "extractor": "safety_evaluation.txt",
            "writer": "safety_evaluation_writer.txt"
        },
        "discussion_conclusions": {
            "extractor": "discussion_conclusions.txt",
            "writer": "discussion_conclusions_writer.txt"
        },
        "demographics": {
            "extractor": "demographics.txt",
            "writer": "demographics_writer.txt"
        },
        "adverse_events": {
            "extractor": "adverse_events.txt",
            "writer": "adverse_events_writer.txt"
        }
    }
    
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-4o",
        prompts_dir: Path = None
    ):
        """
        Initialize the CSR Generator.
        
        Args:
            api_key: OpenAI API key
            model: Model to use (default: gpt-4o)
            prompts_dir: Path to prompts directory
        """
        if not OPENAI_AVAILABLE:
            raise ImportError("OpenAI package not installed. Run: pip install openai")
            
        self.client = OpenAI(api_key=api_key)
        self.async_client = AsyncOpenAI(api_key=api_key)
        self.model = model
        self.prompts_dir = Path(prompts_dir) if prompts_dir else Path("prompts")
        
        # Generation history for traceability
        self.generation_log: List[Dict] = []
        
        # Thread-safe lock for concurrent token tracking
        self._token_lock = threading.Lock()
        
        # Token usage tracking
        self.token_usage = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
            "total_tokens": 0,
            "total_cost_usd": 0.0,
            "calls": [],
            "per_section": {}
        }
        
    def _load_prompt(self, prompt_type: str, section_id: str) -> str:
        """
        Load a prompt template from file.
        
        Args:
            prompt_type: "extractor", "transformer", or "writer"
            section_id: The CSR section ID
            
        Returns:
            Prompt template string
        """
        if prompt_type == "transformer":
            prompt_file = self.prompts_dir / "transformer_prompts" / "tense_and_style.txt"
        elif prompt_type in ["extractor", "writer"]:
            prompts = self.SECTION_PROMPTS.get(section_id, {})
            filename = prompts.get(prompt_type)
            if not filename:
                raise ValueError(f"No {prompt_type} prompt defined for section: {section_id}")
            
            folder = f"{prompt_type}_prompts"
            prompt_file = self.prompts_dir / folder / filename
        else:
            raise ValueError(f"Unknown prompt type: {prompt_type}")
            
        if not prompt_file.exists():
            raise FileNotFoundError(f"Prompt file not found: {prompt_file}")
            
        with open(prompt_file, 'r', encoding='utf-8') as f:
            return f.read()

    def _augment_prompt_with_context(
        self,
        prompt: str,
        generation_context: Optional[Dict[str, Any]],
        stage: str
    ) -> str:
        """
        Inject strict template/rule/evidence constraints into stage prompts.
        Non-breaking: if no context is provided, prompt remains unchanged.
        """
        if not generation_context:
            return prompt

        template = generation_context.get("template", {})
        required = generation_context.get("required_elements", []) or []
        style_rules = generation_context.get("style_rules", []) or []
        formatting = generation_context.get("formatting_guidance", []) or []
        missing = generation_context.get("missing_elements", []) or []
        examples = generation_context.get("example_snippets", []) or []
        strict = generation_context.get("strict_rules", {}) or {}

        blocks = [
            "",
            "=== SECTION GENERATION CONSTRAINTS (STRICT) ===",
            f"Section ID: {generation_context.get('section_id', '')}",
            f"Section Title: {generation_context.get('section_title', '')}",
            f"Target Heading: {template.get('heading', generation_context.get('section_title', ''))}",
            "Expected Subsections:",
        ]
        blocks.extend([f"- {x}" for x in template.get("expected_subsections", [])[:12]] or ["- None specified"])
        blocks.append("Required Elements:")
        blocks.extend([f"- {x}" for x in required[:16]] or ["- None specified"])
        blocks.append("Style Rules:")
        blocks.extend([f"- {x}" for x in style_rules[:12]] or ["- Use formal regulatory tone"])
        blocks.append("Formatting Guidance:")
        blocks.extend([f"- {x}" for x in formatting[:10]] or ["- Use concise structured narrative"])
        blocks.append("Missing-data policy:")
        blocks.append(f"- {strict.get('missing_data_policy', 'Use Not specified in source documents.')}")
        if missing:
            blocks.append("Potentially missing required elements (from evidence scan):")
            blocks.extend([f"- {x}" for x in missing[:16]])
        if examples and stage in {"write", "extract"}:
            blocks.append("Reference style snippets (style only, NOT facts):")
            blocks.extend([f"- {s[:300]}" for s in examples[:2]])
        blocks.append("=== END CONSTRAINTS ===")
        return prompt + "\n" + "\n".join(blocks)
    
    def _call_llm(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        stage_label: str = "",
        use_cot: bool = False
    ) -> str:
        """
        Call the OpenAI API with retry logic and optional chain-of-thought.
        Tracks token usage and cost for each call.
        
        Args:
            prompt: The complete prompt
            temperature: Generation temperature
            max_tokens: Maximum tokens to generate
            stage_label: Label for this call (e.g. 'study_design/extract')
            use_cot: Whether to use chain-of-thought system prompt
            
        Returns:
            Generated text
        """
        system_content = COT_SYSTEM_PROMPT if use_cot else (
            "You are an expert clinical regulatory writer for the KISS clinical investigation following ICH E3 guidelines. "
            "ONLY use information explicitly stated in the provided source text. "
            "NEVER invent, infer, or assume facts not present in the source. "
            "If information is missing, state: 'Not specified in source documents.'"
        )
        
        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ]
        
        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = self.client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    seed=42
                )
                
                # Track token usage
                usage = response.usage
                if usage:
                    prompt_tokens = usage.prompt_tokens or 0
                    completion_tokens = usage.completion_tokens or 0
                    total = prompt_tokens + completion_tokens
                    
                    # Calculate cost
                    costs = TOKEN_COSTS.get(self.model, TOKEN_COSTS.get("gpt-4o"))
                    input_cost = (prompt_tokens / 1000) * costs["input"]
                    output_cost = (completion_tokens / 1000) * costs["output"]
                    call_cost = input_cost + output_cost
                    
                    # Accumulate totals
                    self.token_usage["total_prompt_tokens"] += prompt_tokens
                    self.token_usage["total_completion_tokens"] += completion_tokens
                    self.token_usage["total_tokens"] += total
                    self.token_usage["total_cost_usd"] += call_cost
                    
                    # Store per-call detail
                    call_info = {
                        "stage": stage_label,
                        "model": self.model,
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "total_tokens": total,
                        "cost_usd": round(call_cost, 6),
                        "attempt": attempt + 1
                    }
                    self.token_usage["calls"].append(call_info)
                    
                    # Print per-call usage
                    retry_note = f" (attempt {attempt + 1})" if attempt > 0 else ""
                    print(f"    Tokens: {prompt_tokens:,} in + {completion_tokens:,} out = {total:,} | Cost: ${call_cost:.4f}{retry_note}")
                
                raw_content = response.choices[0].message.content
                
                # Strip chain-of-thought <thinking> blocks from output
                if use_cot and "</thinking>" in raw_content:
                    raw_content = raw_content.split("</thinking>", 1)[-1].strip()
                
                return raw_content
                
            except Exception as e:
                last_error = e
                error_str = str(e).lower()
                
                # Determine if error is retryable
                retryable = any(keyword in error_str for keyword in [
                    "rate_limit", "rate limit", "429", "timeout", "timed out",
                    "server_error", "500", "502", "503", "529",
                    "overloaded", "capacity", "connection"
                ])
                
                if not retryable or attempt == MAX_RETRIES - 1:
                    logger.error(f"LLM call failed [{stage_label}]: {e}")
                    raise
                
                # Exponential backoff with jitter
                delay = min(
                    RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1),
                    RETRY_MAX_DELAY
                )
                logger.warning(
                    f"Retryable error on attempt {attempt + 1}/{MAX_RETRIES} "
                    f"[{stage_label}]: {e}. Retrying in {delay:.1f}s..."
                )
                print(f"    ⚠ API error, retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                time.sleep(delay)
        
        raise last_error  # Should never reach here, but safety net
    
    def _chunk_text(self, text: str, max_chars: int = None) -> List[str]:
        """
        Split large text into manageable chunks for processing.
        Splits on paragraph boundaries to preserve context.
        
        Args:
            text: The text to chunk
            max_chars: Maximum characters per chunk
            
        Returns:
            List of text chunks
        """
        max_chars = max_chars or MAX_TOKENS_PER_CHUNK
        
        if len(text) <= max_chars:
            return [text]
        
        chunks = []
        paragraphs = text.split('\n\n')
        current_chunk = ""
        
        for para in paragraphs:
            if len(current_chunk) + len(para) + 2 > max_chars and current_chunk:
                chunks.append(current_chunk.strip())
                current_chunk = para
            else:
                current_chunk += "\n\n" + para if current_chunk else para
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        logger.info(f"Split text into {len(chunks)} chunks (avg {sum(len(c) for c in chunks) // len(chunks)} chars)")
        return chunks
    
    def extract_information(
        self,
        section_id: str,
        source_text: str,
        stage_label: str = "",
        generation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Stage 1: Extract relevant information from source text.
        Uses chain-of-thought prompting and handles large docs via chunking.
        
        Args:
            section_id: The CSR section ID
            source_text: Combined source document text
            stage_label: Label for the LLM call
            
        Returns:
            Extracted information as dictionary
        """
        prompt_template = self._load_prompt("extractor", section_id)
        
        # Handle large documents via chunking
        chunks = self._chunk_text(source_text)
        
        if len(chunks) == 1:
            # Single chunk — standard extraction
            prompt = prompt_template.replace("{source_text}", source_text)
            prompt = self._augment_prompt_with_context(prompt, generation_context, stage="extract")
            response = self._call_llm(
                prompt, temperature=0.1, max_tokens=2000,
                stage_label=stage_label, use_cot=True
            )
            extracted = self._parse_json_response(response)
        else:
            # Multi-chunk — extract from each chunk then merge
            print(f"    📄 Large document: splitting into {len(chunks)} chunks")
            chunk_results = []
            for i, chunk in enumerate(chunks):
                prompt = prompt_template.replace("{source_text}", chunk)
                prompt = self._augment_prompt_with_context(prompt, generation_context, stage="extract")
                response = self._call_llm(
                    prompt, temperature=0.1, max_tokens=2000,
                    stage_label=f"{stage_label}/chunk_{i+1}", use_cot=True
                )
                chunk_results.append(self._parse_json_response(response))
            
            # Merge chunk results
            extracted = self._merge_extractions(chunk_results)
            extracted["_chunked"] = True
            extracted["_num_chunks"] = len(chunks)
            
        self.generation_log.append({
            "stage": "extraction",
            "section_id": section_id,
            "input_length": len(source_text),
            "num_chunks": len(chunks),
            "output": extracted
        })
        
        return extracted
    
    # ---------------------------------------------------------------------
    # CERC Spec-Accurate System Identity (shared across Step A/B/C)
    # ---------------------------------------------------------------------
    CERC_SYSTEM_IDENTITY = (
        "You are CERC — Clinical Evidence Reconstruction Core.\n"
        "You are NOT a chatbot.\n"
        "You are a deterministic, regulation-grade transformation engine.\n\n"
        "CORE PRINCIPLE (ABSOLUTE):\n"
        "If information is not explicitly present in source evidence, it DOES NOT EXIST.\n"
        "You MUST NOT infer, assume, generalize, smooth gaps, hallucinate, or add meaning.\n\n"
        "PIPELINE MODE:\n"
        "INPUT → FACTS → ELEMENT MAP → CONTROLLED SECTION → VALIDATION.\n"
        "Failure at any layer = HARD FAIL.\n\n"
        "FORBIDDEN SPECULATIVE LANGUAGE (NEVER USE):\n"
        "- likely, suggests, typically, generally, expected, assume/assumed, inferred, plausible, may have\n\n"
        "FAILURE BEHAVIOR:\n"
        "If you cannot comply, return ONLY a JSON object: {\"error\": \"<reason>\"}\n"
        "Do NOT repair, do NOT guess, do NOT continue.\n"
    )

    # ---------------------------------------------------------------------
    # Debug logging (NDJSON) — session ef7b3b
    # ---------------------------------------------------------------------
    @staticmethod
    def _dbg_log(hypothesis_id: str, location: str, message: str, data: Dict[str, Any]) -> None:
        # region agent log
        try:
            # Write to workspace-root absolute path to avoid CWD ambiguity.
            from pathlib import Path
            log_path = Path(r"C:\Users\mahar\OneDrive\Desktop\ai_csr_generator\debug-ef7b3b.log")
            payload = {
                "sessionId": "ef7b3b",
                "runId": "pre-fix",
                "hypothesisId": hypothesis_id,
                "location": location,
                "message": message,
                "data": data,
                "timestamp": int(time.time() * 1000),
            }
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
        # endregion agent log

    def _parse_json_response(self, response: str) -> Dict[str, Any]:
        """Parse JSON from an LLM response, tolerant of extra text."""
        try:
            json_start = response.find('{')
            json_end = response.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                return json.loads(json_str)
            return {"raw_response": response}
        except json.JSONDecodeError:
            return {"raw_response": response}

    @staticmethod
    def _parse_json_object_response_strict(response: str) -> Dict[str, Any]:
        """
        Strict JSON object parsing for spec-accurate Step A/B.
        Hard-fails if the response is not a pure JSON object (no extra text).
        """
        raw = (response or "").strip()
        if not (raw.startswith("{") and raw.endswith("}")):
            raise ValueError("Invalid JSON object from LLM: response is not pure JSON object")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError("Invalid JSON object from LLM: parsed value is not a JSON object")
        if "error" in parsed:
            raise ValueError(f"LLM returned error object: {parsed.get('error')}")
        return parsed

    def _parse_json_array_response(self, response: str) -> List[Dict[str, Any]]:
        """Parse JSON array from an LLM response, tolerant of extra text."""
        try:
            json_start = response.find('[')
            json_end = response.rfind(']') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response[json_start:json_end]
                arr = json.loads(json_str)
                if isinstance(arr, list):
                    return arr  # type: ignore[return-value]
                return [{"raw_response": response}]
            return [{"raw_response": response}]
        except json.JSONDecodeError:
            return [{"raw_response": response}]

    @staticmethod
    def _parse_json_array_response_strict(response: str) -> List[Dict[str, Any]]:
        """
        Strict JSON array parsing for spec-accurate Step A/B.
        Hard-fails if the response is not a pure JSON array (no extra text).
        """
        raw = (response or "").strip()
        # Allow explicit hard-fail contract from the model.
        if raw.startswith("{") and raw.endswith("}"):
            parsed_obj = json.loads(raw)
            if isinstance(parsed_obj, dict) and "error" in parsed_obj:
                raise ValueError(f"LLM returned error object: {parsed_obj.get('error')}")
        if not (raw.startswith("[") and raw.endswith("]")):
            raise ValueError("Invalid JSON array from LLM: response is not pure JSON array")
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise ValueError("Invalid JSON array from LLM: parsed value is not a JSON array")
        return parsed
    
    def _merge_extractions(self, chunk_results: List[Dict]) -> Dict[str, Any]:
        """
        Merge extraction results from multiple document chunks.
        For each field, keeps non-empty values, preferring longer/more detailed ones.
        """
        if not chunk_results:
            return {}
        if len(chunk_results) == 1:
            return chunk_results[0]
        
        merged = {}
        all_keys = set()
        for result in chunk_results:
            all_keys.update(result.keys())
        
        not_specified = "not specified in source documents"
        
        for key in all_keys:
            if key == "raw_response":
                continue
            values = []
            for result in chunk_results:
                val = result.get(key)
                if val and isinstance(val, str) and not_specified not in val.lower():
                    values.append(val)
                elif val and isinstance(val, (list, dict)):
                    values.append(val)
            
            if not values:
                merged[key] = "Not specified in source documents"
            elif isinstance(values[0], list):
                # Merge lists
                merged_list = []
                for v in values:
                    if isinstance(v, list):
                        merged_list.extend(v)
                merged[key] = list(set(merged_list)) if all(isinstance(x, str) for x in merged_list) else merged_list
            elif isinstance(values[0], str):
                # Keep the longest / most detailed value
                merged[key] = max(values, key=len)
            else:
                merged[key] = values[0]
        
        return merged
    
    def transform_content(
        self,
        extracted_data: Dict[str, Any],
        stage_label: str = "",
        generation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Stage 2: Transform extracted content (tense, style).
        
        Args:
            extracted_data: Data from extraction stage
            stage_label: Label for the LLM call
            
        Returns:
            Transformed data
        """
        prompt_template = self._load_prompt("transformer", "")
        prompt = prompt_template.replace("{extracted_data}", json.dumps(extracted_data, indent=2))
        prompt = self._augment_prompt_with_context(prompt, generation_context, stage="transform")
        
        response = self._call_llm(prompt, temperature=0.1, max_tokens=2000, stage_label=stage_label)
        
        # Parse JSON from response
        transformed = self._parse_json_response(response)
            
        self.generation_log.append({
            "stage": "transformation",
            "output": transformed
        })
        
        return transformed
    
    def write_section(
        self,
        section_id: str,
        transformed_data: Dict[str, Any],
        source_documents: List[str],
        stage_label: str = "",
        generation_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Stage 3: Write the final CSR section.
        
        Args:
            section_id: The CSR section ID
            transformed_data: Data from transformation stage
            source_documents: List of source document names used
            stage_label: Label for the LLM call
            
        Returns:
            Final CSR section text
        """
        prompt_template = self._load_prompt("writer", section_id)
        prompt = prompt_template.replace(
            "{transformed_data}",
            json.dumps(transformed_data, indent=2)
        ).replace(
            "{source_documents}",
            ", ".join(source_documents)
        )
        prompt = self._augment_prompt_with_context(prompt, generation_context, stage="write")
        
        response = self._call_llm(
            prompt, temperature=0.05, max_tokens=4000,
            stage_label=stage_label, use_cot=True
        )
        
        self.generation_log.append({
            "stage": "writing",
            "section_id": section_id,
            "output_length": len(response)
        })
        
        return response
    
    def generate_section(
        self,
        section_id: str,
        source_text: str,
        source_documents: List[str],
        generation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Complete 3-stage pipeline to generate a CSR section.
        Tracks token usage per stage and per section.
        
        Args:
            section_id: The CSR section ID
            source_text: Combined source document text
            source_documents: List of source document names
            
        Returns:
            Dictionary with generated section and metadata
        """
        print(f"\nGenerating CSR section: {section_id}")
        section_start_tokens = self.token_usage["total_tokens"]
        section_start_cost = self.token_usage["total_cost_usd"]
        
        # Stage 1: Extract
        print("  Stage 1: Extracting information...")
        extracted = self.extract_information(
            section_id,
            source_text,
            stage_label=f"{section_id}/extraction",
            generation_context=generation_context,
        )
        
        # Stage 2: Transform
        print("  Stage 2: Transforming content...")
        transformed = self.transform_content(
            extracted,
            stage_label=f"{section_id}/transformation",
            generation_context=generation_context,
        )
        
        # Stage 3: Write
        print("  Stage 3: Writing section...")
        final_text = self.write_section(
            section_id,
            transformed,
            source_documents,
            stage_label=f"{section_id}/writing",
            generation_context=generation_context,
        )
        
        # Calculate section totals
        section_tokens = self.token_usage["total_tokens"] - section_start_tokens
        section_cost = self.token_usage["total_cost_usd"] - section_start_cost
        
        # Store per-section summary
        self.token_usage["per_section"][section_id] = {
            "tokens": section_tokens,
            "cost_usd": round(section_cost, 6)
        }
        
        print(f"  Section complete: {len(final_text)} chars | {section_tokens:,} tokens | ${section_cost:.4f}")
        
        return {
            "section_id": section_id,
            "final_text": final_text,
            "extracted_data": extracted,
            "transformed_data": transformed,
            "source_documents": source_documents,
            "generation_context": generation_context or {},
            "generation_context_summary": {
                "required_elements": (generation_context or {}).get("required_elements", [])[:12],
                "missing_elements": (generation_context or {}).get("missing_elements", [])[:12],
                "template_heading": ((generation_context or {}).get("template", {}) or {}).get("heading", ""),
            },
            "generation_log": self.generation_log[-3:],  # Last 3 entries for this section
            "token_usage": self.token_usage["per_section"][section_id]
        }
    
    def generate_all_sections(
        self,
        matching_content: Dict[str, Dict]
    ) -> Dict[str, Dict]:
        """
        Generate all available CSR sections.
        
        Args:
            matching_content: Dictionary mapping section IDs to matched content
            
        Returns:
            Dictionary of all generated sections
        """
        results = {}
        
        for section_id, content_data in matching_content.items():
            if content_data.get("combined_content"):
                source_docs = list(set(
                    m.get("source_document", "unknown")
                    for m in content_data.get("matches", [])
                ))
                
                result = self.generate_section(
                    section_id,
                    content_data["combined_content"],
                    source_docs,
                    generation_context=content_data.get("generation_context"),
                )
                results[section_id] = result
            else:
                print(f"⚠ No matching content found for section: {section_id}")
                results[section_id] = {
                    "section_id": section_id,
                    "final_text": f"[No content available for this section. Source documents did not contain matching information for {section_id}.]",
                    "error": "No matching content"
                }
                
        # Print final usage summary
        print("\n" + "="*60)
        print("TOKEN USAGE SUMMARY")
        print("="*60)
        print(f"  Model: {self.model}")
        print(f"  Total prompt tokens:     {self.token_usage['total_prompt_tokens']:,}")
        print(f"  Total completion tokens:  {self.token_usage['total_completion_tokens']:,}")
        print(f"  Total tokens:            {self.token_usage['total_tokens']:,}")
        print(f"  Total cost:              ${self.token_usage['total_cost_usd']:.4f}")
        print("-"*60)
        for sid, usage in self.token_usage["per_section"].items():
            print(f"  {sid:30s} {usage['tokens']:>8,} tokens  ${usage['cost_usd']:.4f}")
        print("="*60)
        
        return results

    # ================================================================
    # ASYNC CONCURRENT GENERATION (4x speedup)
    # ================================================================

    async def _call_llm_async(
        self,
        prompt: str,
        temperature: float = 0.2,
        max_tokens: int = 2000,
        stage_label: str = "",
        use_cot: bool = False,
        system_content_override: Optional[str] = None,
    ) -> str:
        """
        Async version of _call_llm using AsyncOpenAI.
        Identical retry logic and token tracking (thread-safe).
        """
        system_content = system_content_override if system_content_override is not None else (
            COT_SYSTEM_PROMPT if use_cot else (
                "You are an expert clinical regulatory writer for the KISS clinical investigation following ICH E3 guidelines. "
                "ONLY use information explicitly stated in the provided source text. "
                "NEVER invent, infer, or assume facts not present in the source. "
                "If information is missing, state: 'Not specified in source documents.'"
            )
        )

        messages = [
            {"role": "system", "content": system_content},
            {"role": "user", "content": prompt}
        ]

        last_error = None
        for attempt in range(MAX_RETRIES):
            try:
                response = await self.async_client.chat.completions.create(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    seed=42
                )

                # Track token usage (thread-safe)
                usage = response.usage
                if usage:
                    prompt_tokens = usage.prompt_tokens or 0
                    completion_tokens = usage.completion_tokens or 0
                    total = prompt_tokens + completion_tokens

                    costs = TOKEN_COSTS.get(self.model, TOKEN_COSTS.get("gpt-4o"))
                    input_cost = (prompt_tokens / 1000) * costs["input"]
                    output_cost = (completion_tokens / 1000) * costs["output"]
                    call_cost = input_cost + output_cost

                    with self._token_lock:
                        self.token_usage["total_prompt_tokens"] += prompt_tokens
                        self.token_usage["total_completion_tokens"] += completion_tokens
                        self.token_usage["total_tokens"] += total
                        self.token_usage["total_cost_usd"] += call_cost

                        call_info = {
                            "stage": stage_label,
                            "model": self.model,
                            "prompt_tokens": prompt_tokens,
                            "completion_tokens": completion_tokens,
                            "total_tokens": total,
                            "cost_usd": round(call_cost, 6),
                            "attempt": attempt + 1
                        }
                        self.token_usage["calls"].append(call_info)

                    retry_note = f" (attempt {attempt + 1})" if attempt > 0 else ""
                    print(f"    [{stage_label}] Tokens: {prompt_tokens:,} in + {completion_tokens:,} out = {total:,} | ${call_cost:.4f}{retry_note}")

                raw_content = response.choices[0].message.content

                if use_cot and "</thinking>" in raw_content:
                    raw_content = raw_content.split("</thinking>", 1)[-1].strip()

                return raw_content

            except Exception as e:
                last_error = e
                error_str = str(e).lower()

                retryable = any(keyword in error_str for keyword in [
                    "rate_limit", "rate limit", "429", "timeout", "timed out",
                    "server_error", "500", "502", "503", "529",
                    "overloaded", "capacity", "connection"
                ])

                if not retryable or attempt == MAX_RETRIES - 1:
                    logger.error(f"Async LLM call failed [{stage_label}]: {e}")
                    raise

                delay = min(
                    RETRY_BASE_DELAY * (2 ** attempt) + random.uniform(0, 1),
                    RETRY_MAX_DELAY
                )
                logger.warning(
                    f"Retryable error on attempt {attempt + 1}/{MAX_RETRIES} "
                    f"[{stage_label}]: {e}. Retrying in {delay:.1f}s..."
                )
                print(f"    ⚠ [{stage_label}] API error, retrying in {delay:.1f}s (attempt {attempt + 1}/{MAX_RETRIES})...")
                await asyncio.sleep(delay)

        raise last_error

    async def _extract_information_async(
        self,
        section_id: str,
        source_text: str,
        stage_label: str = "",
        generation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Async version of extract_information."""
        prompt_template = self._load_prompt("extractor", section_id)
        chunks = self._chunk_text(source_text)

        if len(chunks) == 1:
            prompt = prompt_template.replace("{source_text}", source_text)
            prompt = self._augment_prompt_with_context(prompt, generation_context, stage="extract")
            response = await self._call_llm_async(
                prompt, temperature=0.1, max_tokens=2000,
                stage_label=stage_label, use_cot=True
            )
            extracted = self._parse_json_response(response)
        else:
            print(f"    📄 [{section_id}] Large document: splitting into {len(chunks)} chunks")
            chunk_results = []
            for i, chunk in enumerate(chunks):
                prompt = prompt_template.replace("{source_text}", chunk)
                prompt = self._augment_prompt_with_context(prompt, generation_context, stage="extract")
                response = await self._call_llm_async(
                    prompt, temperature=0.1, max_tokens=2000,
                    stage_label=f"{stage_label}/chunk_{i+1}", use_cot=True
                )
                chunk_results.append(self._parse_json_response(response))
            extracted = self._merge_extractions(chunk_results)
            extracted["_chunked"] = True
            extracted["_num_chunks"] = len(chunks)

        self.generation_log.append({
            "stage": "extraction",
            "section_id": section_id,
            "input_length": len(source_text),
            "num_chunks": len(chunks),
            "output": extracted
        })
        return extracted

    async def _transform_content_async(
        self,
        extracted_data: Dict[str, Any],
        stage_label: str = "",
        generation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Async version of transform_content."""
        prompt_template = self._load_prompt("transformer", "")
        prompt = prompt_template.replace("{extracted_data}", json.dumps(extracted_data, indent=2))
        prompt = self._augment_prompt_with_context(prompt, generation_context, stage="transform")
        response = await self._call_llm_async(prompt, temperature=0.2, max_tokens=2000, stage_label=stage_label)
        transformed = self._parse_json_response(response)
        self.generation_log.append({"stage": "transformation", "output": transformed})
        return transformed

    async def _write_section_async(
        self,
        section_id: str,
        transformed_data: Dict[str, Any],
        source_documents: List[str],
        stage_label: str = "",
        generation_context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Async version of write_section."""
        prompt_template = self._load_prompt("writer", section_id)
        prompt = prompt_template.replace(
            "{transformed_data}", json.dumps(transformed_data, indent=2)
        ).replace("{source_documents}", ", ".join(source_documents))
        prompt = self._augment_prompt_with_context(prompt, generation_context, stage="write")

        response = await self._call_llm_async(
            prompt, temperature=0.3, max_tokens=4000,
            stage_label=stage_label, use_cot=True
        )
        self.generation_log.append({
            "stage": "writing", "section_id": section_id, "output_length": len(response)
        })
        return response

    async def _step_a_extract_facts(self, context: Dict[str, Any]) -> List[Dict[str, Any]]:
        """
        STEP A (spec): Extract discrete factual claims as JSON array.
        Output ONLY a JSON array. No commentary.
        Each object: {"element": "...", "value": "...", "source_phrase": "..."}
        """
        required_elements = context.get("required_elements", []) or []
        evidence_text = context.get("user_evidence", "") or ""

        system_content = (
            self.CERC_SYSTEM_IDENTITY
            + "\nSTEP A — FACT EXTRACTION (ATOMIC TRUTH)\n"
            + "Objective: Extract ONLY verifiable, atomic facts.\n"
            + "Output: STRICT JSON ARRAY ONLY (no text before/after).\n"
            + "Schema:\n"
            + "[{\"element\":\"<element_name>\",\"value\":\"<exact extracted value>\",\"source\":{\"file\":\"<source file name>\",\"page\":\"<page number or null>\",\"text\":\"<exact quote from source>\"}}]\n\n"
            + "Rules:\n"
            + "- One fact = one object\n"
            + "- No summarization, no merging, no interpretation\n"
            + "- Must be directly traceable to provided evidence blocks\n"
            + "- If unsure → DO NOT EXTRACT\n"
            + "- ALWAYS include the exact file name and page number if provided in the source block.\n"
        )

        source_blocks = context.get("source_blocks", [])
        if source_blocks:
            evidence_formatted = []
            for b in source_blocks:
                file_name = b.get("source_file", "Unknown")
                page = b.get("page", b.get("metadata", {}).get("page", "Unknown"))
                text = b.get("text", b.get("content", ""))
                evidence_formatted.append(f"--- FILE: {file_name} | PAGE: {page} ---\n{text}\n")
            evidence_text = "\n".join(evidence_formatted)
        
        user_content = "\n".join(
            [
                f"Section ID: {context.get('section_id','')}",
                f"Section Title: {context.get('section_title','')}",
                "Required elements:",
                "\n".join([f"- {x}" for x in required_elements[:30]]) if required_elements else "- None",
                "",
                "Provided user evidence blocks (facts only, no templates):",
                evidence_text,
            ]
        )

        raw = await self._call_llm_async(
            prompt=user_content,
            temperature=0.1,
            max_tokens=2500,
            stage_label=f"{context.get('section_id','')}/step_a_extract_facts",
            system_content_override=system_content,
        )
        # Spec mode: Step A must be strict JSON only. No tolerant fallback.
        facts = self._parse_json_array_response_strict(raw)
        self._dbg_log(
            "H1",
            "pipeline/csr_generator.py:_step_a_extract_facts",
            "Step A parsed facts",
            {"section_id": context.get("section_id"), "facts_count": len(facts or [])},
        )
        return facts

    async def _step_b_map_elements(
        self,
        context: Dict[str, Any],
        extracted_facts: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """
        STEP B (spec): Map required elements to evidence values or null.
        Output ONLY a JSON object. No commentary.
        """
        required_elements = context.get("required_elements", []) or []
        template = context.get("template", {}) or {}
        structure_order = template.get("structure_order", []) or []

        system_content = (
            self.CERC_SYSTEM_IDENTITY
            + "\nSTEP B — ELEMENT MAPPING (STRUCTURAL TRUTH)\n"
            + "Objective: Map ALL required elements to presence/value/subsection.\n"
            + "Output: STRICT JSON OBJECT ONLY (no text before/after).\n\n"
            + "Return JSON ONLY in this exact shape:\n"
            + "{\n"
            + "  \"mapped\": {\n"
            + "    \"<required element>\": {\n"
            + "      \"status\": \"present\" | \"missing\" | \"partial\",\n"
            + "      \"value\": \"value string\" | null,\n"
            + "      \"subsection\": \"<EXACT item from structure_order>\",\n"
            + "      \"source\": {\n"
            + "        \"file\": \"<source file name>\",\n"
            + "        \"page\": \"<page number>\",\n"
            + "        \"text\": \"<exact quote from evidence>\"\n"
            + "      } | null\n"
            + "    }\n"
            + "  },\n"
            + "  \"missing\": [\"missing element\", ...]\n"
            + "}\n\n"
            + "Rules:\n"
            + "- ALL required elements MUST appear in mapped\n"
            + "- Missing elements MUST be explicitly marked (status=missing, value=null, source=null)\n"
            + "- subsection MUST match EXACT template structure_order item text\n"
            + "- No guessed values. Use only extracted_facts\n"
        )

        user_content = "\n".join(
            [
                f"Section ID: {context.get('section_id','')}",
                "Required elements JSON:",
                json.dumps(required_elements, ensure_ascii=False),
                "Extracted facts JSON:",
                json.dumps(extracted_facts, ensure_ascii=False),
                "Template structure_order JSON:",
                json.dumps(structure_order, ensure_ascii=False),
                "",
                "Return the JSON object now."
            ]
        )

        raw = await self._call_llm_async(
            prompt=user_content,
            temperature=0.1,
            max_tokens=2000,
            stage_label=f"{context.get('section_id','')}/step_b_map_elements",
            system_content_override=system_content,
        )
        # Spec mode: Step B must be strict JSON only. No tolerant fallback.
        mapped = self._parse_json_object_response_strict(raw)
        mapped_keys = list((mapped.get("mapped", {}) or {}).keys()) if isinstance(mapped, dict) else []
        self._dbg_log(
            "H2",
            "pipeline/csr_generator.py:_step_b_map_elements",
            "Step B parsed mapping",
            {
                "section_id": context.get("section_id"),
                "mapped_keys_count": len(mapped_keys),
                "missing_len": len((mapped.get("missing", []) or [])) if isinstance(mapped, dict) else None,
            },
        )
        return mapped

    async def _step_c_generate_section(
        self,
        context: Dict[str, Any],
        element_map: Dict[str, Any],
    ) -> str:
        """
        STEP C (spec): Generate final section text from confirmed element map only.
        Output ONLY the section text. No preamble.
        """
        template = context.get("template", {}) or {}
        structure_order = template.get("structure_order", []) or []
        prohibited_phrases = context.get("prohibited_phrases", []) or []
        example_snippets = context.get("example_snippets", []) or []

        heading = template.get("heading", "") or context.get("section_title", "") or context.get("section_id", "")

        # element_map may be either legacy {element: value|null} or rich {element: {status,value,subsection,...}}
        element_values_marked: Dict[str, Any] = {}
        element_subsections: Dict[str, Any] = {}
        for k, v in (element_map or {}).items():
            key = str(k)
            if isinstance(v, dict):
                status = v.get("status")
                val = v.get("value")
                subsection = v.get("subsection")
                element_subsections[key] = subsection
                if status == "missing" or val is None:
                    element_values_marked[key] = "Not specified."
                else:
                    element_values_marked[key] = val
            else:
                element_values_marked[key] = "Not specified." if v is None else v

        system_content = (
            self.CERC_SYSTEM_IDENTITY
            + "\nSTEP C — CONTROLLED GENERATION (NO FREEDOM MODE)\n"
            + "Objective: Generate section with ZERO deviation.\n\n"
            + "STRUCTURE LOCK:\n"
            + "- Output EXACT section heading (first non-empty line)\n"
            + "- Follow structure_order EXACTLY (no reordering/skipping/extra)\n\n"
            + "ELEMENT-LINKED ENFORCEMENT & SYNTHESIS (CRITICAL):\n"
            + "- Controlled Synthesis Layer: You may combine elements into cohesive, professional regulatory paragraphs.\n"
            + "- You may add connecting phrases and smooth sentences to improve flow.\n"
            + "- For missing or null assigned elements (Not specified.), DO NOT output the exact string 'Not specified.' alone.\n"
            + "- Instead, clearly state in readable prose that the information was not specified or not detailed in the source texts (e.g., 'Blinding details were not specified.').\n"
            + "- DO NOT hallucinate, infer, or guess missing values.\n\n"
            + "WRITING RULES:\n"
            + "- Formal regulatory tone\n"
            + "- Past tense only\n"
            + "- No causation unless stated in evidence\n\n"
            + "PROHIBITED PHRASES (never use these):\n"
            + f"{json.dumps(prohibited_phrases, ensure_ascii=False)}\n\n"
            + "TEMPLATE STRUCTURE (follow in this exact order):\n"
            + f"{json.dumps(structure_order, ensure_ascii=False)}\n\n"
            + "OUTPUT FORMAT REQUIREMENT:\n"
            + "Write the template heading first on its own line.\n"
            + "Then, for each item in structure_order in order, write a numbered subheading that includes the exact item text, "
            + "followed by one paragraph under that subheading.\n\n"
            + "STYLE REFERENCES (tone/format only — NOT facts):\n"
            + f"{json.dumps(example_snippets[:3], ensure_ascii=False)}\n\n"
            + "CONFIRMED ELEMENT VALUES:\n"
            + f"{json.dumps(element_values_marked, ensure_ascii=False)}\n\n"
            + "ELEMENT -> SUBSECTION LINKING:\n"
            + f"{json.dumps(element_subsections, ensure_ascii=False)}\n"
        )

        user_content = "\n".join(
            [
                f"Section heading: {heading}",
                "Generate the section now.",
            ]
        )

        raw = await self._call_llm_async(
            prompt=user_content,
            temperature=0.2,
            max_tokens=4500,
            stage_label=f"{context.get('section_id','')}/step_c_generate_section",
            system_content_override=system_content,
        )
        out = raw.strip()
        self._dbg_log(
            "H3",
            "pipeline/csr_generator.py:_step_c_generate_section",
            "Step C generated output",
            {"section_id": context.get("section_id"), "out_len": len(out), "out_first_120": out[:120]},
        )
        return out

    async def generate_section_async(
        self,
        section_id: str,
        source_text: str,
        source_documents: List[str],
        progress_callback: Callable = None,
        generation_context: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Async 3-stage pipeline for a single CSR section.
        Calls progress_callback(section_id, stage) after each stage.
        """
        print(f"\n🚀 [ASYNC] Generating CSR section (3-step element chain): {section_id}")
        section_start_tokens = self.token_usage["total_tokens"]
        section_start_cost = self.token_usage["total_cost_usd"]

        context = generation_context or {}
        # Ensure evidence is present; fallback to passed source_text for safety.
        if not context.get("user_evidence"):
            context["user_evidence"] = source_text or ""

        if progress_callback:
            progress_callback(section_id, "extract_facts")

        try:
            extracted_facts = await self._step_a_extract_facts(context)
        except Exception as e:
            self._dbg_log(
                "H1",
                "pipeline/csr_generator.py:generate_section_async",
                "Step A failed",
                {"section_id": section_id, "error": str(e)[:400]},
            )
            raise

        if progress_callback:
            progress_callback(section_id, "map_elements")

        try:
            mapped_result = await self._step_b_map_elements(context, extracted_facts)
        except Exception as e:
            self._dbg_log(
                "H2",
                "pipeline/csr_generator.py:generate_section_async",
                "Step B failed",
                {"section_id": section_id, "error": str(e)[:400]},
            )
            raise
        raw_mapped = mapped_result.get("mapped", {}) or {}
        missing_elements = mapped_result.get("missing", []) or []

        # Build legacy element_map (Record[str, value|null]) + rich element_map_rich (Record[str, meta])
        element_map: Dict[str, Any] = {}
        element_map_rich: Dict[str, Any] = {}
        for k, v in (raw_mapped or {}).items():
            key = str(k)
            if isinstance(v, dict):
                status = v.get("status")
                val = v.get("value")
                # Normalize: missing => null
                if status == "missing":
                    val = None
                element_map[key] = val
                element_map_rich[key] = {
                    "status": status or ("missing" if val is None else "present"),
                    "value": val,
                    "subsection": v.get("subsection"),
                    "source": v.get("source"),
                }
            else:
                # Back-compat if model returned legacy shape unexpectedly.
                element_map[key] = v
                element_map_rich[key] = {
                    "status": "missing" if v is None else "present",
                    "value": v,
                    "subsection": None,
                    "source": None,
                }

        if not missing_elements:
            # Derive missing from null values if model omitted "missing".
            missing_elements = [k for k, v in element_map.items() if v is None]

        if progress_callback:
            progress_callback(section_id, "generate_section")

        try:
            final_text = await self._step_c_generate_section(context, element_map)
        except Exception as e:
            self._dbg_log(
                "H3",
                "pipeline/csr_generator.py:generate_section_async",
                "Step C failed",
                {"section_id": section_id, "error": str(e)[:400]},
            )
            raise

        with self._token_lock:
            section_tokens = self.token_usage["total_tokens"] - section_start_tokens
            section_cost = self.token_usage["total_cost_usd"] - section_start_cost
            self.token_usage["per_section"][section_id] = {
                "tokens": section_tokens,
                "cost_usd": round(section_cost, 6)
            }

        return {
            "section_id": section_id,
            "final_text": final_text,
            "extracted_facts": extracted_facts,
            "element_map": element_map,
            "element_map_rich": element_map_rich,
            "missing_elements": missing_elements,
            "source_documents": source_documents or (context.get("source_files", []) or []),
            "generation_context": context,
            "token_usage": self.token_usage["per_section"][section_id],
            "generation_steps": {
                "step_a_facts_count": len(extracted_facts or []),
                "step_b_missing_count": len(missing_elements or []),
            },
        }

    async def generate_all_sections_async(
        self,
        matching_content: Dict[str, Dict],
        max_concurrent: int = 4,
        progress_callback: Callable = None
    ) -> Dict[str, Dict]:
        """
        Generate all CSR sections concurrently (up to max_concurrent at a time).
        Uses asyncio.Semaphore to respect API rate limits.

        Args:
            matching_content: Dictionary mapping section IDs to matched content
            max_concurrent: Maximum concurrent section generations (default: 4)
            progress_callback: Optional callback(section_id, stage) for progress

        Returns:
            Dictionary of all generated sections
        """
        results = {}
        semaphore = asyncio.Semaphore(max_concurrent)
        completed_count = 0
        total_sections = len(matching_content)

        async def _generate_with_semaphore(section_id, content_data):
            nonlocal completed_count

            if not content_data.get("combined_content"):
                print(f"⚠ No matching content found for section: {section_id}")
                return section_id, {
                    "section_id": section_id,
                    "final_text": f"[No content available for this section. Source documents did not contain matching information for {section_id}.]",
                    "error": "No matching content"
                }

            gen_ctx = content_data.get("generation_context", {}) or {}
            source_docs = gen_ctx.get("source_files", []) or []

            async with semaphore:
                try:
                    result = await self.generate_section_async(
                        section_id,
                        content_data["combined_content"],
                        source_docs,
                        progress_callback=progress_callback,
                        generation_context=content_data.get("generation_context"),
                    )
                except Exception as e:
                    # Spec mode: Step A/B strict parsing failures must not silently disappear.
                    # Return a failed section result for downstream validation/UI gating.
                    result = {
                        "section_id": section_id,
                        "final_text": "",
                        "error": str(e),
                    }
                completed_count += 1
                if progress_callback:
                    progress_callback(section_id, "complete",
                                     completed=completed_count,
                                     total=total_sections)
                return section_id, result

        # Launch all tasks concurrently (semaphore limits actual concurrency)
        tasks = [
            _generate_with_semaphore(sid, cdata)
            for sid, cdata in matching_content.items()
        ]

        print(f"\n{'='*60}")
        print(f"ASYNC GENERATION: {total_sections} sections, {max_concurrent} concurrent")
        print(f"{'='*60}")

        completed = await asyncio.gather(*tasks, return_exceptions=True)

        for item in completed:
            if isinstance(item, Exception):
                logger.error(f"Section generation failed: {item}")
                continue
            section_id, result = item
            results[section_id] = result

        # Print final usage summary
        print("\n" + "="*60)
        print("TOKEN USAGE SUMMARY")
        print("="*60)
        print(f"  Model: {self.model}")
        print(f"  Total prompt tokens:     {self.token_usage['total_prompt_tokens']:,}")
        print(f"  Total completion tokens:  {self.token_usage['total_completion_tokens']:,}")
        print(f"  Total tokens:            {self.token_usage['total_tokens']:,}")
        print(f"  Total cost:              ${self.token_usage['total_cost_usd']:.4f}")
        print("-"*60)
        for sid, usage in self.token_usage["per_section"].items():
            print(f"  {sid:30s} {usage['tokens']:>8,} tokens  ${usage['cost_usd']:.4f}")
        print("="*60)

        return results

    def get_usage_summary(self) -> Dict[str, Any]:
        """
        Get a clean summary of token usage and costs.
        
        Returns:
            Dictionary with usage stats suitable for API response.
        """
        return {
            "model": self.model,
            "total_prompt_tokens": self.token_usage["total_prompt_tokens"],
            "total_completion_tokens": self.token_usage["total_completion_tokens"],
            "total_tokens": self.token_usage["total_tokens"],
            "total_cost_usd": round(self.token_usage["total_cost_usd"], 4),
            "per_section": self.token_usage["per_section"],
            "num_api_calls": len(self.token_usage["calls"])
        }
    
    def save_generation_log(self, output_file: Path) -> None:
        """Save the complete generation log for traceability."""
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(self.generation_log, f, indent=2, ensure_ascii=False)
