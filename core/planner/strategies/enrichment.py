#core/planner/strategies/enrichment.py
import logging
import re
from typing import Optional, List

from core.planner.navigator import ProjectNavigator
from ..schemas import ExecutionPlan, EnrichedPlanStep, ActionType, DraftPlanStep, SymbolInfo, SearchCriteria
from ..repository import PlannerRepository
from ..utils import FileResolver

logger = logging.getLogger(__name__)

class ContextEnricher:
    def __init__(self, repo: PlannerRepository, navigator: ProjectNavigator):
        self.repo = repo
        # We need a connection for FileResolver. 
        # Ideally FileResolver should use Repository, but let's reuse the connection for now.
        self.resolver = FileResolver(self.repo._get_db_connection())
        self.navigator = navigator
        
    def run(self, draft_plan: ExecutionPlan) -> ExecutionPlan:
        """
        PROCESS 2: Python adds deterministic facts from DB.
        """
        logger.info("🔧 Process 2: Enriching plan with DB facts...")
        
        changes = draft_plan.implementation_plan['changes']
        enriched_changes = []
        
        for i, step in enumerate(changes, 1):
            logger.info(f"  [{i}/{len(changes)}] Enriching {step.action} {step.target_file}")
            enriched_step = self._enrich_single_step(step)
            enriched_changes.append(enriched_step)
        
        # Update plan
        draft_plan.implementation_plan['changes'] = enriched_changes
        logger.info(f"✅ Enrichment complete: {len(enriched_changes)} steps processed")
        return draft_plan

    def _enrich_single_step(self, step: DraftPlanStep) -> EnrichedPlanStep:
        enriched = EnrichedPlanStep(**step.model_dump())
        
        source_file = self._determine_source(step)
        if not source_file:
            return enriched
        
        # ✅ Usa Navigator per risolvere il path
        resolved_path = self.navigator.resolve_path(source_file)
        if not resolved_path:
            return enriched
        
        # ✅ Ottieni il file_id dal path risolto
        file_id = self.repo.get_file_id(resolved_path)
        if not file_id:
            return enriched
        
        # ✅ Usa file_id invece di match.file_id
        entity_types = step.search_criteria.entity_types if step.search_criteria else None
        
        # 1. Scarica simboli già pre-filtrati per tipo dal DB
        symbols = self.repo.get_symbols_filtered(file_id, entity_types)  # ← FIX: file_id
        
        # 2. Applica il filtraggio fine (Regex/Keywords) in Python
        filtered_symbols = self._apply_regex_filters(symbols, step.search_criteria)
        
        # 3. Ottieni tutti i simboli per le statistiche
        all_symbols = self.repo.get_all_symbols(file_id)  # ← FIX: file_id
        
        # 4. Popola l'enriched step
        enriched.available_symbols = filtered_symbols
        enriched.file_stats = self.repo.get_file_stats(file_id, all_symbols)  # ← FIX: file_id
        
        return enriched

    def _apply_regex_filters(self, symbols: List[SymbolInfo], criteria: Optional[SearchCriteria]) -> List[SymbolInfo]:
        """Applica la logica Regex e Keyword (Parte 2 del vecchio _fetch_symbols_filtered)."""
        if not criteria:
            return symbols
            
        filtered = []
        # FIX: Se c'è una keyword speciale "*" o "ALL", salta il filtro keywords
        skip_keyword_filter = False
        if criteria.domain_keywords and ("*" in criteria.domain_keywords or "ALL" in criteria.domain_keywords):
            skip_keyword_filter = True

        for sym in symbols:
            # A. Check ESCLUSIONI (Resta uguale)
            if criteria.exclusion_patterns:
                is_excluded = False
                for pattern in criteria.exclusion_patterns:
                    if re.search(pattern, sym.name): 
                        is_excluded = True
                        break
                if is_excluded:
                    continue 

            # B. Check KEYWORDS (Modificato)
            if criteria.domain_keywords and not skip_keyword_filter: # <--- Aggiungi condizione
                is_relevant = False
                for kw in criteria.domain_keywords:
                    pattern = r'\b' + re.escape(kw) + r'\b'
                    if re.search(pattern, sym.name, re.IGNORECASE) or \
                       (sym.docstring and re.search(pattern, sym.docstring, re.IGNORECASE)):
                        is_relevant = True
                        break

                
                if not is_relevant:
                    continue

            filtered.append(sym)
            
        return filtered

    def _determine_source(self, step: DraftPlanStep) -> Optional[str]:
        if step.action == ActionType.CREATE and step.source_file:
            return step.source_file
        if step.action in [ActionType.MODIFY, ActionType.DELETE]:
            return step.target_file
        if step.action == ActionType.MOVE and step.source_file:
            return step.source_file
        if step.action == ActionType.EXTRACT_AND_MODIFY and step.source_file:  
            return step.source_file  
        return None
