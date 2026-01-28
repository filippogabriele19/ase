from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import json
import shutil


class LoopManager:
    """
    Manages the orchestration of multiple loops within the Ralph loop.
    
    Tracks state across loops, handles temporary file persistence, coordinates
    data passing between loops, and provides access to execution results.
    """

    def __init__(self, project_root: Path, task: str, loop_count: int = 1):
        """
        Initialize the LoopManager.
        
        Args:
            project_root: Root path of the project
            task: Original task to execute
            loop_count: Total number of loop iterations
        """
        self.project_root = Path(project_root).resolve()
        self.task = task
        self.loop_count = max(1, loop_count)
        self.current_loop = 0
        
        # Directory for temporary data persistence
        self.dot_ase = self.project_root / ".ase"
        self.loop_data_dir = self.dot_ase / "loop_data"
        self.loop_data_dir.mkdir(parents=True, exist_ok=True)
        
        # Internal state
        self.loop_results: Dict[int, Dict[str, Any]] = {}
        self.loop_artifacts: Dict[int, Dict[str, Any]] = {}
        self.loop_timestamps: Dict[int, str] = {}
        
        self._initialize_state()


    def _initialize_state(self):
        """Initialize the LoopManager state."""
        self.current_loop = 0
        self.loop_results = {}
        self.loop_artifacts = {}
        self.loop_timestamps = {}


    def start_loop(self) -> int:
        """
        Start a new loop iteration.
        
        Returns:
            Current loop number (1-based)
        """
        self.current_loop += 1
        self.loop_timestamps[self.current_loop] = datetime.now().isoformat()
        return self.current_loop


    def execute_loop(self) -> int:
        """
        Execute loop cycle (alias for start_loop for compatibility).
        
        Returns:
            Current loop number (1-based)
        """
        return self.start_loop()


    def run_loop(self) -> int:
        """
        Execute loop cycle (alias for start_loop for compatibility).
        
        Returns:
            Current loop number (1-based)
        """
        return self.start_loop()


    def get_current_loop(self) -> int:
        """Return the current loop number."""
        return self.current_loop


    def is_last_loop(self) -> bool:
        """Check if the current loop is the last one."""
        return self.current_loop >= self.loop_count


    def get_loop_count(self) -> int:
        """Return the total number of loops."""
        return self.loop_count


    def save_loop_result(self, loop_num: int, result: Dict[str, Any]) -> None:
        """
        Save the result of a loop execution.
        
        Args:
            loop_num: Loop number
            result: Result of the loop execution
        """
        self.loop_results[loop_num] = result
        self._persist_loop_result(loop_num, result)


    def save_loop_artifacts(self, loop_num: int, artifacts: Dict[str, Any]) -> None:
        """
        Save loop artifacts to be used by the next loop.
        
        Args:
            loop_num: Loop number
            artifacts: Artifacts to save (drafted, details, etc.)
        """
        artifacts_with_meta = {
            "loop_iteration": loop_num,
            "timestamp": datetime.now().isoformat(),
            "data": artifacts
        }
        self.loop_artifacts[loop_num] = artifacts_with_meta
        self._persist_loop_artifacts(loop_num, artifacts_with_meta)


    def get_previous_artifacts(self) -> Optional[Dict[str, Any]]:
        """
        Retrieve artifacts from the previous loop for data passing.
        
        Returns:
            Artifacts from the previous loop, or None if this is the first loop
        """
        if self.current_loop <= 1:
            return None
        
        previous_loop = self.current_loop - 1
        if previous_loop in self.loop_artifacts:
            return self.loop_artifacts[previous_loop].get("data")
        
        # Try to load from disk if not in memory
        return self._load_loop_artifacts(previous_loop)


    def get_loop_result(self, loop_num: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve the result of a specific loop.
        
        Args:
            loop_num: Loop number
            
        Returns:
            Loop result or None if not found
        """
        if loop_num in self.loop_results:
            return self.loop_results[loop_num]
        
        # Try to load from disk
        return self._load_loop_result(loop_num)


    def get_all_results(self) -> Dict[int, Dict[str, Any]]:
        """Return all results from completed loops."""
        return self.loop_results.copy()


    def get_loop_summary(self) -> Dict[str, Any]:
        """
        Return a summary of the current loop state.
        
        Returns:
            Dictionary containing summary information
        """
        return {
            "task": self.task,
            "total_loops": self.loop_count,
            "current_loop": self.current_loop,
            "completed_loops": len(self.loop_results),
            "is_last_loop": self.is_last_loop(),
            "loop_timestamps": self.loop_timestamps,
            "results_summary": {
                loop_num: {
                    "success": result.get("success"),
                    "status": result.get("status"),
                    "timestamp": self.loop_timestamps.get(loop_num)
                }
                for loop_num, result in self.loop_results.items()
            }
        }


    def _persist_loop_result(self, loop_num: int, result: Dict[str, Any]) -> None:
        """
        Persist a loop result to disk.
        
        Args:
            loop_num: Loop number
            result: Result to persist
        """
        result_file = self.loop_data_dir / f"loop_{loop_num}_result.json"
        try:
            with open(result_file, "w") as f:
                json.dump(result, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Failed to persist loop {loop_num} result: {e}")


    def _persist_loop_artifacts(self, loop_num: int, artifacts: Dict[str, Any]) -> None:
        """
        Persist loop artifacts to disk.
        
        Args:
            loop_num: Loop number
            artifacts: Artifacts to persist
        """
        artifacts_file = self.loop_data_dir / f"loop_{loop_num}_artifacts.json"
        try:
            with open(artifacts_file, "w") as f:
                json.dump(artifacts, f, indent=2, default=str)
        except Exception as e:
            print(f"⚠️ Failed to persist loop {loop_num} artifacts: {e}")


    def _load_loop_result(self, loop_num: int) -> Optional[Dict[str, Any]]:
        """
        Load a loop result from disk.
        
        Args:
            loop_num: Loop number
            
        Returns:
            Loop result or None if not found
        """
        result_file = self.loop_data_dir / f"loop_{loop_num}_result.json"
        if result_file.exists():
            try:
                with open(result_file, "r") as f:
                    return json.load(f)
            except Exception as e:
                print(f"⚠️ Failed to load loop {loop_num} result: {e}")
        return None


    def _load_loop_artifacts(self, loop_num: int) -> Optional[Dict[str, Any]]:
        """
        Load loop artifacts from disk.
        
        Args:
            loop_num: Loop number
            
        Returns:
            Loop artifacts or None if not found
        """
        artifacts_file = self.loop_data_dir / f"loop_{loop_num}_artifacts.json"
        if artifacts_file.exists():
            try:
                with open(artifacts_file, "r") as f:
                    data = json.load(f)
                    self.loop_artifacts[loop_num] = data
                    return data.get("data")
            except Exception as e:
                print(f"⚠️ Failed to load loop {loop_num} artifacts: {e}")
        return None


    def cleanup_loop_data(self) -> None:
        """Clean up temporary loop data."""
        try:
            if self.loop_data_dir.exists():
                shutil.rmtree(self.loop_data_dir)
                self.loop_data_dir.mkdir(parents=True, exist_ok=True)
        except Exception as e:
            print(f"⚠️ Failed to cleanup loop data: {e}")


    def get_task(self) -> str:
        """Return the original task."""
        return self.task
