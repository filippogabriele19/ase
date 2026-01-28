# core/worker/prompts.py
import json
from pathlib import Path
from typing import Dict, Any, List, Optional

def _render_task_history(history: Optional[List[Dict]]) -> str:
    if not history:
        return ""
    
    lines = ["\nCONTEXT - PREVIOUSLY COMPLETED TASKS:"]
    for task in history:
        desc = task.get("desc", "").split("\n")[0][:100] # Prendi solo la prima riga, max 100 char
        lines.append(f"- [{task.get('action', 'UNKNOWN')}] {task.get('file', 'unknown')}: {desc}")
    
    return "\n".join(lines) + "\n"

def build_rewrite_prompt(original: str, instruction: Dict[str, Any], task_history: Optional[List[Dict]] = None) -> str:
    context = _render_task_history(task_history)
    return f"""
{context}
Apply the following change to the code.

ORIGINAL CODE:
{original}

CHANGE INSTRUCTION:
{json.dumps(instruction, indent=2)}

RULES:
- Return ONLY the full modified file content
- No markdown fences
- No explanations
- Preserve style and formatting
"""

def build_patch_prompt(original: str, instruction: Dict[str, Any], task_history: Optional[List[Dict]] = None) -> str:
    context = _render_task_history(task_history)
    return f"""
You are ASE Worker.
{context}
Return ONLY SEARCH/REPLACE blocks for changes.

FORMAT:
<<<<<<< SEARCH
(exact lines to match)
=======
(replacement lines)
>>>>>>>

ORIGINAL CODE:
{original}

CHANGE INSTRUCTION:
{json.dumps(instruction, indent=2)}
"""

def build_surgical_create_prompt(source_imports: str, source_file: str,target_file: str,full_body: str, task_desc: str, task_history: Optional[List[Dict]] = None) -> str:
    src_ext = Path(source_file).suffix.lower() or ".txt"
    tgt_ext = Path(target_file).suffix.lower() or ".txt"
    tgt_upper = tgt_ext[1:].upper() if tgt_ext.startswith('.') else tgt_upper.upper()
    
    context = _render_task_history(task_history)
    
    imports_block = ""
    if source_imports:
        imports_block = f"SOURCE IMPORTS/HEADERS (Reference):\n{source_imports}\n"

    is_code_target = tgt_ext in ['.py', '.js', '.ts', '.go', '.c', '.cpp', '.java']
    if is_code_target:
        format_rule = f"Output VALID {tgt_upper} code. Include necessary imports/dependencies for the snippet to be functional."
    else:
        format_rule = f"Output RAW {tgt_upper} content. Do NOT include any wrapper syntax from the source format (no quotes, no variable assignments, no escape characters)."

    return f"""
### ROLE
You are a specialized code refactoring engine. Your goal is to move information from a SOURCE format to a TARGET format.

### CONTEXT
{context}
- SOURCE FILE: {source_file} (Format: {src_ext})
- TARGET FILE: {target_file} (Format: {tgt_ext})

### SOURCE CONTENT REFERENCE
---
{full_body}
---
{imports_block}

### TASK
{task_desc}

### CRITICAL EXTRACTION RULES
1. **Unwrap Content**: If you are extracting data from a string literal, a constant, or a template block within the source, REMOVE all source-specific delimiters (like Python's triple quotes, JS backticks, or JSON keys).
2. **Format Adaptation**: Ensure the output strictly follows the {tgt_ext} syntax. 
3. **No Metadata**: {format_rule}
4. **Clean Output**: Return ONLY the file content. No markdown fences (```), no introductory text, no explanations.

### EXECUTION
Analyze the SOURCE CONTENT, find the information required by the TASK, and generate the FULL content for {target_file}:
"""

def build_semantic_delete_prompt(instruction: Dict[str, Any], entities: List[str], task_history: Optional[List[Dict]] = None) -> str:
    """Prompt per cancellazione semantica - chiede all'LLM di scegliere dalla lista."""
    context = _render_task_history(task_history)
    return f"""
TASK:
{json.dumps(instruction, indent=2)}

{context}

AVAILABLE ENTITIES (functions/classes in this file):
{json.dumps(sorted(entities))}

Return ONLY a JSON list of names to DELETE from the available list.
Return [] if none should be deleted.
Example: ["parse_iso8601", "OldClass"]
"""


def build_extract_and_modify_prompt(source_content: str, source_file: str, target_file: str, task_desc: str, task_history: Optional[List[Dict]] = None) -> str:
    context = _render_task_history(task_history)
    return f"""
{context}

### TASK: EXTRACT AND MODIFY
You must extract code from a source file into a new target file, and update the source file to use the extracted code.

SOURCE FILE: {source_file}
TARGET FILE: {target_file}

DESCRIPTION:
{task_desc}

### SOURCE CONTENT:
{source_content}

### OUTPUT FORMAT
Do NOT return JSON. Use the following specific delimiter format:

<<<<<<< TARGET_CONTENT
[Put the FULL content of the NEW target file here]
=======
<<<<<<< SOURCE_CONTENT
[Put the FULL content of the MODIFIED source file here]
>>>>>>>

### CRITICAL RULES:
1. **Target File**: Should contain ONLY the extracted logic.
2. **Source File**: Must be the FULL file content (imports + remaining code), not just a diff.

3. **TEMPLATE CONSISTENCY (VERY IMPORTANT)**:
   - If extracting an HTML template, check how the source file loads it.
   - If source uses `string.Template` or `f-strings`, the target HTML MUST use `$variable` syntax accordingly.
   - If source uses `jinja2`, the target HTML MUST use `{{{{ variable }}}}` syntax.
   - **DO NOT MIX SYNTAXES.** If you write Python code using `Template(html).substitute(title=...)`, your HTML MUST have `$title`.

4. **Delimiters**: Ensure the delimiters `<<<<<<< TARGET_CONTENT`, `=======`, `<<<<<<< SOURCE_CONTENT`, and `>>>>>>>` appear exactly as shown.
"""
