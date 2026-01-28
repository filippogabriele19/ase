from enum import Enum
from typing import List, Optional, Any, Dict, Union
from pydantic import BaseModel, Field, field_validator, model_validator

# --- Enums ---

class ActionType(str, Enum):
    """Supported refactoring actions."""
    CREATE = "CREATE"
    MODIFY = "MODIFY"
    MOVE = "MOVE"
    DELETE = "DELETE"
    EXTRACT_AND_MODIFY = "EXTRACT_AND_MODIFY"

class LLMProviderType(str, Enum):
    """Supported LLM providers."""
    ANTHROPIC = "anthropic"
    OLLAMA = "ollama"
    
# --- Basic Models ---

class SearchCriteria(BaseModel):
    """LLM-defined criteria for entity search (Process 1 output)."""
    entity_types: List[str] = Field(
        default_factory=list,
        description="Types to search: function, method, class, variable"
    )
    domain_keywords: List[str] = Field(
        default_factory=list,
        description="Domain-specific terms: date, time, auth, network, etc."
    )
    exclusion_patterns: List[str] = Field(
        default_factory=list,
        description="Patterns to exclude: test_, _internal, deprecated, etc."
    )

class SymbolInfo(BaseModel):
    """Symbol metadata from DB (Process 2 output)."""
    name: str
    kind: str  # function, method, class, variable
    line_start: int
    line_end: Optional[int] = None
    docstring: Optional[str] = None

class TaskDefinition(BaseModel):
    """Task definition for the planner."""
    task_id: str
    description: str
    target_files: List[str] = Field(default_factory=list)
    search_criteria: Optional[SearchCriteria] = None
    context: Dict[str, Any] = Field(default_factory=dict)

class PlannerResult(BaseModel):
    """Result container for planner output."""
    task_id: str
    success: bool
    plan_steps: List['FinalPlanStep'] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

# --- Plan Steps (The Pipeline) ---

class DraftPlanStep(BaseModel):
    """Plan step from Process 1 (LLM reasoning)."""
    action: ActionType
    target_file: str
    source_file: Optional[str] = None
    description: str
    search_criteria: Optional[SearchCriteria] = None
    
    @field_validator('target_file', 'source_file')
    @classmethod
    def normalize_path(cls, v):
        if v:
            return v.replace("\\", "/")
        return v
    
class EnrichedPlanStep(DraftPlanStep):
    """Plan step after Process 2 (Python enrichment)."""
    resolved_source_id: Optional[int] = None
    file_match_score: float = 0.0
    available_symbols: List[SymbolInfo] = Field(default_factory=list)
    file_stats: Dict[str, Any] = Field(default_factory=dict)

class FinalPlanStep(BaseModel):
    """
    Final plan step for Worker (minimal, clean).
    Does NOT inherit from EnrichedPlanStep to avoid carrying
    internal metadata (available_symbols, file_stats, etc.)
    """
    action: ActionType
    target_file: str
    source_file: Optional[str] = None
    description: str
    
    # Only worker-needed fields
    detected_entities: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    impact: Dict[str, Any] = Field(default_factory=dict)
    
    @field_validator('target_file', 'source_file')
    @classmethod
    def normalize_path(cls, v):
        if v:
            return v.replace("\\", "/")
        return v

class ProviderNormalizedResponse(BaseModel):
    """
    Normalized response structure that handles both Anthropic and OLLAMA formats.
    Provides provider-agnostic access to LLM responses.
    """
    provider: LLMProviderType
    content: str
    stop_reason: Optional[str] = None
    usage: Optional[Dict[str, Any]] = None
    raw_response: Dict[str, Any] = Field(default_factory=dict)
    
    @model_validator(mode='before')
    @classmethod
    def normalize_response(cls, data):
        """Normalize responses from different providers to common format."""
        if isinstance(data, dict):
            provider = data.get('provider')
            
            # Handle Anthropic response format
            if provider == LLMProviderType.ANTHROPIC or provider == 'anthropic':
                if 'content' in data and isinstance(data['content'], list):
                    # Anthropic returns content as list of blocks
                    content_blocks = data['content']
                    text_content = ''.join(
                        block.get('text', '') for block in content_blocks 
                        if block.get('type') == 'text'
                    )
                    data['content'] = text_content
                
                if 'stop_reason' not in data and 'stop_reason' in data:
                    data['stop_reason'] = data.get('stop_reason')
                
                if 'usage' not in data:
                    data['usage'] = {
                        'input_tokens': data.get('usage', {}).get('input_tokens'),
                        'output_tokens': data.get('usage', {}).get('output_tokens')
                    }
            
            # Handle OLLAMA response format
            elif provider == LLMProviderType.OLLAMA or provider == 'ollama':
                if 'response' in data and 'content' not in data:
                    data['content'] = data.get('response', '')
                
                if 'stop_reason' not in data:
                    data['stop_reason'] = data.get('done', False) and 'stop' or None
                
                if 'usage' not in data:
                    data['usage'] = {
                        'input_tokens': data.get('prompt_eval_count'),
                        'output_tokens': data.get('eval_count')
                    }
        
        return data

class ExecutionPlan(BaseModel):
    """Complete execution plan container matching LLM JSON."""
    thought_process: Optional[str] = None
    implementation_plan: Dict[str, Any] = Field(default_factory=dict)
    validation_summary: Optional[Dict[str, Any]] = None
    provider: Optional[LLMProviderType] = None
    loop_count: int = Field(default=1, description="Number of complete iterations (scan->plan->work) to execute")
    previous_artifacts: List[str] = Field(default_factory=list, description="Temporary files from previous loop iteration")
    
    @property
    def changes(self) -> List[Any]:
        return self.implementation_plan.get('changes', [])
    
    def ensure_changes(self) -> bool:
        """Verify that changes exist in the plan."""
        return len(self.changes) > 0
    
    @model_validator(mode='before')
    @classmethod
    def normalize_plan_structure(cls, data):
        """
        Normalize execution plan from different provider response formats.
        Handles both Anthropic and OLLAMA response structures.
        """
        if isinstance(data, dict):
            # If implementation_plan is empty but data has changes at root level
            if not data.get('implementation_plan') and 'changes' in data:
                data['implementation_plan'] = {'changes': data.get('changes', [])}
            
            # Ensure implementation_plan exists
            if 'implementation_plan' not in data:
                data['implementation_plan'] = {}
        
        return data