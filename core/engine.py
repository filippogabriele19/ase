from pathlib import Path
from typing import Callable, Optional, Dict, Any, List, Union
import shutil
import json
from datetime import datetime
from utils.visualizer import ProjectVisualizer
from core import scanner, planner
from core.loop_manager import LoopManager
from llm.factory import LLMFactory


class LoopState:
    """Tracks state across multiple execution loops."""
    
    def __init__(self):
        self.loop_iteration = 0
        self.previous_artifacts = None
        self.previous_plan = None
        self.previous_work_stats = None
        self.all_modifications = []
    
    def update_after_loop(self, plan_result: Dict[str, Any], work_stats: Dict[str, Any]):
        """
        Updates state after a loop completion.
        
        Args:
            plan_result: Result from the planning phase
            work_stats: Statistics from the worker execution
        """
        self.previous_plan = plan_result
        self.previous_work_stats = work_stats
        self.previous_artifacts = {
            "drafted": work_stats.get("drafted", 0),
            "details": work_stats.get("details", {}),
            "loop_iteration": self.loop_iteration,
            "plan_summary": plan_result.get("summary", "")
        }
        if work_stats.get("drafted", 0) > 0:
            self.all_modifications.append({
                "loop": self.loop_iteration,
                "drafted": work_stats.get("drafted", 0),
                "details": work_stats.get("details", {})
            })
    
    def get_context_for_next_loop(self) -> Dict[str, Any]:
        """Prepares context for the subsequent loop."""
        return {
            "previous_artifacts": self.previous_artifacts,
            "previous_plan": self.previous_plan,
            "previous_work_stats": self.previous_work_stats,
            "all_modifications": self.all_modifications,
            "loop_iteration": self.loop_iteration
        }


class ASEEngine:
    def __init__(
        self, 
        project_root: Path,
        llm_provider: str = "anthropic",
        llm_config: Optional[Dict[str, Any]] = None
    ):
        self.project_root = Path(project_root).resolve()
        self.dot_ase = self.project_root / ".ase"
        self.backups_dir = self.dot_ase / "backups"
        self.llm_provider_type = llm_provider
        self.llm_config = llm_config or {}
        self.llm_provider = LLMFactory.get_provider(llm_provider, self.llm_config)
        self._ensure_env()


    def _ensure_env(self):
        """Sets up the ASE working environment."""
        self.dot_ase.mkdir(exist_ok=True)
        self.backups_dir.mkdir(exist_ok=True)


    def _create_backup(self) -> str:
        """Creates a safety snapshot before modifying code."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = self.backups_dir / f"pre_work_{timestamp}"
        # Implementation of copy logic would go here if needed, currently just returns path
        return str(backup_path)


    def _refresh_visuals(self):
        """Regenerates the visualization graph without opening the browser."""
        file_tree = scanner.build_file_tree(str(self.project_root))
        viz = ProjectVisualizer(self.project_root)
        viz.generate_and_open(file_tree=file_tree, open_browser=False)


    def scan(self) -> bool:
        """Scans the project structure and updates graphs."""
        try:
            _, success = scanner.scan_logic_db(str(self.project_root))
            if success:
                self._refresh_visuals()
            return success
        except Exception as e:
            print(f"Error during scan: {e}")
            return False


    def plan(self, task: str, previous_artifacts: Optional[Dict[str, Any]] = None, loop_index: int = None) -> Dict[str, Any]:
        """Architects solutions for the given task."""
        try:
            result = planner.plan_logic_db(
                task, 
                project_root=str(self.project_root), 
                provider_instance=self.llm_provider,
                previous_artifacts=previous_artifacts,
                loop_index=loop_index
            )
            return {
                "success": result,
                "summary": f"Planning completed for task: {task}",
                "has_previous_artifacts": previous_artifacts is not None
            }
        except Exception as e:
            print(f"Error during planning: {e}")
            return {"success": False, "error": str(e)}


    def work(self, loop: int = 1, plan_path: Optional[str] = None) -> Dict[str, Any]:
        """
        Executes refactoring work with drafting and committing.
        
        Args:
            loop: Number of loop iterations (default: 1 for single-loop execution)
            plan_path: Path to the execution plan file
        
        Returns:
            Dict containing work results, including "review_needed" status if drafts generated
        """
        try:
            from core.worker import Worker
            worker_instance = Worker(self.project_root, llm_provider=self.llm_provider)
            
            # 1. Generate drafts
            stats = worker_instance.create_diff_draft(plan_path=plan_path)
            
            if not stats.get("success", True):
                return stats

            if stats["drafted"] > 0:
                # If changes exist, do NOT apply immediately.
                # Return special status "review_needed"
                return {
                    "success": True, 
                    "status": "review_needed", 
                    "drafted": stats["drafted"],
                    "details": stats.get("details", {}),
                    "loop": loop
                }
            else:
                return {"success": False, "error": "No changes generated"}
        except Exception as e:
            return {"success": False, "error": str(e)}


    def apply_staged_changes(self):
        """Call this method ONLY after user confirmation via UI/CLI."""
        try:
            from core.worker import Worker
            worker_instance = Worker(self.project_root, llm_provider=self.llm_provider)
            worker_instance.commit_changes()
        except Exception as e:
            print(f"Error applying staged changes: {e}")
            raise
        
    def run_autonomous_mission(
        self, 
        task: str, 
        on_progress: Optional[Callable[[str, str], None]] = None,
        loop_count: int = 1
    ) -> Dict[str, Any]:
        """
        Main orchestrator managing the Scan -> Plan -> Work loop.
        """
        def log(msg, style="white"):
            if on_progress: on_progress(msg, style)

        log(f"🚀 Starting mission: {task}", "cyan")
        
        loop_manager = LoopManager(project_root=self.project_root, task=task, loop_count=loop_count)
        stage_dir = self.project_root / ".ase" / "stage"
        
        total_drafted = 0
        final_status = "completed"
        
        for i in range(loop_count):
            current_loop = loop_manager.start_loop()
            log(f"\n🔄 Loop {current_loop}/{loop_count} started", "magenta")

            # A. SCAN (First run only)
            if current_loop == 1:
                log("🔍 Scanning project structure...", "yellow")
                if not self.scan():
                    log("❌ Scan failed", "red")
                    return {"success": False, "error": "Scan operation failed"}
            
            # B. PLAN
            previous_artifacts = loop_manager.get_previous_artifacts()
            if previous_artifacts:
                log(f"🧠 Refining plan based on previous loop...", "yellow")
            else:
                log("🧠 Architecting solutions...", "yellow")

            # Planning
            plan_result = self.plan(task, previous_artifacts=previous_artifacts, loop_index=current_loop)
            
            # CONVERGENCE CHECK: Verify if plan is empty
            plan_file = self.project_root / ".ase" / f"plan_loop_{current_loop}.json"
            
            # 1. If specific plan for this loop doesn't exist, assume CONVERGENCE
            if not plan_file.exists():
                 log(f"✅ Loop {current_loop}: No plan generated (Planner converged). Stopping.", "green")
                 break

            # 2. If exists, check if empty (Explicit Convergence)
            try:
                 with open(plan_file, "r") as f:
                      plan_data = json.load(f)
                      changes = plan_data.get("implementation_plan", {}).get("changes", [])
                      if not changes:
                          log(f"✅ Loop {current_loop}: Plan is empty (Planner converged). Stopping.", "green")
                          break
            except Exception: pass
            
            # C. WORK
            log(f"🔨 Executing refactoring (Loop {current_loop})...", "yellow")
            # EXPLICIT PLAN PASSING TO WORKER
            work_stats = self.work(loop=current_loop, plan_path=str(plan_file)) 
            
            loop_manager.save_loop_result(current_loop, work_stats)

            if not work_stats.get("success"):
                log(f"⚠️ Work finished with errors in loop {current_loop}.", "red")
                break
            
            drafted_in_loop = work_stats.get("drafted", 0)
            total_drafted += drafted_in_loop

            # === [SNAPSHOT & ARTIFACTS SYSTEM] ===
            # 1. Extract changed files list (always safe)
            changed_files = set()
            raw_details = work_stats.get("details", [])
            
            if isinstance(raw_details, dict):
                changed_files.update(raw_details.keys())
            elif isinstance(raw_details, list):
                for item in raw_details:
                    if isinstance(item, str): changed_files.add(item)
                    elif isinstance(item, dict):
                        p = item.get('file') or item.get('target') or item.get('path')
                        if p: changed_files.add(p)
            
            # 2. Create Snapshot (Optional for debug)
            if drafted_in_loop > 0:
                try:
                    snapshot_root = self.project_root / ".ase" / "snapshots" / f"loop_{current_loop}"
                    snapshot_root.mkdir(parents=True, exist_ok=True)
                    
                    count = 0
                    for rel_path in changed_files:
                        staged_file = stage_dir / rel_path
                        # Look in stage, fallback to root if not found
                        src = staged_file if staged_file.exists() else (self.project_root / rel_path)
                        
                        if src.exists() and src.is_file():
                            dest = snapshot_root / rel_path
                            dest.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copy2(src, dest)
                            count += 1
                    
                    if count > 0:
                        log(f"📸 Snapshot saved: {count} files in .ase/snapshots/loop_{current_loop}/", "blue")
                except Exception as e:
                    log(f"⚠️ Snapshot failed: {e}", "magenta")

            # 3. Prepare Artifacts for Planner (Shadow Mode)
            # Map modified file paths to their real paths in STAGE
            temp_files_map = {}
            for fpath in changed_files:
                staged_path = stage_dir / fpath
                if staged_path.exists():
                    temp_files_map[fpath] = str(staged_path)
                else:
                    # Fallback: if not in stage, maybe we didn't touch it but planner needs to know?
                    pass

            artifacts = {
                "loop_iteration": current_loop,
                "status": "success",
                "temp_files": temp_files_map, # Absolute paths to stage
                "plan_summary": plan_result.get("summary", ""),
                "changes_made": drafted_in_loop,
            }
            loop_manager.save_loop_artifacts(current_loop, artifacts)

            # E. Early exit if worker did nothing (even if planner had plans)
            if drafted_in_loop == 0:
                log(f"ℹ️ Loop {current_loop}: No modifications made by worker.", "green")
                # Usually implies convergence.
                if current_loop > 1: break 

        # FINAL REPORT
        all_results = loop_manager.get_all_results()
        final_details = [] 
        for l_num, res in all_results.items():
            d = res.get("details", [])
            if isinstance(d, list): final_details.extend(d)
            elif isinstance(d, dict): final_details.append(d)

        log(f"\n🏁 Mission ended. Total drafted files: {total_drafted}", "cyan")

        return {
            "success": True,
            "status": "review_needed" if total_drafted > 0 else "no_changes",
            "drafted": total_drafted,
            "details": final_details,
            "loop_summary": loop_manager.get_loop_summary()
        }
