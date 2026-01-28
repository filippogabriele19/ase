import os
import webbrowser
import uvicorn
import typer
from pathlib import Path
from typing import Dict, Any

# Local imports
from core.engine import ASEEngine
from core.scanner import build_file_tree
from utils.visualizer import ProjectVisualizer
from server.api import app as fastapi_app

app = typer.Typer(
    help="ASE (Autonomous Software Engineer) CLI - v1.1 Polyglot",
    add_completion=False,
    no_args_is_help=True
)

def launch_dashboard(port: int, project_path: Path) -> None:
    """Helper function to launch the FastAPI dashboard."""
    url = f"http://localhost:{port}"
    typer.secho(f"🚀 Starting ASE Dashboard on {url}", fg="green")
    
    # IPC: Pass project path to the server process via environment variable
    os.environ["ASE_PROJECT_ROOT"] = str(project_path.resolve())
    
    webbrowser.open(url)
    uvicorn.run(fastapi_app, host="127.0.0.1", port=port, log_level="error")

@app.command(name="scan")
def run_scan(path: Path = typer.Argument(".", help="Target directory to scan")) -> None:
    """[👀 SKELETON] Scans the directory to build the codebase context."""
    engine = ASEEngine(path)
    if engine.scan():
        typer.secho("\n✅ Scan complete.", fg=typer.colors.GREEN)
    else:
        raise typer.Exit(code=1)

@app.command(name="plan")
def run_plan(
    task: str = typer.Argument(..., help="Natural language description of the task"),
    path: Path = typer.Option(".", help="Project root directory")
) -> None:
    """[🧠 ARCHITECT] Analyzes requirements and creates an execution plan."""
    engine = ASEEngine(path)
    if engine.plan(task):
        typer.secho("\n✅ Planning complete.", fg=typer.colors.GREEN)
    else:
        raise typer.Exit(code=1)

@app.command(name="work")
def run_worker(
    path: Path = typer.Option(".", help="Project root directory"),
    auto_apply: bool = typer.Option(False, "--auto", help="Skip review phase (DANGEROUS)"),
    loop: int = typer.Option(1, "--loop", help="Number of refinement iterations")
) -> None:
    """[🔨 WORKER] Executes planned changes and drafts code for review."""
    engine = ASEEngine(path)
    stats: Dict[str, Any] = engine.work(loop=loop)
    
    if stats.get("status") == "review_needed":
        count = stats.get('drafted', 0)
        typer.secho(f"\n✨ {count} file(s) drafted for review.", fg=typer.colors.CYAN)
        
        if auto_apply:
            engine.apply_staged_changes()
            typer.secho("✅ Changes applied automatically.", fg=typer.colors.GREEN)
        else:
            typer.secho("\n👀 Launching Review UI...", fg=typer.colors.YELLOW)
            launch_dashboard(port=8000, project_path=path)

    elif stats.get("success") is False:
        typer.secho(f"❌ Error: {stats.get('error')}", fg=typer.colors.RED)
    else:
        typer.secho("⚠️ No changes needed.", fg=typer.colors.YELLOW)

@app.command(name="ui")
def run_ui(
    path: Path = typer.Argument(Path.cwd(), help="Project root directory"),
    port: int = typer.Option(8000, help="Server port")
) -> None:
    """🌐 Launches the web dashboard for interactive code review."""
    launch_dashboard(port, project_path=path)

@app.command("graph")
def run_graph(path: Path = typer.Argument(".", help="Path to visualize")) -> None:
    """[📊 VISUALIZER] Generates and opens a dependency graph of the project."""
    project_root = Path(path).resolve()
    
    # 1. Build tree in-memory
    file_tree = build_file_tree(str(project_root))
    
    # 2. Pass to visualizer
    viz = ProjectVisualizer(project_root)
    viz.generate_and_open(file_tree=file_tree, open_browser=True)

@app.command(name="apply")
def run_all(
    task: str = typer.Argument(..., help="Task description"),
    path: Path = typer.Option(".", help="Project root directory"),
    loop: int = typer.Option(1, "--loop", help="Max autonomous iterations")
) -> None:
    """[🚀 AUTO-LOOP] Full autonomous cycle: Scan -> Plan -> Work."""
    engine = ASEEngine(path)
    
    typer.secho(f"\n🚀 Mission starting: '{task}'", fg=typer.colors.BRIGHT_CYAN)
    
    # Optional progress callback for better UX
    def logger(msg: str, color: str = typer.colors.WHITE) -> None:
        typer.secho(msg, fg=color)

    stats = engine.run_autonomous_mission(
        task, 
        loop_count=loop,         
        on_progress=logger      
    )

    if stats.get("success"):
        drafted_count = stats.get("drafted", 0)
        
        if drafted_count > 0:
            typer.secho(f"\n✨ Mission accomplished! {drafted_count} files waiting for review.", fg=typer.colors.BRIGHT_GREEN, bold=True)
            typer.secho("\n👀 Launching Review UI...", fg=typer.colors.YELLOW)
            launch_dashboard(port=8000, project_path=path)
        else:
            typer.secho("\nMission accomplished! (No changes necessary) 🎯", fg=typer.colors.GREEN)
    else:
        typer.secho(f"\n❌ Mission failed: {stats.get('error')}", fg=typer.colors.RED)

@app.command(name="undo")
def run_undo(path: Path = typer.Argument(".")) -> None:
    """⏪ Reverts the project to the state before the last ASE execution."""
    engine = ASEEngine(path)
    if engine.undo():
        typer.secho("⏪ Project restored to previous state.", fg=typer.colors.GREEN)
    else:
        typer.secho("❌ No backup found to restore.", fg=typer.colors.RED)
        
if __name__ == "__main__":
    app()
