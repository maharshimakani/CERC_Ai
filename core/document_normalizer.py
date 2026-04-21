"""
Document Normalizer — Layer 1
─────────────────────────────
Converts raw uploaded files into structured, clean, usable text.

Responsibilities:
  1. Traverse expected_input/ (flat or subfolder layout)
  2. Detect document types from filenames or folder names
  3. Extract text from PDF/DOCX/TXT files
  4. Clean text (whitespace, headers/footers, formatting)
  5. Return structured dict: {doc_type: [clean_texts]}

This module is ADDITIVE — it does not modify any existing pipeline.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# Project root for default paths
_PROJECT_ROOT = Path(__file__).parent.parent

# Document type classification patterns
_TYPE_PATTERNS: Dict[str, List[str]] = {
    "protocol": ["cip", "protocol", "investigational_plan", "investigation_plan", "clinical_investigation"],
    "sap": ["sap", "statistical", "analysis_plan"],
    "monitoring_plan": ["monitor", "monitoring", "cmp"],
    "cec_charter": ["cec", "charter"],
    "clinical_report": ["clinical_investigation_report", "csr", "clinical_report"],
    "safety_report": ["safety", "adverse"],
    "appendix": ["appendix", "annual", "corelab", "quality", "data_management"],
}


class DocumentNormalizer:
    """Ingests raw clinical documents and returns clean structured text."""

    def __init__(self, input_dir: Optional[Path] = None):
        """
        Args:
            input_dir: Root directory containing source documents.
                       Defaults to <project>/Expected input/
        """
        self.input_dir = Path(input_dir or _PROJECT_ROOT / "Expected input")

    # ── Text extraction ──────────────────────────────────────────────

    @staticmethod
    def _extract_pdf(filepath: Path) -> str:
        """Extract text from a PDF file."""
        try:
            import fitz  # PyMuPDF
            doc = fitz.open(str(filepath))
            pages = []
            for page in doc:
                pages.append(page.get_text("text"))
            doc.close()
            return "\n\n".join(pages)
        except ImportError:
            logger.warning("PyMuPDF not installed — cannot extract PDF: %s", filepath.name)
            return ""
        except Exception as exc:
            logger.error("PDF extraction failed for %s: %s", filepath.name, exc)
            return ""

    @staticmethod
    def _extract_docx(filepath: Path) -> str:
        """Extract text from a DOCX file."""
        try:
            from docx import Document
            doc = Document(str(filepath))
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except ImportError:
            logger.warning("python-docx not installed — cannot extract DOCX: %s", filepath.name)
            return ""
        except Exception as exc:
            logger.error("DOCX extraction failed for %s: %s", filepath.name, exc)
            return ""

    @staticmethod
    def _extract_txt(filepath: Path) -> str:
        """Read a plain text file."""
        try:
            return filepath.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.error("TXT read failed for %s: %s", filepath.name, exc)
            return ""

    def _extract_file(self, filepath: Path) -> str:
        """Route extraction by file extension."""
        ext = filepath.suffix.lower()
        if ext == ".pdf":
            return self._extract_pdf(filepath)
        elif ext in (".docx",):
            return self._extract_docx(filepath)
        elif ext in (".doc",):
            # .doc is legacy; try PDF extraction first (some are converted)
            return self._extract_pdf(filepath)
        elif ext in (".txt", ".md", ".csv"):
            return self._extract_txt(filepath)
        else:
            logger.debug("Unsupported file type skipped: %s", filepath.name)
            return ""

    # ── Text cleaning ────────────────────────────────────────────────

    @staticmethod
    def clean_text(raw: str) -> str:
        """
        Clean extracted text:
          - collapse repeated whitespace
          - remove common header/footer artifacts
          - normalize line endings
          - strip leading/trailing whitespace
        """
        if not raw:
            return ""

        text = raw

        # Normalize line endings
        text = text.replace("\r\n", "\n").replace("\r", "\n")

        # Remove common header/footer patterns (page numbers, confidential stamps)
        text = re.sub(r"(?i)page\s+\d+\s+of\s+\d+", "", text)
        text = re.sub(r"(?i)confidential", "", text)
        text = re.sub(r"(?i)draft\s*[-–—]?\s*not for distribution", "", text)

        # Collapse 3+ consecutive newlines into 2
        text = re.sub(r"\n{3,}", "\n\n", text)

        # Collapse repeated spaces/tabs within lines
        text = re.sub(r"[ \t]{2,}", " ", text)

        # Strip every line
        text = "\n".join(line.strip() for line in text.split("\n"))

        # Final trim
        return text.strip()

    # ── Document type classification ─────────────────────────────────

    @staticmethod
    def classify_document(filename: str, parent_folder: str = "") -> str:
        """
        Classify a document by filename and optional parent folder name.
        Returns a document type key.
        """
        name = (filename + " " + parent_folder).lower()
        for doc_type, patterns in _TYPE_PATTERNS.items():
            if any(pat in name for pat in patterns):
                return doc_type
        return "unknown"

    # ── Main ingestion API ───────────────────────────────────────────

    def ingest(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Traverse the input directory, extract and clean all documents.

        Returns:
            {
                "protocol": [
                    {"filename": "...", "text": "...", "char_count": int},
                    ...
                ],
                "sap": [...],
                ...
            }
        """
        if not self.input_dir.exists():
            logger.warning("Input directory does not exist: %s", self.input_dir)
            return {}

        result: Dict[str, List[Dict[str, Any]]] = {}

        supported = {".pdf", ".docx", ".doc", ".txt"}
        files = [
            f for f in self.input_dir.rglob("*")
            if f.is_file() and f.suffix.lower() in supported
        ]

        if not files:
            logger.warning("No supported files found in %s", self.input_dir)
            return {}

        for filepath in sorted(files):
            # Parent folder name (for subfolder-based classification)
            parent = filepath.parent.name if filepath.parent != self.input_dir else ""
            doc_type = self.classify_document(filepath.name, parent)

            logger.info("Processing [%s] %s", doc_type, filepath.name)

            raw = self._extract_file(filepath)
            if not raw.strip():
                logger.warning("Empty extraction for %s — skipping", filepath.name)
                continue

            cleaned = self.clean_text(raw)
            if not cleaned:
                continue

            entry = {
                "filename": filepath.name,
                "filepath": str(filepath),
                "text": cleaned,
                "char_count": len(cleaned),
                "doc_type": doc_type,
            }

            result.setdefault(doc_type, []).append(entry)

        total = sum(len(v) for v in result.values())
        logger.info(
            "DocumentNormalizer: ingested %d files across %d types",
            total, len(result),
        )
        return result

    def get_combined_by_type(self) -> Dict[str, str]:
        """
        Convenience method: ingest and return combined text per type.

        Returns:
            {"protocol": "all protocol text...", "sap": "all sap text...", ...}
        """
        ingested = self.ingest()
        combined: Dict[str, str] = {}
        for doc_type, entries in ingested.items():
            texts = [e["text"] for e in entries if e.get("text")]
            combined[doc_type] = "\n\n---\n\n".join(texts)
        return combined
