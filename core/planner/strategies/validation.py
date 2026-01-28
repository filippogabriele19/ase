import logging
import re

from ..prompts import VALIDATION_SYSTEM_PROMPT, build_validation_user_prompt
from ..schemas import ActionType, ExecutionPlan, FinalPlanStep, EnrichedPlanStep
from ..utils import safe_json_parse
from typing import Dict, List
from llm import call_model

logger = logging.getLogger(__name__)

class PlanValidator:
    def __init__(self, llm_client):
        self.llm_client = llm_client

    def run(self, enriched_plan: ExecutionPlan, task: str) -> ExecutionPlan:
        """
        PROCESS 3: LLM validates and completes the plan.
        
        LLM:
        - Selects relevant entities from available_symbols using search_criteria
        - Validates coherence (CREATE extracts same entities MODIFY removes)
        - Calculates impact and risk
        - Refines descriptions with concrete entity names
        """
        logger.info("✨ Process 3: LLM final validation and completion...")
        
        system_prompt = VALIDATION_SYSTEM_PROMPT
        user_prompt = build_validation_user_prompt(enriched_plan, task)
        
        try:
            response = call_model(
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=0.1  # Very deterministic for validation
            )
            
            parsed = safe_json_parse(response)
            if not parsed:
                logger.error("Failed to parse LLM validation response")
                return enriched_plan  # Return enriched as fallback
            
            # ✅ DEBUG: Log LLM response structure
            logger.info(f"LLM validation keys: {list(parsed.keys())}")
            if 'steps' in parsed:
                logger.info(f"LLM returned {len(parsed['steps'])} steps")
            else:
                logger.error(f"❌ LLM did NOT return 'steps' key!")
                logger.error(f"Available keys: {list(parsed.keys())}")
                
            # Convert to final plan
            final_plan = self._merge_validation_into_plan(enriched_plan, parsed)
            final_plan = self._cleanup_final_plan_for_worker(final_plan)

            logger.info(f"✅ Final plan validated: {len(final_plan.implementation_plan['changes'])} steps")
            return final_plan
            
        except Exception as e:
            logger.error(f"Validation failed: {e}", exc_info=True)
            return enriched_plan  # Return enriched as fallback


    def _merge_validation_into_plan(
        self,
        enriched_plan: ExecutionPlan,
        validation: Dict
    ) -> ExecutionPlan:
        """Create CLEAN final plan from enriched + validation."""
        changes = enriched_plan.implementation_plan['changes']
        final_changes = []
        validation_steps = validation.get('steps', [])
        
        if not validation_steps:
            logger.error(
                f"❌ LLM validation returned NO 'steps' array!\n"
                f" Keys present: {list(validation.keys())}\n"
                f" This indicates the LLM did not follow the output format.\n"
                f" Using fallback extraction for ALL steps."
            )
        else:
            logger.info(f"✅ LLM returned {len(validation_steps)} validated steps")
        
        # Process each step
        for i, enriched_step in enumerate(changes):
            validation_step = next(
                (v for v in validation_steps if v.get('step_index') == i),
                None
            )
            
            # Create NEW FinalPlanStep
            final_step = FinalPlanStep(
                action=enriched_step.action,
                target_file=enriched_step.target_file,
                source_file=enriched_step.source_file,
                description=enriched_step.description,
            )
            
            if validation_step:
                # LLM provided validation
                final_step.detected_entities = validation_step.get('detected_entities', [])
                final_step.warnings = validation_step.get('warnings', [])
                final_step.impact = validation_step.get('impact', {})
                
                # 👇 NUOVO: Per EXTRACT_AND_MODIFY, empty entities è OK
                if enriched_step.action == ActionType.EXTRACT_AND_MODIFY:
                    if not final_step.detected_entities:
                        # Override confidence: la mancanza di entities è prevista
                        final_step.warnings = [
                            w for w in final_step.warnings 
                            if 'empty' not in w.lower() and 'no_symbols' not in w.lower()
                        ]
                        final_step.warnings.append(
                            "EXTRACT_AND_MODIFY: bulk extraction mode - "
                            "LLM will analyze entire file content"
                        )
                        logger.info(
                            f"   ℹ️  Step {i} (EXTRACT_AND_MODIFY): "
                            f"Empty detected_entities is expected for bulk extraction"
                        )
                
                logger.info(
                    f"   ✅ Step {i}: {len(final_step.detected_entities)} entities "
                )
            else:
                # FALLBACK
                logger.warning(f"   ⚠️ Step {i}: No LLM validation, using fallback")
                final_step.detected_entities = self._fallback_entity_extraction(enriched_step)
                final_step.warnings = ["No LLM validation - used fallback keyword matching"]
                logger.info(f"   Fallback found {len(final_step.detected_entities)} entities")
            
            final_changes.append(final_step)
        
        # Update plan
        enriched_plan.implementation_plan['changes'] = final_changes
        
        # 👇 NUOVO: Override validation_summary se EXTRACT_AND_MODIFY ha senso
        validation_summary = validation.get('validation_summary', {})
        # if validation_summary.get('overall_viability') in ['BLOCKED', 'NOT_VIABLE']:
        #     # Check se il blocco è solo per "no symbols" su EXTRACT_AND_MODIFY
        #     extract_steps = [
        #         s for s in final_changes 
        #         if s.action == ActionType.EXTRACT_AND_MODIFY
        #     ]

        
        enriched_plan.validation_summary = validation_summary
        return enriched_plan

    def _cleanup_final_plan_for_worker(self, final_plan: ExecutionPlan) -> ExecutionPlan:
        """
        Remove internal metadata from final plan.
        
        Worker only needs:
        - action, target_file, source_file, description
        - detected_entities (core!)
        - warnings, impact (optional)
        
        Remove:
        - search_criteria (was for Process 3)
        - resolved_source_id (internal)
        - file_match_score (internal)
        - available_symbols (was for LLM)
        - file_stats (internal)
        """
        logger.info("🧹 Cleaning up plan for Worker...")
        
        changes = final_plan.implementation_plan['changes']
        cleaned_changes = []
        
        for step in changes:
            # Convert to simple dict with only worker-needed fields
            cleaned = {
                "action": step.action,
                "target_file": step.target_file,
                "source_file": step.source_file,
                "description": step.description,
                "detected_entities": step.detected_entities,
                "warnings": step.warnings,
                "impact": step.impact
            }
            cleaned_changes.append(cleaned)
        
        # Update plan
        final_plan.implementation_plan['changes'] = cleaned_changes
        
        total_removed = sum(
            len(getattr(step, 'available_symbols', [])) 
            for step in changes
        )
        
        logger.info(f"  ✓ Removed {total_removed} symbol entries (internal metadata)")
        logger.info(f"  ✓ Removed search_criteria, file_stats, etc.")
        
        return final_plan

    def _fallback_entity_extraction(self, enriched_step: EnrichedPlanStep) -> List[str]:
        """
        Fallback: Extract entities from available_symbols using keyword matching.
        
        Used when LLM Process 3 fails.
        """
        if not enriched_step.available_symbols or not enriched_step.search_criteria:
            return []
        
        keywords = [kw.lower() for kw in enriched_step.search_criteria.domain_keywords]
        exclusions = enriched_step.search_criteria.exclusion_patterns
        
        matched = []
        for symbol in enriched_step.available_symbols:
            name_lower = symbol.name.lower()
            
            # Check exclusions FIRST (early exit)
            if any(re.search(excl, symbol.name, re.IGNORECASE) for excl in exclusions):
                continue
            
            # Check if matches any keyword
            for kw in keywords:
                if kw in name_lower:
                    matched.append(symbol.name)
                    break  # ← Stop at first match
            
            # Also check docstring if available
            if not matched and symbol.docstring:
                doc_lower = symbol.docstring.lower()
                for kw in keywords:
                    if kw in doc_lower:
                        matched.append(symbol.name)
                        logger.debug(f"Matched '{symbol.name}' via docstring: {kw}")
                        break
        
        logger.info(
            f"✅ Fallback extracted {len(matched)} entities from "
            f"{len(enriched_step.available_symbols)} symbols"
        )
        return matched