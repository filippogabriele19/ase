import json
import shutil
import time
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional

class SafetyManager:
    """
    Manages operational safety: backups, audit logging, and permission checks.
    Ensures no destructive action is taken without recovery options.
    """
    
    def __init__(self, project_root: str):
        self.project_root = Path(project_root)
        self.history_dir = self.project_root / ".ase" / "history"
        self.backup_dir = self.project_root / ".ase" / "backups"
        self._init_directories()

    def _init_directories(self):
        """Creates hidden directories for logs and backups if they don't exist."""
        self.history_dir.mkdir(parents=True, exist_ok=True)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def get_transaction_id(self) -> str:
        """Generates a time-based transaction ID."""
        return datetime.now().strftime("%Y%m%d_%H%M%S")

    def archive_plan(self, plan_path: Path, task_name: str = "") -> Optional[Path]:
        """
        Archives the plan.json into history with a timestamp.
        Example: 20260105_1030_Refactor_utils.json
        """
        if not plan_path.exists():
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize task name
        safe_task = "".join([c if c.isalnum() else "_" for c in task_name])[:30]
        if not safe_task: safe_task = "plan"
        
        new_name = f"{timestamp}_{safe_task}.json"
        dest_path = self.history_dir / new_name
        
        try:
            shutil.copy2(plan_path, dest_path)
            return dest_path
        except Exception as e:
            print(f"❌ Error archiving plan: {e}")
            return None

    def create_backup(self, file_path: Path, transaction_id: Optional[str] = None) -> Optional[Path]:
        """
        Creates a file backup BEFORE modification.
        Supports transactional mode (folder) or single file mode.
        """
        if not file_path.exists():
            return None

        if transaction_id:
            # Mode: .ase/backups/20240105_120000/filename.py
            target_dir = self.backup_dir / transaction_id
            target_dir.mkdir(exist_ok=True)
            backup_path = target_dir / file_path.name
        else:
            # Mode: .ase/backups/filename.py.120000.bak
            ts = time.strftime("%H%M%S")
            backup_path = self.backup_dir / f"{file_path.name}.{ts}.bak"

        try:
            shutil.copy2(file_path, backup_path)
            return backup_path
        except Exception as e:
            print(f"❌ Error creating backup for {file_path}: {e}")
            return None

    def log_operation(self, task: str, plan: Dict, result: Dict = None):
        """Saves a full operation log (Flight Recorder)."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        # Sanitize task for filename
        safe_task = "".join([c if c.isalnum() else "_" for c in task])[:50]
        
        log_entry = {
            "timestamp": datetime.now().isoformat(),
            "task": task,
            "plan": plan,
            "result": result
        }

        filename = f"{timestamp}_{safe_task}.json"
        log_path = self.history_dir / filename
        
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log_entry, f, indent=2)
            
        print(f"📝 Operation log saved to: .ase/history/{filename}")

    def check_permissions(self, action_type: str, file_path: str) -> bool:
        """
        Intervenes BEFORE execution.
        Returns True if allowed, False if blocked.
        Prompts user confirmation for dangerous actions.
        """
        dangerous_actions = ["delete_file", "execute_shell"]
        
        if action_type in dangerous_actions:
            print(f"\n⚠️  WARNING: Agent is attempting a DANGEROUS action!")
            print(f"   Action: {action_type}")
            print(f"   Target: {file_path}")
            confirm = input("   Authorize execution? (y/N): ").strip().lower()
            return confirm == 'y'
        
        return True
