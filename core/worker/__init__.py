import json
import os
import ast
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List

from llm.base import BaseLLMProvider  # For type hinting
from llm.factory import LLMFactory    # For fallback

from ..safety import SafetyManager
from .utils import (
    _clean_llm_code, _validate_syntax, _is_suspicious,
    _format_import, build_import_statement_code
)
from .strategies import (
    _full_rewrite, _patch_large_file, _surgical_create,
    _process_change, _semantic_delete, _looks_like_delete,
    _extract_and_modify  
)

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, project_root: Path, llm_provider: Optional[BaseLLMProvider] = None):
        self.project_root = Path(project_root).resolve()
        self.safety = SafetyManager(self.project_root)
        self.stage_dir = self.project_root / ".ase" / "stage"
        self.stage_dir.mkdir(parents=True, exist_ok=True)
        self.logger = logger
        
        # Dependency Injection or Fallback
        if llm_provider:
            self.llm_client = llm_provider
        else:
            # Legacy fallback for backward compatibility
            self.llm_client = LLMFactory.get_provider("anthropic")
        
        self.current_plan = None
        self.task_history: List[Dict] = []
        self.extraction_map: Dict[str, Dict] = {}


    # --- STRATEGY BINDING (unchanged) ---
    _full_rewrite = _full_rewrite
    _patch_large_file = _patch_large_file
    _surgical_create = _surgical_create
    _process_change = _process_change
    _semantic_delete = _semantic_delete
    _looks_like_delete = _looks_like_delete
    _extract_and_modify = _extract_and_modify


    # --- UTILITY BINDING ---
    _clean_llm_code = _clean_llm_code
    _validate_syntax = _validate_syntax
    _is_suspicious = _is_suspicious
    _format_import = _format_import
    _build_import_statement_code = build_import_statement_code


    # =========================================================
    # LLM METHODS
    # =========================================================


    def _call_llm(self, user_prompt: str, system_prompt: str) -> str:
        """LLM wrapper with error handling and type safety."""
        # MODIFIED to use self.llm_client.generate_response
        try:
            raw = self.llm_client.generate_response(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.0
            )
        except Exception as e:
            raise RuntimeError(f"LLM Provider Error: {e}")
        
        # 🛡️ SAFETY CHECK (Handle dirty outputs)
        if isinstance(raw, list):
            if not raw: return ""
            if all(isinstance(x, str) for x in raw):
                raw = "".join(raw)
            else:
                raw = str(raw[0])

        if not isinstance(raw, str):
            raw = str(raw)

        if raw.startswith("❌"):
            raise RuntimeError(raw)
            
        return raw.strip()


    def _call_llm_with_retry(self, user_prompt: str, system_prompt: str, original_code: str = None, validate_syntax: bool = True) -> str:
        """
        Calls the LLM and automatically retries if generated code is broken,
        passing the error back to the LLM.
        """
        for attempt in range(3): # 3 attempts max
            # 1. Call LLM
            raw = self._call_llm(user_prompt, system_prompt)
            
            # 2. Clean Markdown
            raw = self._clean_llm_code(raw)

            # 3. Syntax Check (only if requested)
            if not validate_syntax:
                return raw
                
            # Improved heuristic:
            # - If original_code is None, DO NOT assume Python just because "def" is present.
            # - If output contains custom delimiters (<<<<), it is NOT pure Python.
            contains_delimiters = "<<<<<<<" in raw
            looks_like_python = (original_code and "def " in original_code)
            
            # Validate ONLY if:
            # 1. Explicitly requested (validate_syntax=True by default)
            # 2. DOES NOT contain merge/diff delimiters (which break AST)
            # 3. Looks like Python from original context OR starts unequivocally
            should_validate = (not contains_delimiters) and (looks_like_python or raw.startswith("import ") or raw.startswith("from "))

            if should_validate:
                try:
                    ast.parse(raw)
                    return raw # Syntax OK
                except SyntaxError as e:
                    # Log for debug
                    # print("====="*60)
                    # print(f"FAILED CODE PREVIEW:\n{raw[:500]}...")
                    print(f"   ⚠️ Syntax Error in LLM draft (Attempt {attempt+1}): {e}")
                    
                    user_prompt += f"\n\nERROR: Your previous code had a SyntaxError: {e}\nFix it and return the full valid code."
            else:
                return raw # Not pure Python or validation not required

        raise RuntimeError("LLM failed to generate valid syntax after 3 attempts.")


    # =========================================================
    # PUBLIC ENTRY (Pipeline with Cache)
    # =========================================================


    def create_diff_draft(self, plan_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Sequential pipeline: accumulates changes per file before writing.
        Supports multi-file changes (EXTRACT_AND_MODIFY).
        """
        plan = self._load_plan(custom_path=plan_path)
        
        if not plan:
            return {"success": False, "error": "No plan found"}

        self.current_plan = plan

        changes = plan.get("implementation_plan", {}).get("changes", [])
        total = len(changes)
        
        self.task_history = []
        self.extraction_map = {}
        
        stats = {"total": total, "drafted": 0, "failed": 0, "details": []}

        print(f"\n🔨 Starting execution of {total} tasks...\n")
        
        # CACHE: working[file_path] = current_content
        working: Dict[str, str] = {}

        for idx, change in enumerate(changes, 1):
            target_rel = change.get("file") or change.get("target_file")
            abs_target = self.project_root / target_rel
            
            print(f"[{idx}/{total}] 🛠️ Processing {target_rel}...")

            try:
                # 1. GET BASE CONTENT (Hierarchy: Memory -> Stage -> Disk)
                if target_rel in working:
                    original = working[target_rel]
                    print(f"    📝 Using cached version (in-memory)")
                
                else:
                    # CHECK STAGE (Crucial for Iterative Loops)
                    # Check if a 'staged' version exists from a previous loop
                    # but hasn't been applied to disk yet.
                    staged_path = self.stage_dir / target_rel
                    
                    if staged_path.exists():
                        original = staged_path.read_text(encoding="utf-8")
                        print(f"    📝 Using STAGED version (from previous loop)")
                        # Load into working for consistency
                        working[target_rel] = original
                        
                    elif abs_target.exists():
                        original = abs_target.read_text(encoding="utf-8")
                        # print(f"    📄 Using DISK version")
                    else:
                        original = ""
                        # print(f"    ✨ New file (empty content)")


                # 2. APPLY CHANGE (passing Context)
                # result can be a string (target content) or a dict {path: content}
                result = self._process_change(
                    original, 
                    change, 
                    task_history=self.task_history,
                    extraction_map=self.extraction_map
                )

                # 3. NORMALIZE RESULT
                files_to_update = {}
                
                if isinstance(result, dict) and not isinstance(result, str):
                    # Multi-file Case (EXTRACT_AND_MODIFY)
                    files_to_update = result
                    print(f"   🔄 Multi-file update received: {list(files_to_update.keys())}")
                else:
                    # Single-file Case (Standard)
                    files_to_update = {target_rel: result}

                # 4. UPDATE CACHE FOR ALL INVOLVED FILES
                for path, content in files_to_update.items():
                    # Quick safety check (optional)
                    if self._is_suspicious("", content): # "" because we don't have original for all files here
                         print(f"   ⚠️ Suspicious content generated for {path}, check manually.")
                    
                    working[path] = content
                    print(f"   ✅ Staged {path} in memory.")

                stats["drafted"] += 1
                stats["details"].append({"file": target_rel, "status": "staged"})
                
                # 5. UPDATE TASK HISTORY
                self.task_history.append({
                    "action": change.get("action", "UNKNOWN"),
                    "file": target_rel,
                    "desc": change.get("description", "")
                })

                # --- LOG CONTEXT SNAPSHOT ---
                self._print_context_snapshot()

            except Exception as e:
                stats["failed"] += 1
                stats["details"].append({
                    "file": target_rel,
                    "status": "error",
                    "message": str(e)
                })
                print(f"   ❌ Failed: {e}")

        # 6. FINAL WRITE (Once per file)
        print(f"\n💾 Writing {len(working)} files to stage...")
        for target_rel, content in working.items():
            stage_file = self.stage_dir / target_rel
            stage_file.parent.mkdir(parents=True, exist_ok=True)
            stage_file.write_text(content, encoding="utf-8")
            print(f"   ✍️ {target_rel}")

        # Summary of Context
        print(f"\n📊 Context Summary:")
        print(f"   - History: {len(self.task_history)} tasks completed")
        print(f"   - Extractions: {len(self.extraction_map)} source files processed")

        return stats


    def _print_context_snapshot(self):
        """Prints a visual summary of the Worker state."""
        print(f"\n   🧠 [CONTEXT SNAPSHOT]")
        # Print compact history (last 3 tasks)
        history_len = len(self.task_history)
        print(f"      History ({history_len} tasks completed):")
        start_idx = max(0, history_len - 3)
        for i in range(start_idx, history_len):
            t = self.task_history[i]
            print(f"        {i+1}. [{t['action']}] {t['file']}")
        
        # Print Mapping if exists
        if self.extraction_map:
            print(f"      Extraction Map:")
            for src, data in self.extraction_map.items():
                targets = data.get('moved_to', [])
                print(f"        - {src} -> {targets}")
        print("")


    def _load_plan(self, custom_path: Optional[str] = None) -> Optional[Dict]:
        """Reads the plan. If custom_path provided, uses that, otherwise default."""
        if custom_path:
            path = Path(custom_path)
        else:
            path = self.project_root / ".ase" / "plan.json"
            
        if not path.exists():
            print(f"❌ Plan not found at {path}")
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"❌ Error loading plan: {e}")
            return None


    def commit_changes(self) -> bool:
        """
        Moves files from stage to root (optional, for auto-apply).
        """
        for staged in self.stage_dir.rglob("*"):
            if staged.is_file():
                rel = staged.relative_to(self.stage_dir)
                dest = self.project_root / rel
                self.safety.create_backup(dest)
                os.replace(staged, dest)
        return True


    def _find_move_target_file(self, entities: List[str]) -> Optional[str]:
        """Searches current plan for which CREATE file contains (part of) removed entities."""
        if not hasattr(self, 'current_plan') or not self.current_plan:
            return None
            
        changes = self.current_plan.get("implementation_plan", {}).get("changes", [])
        
        # Look for a CREATE step that has at least one of the entities we are removing
        entities_set = set(entities)
        
        for change in changes:
            if change.get("action") == "CREATE":
                created_entities = set(change.get("detected_entities", []))
                # If significant intersection exists (e.g. we are moving these functions)
                if not entities_set.isdisjoint(created_entities):
                    return change.get("target_file")
                    
        return None
