import os
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse
from pathlib import Path
import uvicorn
from core.safety import SafetyManager
from utils.visualizer import ProjectVisualizer
from core import scanner
from core.engine import ASEEngine
from llm.factory import LLMFactory
import json


app = FastAPI()


# Initialize once (or per request)
root = Path(os.getcwd())
safety = SafetyManager(root)


# Generate a transaction ID for this server session (or per action)
session_id = safety.get_transaction_id() 


# Supported LLM providers
SUPPORTED_PROVIDERS = ["anthropic", "ollama", "openai"]
DEFAULT_PROVIDER = "anthropic"


# Provider configuration documentation
PROVIDER_CONFIGS = {
    "anthropic": {
        "description": "Anthropic Claude API",
        "required_fields": ["api_key"],
        "optional_fields": ["model", "max_tokens"]
    },
    "ollama": {
        "description": "Local OLLAMA instance",
        "required_fields": ["base_url"],
        "optional_fields": ["model", "timeout"]
    },
    "openai": {
        "description": "OpenAI API",
        "required_fields": ["api_key"],
        "optional_fields": ["model", "organization"]
    }
}


def get_project_root() -> Path:
    env_root = os.getenv("ASE_PROJECT_ROOT")
    if env_root:
        return Path(env_root).resolve()
    return Path(os.getcwd()).resolve()


def validate_provider(provider_type: str) -> bool:
    """Validate if provider is supported"""
    return provider_type.lower() in SUPPORTED_PROVIDERS


def validate_loop_count(loop_count: int) -> bool:
    """Validate if loop_count is within acceptable range"""
    return 1 <= loop_count <= 10


def parse_llm_config(config_str: str = None) -> dict:
    """Parse LLM configuration from JSON string"""
    if not config_str:
        return {}
    try:
        return json.loads(config_str)
    except json.JSONDecodeError:
        return {}


def load_html_template() -> str:
    """Load HTML template from utils/templates/api_templates.html"""
    template_path = Path(__file__).parent.parent / "utils" / "templates" / "api_templates.html"
    if template_path.exists():
        return template_path.read_text(encoding="utf-8")
    else:
        return "<html><body>Template not found</body></html>"


@app.get("/")
def home():
    html_content = load_html_template()
    return HTMLResponse(html_content)


@app.get("/api/changes")
def get_changes():
    root = get_project_root() 
    stage_dir = root / ".ase" / "stage"
    changes = []
    
    if stage_dir.exists():
        for f in stage_dir.rglob("*"):
            if f.is_file():
                rel_path = f.relative_to(stage_dir)
                orig_path = root / rel_path
                
                original_content = orig_path.read_text(encoding="utf-8") if orig_path.exists() else "(New File)"
                proposed_content = f.read_text(encoding="utf-8")
                
                changes.append({
                    "file": str(rel_path),
                    "original": original_content, 
                    "proposed": proposed_content  
                })
    return {"changes": changes}


@app.get("/api/providers")
def get_providers():
    """Get list of supported LLM providers and their configurations"""
    return {
        "supported_providers": SUPPORTED_PROVIDERS,
        "default_provider": DEFAULT_PROVIDER,
        "configurations": PROVIDER_CONFIGS
    }


@app.post("/api/execute")
def execute_task(
    task: str = Query(...),
    llm_provider: str = Query(DEFAULT_PROVIDER),
    llm_config: str = Query(None),
    loop: int = Query(1)
):
    """
    Execute a task with the specified LLM provider and loop count.
    
    Query Parameters:
    - task: Task description or identifier (required)
    - llm_provider: LLM provider to use (default: 'anthropic')
      Supported: 'anthropic', 'ollama', 'openai'
    - llm_config: JSON string with provider-specific configuration
      Example: '{"api_key": "sk-...", "model": "gpt-4"}'
    - loop: Ralph loop iteration count (default: 1, range: 1-10)
      Controls the number of refinement iterations for planning and refactoring.
      Loop 1: Initial planning and refactoring
      Loop 2+: Iterative refinement based on previous artifacts and analysis
    """
    # Validate provider
    if not validate_provider(llm_provider):
        return {
            "status": "error",
            "message": f"Unsupported provider: {llm_provider}. Supported: {SUPPORTED_PROVIDERS}"
        }
    
    # Validate loop
    if not validate_loop_count(loop):
        return {
            "status": "error",
            "message": f"Invalid loop: {loop}. Must be between 1 and 10"
        }
    
    # Parse LLM configuration
    config = parse_llm_config(llm_config)
    
    # Initialize LLM provider
    try:
        llm_provider_instance = LLMFactory.get_provider(llm_provider, config)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to initialize LLM provider: {str(e)}"
        }
    
    # Initialize Engine with loop support
    try:
        root = get_project_root()
        engine = ASEEngine(root=root, llm_provider=llm_provider_instance)
        
        # Execute task with loop parameter
        results = engine.work(
            task=task,
            loop=loop,
            transaction_id=session_id
        )
        
        # Collect results from all loops
        loop_results = []
        temp_files = []
        
        if isinstance(results, dict):
            loop_results = results.get("loop_results", [])
            temp_files = results.get("temp_files", [])
        elif isinstance(results, list):
            loop_results = results
        
        return {
            "status": "completed",
            "task": task,
            "provider": llm_provider,
            "loop": loop,
            "transaction_id": session_id,
            "loop_results": loop_results,
            "temp_files": temp_files,
            "total_loops_executed": len(loop_results)
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Task execution failed: {str(e)}"
        }


@app.post("/api/approve")
def approve_change(
    file: str,
    llm_provider: str = Query(DEFAULT_PROVIDER),
    llm_config: str = Query(None),
    loop: int = Query(1)
):
    """
    Approve a change and apply it to the project.
    
    Query Parameters:
    - file: Path to the file to approve
    - llm_provider: LLM provider to use (default: 'anthropic')
      Supported: 'anthropic', 'ollama', 'openai'
    - llm_config: JSON string with provider-specific configuration
      Example: '{"api_key": "sk-...", "model": "gpt-4"}'
    - loop: Ralph loop iteration count (default: 1, range: 1-10)
      Controls the number of refinement iterations for planning and refactoring.
      Loop 1: Initial planning and refactoring
      Loop 2+: Iterative refinement based on previous artifacts and analysis
    """
    # Validate provider
    if not validate_provider(llm_provider):
        return {
            "status": "error",
            "message": f"Unsupported provider: {llm_provider}. Supported: {SUPPORTED_PROVIDERS}"
        }
    
    # Validate loop
    if not validate_loop_count(loop):
        return {
            "status": "error",
            "message": f"Invalid loop: {loop}. Must be between 1 and 10"
        }
    
    # Parse LLM configuration
    config = parse_llm_config(llm_config)
    
    # Initialize LLM provider
    try:
        llm_provider_instance = LLMFactory.get_provider(llm_provider, config)
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to initialize LLM provider: {str(e)}"
        }
    
    root = get_project_root() 
    stage_file = root / ".ase" / "stage" / file
    dest_file = root / file
    plan_file = root / ".ase" / "plan.json"
    
    if stage_file.exists():
        # 1. Backup Code
        if dest_file.exists():
            safety.create_backup(dest_file, transaction_id=session_id)
            
        # 2. Archive Plan (Only the first time it is called for this batch)
        # Heuristic check: if the plan still exists in the .ase root, we archive it
        # (Note: here we COPY it. We will delete it only at the end of the session or manually)
        if plan_file.exists():
             # Try to recover the task name from the json for a better filename
             try:
                 data = json.loads(plan_file.read_text())
                 task_name = data.get("task", "unknown_task")
                 safety.archive_plan(plan_file, task_name)
             except:
                 safety.archive_plan(plan_file)

        # 3. Apply Change
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        dest_file.write_text(stage_file.read_text(encoding="utf-8"), encoding="utf-8")
        stage_file.unlink()
        
        # 4. Generate visualization
        try:
            file_tree = scanner.build_file_tree(str(root))
            visualizer = ProjectVisualizer(root)
            visualizer.generate_and_open(file_tree=file_tree, open_browser=False)
        except Exception as e:
            print(f"Visualization generation failed: {e}")
        
        return {
            "status": "applied",
            "provider": llm_provider,
            "file": file,
            "loop": loop
        }
    return {"status": "error", "message": "Stage file not found"}


@app.post("/api/discard")
def discard_change(file: str):
    root = get_project_root() 
    stage_file = root / ".ase" / "stage" / file
    if stage_file.exists():
        stage_file.unlink()
    return {"status": "discarded"}


def start_server(port=8000):
    uvicorn.run(app, host="127.0.0.1", port=port)
