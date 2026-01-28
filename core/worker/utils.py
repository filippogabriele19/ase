import ast
from typing import List


def _clean_llm_code(self, raw_code: str) -> str:
    """Removes markdown fences and extraneous text."""
    if not isinstance(raw_code, str):
        return str(raw_code)
        
    raw_code = raw_code.strip()
    
    # Remove leading ```python or ```
    if raw_code.startswith("```"):
        lines = raw_code.splitlines()
        # Remove first line if it's a fence
        if lines and lines.startswith("```"):
            lines = lines[1:]
        # Remove last line if it's a fence
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        raw_code = "\n".join(lines)
        
    return raw_code.strip()


def _validate_syntax(self, code: str) -> bool:
    """Verifies that Python code is syntactically valid."""
    try:
        ast.parse(code)
        return True
    except SyntaxError:
        return False
        
def _is_suspicious(self, original: str, proposed: str) -> bool:
    """Safety heuristics to prevent code truncation."""
    if not original:
        return False
    # For DELETE actions, significant reduction is expected
    if len(proposed) < len(original) * 0.3 and len(original) > 500:
        return True
    if "As an AI" in proposed or "I cannot" in proposed:
        return True
    return False


def _format_import(self, module: str, entities: List[str]) -> str:
    """Formats import statement aesthetically (single-line if short, multi-line if long)."""
    if not entities: 
        return ""
        
    # Sort alphabetically for cleanliness
    entities = sorted(list(set(entities))) # Remove duplicates and sort
    
    # Attempt 1: Single line
    single_line = f"from {module} import {', '.join(entities)}"
    if len(single_line) <= 80:
        return single_line
        
    # Attempt 2: Multi-line (Parentheses)
    # from module import (
    #     Entity1,
    #     Entity2,
    # )
    lines = [f"from {module} import ("]
    for e in entities:
        lines.append(f"    {e},")
    lines.append(")")
    return "\n".join(lines)


def build_import_statement_code(self, entities: List[str], source_file: str, target_file: str) -> str:
    """
    Constructs the import statement deterministically by calculating the relative path.
    """
    # Normalize paths
    src_parts = source_file.replace("\\", "/").split("/")
    tgt_parts = target_file.replace("\\", "/").split("/")
    
    # Source directory (where we are)
    src_dir = src_parts[:-1]
    
    # Find common path
    common_len = 0
    min_len = min(len(src_dir), len(tgt_parts) - 1)
    for i in range(min_len):
        if src_dir[i] == tgt_parts[i]:
            common_len += 1
        else:
            break
            
    # Calculate levels to go up
    up_levels = len(src_dir) - common_len
    
    # Calculate descending path to target
    # Note: tgt_parts[-1] is the file.py, handled separately
    down_path_parts = tgt_parts[common_len:-1]
    target_filename = tgt_parts[-1]
    
    # Remove .py extension from filename
    target_module_name = target_filename
    if target_module_name.endswith(".py"):
        target_module_name = target_module_name[:-3]
        
    # Build module string
    module_path = ""
    
    if up_levels == 0:
        # Same folder or subfolder
        module_path = "."
    else:
        # Go up (.. for parent, ... for grandparent)
        # Recall: . = current, .. = parent
        module_path = "." * (up_levels + 1)
        
    # Add descending parts
    if down_path_parts:
        module_path += ".".join(down_path_parts) + "."
        
    module_path += target_module_name
    
    # Delegate formatting to _format_import for consistency
    return self._format_import(module_path, entities)
