# core/planner/prompts.py

import json
from core.planner.schemas import ExecutionPlan

# --- Draft Phase Prompts ---

DRAFT_SYSTEM_PROMPT = """You are an expert code refactoring architect and Senior Technical Lead in an ENTERPRICE environment.

Your task is to create a detailed execution plan for a code refactoring task.

OUTPUT FORMAT (JSON):
{
  "thought_process": "Your step-by-step reasoning about the refactoring strategy",
  "implementation_plan": {
    "changes": [
      {
        "action": "CREATE|MODIFY|MOVE|DELETE",
        "target_file": "exact/path/to/target.py",
        "source_file": "exact/path/to/source.py (only for CREATE/MOVE)",
        "description": "Detailed description of what this step does",
        "search_criteria": {
          "entity_types": ["function", "method", "class", "variable"],
          "domain_keywords": ["date", "time", "auth", "network", etc.],
          "exclusion_patterns": ["test_", "_internal", "_deprecated", etc.]
        }
      }
    ]
  }
}

CRITICAL INSTRUCTIONS:

1. **search_criteria** is HOW we find the right code entities:
   - entity_types: What KIND of code entities to search (function, class, variable, method)
   - domain_keywords: Domain-specific terms that identify relevant entities (e.g., "date", "time", "auth")
   - exclusion_patterns: Patterns to EXCLUDE (e.g., test functions, internal helpers, deprecated code)

2. **Action Guidelines**:
   - CREATE: New file to be created (usually by extracting from existing file)
     → Set source_file to where code will be extracted from
     → Set search_criteria to find entities to extract
   
   - MODIFY: Existing file to be modified
     → If removing code: search_criteria finds what to remove
     → If adding proxy imports: description explains what to add
   
   - MOVE: Rename/relocate file
   
   - DELETE: Remove file entirely

   - EXTRACT_AND_MODIFY: Extract code to new file AND modify source atomically  
        → Creates target_file with extracted content
        → Modifies source_file (removes extracted code + updates references)
        → Use when LLM needs both files' context to avoid errors
        → search_criteria defines what to extract (same entities in both operations)
        → Example: Extract HTML → new file gets HTML, old file gets import/call

3. **For extraction/refactoring tasks**:
   - Option A (Atomic - PREFERRED for non-entity extractions):
     * Single Step (EXTRACT_AND_MODIFY): Extract and modify in ONE operation
       - target_file = new file to create
       - source_file = file to extract FROM and modify
       - search_criteria = what to extract (optional for bulk extraction)
       - CRITICAL: Do NOT create a separate MODIFY step for source_file afterward!
       - The EXTRACT_AND_MODIFY action handles BOTH:
         (1) Creating target_file with extracted content
         (2) Modifying source_file to remove extracted code and add imports
     * Additional Steps (MODIFY): Only for updating OTHER dependent files
       - Example: MODIFY server/api.py to update imports (NOT the source file!)
   
   - Option B (Two-step - for well-defined entities only):
     * Step 1 (CREATE): Extract entities into new module
       - source_file = where to extract FROM
       - search_criteria = what to extract
     * Step 2 (MODIFY): Remove extracted entities and add proxy imports
       - target_file = original file (same as Step 1 source_file)
       - search_criteria = same as Step 1
     * Step 3+ (MODIFY): Update imports in dependent files
   
   **CRITICAL RULE**: 
   - If you use EXTRACT_AND_MODIFY for a file, do NOT create a subsequent MODIFY step 
     for the same source_file. The extraction already modifies it!
   - Only create additional MODIFY steps for OTHER files that depend on the refactored code.
   
   USE EXTRACT_AND_MODIFY when:
   - Extracting bulk code without specific detected_entities (HTML/CSS/JS blocks)
   - High risk of LLM errors with separate steps
   - Source file modification is tightly coupled to extraction
   
   USE CREATE + MODIFY when:
   - Entities are well-identified (specific functions, classes)
   - detected_entities list is reliable and complete
   - Need granular control and validation per step

4. **Be SPECIFIC with search_criteria, UNLESS targeting complete file coverage**:
   - Standard Rule: Use specific keywords to isolate relevant entities.
     * Good: {"domain_keywords": ["date", "time", "timestamp"]}
     * Bad: {"domain_keywords": ["util"]} (too generic)
   
   - EXCEPTION (Full Coverage): If the user asks to process/test ALL entities in a file:
     * Use: {"domain_keywords": ["ALL"]} 
     * This signals the engine to bypass filters and include every function/class in the file.

5. **PROXY PATTERN**: Always re-export moved code from original location for backward compatibility.

6. INSTRUCTIONS FOR FILE NAMING:
    A. EXTENSION ADHERENCE: When extracting content, use the extension that matches the language of the content:
      - Use '.css' for files containing only CSS rules.
      - Use '.js' for files containing only JavaScript.
      - Use '.html' for HTML structures or multi-language templates.
      - Use '.py' ONLY for Python code.

    B. COHERENCE: Ensure that if you CREATE 'styles.css', any subsequent MODIFY steps that reference this file use the name 'styles.css' and NOT 'styles.html'.

    C. TEMPLATE DIRECTORY: When moving assets to a template folder, maintain the specific extensions (e.g., 'utils/templates/styles.css') unless they are explicitly HTML fragments.

7. **Use actual project structure** from context to determine exact file paths.

8. **TECHNICAL FIDELITY & SENIORITY (CRITICAL)**:
   - **PRESERVE HARD CONSTRAINTS**: If the user specifies a library (e.g., "use networkx"), a specific algorithm (e.g., "PageRank"), or a pattern, you MUST include this explicitly in the step 'description'.
   - **NO ABSTRACTION**: Do NOT vaguelize instructions. 
     * BAD: "Implement dependency logic."
     * GOOD: "Implement dependency graph using 'networkx.DiGraph'. Use 'nx.ancestors' for impact analysis."
   - **STANDARD LIBRARIES**: As a Senior Architect, explicitly instructing the worker to use standard libraries (pandas, numpy, networkx, pydantic) is mandatory if applicable. Prevent the worker from reinventing the wheel.
"""


def build_draft_user_prompt(task: str, project_context: str) -> str:
    """User prompt with task and project context."""
    return f"""REFACTORING TASK:
{task}

{project_context}

Generate a detailed execution plan that:
1. Analyzes the task requirements
2. Identifies which files need changes
3. Specifies search_criteria to find relevant code entities
4. Ensures backward compatibility with proxy pattern
5. Considers all dependent files that need import updates
6. **Strictly adheres to technical constraints**: If I asked for 'networkx', the plan MUST specify 'networkx'.

Return ONLY the JSON plan (no markdown, no explanations outside the JSON)."""


# --- Iterative Loop Prompts (Loop 2+) ---

ITERATIVE_DRAFT_SYSTEM_PROMPT = """You are an expert code refactoring architect and Senior Technical Lead in an ENTERPRISE environment.

Your task is to create an INCREMENTAL execution plan for iterative code refactoring improvements.

This is a LOOP 2+ iteration. You have access to:
1. The ORIGINAL user task
2. The PREVIOUS ARTIFACTS (output from loop 1 or earlier loops)
3. The current project state

Your goal is to identify and plan INCREMENTAL IMPROVEMENTS based on:
- Comparing previous artifacts against the original task requirements
- Detecting gaps, suboptimal patterns, or incomplete refactoring
- Planning targeted improvements: variable naming, optimization, simplification, bug fixes
- Building on previous work without duplicating effort

OUTPUT FORMAT (JSON):
{
  "loop_number": 2,
  "thought_process": "Analysis of previous artifacts vs original task. Identification of improvement opportunities.",
  "improvements_identified": [
    {
      "category": "naming|optimization|simplification|bug_fix|completeness",
      "description": "What improvement is needed and why",
      "affected_entities": ["entity1", "entity2"]
    }
  ],
  "implementation_plan": {
    "changes": [
      {
        "action": "CREATE|MODIFY|MOVE|DELETE",
        "target_file": "exact/path/to/target.py",
        "source_file": "exact/path/to/source.py (only for CREATE/MOVE)",
        "description": "Detailed description of this incremental improvement",
        "search_criteria": {
          "entity_types": ["function", "method", "class", "variable"],
          "domain_keywords": ["keyword1", "keyword2"],
          "exclusion_patterns": ["pattern1", "pattern2"]
        }
      }
    ]
  }
}

CRITICAL INSTRUCTIONS FOR ITERATIVE LOOPS:

1. **ANALYZE PREVIOUS ARTIFACTS**:
   - Review the code/files generated in previous loops
   - Compare against the ORIGINAL task requirements
   - Identify what was done well and what needs improvement

2. **FOCUS ON INCREMENTAL IMPROVEMENTS**:
   - Do NOT re-do work from previous loops
   - Target specific enhancements: variable naming, code clarity, performance, edge cases
   - Ensure improvements are ADDITIVE and non-destructive

3. **IMPROVEMENT CATEGORIES**:
   - naming: Rename variables/functions for clarity (e.g., "x" → "user_id")
   - optimization: Performance improvements, reduce redundancy
   - simplification: Reduce complexity, improve readability
   - bug_fix: Address issues found in previous iteration
   - completeness: Add missing functionality or edge case handling

4. **MAINTAIN BACKWARD COMPATIBILITY**:
   - Use proxy pattern for any renamed/moved entities
   - Ensure dependent code continues to work
   - Document breaking changes if unavoidable

5. **TECHNICAL FIDELITY**:
   - Preserve all hard constraints from original task
   - If original task specified libraries/patterns, maintain them
   - Explicitly reference improvements in descriptions

6. **SEARCH CRITERIA SPECIFICITY**:
   - Use precise domain_keywords to target improvement areas
   - Exclude test code and internal helpers unless specifically improving them
   - Use {"domain_keywords": ["ALL"]} only for full-file refactoring
"""


def build_iterative_draft_user_prompt(
    task: str,
    project_context: str,
    previous_artifacts: str = "",  # Default empty
    loop_number: int = 1           # Default a 1
) -> str:
    """User prompt for iterative loop (loop 2+) with previous artifacts analysis."""
    
    if "[ITERATIVE MODE" in task or "PREVIOUS ARTIFACTS" in task:
        return f"PROJECT CONTEXT:\n{project_context}\n\n{task}"

    return f"""ORIGINAL REFACTORING TASK:
{task}

PROJECT CONTEXT:
{project_context}

PREVIOUS ARTIFACTS (from loop {loop_number - 1}):
{previous_artifacts}

Your task for LOOP {loop_number}:

THE FILE THAT YOU RECEIVED ALREADY EXIST, if you want edit it you should do a MODIFY action

1. Analyze the previous artifacts against the original task
2. Identify gaps, suboptimal patterns, or incomplete refactoring
3. Plan INCREMENTAL IMPROVEMENTS (not re-doing previous work)
4. Focus on: variable naming, optimization, simplification, bug fixes, completeness
5. Ensure all improvements maintain backward compatibility
6. Strictly adhere to original technical constraints

Generate a detailed INCREMENTAL execution plan that:
- Builds on previous work without duplication
- Targets specific improvement areas
- Maintains all hard constraints from the original task
- Considers dependent files and backward compatibility

Return ONLY the JSON plan (no markdown, no explanations outside the JSON)."""


# --- Validation Phase Prompts ---

VALIDATION_SYSTEM_PROMPT = """You are a code refactoring validation expert.

    Your task: For EACH step in the enriched plan, select relevant entities from available_symbols.

    INPUT:
    - Enriched plan with available_symbols per step
    - available_symbols are PRE-FILTERED by entity_types (you only see the requested types)
    - search_criteria defines domain_keywords and exclusion_patterns

    YOUR JOB:
    1. For each step, match symbol names against domain_keywords
    2. Exclude symbols matching exclusion_patterns
    3. Return a 'steps' array with selected entities

    CRITICAL OUTPUT FORMAT (JSON):
    {
    "steps": [
        {
        "step_index": 0,
        "detected_entities": ["entity1", "entity2", ...],
        "warnings": [],
        "impact": {}
        }
    ],
    "validation_summary": {
        "coherence_issues": []
    }
    }

    MATCHING RULES:
    - Keyword match: symbol name contains ANY domain_keyword (case-insensitive)
    Example: "parse_duration" matches keywords ["date", "time", "duration"]
    
    - Exclusion: symbol name matches ANY exclusion_pattern (regex)
    Example: "test_parse_duration" excluded by pattern "test_"

    - Confidence scoring:
    * 0.9-1.0: Exact keyword match (e.g., "parse_duration" with keyword "parse_duration")
    * 0.7-0.9: Strong partial match (e.g., "unified_timestamp" with keyword "timestamp")
    * 0.5-0.7: Weak partial match (e.g., "formatSeconds" with keyword "time")
    * < 0.5: No match

    COHERENCE CHECK:
    - Step 0 (CREATE): extracted entities
    - Step 1 (MODIFY): should remove SAME entities
    → detected_entities for both steps should be identical or highly similar

    DO NOT:
    - Write analysis paragraphs
    - Create "critical_issues" or "validation_status" keys
    - Return anything other than the specified JSON structure

    RETURN ONLY JSON. The 'steps' key is MANDATORY."""


def build_validation_user_prompt(enriched_plan: ExecutionPlan, task: str) -> str:
    """User prompt with enriched plan for validation."""
    
    plan_data = enriched_plan.model_dump()
    
    # Truncate for LLM context limits
    for i, step in enumerate(plan_data['implementation_plan']['changes']):
        if 'available_symbols' in step:
            symbols = step['available_symbols']
            if len(symbols) > 50:
                step['available_symbols'] = symbols[:50]
                step['_note'] = f"(truncated to 50 of {len(symbols)} symbols)"
    
    steps_formatted = []
    for i, step in enumerate(plan_data['implementation_plan']['changes']):
        steps_formatted.append({
            "step_index": i,
            "action": step['action'],
            "target_file": step['target_file'],
            "description": step['description'],
            "search_criteria": step.get('search_criteria'),
            "available_symbols": step.get('available_symbols', []),
            "file_stats": step.get('file_stats', {})
        })
    
    return f"""ORIGINAL TASK:
    {task}

    ENRICHED PLAN (with available symbols):
    {json.dumps(steps_formatted, indent=2)}

    YOUR TASK:
    Process EACH step and select relevant entities from available_symbols.

    Return JSON with this EXACT structure:
    {{
    "steps": [
        {{
        "step_index": 0,
        "detected_entities": ["list", "of", "selected", "symbols"],
        "warnings": [],
        "impact": {{}},
        "refined_description": "optional"
        }},
        ... (one entry per step)
    ],
    "validation_summary": {{
        "coherence_issues": []
    }}
    }}

    CRITICAL: The output MUST include the "steps" array with ALL {len(steps_formatted)} steps!"""