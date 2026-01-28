import json
import webbrowser
from pathlib import Path
from string import Template
from .mermaid_gen import generate_mermaid


# Load HTML template
_TEMPLATE_PATH = Path(__file__).parent / "templates" / "graph_templates.html"
# Ensure template exists or handle gracefully if this is a fresh install without templates
if _TEMPLATE_PATH.exists():
    _HTML_TEMPLATE = Template(_TEMPLATE_PATH.read_text(encoding="utf-8"))
else:
    # Fallback or error placeholder if template is missing
    _HTML_TEMPLATE = Template("<html><body><h1>Template not found</h1><pre>$code</pre></body></html>")


class ProjectVisualizer:
    """Handles the generation and rendering of project structure visualizations."""

    def __init__(self, project_root: Path):
        self.root = Path(project_root).resolve()
        self.map_path = self.root / ".ase" / "project_map.json"
        self.html_path = self.root / ".ase" / "graph.html"


    def generate_and_open(self, file_tree=None, open_browser=True):
        """
        Generates the Mermaid graph from the file tree and optionally opens it in the browser.
        
        Args:
            file_tree: Dictionary representing the project file structure.
            open_browser: Boolean flag to automatically open the generated HTML.
        """
        if not file_tree:
            print("❌ Error: No 'file_tree' data provided for visualization.")
            return
        
        try:
            # Generate Mermaid code from provided data
            mermaid_code = generate_mermaid(file_tree, max_depth=4)
            
            # Build HTML content
            html_content = self._build_html("ASE Project Structure", mermaid_code)
            
            # Write to file
            self.html_path.write_text(html_content, encoding="utf-8")
            print(f"✅ Graph generated: {self.html_path}")
            
            if open_browser:
                webbrowser.open(f"file://{self.html_path}")
        except Exception as e:
            print(f"❌ Error during visualization: {e}")


    def _build_html(self, title, code):
        """Substitutes values into the HTML template."""
        return _HTML_TEMPLATE.substitute(title=title, code=code)
