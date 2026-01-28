import json
import re
import ast
import logging
import sqlite3
from typing import Optional, Dict
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# --- JSON Parsing ---

def safe_json_parse(text: str) -> Optional[Dict]:
    """
    Parses JSON content from an LLM response string.
    
    It handles markdown code blocks (e.g., ```json ... ```) and attempts
    multiple parsing strategies (json.loads, ast.literal_eval) to maximize
    robustness against malformed LLM outputs.

    Args:
        text (str): The raw text response from the LLM.

    Returns:
        Optional[Dict[str, Any]]: The parsed dictionary if successful, None otherwise.
    """

    text = text.strip()
    
    # Extract from markdown
    for pattern in [r'```(?:json)?\s*(\{.*?\})\s*```', r'```(?:json)?\s*(\[.*?\])\s*```']:
        match = re.search(pattern, text, re.DOTALL)
        if match:
            text = match.group(1)
            break
    
    # Try JSON then literal_eval
    for parser in [json.loads, ast.literal_eval]:
        try:
            return parser(text)
        except:
            continue
    
    return None

# --- File Resolution ---

@dataclass
class FileMatch:
    """
    Represents a successful file path resolution.
    
    Attributes:
        file_id (int): The unique identifier of the file in the database.
        path (str): The relative path of the file.
        score (float): A confidence score between 0.0 and 1.0.
        match_type (str): The strategy used (exact, suffix, filename, fuzzy).
    """
    file_id: int
    path: str
    score: float
    match_type: str  # exact, suffix, filename, fuzzy

class FileResolver:
    """
    Resolves ambiguous or partial file paths to concrete database records.
    
    Implements a deterministic scoring system using multiple matching strategies:
    1. Exact match
    2. Suffix match
    3. Filename match
    4. Fuzzy (Levenshtein) match
    """
    
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.logger = logging.getLogger(__name__)
    
    def resolve(self, path_fragment: str) -> Optional[FileMatch]:
        """Resolve file path with multiple strategies."""
        normalized = path_fragment.replace("\\", "/").strip()
        
        strategies = [
            self._exact_match,
            self._suffix_match,
            self._filename_match,
            self._fuzzy_match
        ]
        
        best_match = None
        for strategy in strategies:
            match = strategy(normalized)
            if match and (not best_match or match.score > best_match.score):
                best_match = match
                if match.score >= 0.95:
                    break
        
        if best_match and best_match.score < 0.3:
            self.logger.warning(f"Low confidence match for: {normalized}")
            return None
        
        return best_match
    
    def _exact_match(self, path: str) -> Optional[FileMatch]:
        row = self.conn.execute(
            "SELECT id, path FROM files WHERE path = ?", (path,)
        ).fetchone()
        return FileMatch(row['id'], row['path'], 1.0, 'exact') if row else None
    
    def _suffix_match(self, path: str) -> Optional[FileMatch]:
        rows = self.conn.execute(
            "SELECT id, path FROM files WHERE path LIKE ?", (f"%{path}",)
        ).fetchall()
        if not rows:
            return None
        best = max(rows, key=lambda r: self._path_similarity(path, r['path']))
        sim = self._path_similarity(path, best['path'])
        return FileMatch(best['id'], best['path'], 0.8 * sim, 'suffix')
    
    def _filename_match(self, path: str) -> Optional[FileMatch]:
        filename = path.split("/")[-1]
        rows = self.conn.execute(
            "SELECT id, path FROM files WHERE path LIKE ?", (f"%{filename}",)
        ).fetchall()
        if not rows:
            return None
        path_parts = set(path.split("/"))
        best = max(rows, key=lambda r: len(set(r['path'].split("/")) & path_parts))
        ratio = len(set(best['path'].split("/")) & path_parts) / len(path_parts)
        return FileMatch(best['id'], best['path'], 0.4 * ratio, 'filename')
    
    def _fuzzy_match(self, path: str) -> Optional[FileMatch]:
        all_files = self.conn.execute("SELECT id, path FROM files").fetchall()
        if not all_files:
            return None
        scored = [(f, self._levenshtein_ratio(path, f['path'])) for f in all_files]
        best, score = max(scored, key=lambda x: x[1])
        return FileMatch(best['id'], best['path'], 0.6 * score, 'fuzzy') if score >= 0.5 else None
    
    @staticmethod
    def _path_similarity(p1: str, p2: str) -> float:
        parts1, parts2 = p1.split("/"), p2.split("/")
        common = len(set(parts1) & set(parts2))
        return common / max(len(parts1), len(parts2)) if parts1 or parts2 else 0.0
    
    @staticmethod
    def _levenshtein_ratio(s1: str, s2: str) -> float:
        """
        Calculate a simple similarity ratio (Jaccard-like index on characters).
        Note: Keeps original logic as requested, despite function name.
        """
        if not s1 or not s2:
            return 0.0
        if s1 in s2 or s2 in s1:
            return max(len(s1), len(s2)) / max(len(s1), len(s2), 1)
        return len(set(s1) & set(s2)) / max(len(set(s1)), len(set(s2)))
