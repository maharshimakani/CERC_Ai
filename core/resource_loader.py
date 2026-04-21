"""
Resource Loader
───────────────
Loads templates from resources/templates/ and examples from resources/examples/.
Handles missing files gracefully — never crashes the pipeline.

This module is ADDITIVE and does not touch any existing code.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# Default directories (relative to project root)
_PROJECT_ROOT = Path(__file__).parent.parent
_DEFAULT_TEMPLATES_DIR = _PROJECT_ROOT / "resources" / "templates"
_DEFAULT_EXAMPLES_DIR = _PROJECT_ROOT / "resources" / "examples"


class ResourceLoader:
    """Loads template structures and exemplar style references for CSR sections."""

    def __init__(
        self,
        templates_dir: Optional[Path] = None,
        examples_dir: Optional[Path] = None,
    ):
        self.templates_dir = Path(templates_dir or _DEFAULT_TEMPLATES_DIR)
        self.examples_dir = Path(examples_dir or _DEFAULT_EXAMPLES_DIR)

    # ── Private helpers ──────────────────────────────────────────────

    @staticmethod
    def _read_file(path: Path) -> Optional[str]:
        """Read a text file, returning None if missing / unreadable."""
        if not path.exists():
            logger.debug("Resource not found: %s", path)
            return None
        try:
            return path.read_text(encoding="utf-8").strip() or None
        except OSError as exc:
            logger.warning("Could not read %s: %s", path, exc)
            return None

    # ── Public API ───────────────────────────────────────────────────

    def load_template(self, filename: str) -> Optional[str]:
        """
        Load a template file from resources/templates/.

        Args:
            filename: e.g. "synopsis.txt"

        Returns:
            Template content string, or None if missing.
        """
        if not filename:
            return None
        return self._read_file(self.templates_dir / filename)

    def load_example(self, filename: str) -> Optional[str]:
        """
        Load an example file from resources/examples/.

        Args:
            filename: e.g. "synopsis_example.txt"

        Returns:
            Example content string, or None if missing.
        """
        if not filename:
            return None
        return self._read_file(self.examples_dir / filename)

    def has_template(self, filename: str) -> bool:
        """Check if a template file exists."""
        if not filename:
            return False
        return (self.templates_dir / filename).exists()

    def has_example(self, filename: str) -> bool:
        """Check if an example file exists."""
        if not filename:
            return False
        return (self.examples_dir / filename).exists()

    def list_templates(self) -> list[str]:
        """List all template filenames available."""
        if not self.templates_dir.exists():
            return []
        return sorted(f.name for f in self.templates_dir.iterdir() if f.is_file())

    def list_examples(self) -> list[str]:
        """List all example filenames available."""
        if not self.examples_dir.exists():
            return []
        return sorted(f.name for f in self.examples_dir.iterdir() if f.is_file())
