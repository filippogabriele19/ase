from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass, field

# --- DB DATA STRUCTURES ---

@dataclass
class Symbol:
    """Represents a function, class, or global variable."""
    name: str
    kind: str          # 'FUNCTION', 'CLASS', 'VARIABLE', 'CONST'
    line_start: int
    line_end: int
    docstring: str = "" # Symbol-specific docstring

@dataclass
class Import:
    """Represents a dependency."""
    module: str        # 'numpy', 'utils', 'react'
    alias: Optional[str] = None

@dataclass
class ConfigKey:
    """Represents a configuration key (for JSON/YAML)."""
    key_path: str      # 'scripts.build'
    value_type: str    # 'string', 'int', 'object'

@dataclass
class ParseResult:
    """Standardized parsing result."""
    # Content Metadata
    content_preview: str = ""    # First N characters
    docstring: str = ""          # File/Module level docstring
    lines_count: int = 0
    is_generated: bool = False   # Heuristic detection for minified/generated files

    # Relational Data (Flat lists ready for INSERT)
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[Import] = field(default_factory=list)
    config_keys: List[ConfigKey] = field(default_factory=list)


class LanguageParser(ABC):
    # HARD LIMIT: 1MB. 
    MAX_FILE_SIZE_BYTES = 1 * 1024 * 1024 
    PREVIEW_LENGTH = 500  # Characters to store in DB for preview

    @abstractmethod
    def parse(self, file_path: Path) -> ParseResult:
        """
        Analyzes the file and returns a DB-ready structure.
        Must handle safe reading internally.
        """
        pass

    def _read_content_safely(self, file_path: Path) -> str:
        """Helper to read files respecting the size limit."""
        size = file_path.stat().st_size
        if size > self.MAX_FILE_SIZE_BYTES:
            raise ValueError(f"File too large ({size} bytes)")
        
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    def _generate_preview(self, content: str) -> str:
        """Generates a truncated preview for the DB."""
        if len(content) <= self.PREVIEW_LENGTH:
            return content
        return content[:self.PREVIEW_LENGTH] + "...[TRUNCATED]"
