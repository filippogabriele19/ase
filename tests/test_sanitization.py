# test_sanitization.py (per verificare)

import json
from core.planner.strategies.draft import DraftGenerator
from core.planner.schemas import ExecutionPlan, DraftPlanStep, ActionType

# Simula il draft problematico
draft_data = {
    "thought_process": "...",
    "implementation_plan": {
        "changes": [
            {
                "action": "EXTRACT_AND_MODIFY",
                "target_file": "utils/templates/visualization.html",
                "source_file": "utils/visualizer.py",
                "description": "Extract HTML...",
                "search_criteria": {"entity_types": ["variable", "string"], "domain_keywords": ["html"]}
            },
            {
                "action": "MODIFY",
                "target_file": "utils/visualizer.py",  # 👈 STESSO FILE!
                "source_file": None,
                "description": "Update visualizer.py...",
                "search_criteria": {"entity_types": ["function"], "domain_keywords": ["render"]}
            },
            {
                "action": "MODIFY",
                "target_file": "server/api.py",  # 👈 FILE DIVERSO, OK
                "source_file": None,
                "description": "Update api.py...",
                "search_criteria": {"entity_types": ["import"], "domain_keywords": ["visualizer"]}
            }
        ]
    }
}

plan = ExecutionPlan(**draft_data)
plan.implementation_plan['changes'] = [
    DraftPlanStep(**s) for s in plan.implementation_plan['changes']
]

generator = DraftGenerator(None)
sanitized_plan = generator._sanitize_plan(plan)

print(f"Before: {len(draft_data['implementation_plan']['changes'])} steps")
print(f"After: {len(sanitized_plan.implementation_plan['changes'])} steps")
print("\nRemaining steps:")
for i, step in enumerate(sanitized_plan.implementation_plan['changes']):
    print(f"  {i}: {step.action} → {step.target_file}")

# Output atteso:
# Before: 3 steps
# After: 2 steps  ✅
# Remaining steps:
#   0: EXTRACT_AND_MODIFY → utils/templates/visualization.html
#   1: MODIFY → server/api.py
