import json
from typing import Dict, List, Any


from ..cst_patcher import remove_definitions_cst
from ..patcher import apply_patches_robust


from .prompts import (
    build_rewrite_prompt,
    build_patch_prompt,
    build_surgical_create_prompt,
    build_semantic_delete_prompt,
    build_extract_and_modify_prompt
)


from ..ast_patcher import (
    collect_definitions,
    delete_definitions,
    parse_llm_json_list,
    extract_function_source, 
    extract_imports_source,
    inject_import_at_top
)


DELETE_KEYWORDS = ("delete",  "drop", "eliminate")


def _extract_and_modify(self, source_content: str, instruction: Dict, task_history: List[Dict] = None) -> Dict[str, str]:
    """
    Handles atomic EXTRACT_AND_MODIFY action.
    Returns dict: {'source_path': 'content', 'target_path': 'content'}
    """
    source_file = instruction['source_file']
    target_file = instruction['target_file']
    desc = instruction['description']
    
    print(f"\n🔄 [EXTRACT_AND_MODIFY] Atomically processing {source_file} -> {target_file}")
    
    prompt = build_extract_and_modify_prompt(source_content, source_file, target_file, desc, task_history)
    
    # LLM Call (expecting JSON output)
    raw_response = self._call_llm_with_retry(
        prompt, 
        "Output using the <<<<<<< delimiters format.",
        original_code=None,
        validate_syntax=False
    )      

    try:
        # Manual block parsing
        target_marker = "<<<<<<< TARGET_CONTENT"
        mid_marker = "======="
        source_marker = "<<<<<<< SOURCE_CONTENT"
        end_marker = ">>>>>>>"
        
        # 1. Extract TARGET
        t_start = raw_response.find(target_marker)
        t_end = raw_response.find(mid_marker)
        
        if t_start == -1 or t_end == -1:
            raise ValueError("Could not find TARGET_CONTENT block delimiters")
        
        target_content = raw_response[t_start + len(target_marker):t_end].strip()
        
        # 2. Extract SOURCE
        s_start = raw_response.find(source_marker, t_end) # Search AFTER the first block
        s_end = raw_response.find(end_marker, s_start)
        
        if s_start == -1:
            raise ValueError("Could not find SOURCE_CONTENT block start")
        
        # If end marker missing (truncation), try to take everything until end
        if s_end == -1:
            print("⚠️ Warning: Output might be truncated (missing end delimiter). Using remaining text.")
            source_content = raw_response[s_start + len(source_marker):].strip()
        else:
            source_content = raw_response[s_start + len(source_marker):s_end].strip()
        
        # Extra cleanup (remove potential ```python wrappers if LLM put them inside blocks)
        target_content = self._clean_llm_code(target_content)
        source_content = self._clean_llm_code(source_content)
        
        if instruction['source_file'].endswith('.py'):
            try:
                import ast
                ast.parse(source_content)
            except SyntaxError as e:
                print(f"⚠️ Warning: Extracted source content has SyntaxError: {e}")
                # We could decide to fail or accept anyway

        return {
            "target_content": target_content,
            "source_content": source_content
        }
        
    except Exception as e:
        print(f"❌ JSON Parsing failed for EXTRACT_AND_MODIFY: {e}")
        print(f"FULL RESPONSE:\n{raw_response}")
        raise e


def _full_rewrite(self, original: str, instruction: Dict, task_history: List[Dict] = None) -> str:
    """For small files: complete rewrite."""
    prompt = build_rewrite_prompt(original, instruction, task_history)
    # Note: Calling _call_llm_with_retry here, which must exist!
    return self._call_llm_with_retry(prompt, "Output ONLY raw Python code.", original_code=original, validate_syntax=True)


def _patch_large_file(self, original: str, instruction: Dict, task_history: List[Dict] = None) -> str:
    """For files > 600 lines: SEARCH/REPLACE blocks with validation."""
    prompt = build_patch_prompt(original, instruction, task_history)
    # First attempt: Generate patch
    patch = self._call_llm(prompt, "Output ONLY SEARCH/REPLACE blocks.")
    
    # Apply patch
    patched_content = apply_patches_robust(original, patch)
    
    # FINAL SYNTAX VALIDATION
    # If patching broke syntax, ask for FULL REWRITE as fallback
    if not self._validate_syntax(patched_content):
        print("⚠️ Patching created invalid syntax. Falling back to Full Rewrite with Retry.")
        return self._full_rewrite(original, instruction, task_history)
        
    return patched_content


def _surgical_create(self, source_content: str, source: str, target: str, entities: List[str], task_desc: str, task_history: List[Dict] = None) -> str:
    """
    Builds new file assembling real pieces + LLM generated imports.
    Handles both punctual extraction (if entities present) and semantic extraction (if entities empty).
    """
    print(f"\n🔬 [SURGICAL_CREATE] Starting extraction")
    print(f"   📋 Total entities requested: {len(entities)}")
    print(f"   📄 Source content size: {len(source_content)} chars")

    # 1. EXTRACTION LOGIC
    extracted_code = []
    failed_extractions = []
    use_full_source_as_context = False

    if entities:
        print(f"   📝 Entities list: {entities}")
        for idx, entity in enumerate(entities, 1):
            print(f"   [{idx}/{len(entities)}] Extracting '{entity}'...", end=" ")
            code = extract_function_source(source_content, entity)
            if code:
                extracted_code.append(code)
                print(f"✅ ({len(code)} chars)")
            else:
                failed_extractions.append(entity)
                print(f"❌ NOT FOUND")
        
        # If all specific extractions fail, activate fallback to full source
        if not extracted_code and failed_extractions:
            print("   ⚠️ All specific extractions failed. Switching to FULL SOURCE context.")
            use_full_source_as_context = True
    else:
        # No entities specified in plan: fallback to full source
        print("   ⚠️ No specific entities provided. Using FULL SOURCE as context.")
        use_full_source_as_context = True

    # 2. BODY PREPARATION FOR PROMPT
    if use_full_source_as_context:
        # "You extract from here" mode: pass entire file commented or demarcated
        # Add clear header for LLM
        full_body = (
            "# --- FULL SOURCE CODE REFERENCE (EXTRACT NEEDED PARTS FROM HERE) ---\n"
            f"{source_content}\n"
            "# --- END SOURCE REFERENCE ---"
        )
        print(f"   📦 Strategy: Implicit Extraction (Source size: {len(full_body)} chars)")
    else:
        # "Use these snippets" mode: pass only clean code
        full_body = "\n\n".join(extracted_code)
        print(f"   📦 Strategy: Explicit Stitching (Combined size: {len(full_body)} chars)")

    # 3. IMPORTS EXTRACTION (Always useful for context)
    # Needed for LLM to know which libraries were used in original file
    source_imports = extract_imports_source(source_content)
    print(f"   📥 Source imports extracted: {len(source_imports)} chars")

    # 4. LLM CALL
    # Prompt builder (build_surgical_create_prompt) must be updated
    # to accept hybrid instructions (snippet vs full source)
    prompt = build_surgical_create_prompt(source_imports, source, target, full_body, task_desc, task_history)
    
    print(f"\n   🤖 Calling LLM with prompt ({len(prompt)} chars)...")
    
    # Retry policy to ensure valid syntax
    result = self._call_llm_with_retry(prompt, "Output valid Python code.", validate_syntax=True)
    
    print(f"   📤 LLM returned: {len(result)} chars")
    print(f"   🔍 First 200 chars: {result[:200]}")
    
    return result


def _process_change(self, original: str, instruction: Dict, task_history: List[Dict] = None, extraction_map: Dict = None) -> str:
    action = instruction.get("action", "").upper()
    target = instruction.get("target_file", "")
    desc = instruction.get("description", "")
    
    print(f"\n🔧 [PROCESS_CHANGE] Action: {action}, Target: {target}")
    
    # CASE 1: SURGICAL CREATION (Extract)
    if action == "CREATE" and instruction.get("source_file"):
        source_file = instruction["source_file"]
        entities = instruction.get("detected_entities", [])
        
        print(f"   🎯 CREATE from Source detected: {source_file}")
        
        # 1. Load Source
        source_path = self.project_root / source_file
        source_content = ""
        if source_path.exists():
            source_content = source_path.read_text("utf-8")
        else:
            print(f"   ⚠️ Source file {source_file} not found!")

        # 2. Execute Surgical Create (LLM generates new file)
        # Note: Pass source_content even if empty, _surgical_create will handle fallback
        new_content = self._surgical_create(source_content, source_file, target, entities, desc, task_history)

        # 3. AUTO-DISCOVERY FOR MAPPING
        # Analyze what LLM actually put in new file
        try:
            created_symbols = collect_definitions(new_content)
            print(f"   🔍 Discovered new symbols in {target}: {created_symbols}")
        except Exception as e:
            print(f"   ⚠️ Could not parse new content for symbols: {e}")
            created_symbols = []

        # 4. MAPPING UPDATE
        if extraction_map is not None:
            if source_file not in extraction_map:
                extraction_map[source_file] = {"moved_to": [], "symbols": []}
            
            # Register target file
            if target not in extraction_map[source_file]["moved_to"]:
                extraction_map[source_file]["moved_to"].append(target)
            
            # Register discovered symbols (this is the precise mapping needed!)
            for sym in created_symbols:
                if sym not in extraction_map[source_file]["symbols"]:
                    extraction_map[source_file]["symbols"].append(sym)
            
            print(f"   🗺️  Mapped: {source_file} -> {target} (Symbols: {len(created_symbols)})")

        return new_content

    # CASE 2: SURGICAL REMOVAL WITH PROXY (Refactor Move)
    is_delete = "remove" in desc.lower() or "delete" in desc.lower() or "cleanup" in desc.lower()
    
    if action == "MODIFY" and is_delete:
        # Retrieve info from Mapping if available
        mapped_symbols = []
        if extraction_map and target in extraction_map:
            mapped_symbols = extraction_map[target].get("symbols", [])
            print(f"   💡 Context indicates these symbols were moved away: {mapped_symbols}")

        entities = instruction.get("detected_entities", [])
        
        # If planner didn't give entities, but mapping did, use mapping!
        if not entities and mapped_symbols:
            print(f"   🔄 Using Mapped symbols for deletion candidates: {mapped_symbols}")
            entities = mapped_symbols

        if entities:
            print(f"   ✂️ MODIFY with deletion detected: {entities}")
            # Remove definitions
            current_code = remove_definitions_cst(original, entities)
            
            # TODO: Handle Proxy Import if necessary (simplified here)
            return current_code

    if action == "EXTRACT_AND_MODIFY":
        source_file = instruction['source_file']
        target_file = instruction['target_file']
        
        # 1. Determine SOURCE content
        # If 'original' is empty (because target doesn't exist) or doesn't match source
        if not original or target_file in str(instruction.get('target_file')):
            # Must read source file explicitly
            source_path = self.project_root / source_file
            if source_path.exists():
                source_content = source_path.read_text("utf-8")
            else:
                raise FileNotFoundError(f"Source file {source_file} not found for extraction")
        else:
            # If caller passed source already
            source_content = original

        # 2. Call Strategy (LLM generates JSON with both files)
        # result_map = {'target_content': '...', 'source_content': '...'}
        result_map = self._extract_and_modify(source_content, instruction, task_history)

        return {
            instruction['target_file']: result_map["target_content"],
            instruction['source_file']: result_map["source_content"]
        }

    # --- FALLBACK TO LEGACY SYSTEM ---
    print(f"    ⚙️ Using fallback strategy...")
    
    # === FIX: Protection for CREATE ===
    # If action is CREATE, force file generation.
    # Prevent "move" in description from triggering _semantic_delete on a new file.
    if action == "CREATE":
         print(f"    📝 Standard CREATE detected (fallback), generating full content...")
         return self._full_rewrite(original, instruction, task_history)
    # ==================================

    if self._looks_like_delete(instruction):
        print(f"    🗑️ Detected as deletion, using semantic delete")
        return self._semantic_delete(original, instruction, task_history, extraction_map)

    if len(original.splitlines()) > 600:
        print(f"    📄 Large file ({len(original.splitlines())} lines), using patch strategy")
        return self._patch_large_file(original, instruction, task_history)

    print(f"    📝 Small file, using full rewrite")
    return self._full_rewrite(original, instruction, task_history)


def _semantic_delete(self, original: str, instruction: Dict, task_history: List[Dict] = None, extraction_map: Dict = None) -> str:
        """
        Uses AST for surgical deletion.
        If AST fails or produces no changes, fallbacks to full_rewrite.
        """
        if not original.strip():
            return original

        # 1. Extract existing definitions (Ground Truth)
        try:
            entities = collect_definitions(original)
        except SyntaxError:
            print("    ⚠️ Syntax error in source, cannot parse for deletion. Falling back to rewrite.")
            return self._full_rewrite(original, instruction, task_history)

        if not entities:
            print("    ℹ️ No top-level entities found.")
            return original

        target_file = instruction.get("target_file", "")
        moved_symbols = []
        if extraction_map and target_file in extraction_map:
            moved_symbols = extraction_map[target_file].get("symbols", [])

        # 2. Ask LLM to CHOOSE from list
        prompt = build_semantic_delete_prompt(instruction, entities, task_history)
        if moved_symbols:
            prompt += f"\n\nCONTEXT: The following symbols were recently MOVED to other files: {json.dumps(moved_symbols)}. You should probably DELETE them."
                
        raw = self._call_llm(prompt, "Return ONLY a JSON list.")
        names = parse_llm_json_list(raw)

        # 3. WHITELIST: only names that really exist
        valid_names = [n for n in names if n in entities]

        if not valid_names:
            print("    ℹ️ No valid entities selected for deletion.")
            return original

        # 4. EXECUTE AST DELETION
        print(f"    ✂️ Deleting via AST: {', '.join(valid_names)}")
        try:
            # ASSIGNMENT OF RESULT (Missing in original snippet)
            result = delete_definitions(original, valid_names)
            
            # 5. VERIFY IF AST ACTUALLY CHANGED ANYTHING
            if result.strip() == original.strip() and valid_names:
                print("    ⚠️ AST deletion produced no changes (symbols not found). Falling back to LLM rewrite...")
                return self._full_rewrite(original, instruction, task_history)
            
            return result

        except Exception as e:
            print(f"    ❌ AST deletion failed: {e}. Falling back to LLM rewrite...")
            return self._full_rewrite(original, instruction, task_history)
        
def _looks_like_delete(self, instruction: Dict) -> bool:
    """
    Heuristic: looks for deletion keywords, but avoids false positives 
    like 'remove import' or 'move logic' in a modification context.
    """
    desc = instruction.get("description", "").lower()
    action = instruction.get("action", "").upper()
    
    # If action is explicitly DELETE, it's obvious.
    if action == "DELETE":
        return True

    # If action is CREATE, it can never be a deletion
    if action == "CREATE":
        return False
        
    # Strong keywords almost always indicating full file deletion
    strong_keywords = ["delete file", "remove file", "drop file"]
    if any(k in desc for k in strong_keywords):
        return True

    has_delete_keyword = any(k in desc for k in ["delete", "drop", "eliminate"])
    
    # "remove" is ambiguous. Accept only if associated with entities.
    is_remove_entity = "remove" in desc and ("function" in desc or "class" in desc or "method" in desc)
    
    return has_delete_keyword or is_remove_entity
