from __future__ import annotations

import ast
import json
import re
from typing import Iterable, List, Set, Tuple, Optional


class ASTPatchError(RuntimeError):
    """Custom exception for AST patching operations."""
    pass


# -----------------------------
# LLM OUTPUT PARSING (ROBUST)
# -----------------------------


_JSON_BLOCK_RE = re.compile(
    r"```(?:json)?\s*(.*?)\s*```",
    re.DOTALL | re.IGNORECASE,
)


def parse_llm_json_list(raw: str) -> List[str]:
    """
    Parse a JSON list returned by an LLM.
    
    Accepts multiple formats:
      - Pure JSON array
      - JSON fenced in markdown code blocks (```json [...] ```)
      - JSON embedded within text
    
    Args:
        raw: Raw LLM output string
    
    Returns:
        Parsed list of strings, or empty list if parsing fails
    """
    if not raw or not raw.strip():
        return []

    candidates: List[str] = []

    # 1. Extract fenced code blocks
    for match in _JSON_BLOCK_RE.findall(raw):
        candidates.append(match.strip())

    # 2. Extract JSON list patterns from text
    # Look for [...] patterns that might be JSON lists
    json_pattern = re.compile(r'\[\s*(?:"[^"]*"(?:\s*,\s*"[^"]*")*)\s*\]', re.DOTALL)
    for match in json_pattern.findall(raw):
        candidates.append(match.strip())

    # 3. Try raw text as fallback
    candidates.append(raw.strip())

    for candidate in candidates:
        try:
            data = json.loads(candidate)
            if isinstance(data, list) and all(isinstance(x, str) for x in data):
                return data
        except json.JSONDecodeError:
            continue

    return []


# -----------------------------
# AST ANALYSIS
# -----------------------------


class DefinitionCollector(ast.NodeVisitor):
    """Collects all function and class definition names from an AST."""
    
    def __init__(self) -> None:
        self.definitions: Set[str] = set()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self.definitions.add(node.name)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.definitions.add(node.name)
        self.generic_visit(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.definitions.add(node.name)
        self.generic_visit(node)


def collect_definitions(source: str) -> Set[str]:
    """
    Collect all top-level function and class names from source code.
    
    Args:
        source: Python source code string
        
    Returns:
        Set of definition names
    """
    tree = ast.parse(source)
    collector = DefinitionCollector()
    collector.visit(tree)
    return collector.definitions


# -----------------------------
# AST PATCHING
# -----------------------------


class DeletionTransformer(ast.NodeTransformer):
    """Transformer that removes specific function and class definitions by name."""
    
    def __init__(self, to_delete: Iterable[str]) -> None:
        self.to_delete = set(to_delete)

    def visit_FunctionDef(self, node):
        if node.name in self.to_delete:
            return None
        return self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node):
        if node.name in self.to_delete:
            return None
        return self.generic_visit(node)

    def visit_ClassDef(self, node):
        if node.name in self.to_delete:
            return None
        return self.generic_visit(node)


def delete_definitions(source: str, names: Iterable[str]) -> str:
    """
    Remove functions or classes by name from source code.
    
    Args:
        source: Original Python source code
        names: Iterable of function/class names to remove
        
    Returns:
        Modified source code. If no matches found, returns source unchanged.
    """
    if not names:
        return source

    tree = ast.parse(source)
    transformer = DeletionTransformer(names)
    new_tree = transformer.visit(tree)
    ast.fix_missing_locations(new_tree)

    return ast.unparse(new_tree)


def extract_function_source(source_code: str, func_name: str) -> Optional[str]:
    """
    Extract the exact source code of a function or class by name.
    
    Uses ast.get_source_segment (Python 3.8+) for byte-level precision.
    Includes decorators if present.
    
    Args:
        source_code: Full source code string
        func_name: Name of the function or class to extract
        
    Returns:
        Source code of the definition, or None if not found
    """
    try:
        tree = ast.parse(source_code)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == func_name:
                    # Determine start line, including decorators
                    start_line = node.lineno
                    if hasattr(node, 'decorator_list') and node.decorator_list:
                        # If decorators exist, use the first decorator's line
                        first_decorator = node.decorator_list[0]
                        if hasattr(first_decorator, 'lineno'):
                            start_line = first_decorator.lineno
                    
                    # Extract lines from source
                    lines = source_code.splitlines(keepends=True)
                    end_line = node.end_lineno if hasattr(node, 'end_lineno') else node.lineno
                    
                    if start_line and end_line:
                        extracted = "".join(lines[start_line - 1:end_line])
                        return extracted
                    else:
                        # Fallback to ast.get_source_segment if line numbers unavailable
                        return ast.get_source_segment(source_code, node)
    except Exception:
        return None
    return None


def extract_imports_source(source_code: str) -> str:
    """
    Extract ONLY import lines from source code.
    
    Useful for providing LLM context about available libraries.
    
    Args:
        source_code: Full Python source code
        
    Returns:
        String containing all import statements, one per line
    """
    try:
        tree = ast.parse(source_code)
        imports = []
        for node in tree.body:
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                segment = ast.get_source_segment(source_code, node)
                if segment:
                    imports.append(segment)
        return "\n".join(imports)
    except Exception:
        return ""


def inject_import_at_top(source_code: str, new_import_code: str) -> str:
    """
    Insert a new import at the correct position in the file.
    
    Insertion strategy:
    1. After any header comments or shebang
    2. After __future__ imports
    3. At the end of the existing import block
    
    Args:
        source_code: Original source code
        new_import_code: Import statement(s) to inject
        
    Returns:
        Modified source code with import injected
    """
    if not new_import_code.strip():
        return source_code

    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        # Fallback if code is broken: insert at top
        return new_import_code + "\n" + source_code

    lines = source_code.splitlines()
    insert_line_index = 0
    
    # Find the last existing import
    last_import_line = 0
    has_imports = False
    
    for node in tree.body:
        # Skip docstrings and initial string expressions
        if isinstance(node, ast.Expr) and isinstance(node.value, (ast.Str, ast.Constant)):
            continue
            
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            has_imports = True
            # node.end_lineno exists in Python 3.8+
            if hasattr(node, 'end_lineno') and node.end_lineno:
                last_import_line = max(last_import_line, node.end_lineno)
            else:
                last_import_line = max(last_import_line, node.lineno)
        else:
            # Once we encounter non-import code after imports, stop
            if has_imports:
                break
    
    # Insertion logic
    if last_import_line > 0:
        insert_line_index = last_import_line
    else:
        # No imports found. Skip shebang and docstrings.
        # Simple heuristic: skip lines starting with # or empty lines or strings
        for i, line in enumerate(lines):
            l = line.strip()
            if not l: continue
            if l.startswith("#"): continue
            if l.startswith('"""') or l.startswith("'''"): 
                # Skip multiline comments (basic check)
                continue 
            # Found real code
            insert_line_index = i
            break
            
    # Perform insertion
    new_lines = new_import_code.strip().splitlines()
    
    final_lines = lines[:insert_line_index] + new_lines + lines[insert_line_index:]
    
    return "\n".join(final_lines)
