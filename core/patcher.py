import re
import os
import shutil
from typing import Optional
from pathlib import Path


# Configuration for temporary artifacts
TEMP_ARTIFACTS_DIR = ".temp_artifacts"
CLEANUP_PREVIOUS_LOOPS = True


def ensure_temp_artifacts_dir():
    """Ensure the temporary artifacts directory exists."""
    Path(TEMP_ARTIFACTS_DIR).mkdir(exist_ok=True)


def save_temp_artifact(content: str, filename: str, loop_count: int) -> str:
    """
    Save temporary artifact with loop number in filename.
    
    Args:
        content: File content to save
        filename: Original filename
        loop_count: Current loop number
        
    Returns:
        Path to saved file
    """
    ensure_temp_artifacts_dir()
    
    # Generate loop-prefixed filename
    name_parts = filename.rsplit('.', 1)
    if len(name_parts) == 2:
        base_name, ext = name_parts
        temp_filename = f"loop_{loop_count}_{base_name}.{ext}"
    else:
        temp_filename = f"loop_{loop_count}_{filename}"
    
    temp_path = os.path.join(TEMP_ARTIFACTS_DIR, temp_filename)
    
    with open(temp_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return temp_path


def load_temp_artifact(filename: str, loop_count: int) -> Optional[str]:
    """
    Load temporary artifact from previous loop.
    
    Args:
        filename: Original filename
        loop_count: Loop number to load from
        
    Returns:
        File content or None if not found
    """
    name_parts = filename.rsplit('.', 1)
    if len(name_parts) == 2:
        base_name, ext = name_parts
        temp_filename = f"loop_{loop_count}_{base_name}.{ext}"
    else:
        temp_filename = f"loop_{loop_count}_{filename}"
    
    temp_path = os.path.join(TEMP_ARTIFACTS_DIR, temp_filename)
    
    if os.path.exists(temp_path):
        with open(temp_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    return None


def cleanup_loop_artifacts(loop_count: int) -> None:
    """
    Clean up temporary artifacts from a specific loop.
    
    Args:
        loop_count: Loop number to clean up
    """
    if not os.path.exists(TEMP_ARTIFACTS_DIR):
        return
    
    for filename in os.listdir(TEMP_ARTIFACTS_DIR):
        if filename.startswith(f"loop_{loop_count}_"):
            file_path = os.path.join(TEMP_ARTIFACTS_DIR, filename)
            try:
                if os.path.isfile(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"⚠️ Failed to delete {file_path}: {e}")


def cleanup_previous_loop_artifacts(current_loop: int) -> None:
    """
    Clean up temporary artifacts from the previous loop.
    
    Args:
        current_loop: Current loop number (will clean up current_loop - 1)
    """
    if current_loop > 1:
        cleanup_loop_artifacts(current_loop - 1)


def cleanup_all_artifacts() -> None:
    """Clean up all temporary artifacts directory."""
    if os.path.exists(TEMP_ARTIFACTS_DIR):
        try:
            shutil.rmtree(TEMP_ARTIFACTS_DIR)
        except Exception as e:
            print(f"⚠️ Failed to clean up {TEMP_ARTIFACTS_DIR}: {e}")


def apply_patches_robust(original_code: str, patch_text: str, loop_count: int = 1, save_artifacts: bool = True) -> str:
    """
    Apply SEARCH/REPLACE blocks with whitespace tolerance and Smart Delete support.
    
    Uses three matching strategies in order:
    1. Smart Delete: Handles <ELLIPSIS> markers to delete entire blocks based on indentation
    2. Exact Match: Direct string replacement when search block matches exactly
    3. Soft Match: Line-by-line matching ignoring leading/trailing whitespace
    
    Args:
        original_code: Original code to patch
        patch_text: Patch text containing SEARCH/REPLACE blocks
        loop_count: Current loop number for artifact naming
        save_artifacts: Whether to save temporary artifacts
        
    Returns:
        Modified code with all applicable patches applied
        
    Raises:
        ValueError: If no patches could be applied when patches were present
    """
    if "```" in patch_text:
        patch_text = patch_text.split("```")[1]
        
    blocks = re.split(r'<<<<<<< SEARCH\n', patch_text)
    modified_code = original_code
    applied_count = 0
    
    for block in blocks[1:]: 
        try:
            if '=======\n' not in block or '>>>>>>>' not in block:
                continue
                
            search_block, rest = block.split('\n=======\n', 1)
            replace_block, _ = rest.split('\n>>>>>>>', 1)
            
            search_block = search_block.strip('\n')
            replace_block = replace_block.strip('\n')
            
            # Strategy 1: Smart Delete with <ELLIPSIS> marker
            if "<ELLIPSIS>" in search_block:
                signature = search_block.replace("<ELLIPSIS>", "").strip()
                start_idx = modified_code.find(signature)
                
                if start_idx != -1:
                    line_start = modified_code.rfind('\n', 0, start_idx) + 1
                    line_end = modified_code.find('\n', start_idx)
                    if line_end == -1: line_end = len(modified_code)
                    
                    # Calculate target indentation level
                    target_indent = 0
                    for char in modified_code[line_start:start_idx]:
                        if char == ' ': target_indent += 1
                        elif char == '\t': target_indent += 4
                    
                    # Find end of block based on indentation
                    curr_pos = line_end + 1
                    while curr_pos < len(modified_code):
                        next_line_end = modified_code.find('\n', curr_pos)
                        if next_line_end == -1: next_line_end = len(modified_code)
                        line_content = modified_code[curr_pos:next_line_end]
                        
                        if not line_content.strip():
                            curr_pos = next_line_end + 1
                            continue
                            
                        current_indent = 0
                        for char in line_content:
                            if char == ' ': current_indent += 1
                            elif char == '\t': current_indent += 4
                            else: break
                        
                        if current_indent <= target_indent:
                            break
                        curr_pos = next_line_end + 1
                    
                    # Apply replacement
                    modified_code = modified_code[:line_start] + replace_block + modified_code[curr_pos:]
                    applied_count += 1
                    continue
                else:
                    print(f"⚠️ Smart Delete failed: Signature not found '{signature}'")
                    continue

            # Strategy 2: Exact match
            if search_block in modified_code:
                modified_code = modified_code.replace(search_block, replace_block, 1)
                applied_count += 1
                continue
                
            # Strategy 3: Soft match (whitespace-insensitive)
            soft_result = _apply_soft_match(modified_code, search_block, replace_block)
            if soft_result:
                modified_code = soft_result
                applied_count += 1
                continue

            print(f"⚠️ Patch failed (No match found):\n{search_block[:50]}...")
            
        except ValueError:
            continue

    if applied_count == 0 and len(blocks) > 1:
        raise ValueError("Failed to apply patches: No blocks matched.")
    
    # Save artifacts and cleanup previous loop if configured
    if save_artifacts:
        if CLEANUP_PREVIOUS_LOOPS:
            cleanup_previous_loop_artifacts(loop_count)
        
    return modified_code


def _apply_soft_match(full_text: str, search: str, replace: str) -> Optional[str]:
    """
    Attempt to match and replace code blocks ignoring leading/trailing whitespace.
    
    Compares lines after stripping whitespace, useful when indentation differs
    slightly between the search block and actual code.
    
    Args:
        full_text: Complete text to search within
        search: Search pattern to find
        replace: Replacement text
        
    Returns:
        Modified text if match found, None otherwise
    """
    search_lines = [l.strip() for l in search.splitlines() if l.strip()]
    text_lines = full_text.splitlines()
    
    if not search_lines: 
        return None
    
    for i in range(len(text_lines) - len(search_lines) + 1):
        match = True
        for j, s_line in enumerate(search_lines):
            if text_lines[i + j].strip() != s_line:
                match = False
                break
        
        if match:
            pre_text = "\n".join(text_lines[:i])
            post_text = "\n".join(text_lines[i + len(search_lines):])
            return f"{pre_text}\n{replace}\n{post_text}"

    return None
