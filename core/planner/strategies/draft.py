#core/planner/strategies/draft.py

import logging
from typing import Optional
from llm import call_model
from ..prompts import DRAFT_SYSTEM_PROMPT, build_draft_user_prompt,ITERATIVE_DRAFT_SYSTEM_PROMPT,build_iterative_draft_user_prompt
from ..schemas import ExecutionPlan, DraftPlanStep, ActionType  # 👈 aggiungi ActionType
from ..utils import safe_json_parse

logger = logging.getLogger(__name__)

class DraftGenerator:
    def __init__(self, llm_client, repository, navigator):
        self.llm_client = llm_client
        self.repository = repository
        self.navigator = navigator

    def run(self, task: str, project_context: str) -> Optional[ExecutionPlan]:
        """
        PROCESS 1: LLM generates draft plan with reasoning.
        """
        logger.info("📝 Process 1: Generating draft plan with LLM...")
        
        # 👇 NUOVO: Symbol Grounding (Pre-Draft Intelligence)
        symbol_hints = self.navigator.ground_task(task)
        
        # Inietta gli hints nel task stesso
        enriched_task = task
        if symbol_hints:
            enriched_task = f"{task}\n\n{symbol_hints}"
        
        # === FIX: Rilevamento Modalità Iterativa ===
        # Se il task contiene il marcatore iniettato dal Planner, cambiamo prompt
        is_iterative = "[ITERATIVE MODE" in task
        
        if is_iterative:
            logger.info("🧠 DraftGenerator: Switching to ITERATIVE prompts")
            system_prompt = ITERATIVE_DRAFT_SYSTEM_PROMPT
            user_prompt = f"PROJECT CONTEXT:\n{project_context}\n\n{task}"
        else:
            # Modalità Standard (Loop 1)
            system_prompt = DRAFT_SYSTEM_PROMPT
            user_prompt = build_draft_user_prompt(enriched_task, project_context)
        # ============================================
        
        try:
            response = call_model(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.2
            )
            
            parsed = safe_json_parse(response)
            if not parsed:
                logger.error("Failed to parse LLM draft plan response")
                return None
            
            # Validate structure
            plan = ExecutionPlan(**parsed)
            
            # Convert changes to DraftPlanStep objects
            plan.implementation_plan['changes'] = [
                DraftPlanStep(**step) if isinstance(step, dict) else step
                for step in plan.implementation_plan['changes']
            ]
            
            # Sanitizza il piano
            plan = self._sanitize_plan(plan)
            
            logger.info(f"✅ Draft plan generated: {len(plan.implementation_plan['changes'])} steps")
            return plan
            
        except Exception as e:
            logger.error(f"Draft plan generation failed: {e}", exc_info=True)
            return None

    
    def _sanitize_plan(self, plan: ExecutionPlan) -> ExecutionPlan:
        """
        Post-process draft plan to remove common LLM mistakes:
        1. Redundant MODIFY steps after EXTRACT_AND_MODIFY
        2. Invalid entity_types
        """
        changes = plan.implementation_plan['changes']
        sanitized = []
        removed_count = 0
        
        for i, step in enumerate(changes):
            should_keep = True
            
            # Rule 1: Remove redundant MODIFY on same file as EXTRACT_AND_MODIFY source
            if step.action == ActionType.MODIFY and i > 0:
                prev_step = changes[i - 1]
                if prev_step.action == ActionType.EXTRACT_AND_MODIFY:
                    if prev_step.source_file == step.target_file:
                        logger.warning(
                            f"⚠️  Removing redundant step {i}: "
                            f"MODIFY {step.target_file} already handled by "
                            f"EXTRACT_AND_MODIFY in step {i-1}"
                        )
                        should_keep = False
                        removed_count += 1
            
            # Rule 2: Sanitize entity_types (only allow: function, method, class, variable)
            if step.search_criteria and step.search_criteria.entity_types:
                valid_types = {'function', 'method', 'class', 'variable'}
                original_types = step.search_criteria.entity_types
                sanitized_types = [t for t in original_types if t in valid_types]
                
                if len(sanitized_types) != len(original_types):
                    invalid = set(original_types) - valid_types
                    logger.warning(
                        f"⚠️  Step {i}: Removed invalid entity_types: {invalid}"
                    )
                    step.search_criteria.entity_types = sanitized_types
            
            if should_keep:
                sanitized.append(step)
        
        plan.implementation_plan['changes'] = sanitized
        
        if removed_count > 0:
            logger.info(f"🧹 Sanitization: removed {removed_count} redundant step(s)")
        
        return plan

