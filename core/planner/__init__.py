import sys
import logging
import json
from pathlib import Path
from typing import Any, Dict, Optional, Union


# Import LLM modules
from llm import LLMFactory
from llm.base import BaseLLMProvider


# Import internal Planner components
from core.planner.navigator import ProjectNavigator
from .repository import PlannerRepository
from .strategies.draft import DraftGenerator
from .strategies.enrichment import ContextEnricher
from .strategies.validation import PlanValidator
from .schemas import ExecutionPlan, ActionType


logger = logging.getLogger(__name__)


__all__ = ["ASEPlanner", "ExecutionPlan", "ActionType", "plan_logic_db"]


class ASEPlanner:
    """
    Main orchestration: 3-process pipeline with support for standard and iterative modes.
    """
    
    def __init__(
        self, 
        project_root: str, 
        # Explicitly accept EITHER a string (Name) OR an instance (Object)
        llm_input: Optional[Union[str, BaseLLMProvider]] = None, 
        llm_config: Optional[Dict[str, Any]] = None
    ):
        self.root = Path(project_root).resolve()
        self.db_path = self.root / ".ase" / "ase.db"
        self._setup_logging()
        
        if llm_config is None:
            llm_config = {}


        # --- PROVIDER RESOLUTION LOGIC ---
        
        # CASE 1: No input -> Default to Anthropic (created via Factory)
        if llm_input is None:
            self.logger.debug("No provider specified, using default 'anthropic'")
            self.llm_client = LLMFactory.get_provider("anthropic", llm_config)


        # CASE 2: Input is a STRING (e.g., "ollama") -> Create instance via Factory
        elif isinstance(llm_input, str):
            self.logger.debug(f"Provider specified by name: '{llm_input}'")
            self.llm_client = LLMFactory.get_provider(llm_input, llm_config)
            
        # CASE 3: Input is an OBJECT (e.g., AnthropicProvider()) -> Use instance directly
        # (Note: BaseLLMProvider must be imported correctly from llm.base)
        elif isinstance(llm_input, BaseLLMProvider):
            self.logger.debug(f"Provider passed as instance: {type(llm_input).__name__}")
            self.llm_client = llm_input
            
        # CASE 4: Error
        else:
            raise TypeError(
                f"Parameter 'llm_input' must be str or BaseLLMProvider. "
                f"Received: {type(llm_input)}"
            )
        
        # --- Initialize Components ---
        self.repo = PlannerRepository(self.db_path)
        self.navigator = ProjectNavigator(self.db_path)  
        
        # Inject the initialized LLM client into strategies
        self.draft_gen = DraftGenerator(self.llm_client, self.repo, self.navigator)  
        self.enricher = ContextEnricher(self.repo, self.navigator)
        self.validator = PlanValidator(self.llm_client)



    def _setup_logging(self):
        """Configure structured logging."""
        # FIX: Avoid re-wrapping sys.stdout if already done or stream is closed
        if sys.platform == 'win32':
            try:
                # Check if it's already a TextIOWrapper with utf-8 encoding to avoid double wrapping
                if not hasattr(sys.stdout, 'encoding') or sys.stdout.encoding.lower() != 'utf-8':
                    import io
                    # Use detach() if possible to prevent GC closing the underlying buffer
                    if hasattr(sys.stdout, 'buffer'):
                        sys.stdout = io.TextIOWrapper(
                            sys.stdout.buffer, encoding='utf-8', errors='replace'
                        )
            except Exception:
                pass
        
        # Standard Logger Configuration
        logger = logging.getLogger()
        
        # Add handlers only if none exist (avoid duplicates in loops)
        if not logger.handlers:
            log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
            formatter = logging.Formatter(log_format)
            
            # Console Handler
            stream_handler = logging.StreamHandler(sys.stdout)
            stream_handler.setFormatter(formatter)
            logger.addHandler(stream_handler)
            
            # File Handler
            try:
                file_handler = logging.FileHandler(self.root / ".ase" / "planner.log", encoding='utf-8')
                file_handler.setFormatter(formatter)
                logger.addHandler(file_handler)
            except Exception as e:
                # Fallback if log file creation fails
                print(f"⚠️ Could not create log file: {e}")


            logger.setLevel(logging.INFO)
        
        self.logger = logging.getLogger(__name__)




    def _determine_mode(self, scan_results: Optional[Dict[str, Any]], previous_results: Optional[Dict[str, Any]]) -> str:
        """
        Determine the execution mode based on input parameters.
        
        Args:
            scan_results: Results from the scan phase (standard mode)
            previous_results: Results from previous iteration (iterative mode)
            
        Returns:
            str: Either 'standard' or 'iterative'
        """
        if previous_results and previous_results.get('temp_files'):
            self.logger.info("🔄 Mode: ITERATIVE (previous results detected)")
            return 'iterative'
        elif scan_results:
            self.logger.info("📊 Mode: STANDARD (scan results provided)")
            return 'standard'
        else:
            self.logger.info("📊 Mode: STANDARD (default)")
            return 'standard'



    def _load_previous_results(self, previous_results: Dict[str, Any]) -> Dict[str, str]:
        """
        Load temporary files from previous iteration.
        
        Args:
            previous_results: Dictionary containing temp_files paths
            
        Returns:
            dict: Mapping of file names to their content
        """
        loaded_files = {}
        temp_files = previous_results.get('temp_files', {})
        
        for file_key, file_path in temp_files.items():
            try:
                file_path = Path(file_path)
                if file_path.exists():
                    with open(file_path, 'r', encoding='utf-8') as f:
                        loaded_files[file_key] = f.read()
                    self.logger.debug(f"✓ Loaded previous result: {file_key}")
                else:
                    self.logger.warning(f"⚠️ Previous result file not found: {file_path}")
            except Exception as e:
                self.logger.warning(f"⚠️ Failed to load previous result {file_key}: {e}")
        
        return loaded_files



    def _analyze_incremental_improvements(self, original_task: str, previous_results: Dict[str, Any], loaded_files: Dict[str, str]) -> str:
        """
        Analyze differences between original task and previous results to identify incremental improvements.
        
        Args:
            original_task: The original task description
            previous_results: Metadata from previous iteration
            loaded_files: Content of temporary files from previous iteration
            
        Returns:
            str: Augmented task with incremental improvement analysis
        """
        analysis = []
        analysis.append("[ITERATIVE MODE - INCREMENTAL ANALYSIS]")
        analysis.append(f"Iteration: {previous_results.get('loop_iteration', '?')}")
        analysis.append(f"Previous Status: {previous_results.get('status', 'unknown')}")
        
        if previous_results.get('errors'):
            analysis.append("\nPrevious Errors:")
            for error in previous_results.get('errors', []):
                analysis.append(f"  - {error}")
        
        if previous_results.get('incomplete_tasks'):
            analysis.append("\nIncomplete Tasks:")
            for task in previous_results.get('incomplete_tasks', []):
                analysis.append(f"  - {task}")
        
        if loaded_files:
            analysis.append("\n[CURRENT CODE IMPLEMENTATION]") 
            for file_key, content in loaded_files.items():
                analysis.append(f"\n--- FILE: {file_key} ---")
                analysis.append(content) 
                analysis.append("------------------------")


        
        analysis.append("\nObjective: Review previous work, fix errors, complete missing parts, or optimize.")
        analysis.append("If the original task is fully satisfied, produce an empty plan.")
        
        augmented_task = original_task + "\n\n" + "\n".join(analysis)
        return augmented_task



    def plan(
        self, 
        task: str, 
        scan_results: Optional[Dict[str, Any]] = None,
        previous_results: Optional[Dict[str, Any]] = None,
        loop_index: int = None
    ) -> bool:
        """
        Create an execution plan with support for standard and iterative modes.
        
        Args:
            task: The task description to plan
            scan_results: Optional results from the scan phase (standard mode)
            previous_results: Optional results from previous iteration (iterative mode)
            
        Returns:
            bool: True if plan creation succeeded, False otherwise
        """
        # Determine execution mode
        mode = self._determine_mode(scan_results, previous_results)
        
        try:
            if mode == 'iterative':
                return self._plan_iterative(task, previous_results, loop_index)
            else:
                return self._plan_standard(task, scan_results, loop_index)
                
        except Exception as e:
            self.logger.error(f"❌ Plan creation failed: {e}", exc_info=True)
            return False



    def _plan_standard(self, task: str, scan_results: Optional[Dict[str, Any]] = None, loop_index: int = None) -> bool:
        """
        Standard mode: Create plan from task and optional scan results.
        
        Args:
            task: The task description
            scan_results: Optional scan results to augment the task
            
        Returns:
            bool: True if plan creation succeeded, False otherwise
        """
        self.logger.info(f"🧠 DBPlanner v3.0 - Standard Mode")
        
        # Augment task with scan results if provided
        if scan_results:
            scan_context = json.dumps(scan_results, default=str, indent=2)
            task = f"{task}\n\n[SCAN RESULTS]\n{scan_context}"
        
        self.logger.info(f"📋 Task: {task}\n")
        
        try:
            # 1. GENERATE DRAFT
            summary = self.repo.get_project_summary()
            plan = self.draft_gen.run(task, summary)
            
            if not plan or not plan.ensure_changes():
                self.logger.error("❌ Process 1 failed: No valid plan generated")
                return False
                
            self._save_plan(plan, "1_draft")


            # 2. ENRICH CONTEXT
            plan = self.enricher.run(plan)
            self._save_plan(plan, "2_enriched")


            # 3. VALIDATE & FINALIZE
            final_plan = self.validator.run(plan, task)
            final_plan = self._post_validation_check(final_plan)


            self._save_plan(final_plan, "plan", is_final=True, loop_index=loop_index)
            
            self.logger.info(f"\n{'='*70}")
            self.logger.info(f"✅ PLAN GENERATION COMPLETE")
            self.logger.info(f"{'='*70}")
            return True


        except Exception as e:
            self.logger.error(f"❌ Plan creation failed: {e}", exc_info=True)
            return False



    def _plan_iterative(self, task: str, previous_results: Dict[str, Any], loop_index: int = None) -> bool:
        """
        Iterative mode: Create plan based on previous iteration results.
        
        Args:
            task: The original task description
            previous_results: Results from previous iteration including temp files
            
        Returns:
            bool: True if plan creation succeeded, False otherwise
        """
        self.logger.info(f"🧠 DBPlanner v3.0 - Iterative Mode (Refinement)")
        
        iteration = previous_results.get('loop_iteration', '?')
        self.logger.info(f"🔄 REFINEMENT MODE (Iter {iteration}): Activating Shadow Mode")
        
        # 1. Enable Shadow Mode in Navigator
        if hasattr(self.navigator, 'enable_shadow_mode'):
            self.navigator.enable_shadow_mode(True)
        else:
            self.logger.warning("⚠️ Navigator does not support Shadow Mode! Refinement might fail.")


        # 2. Load previous results from temporary files
        loaded_files = self._load_previous_results(previous_results)
        
        # 3. Analyze incremental improvements
        augmented_task = self._analyze_incremental_improvements(task, previous_results, loaded_files)
        
        self.logger.info(f"📋 Augmented Task: {augmented_task}\n")
        
        try:
            # 1. GENERATE DRAFT
            summary = self.repo.get_project_summary()
            plan = self.draft_gen.run(augmented_task, summary)
            
            if not plan or not plan.ensure_changes():
                # In Refinement Mode, an empty plan might be a success (No changes needed)
                self.logger.info("✅ Refinement complete: No further changes needed.")
                return True
                
            self._save_plan(plan, "1_draft")


            # 2. ENRICH CONTEXT
            plan = self.enricher.run(plan)
            self._save_plan(plan, "2_enriched")


            # 3. VALIDATE & FINALIZE
            final_plan = self.validator.run(plan, augmented_task)
            final_plan = self._post_validation_check(final_plan)


            self._save_plan(final_plan, "plan", is_final=True, loop_index=loop_index)
            
            self.logger.info(f"\n{'='*70}")
            self.logger.info(f"✅ ITERATIVE PLAN GENERATION COMPLETE")
            self.logger.info(f"{'='*70}")
            return True


        except Exception as e:
            self.logger.error(f"❌ Iterative plan creation failed: {e}", exc_info=True)
            return False



    def _save_plan(self, plan, name: str, is_final: bool = False, loop_index: int = None):
        """Helper to save JSON plans."""
        # If we are in a loop and saving the final plan, use plan_loop_X.json
        if is_final and loop_index is not None:
            filename = f"plan_loop_{loop_index}.json"
        elif is_final:
            filename = "plan.json"
        else:
            filename = f"plan_{name}.json"
        path = self.root / ".ase" / filename
        
        try:
            with open(path, "w", encoding="utf-8") as f:
                if hasattr(plan, 'model_dump'):
                    data = plan.model_dump()
                else:
                    data = plan


                if is_final and isinstance(data, dict):
                    data["metadata"] = {
                        "version": "3.0-modular",
                        "project_root": str(self.root)
                    }
                    
                json.dump(data, f, indent=2, ensure_ascii=False)
                
            if not is_final:
                self.logger.debug(f"💾 Saved intermediate: {filename}")
            else:
                self.logger.info(f"📄 Plan saved: {path}")
        except Exception as e:
            self.logger.warning(f"Failed to save plan {filename}: {e}")


    def _post_validation_check(self, plan: ExecutionPlan) -> ExecutionPlan:
        """
        PHASE 4: Final review with impact analysis.
        Adds warnings if critical dependent files are missing.
        """
        logger.info("🔍 Phase 4: Post-validation impact check...")
        
        changes = plan.implementation_plan['changes']
        for step in changes:
            if step.get('action') in ['MODIFY', 'DELETE']:
                impact = self.navigator.get_impact_analysis(step['target_file'])
                if impact['count'] > 0:
                    warning = f"Impact: {impact['count']} files depend on this ({', '.join(impact['callers'][:3])})"
                    if 'warnings' not in step:
                        step['warnings'] = []
                    step['warnings'].append(warning)
        
        logger.info("✅ Impact check complete")
        return plan



def plan_logic_db(
    task: str, 
    project_root: str, 
    provider_instance: Optional[Union[str, BaseLLMProvider]] = None, 
    llm_config: Optional[Dict[str, Any]] = None,
    previous_artifacts: Optional[Dict[str, Any]] = None,
    scan_results: Optional[Dict[str, Any]] = None,
    loop_index: int = None
) -> bool:
    """
    CLI entry point.
    Wrapper using the new modular ASEPlanner with configurable provider support
    and standard/iterative modes.
    """
    planner = ASEPlanner(
        project_root, 
        llm_input=provider_instance, 
        llm_config=llm_config
    )
    
    # UNIFICATION: Always use .plan()
    # The .plan() method internally checks 'previous_results' and decides
    # whether to use iterative mode (_plan_iterative) or standard mode (_plan_standard).
    return planner.plan(
        task, 
        scan_results=scan_results, 
        previous_results=previous_artifacts, 
        loop_index=loop_index
    )


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python planner.py <task> <project_root> [llm_provider] [llm_config_json]")
        sys.exit(1)
    
    task = sys.argv[1]
    project_root = sys.argv[2]
    llm_provider = sys.argv[3] if len(sys.argv) > 3 else None
    llm_config = {}
    
    if len(sys.argv) > 4:
        try:
            llm_config = json.loads(sys.argv[4])
        except json.JSONDecodeError:
            print("Invalid JSON for llm_config")
            sys.exit(1)
    
    # previous_artifacts remains None if called from direct CLI
    success = plan_logic_db(task, project_root, provider_instance=llm_provider, llm_config=llm_config)
    sys.exit(0 if success else 1)
