from typing import List, Dict, Optional, Any
import logging
from pathlib import Path
import re
from tree_sitter_languages import get_language, get_parser


from .repository import PlannerRepository
from .utils import FileResolver
from .schemas import SymbolInfo


logger = logging.getLogger(__name__)


class ProjectNavigator:
    """
    Central intelligence for project navigation.
    Combines DB access, Fuzzy Matching, and Graph Dependency analysis.
    Supports both standard mode (loop 1) and iterative mode (loop 2+) with previous artifacts.
    Can navigate both scan results and temporary files from previous loops.
    """
    
    def __init__(self, db_path: Path, previous_artifacts: Optional[Dict[str, Any]] = None, temp_files_dir: Optional[Path] = None):
        self.repo = PlannerRepository(db_path)
        self.resolver = FileResolver(self.repo._get_db_connection()) 
        self.project_root = db_path.parent.parent
        
        self.temp_files_dir = temp_files_dir
        self.temp_file_cache = {}
        if temp_files_dir and temp_files_dir.exists():
            self._load_temp_files()
        
        self.previous_artifacts = previous_artifacts or {}
        self.is_iterative_mode = bool(previous_artifacts and len(previous_artifacts) > 0)
        
        if self.is_iterative_mode:
            logger.info(f"🔄 ProjectNavigator in ITERATIVE MODE with {len(previous_artifacts)} artifacts")
            if self.temp_files_dir:
                logger.info(f"📁 Using temporary files from: {self.temp_files_dir}")
        else:
            logger.info("📊 ProjectNavigator in STANDARD MODE (full project scan)")


    def _load_temp_files(self) -> None:
        """Loads temporary files from previous loop into cache."""
        if not self.temp_files_dir or not self.temp_files_dir.exists():
            return
        
        try:
            for temp_file in self.temp_files_dir.glob("**/*"):
                if temp_file.is_file():
                    try:
                        content = temp_file.read_text(encoding='utf-8')
                        rel_path = str(temp_file.relative_to(self.temp_files_dir)).replace("\\", "/")
                        self.temp_file_cache[rel_path] = content
                        logger.debug(f"Loaded temp file: {rel_path}")
                    except Exception as e:
                        logger.debug(f"Could not load temp file {temp_file}: {e}")
        except Exception as e:
            logger.warning(f"Error loading temporary files: {e}")


    def _get_file_content(self, file_path: str) -> Optional[str]:
        """
        Retrieves file content from:
        1. Temporary files cache (high priority)
        2. Project file system
        """
        # Try temp files first
        if file_path in self.temp_file_cache:
            logger.debug(f"Using temp file content for: {file_path}")
            return self.temp_file_cache[file_path]
        
        # Then try file system
        full_path = self.project_root / file_path
        if full_path.exists() and full_path.is_file():
            try:
                return full_path.read_text(encoding='utf-8')
            except Exception as e:
                logger.debug(f"Could not read file {file_path}: {e}")
        
        return None


    def resolve_path(self, ambiguous_path: str) -> Optional[str]:
        """Convert 'scanner.py' -> 'core/scanner.py' using fuzzy logic."""
        match = self.resolver.resolve(ambiguous_path)
        return match.path if match else None


    def find_symbol_definition(self, symbol_name: str) -> Optional[str]:
        """Finds the file defining a symbol."""
        # ✅ NEW: In iterative mode, check artifacts first
        if self.is_iterative_mode and "symbols" in self.previous_artifacts:
            artifact_symbols = self.previous_artifacts.get("symbols", {})
            if symbol_name in artifact_symbols:
                return artifact_symbols[symbol_name].get("file")
        
        # Use optimized logic
        res = self.repo.search_symbols_by_name([symbol_name])
        return res.get(symbol_name)


    def get_impact_analysis(self, file_path: str) -> Dict[str, Any]:
        """
        Returns what breaks if you touch this file.
        {
            "callers": ["api.py", "engine.py"],
            "criticality_score": 0.85
        }
        """
        # ✅ NEW: In iterative mode, use artifact dependencies
        if self.is_iterative_mode and "dependencies" in self.previous_artifacts:
            artifact_deps = self.previous_artifacts.get("dependencies", {})
            if file_path in artifact_deps:
                return artifact_deps[file_path]
        
        callers = self.repo.graph.get_callers_of(file_path)
        # We could add scoring logic here in the future
        return {
            "callers": list(callers),
            "count": len(callers)
        }


    def get_file_context(self, file_path: str) -> Dict[str, Any]:
        """Full context bundle for a file (stats, symbols, dependencies)."""
        # ✅ NEW: In iterative mode, use artifact file context
        if self.is_iterative_mode and "file_contexts" in self.previous_artifacts:
            artifact_contexts = self.previous_artifacts.get("file_contexts", {})
            if file_path in artifact_contexts:
                return artifact_contexts[file_path]
        
        file_id = self.repo.get_file_id(file_path)
        if not file_id: return {}
        
        return {
            "stats": self.repo.get_file_stats(file_id),
            "symbols": self.repo.get_all_symbols(file_id),
            "dependencies": self.get_impact_analysis(file_path)
        }


    def ground_task(self, task_description: str) -> str:
        """
        Analyzes the task description to identify relevant files and symbols.
        Returns a context string to guide the LLM.
        """
        ignore_words = {
            'modify', 'create', 'update', 'delete', 'function', 'class', 'file',
            'with', 'from', 'code', 'import', 'method', 'variable', 'using',
            'ensure', 'should', 'must', 'will', 'need', 'have', 'this', 'that',
            'return', 'value', 'parameter', 'bool', 'false', 'true', 'none',
            'extract', 'logic', 'database', 'db', 'schema', 'connection'
        }


        # 1) FILE CANDIDATES: capture "scanner.py", "core/scanner.py", "foo/bar.ts", etc.
        # re.finditer is better than findall with groups
        file_tokens = [m.group(0) for m in re.finditer(
            r'(?i)\b[\w./-]+\.(py|js|ts|tsx|jsx|java|c|cc|cpp|cxx|h|hpp|go|rs|php|rb|cs)\b',
            task_description
        )]


        # 2) SYMBOL CANDIDATES: identifiers
        symbol_tokens = re.findall(r'\b[a-zA-Z_][a-zA-Z0-9_]{3,}\b', task_description)
        symbol_tokens = [t for t in symbol_tokens if t.lower() not in ignore_words]


        hints = []


        # A) FILE Resolution (High Priority)
        for token in dict.fromkeys(file_tokens):  # dedup keeping order
            resolved = None


            # If it already has "/", try direct fuzzy resolution
            if "/" in token or "\\" in token:
                resolved = self.resolve_path(token)
            else:
                # Otherwise look up by filename (must be implemented in repo)
                resolved = self.repo.find_file_by_name(token)


            if resolved:
                hints.append(f"FILE: '{token}' -> '{resolved}' (EXACT PATH)")


        # B) SYMBOL Resolution
        for sym in dict.fromkeys(symbol_tokens[:10]):
            path = self.find_symbol_definition(sym)
            if not path:
                continue


            # You can add references/impact here if desired
            hints.append(f"SYMBOL: '{sym}' defined in '{path}' (EXACT PATH)")


        if not hints:
            return ""


        header = "[SYSTEM CONTEXT - VERIFIED FILES & SYMBOLS]:\n"
        footer = (
            "\n⚠️ CRITICAL PATH RULES:\n"
            "- Copy paths EXACTLY as shown above (no abbreviations).\n"
            "- If you see 'core/scanner.py', you MUST use 'core/scanner.py' in target_file/source_file.\n"
        )
        return header + "\n".join(hints) + footer


    def find_symbol_references(self, symbol_name: str, defining_file: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Find ALL usages of a symbol using Tree-sitter.
        Filters backups, tests, and other ignored directories.
        Supports both scan files and temporary files from previous loops.
        
        ✅ NEW: In iterative mode, uses artifact references if available.
        """
        logger.info(f"🔍 Finding all references to '{symbol_name}'...")
        
        # ✅ NEW: In iterative mode, check artifacts first
        if self.is_iterative_mode and "symbol_references" in self.previous_artifacts:
            artifact_refs = self.previous_artifacts.get("symbol_references", {})
            if symbol_name in artifact_refs:
                logger.info(f"✅ Using cached references for '{symbol_name}' from previous artifacts")
                return artifact_refs[symbol_name]
        
        if not defining_file:
            defining_file = self.find_symbol_definition(symbol_name)
            if not defining_file:
                return []
        
        results = []
        seen = set()
        
        # ✅ Directories to completely EXCLUDE
        ignore_dirs = {
            '.git', '.ase', '__pycache__', 'venv', '.venv', 'node_modules',
            '.idea', '.vscode', 'build', 'dist', '.pytest_cache', '.mypy_cache',
            'backups'
        }
        
        # Extension -> Language map
        lang_map = {
            '.py': 'python',
            '.js': 'javascript', '.jsx': 'javascript',
            '.ts': 'typescript', '.tsx': 'typescript',
            '.java': 'java',
            '.c': 'c', '.h': 'c',
            '.cpp': 'cpp', '.cc': 'cpp', '.cxx': 'cpp', '.hpp': 'cpp',
            '.go': 'go',
            '.rs': 'rust',
            '.rb': 'ruby',
            '.php': 'php',
            '.cs': 'c_sharp',
        }
        
        # ✅ NEW: Search in both temp files and project
        files_to_scan = []
        
        # Add temp files
        if self.temp_file_cache:
            for temp_file_path in self.temp_file_cache.keys():
                files_to_scan.append(('temp', temp_file_path))
        
        # Add project files
        for file_path in self.project_root.rglob("*"):
            if not file_path.is_file():
                continue
            
            try:
                rel_path = file_path.relative_to(self.project_root)
                rel_path_str = str(rel_path).replace("\\", "/")
            except ValueError:
                continue
            
            if any(ignored in rel_path.parts for ignored in ignore_dirs):
                logger.debug(f"Skipping ignored directory: {rel_path_str}")
                continue
            
            files_to_scan.append(('project', rel_path_str))
        
        # Process all files
        for source_type, file_path in files_to_scan:
            # ✅ FIX: Skip the defining file itself
            if file_path == defining_file:
                continue
            
            # Check extension
            ext = Path(file_path).suffix.lower()
            if ext not in lang_map:
                continue
            
            try:
                # Retrieve content from cache or file system
                if source_type == 'temp':
                    content = self.temp_file_cache.get(file_path)
                else:
                    content = self._get_file_content(file_path)
                
                if not content:
                    continue
                
                # Try Tree-sitter
                refs = self._find_calls_treesitter(content, symbol_name, lang_map[ext])
                
                # Fallback to regex
                if refs is None:
                    refs = self._find_calls_regex(content, symbol_name)
                
                # Add results
                for line_num, context in refs:
                    key = (file_path, line_num)
                    if key not in seen:
                        seen.add(key)
                        results.append({
                            "file": file_path,
                            "line": line_num,
                            "context": context,
                            "source": source_type
                        })
            
            except Exception as e:
                logger.debug(f"Could not scan {file_path}: {e}")
                continue
        
        logger.info(f"✅ Found {len(results)} references to '{symbol_name}' (excluding backups and tests)")
        return results


    def _find_calls_treesitter(self, content: str, symbol_name: str, language: str) -> Optional[List[tuple]]:
        """
        Use Tree-sitter to find calls in a language-aware manner.
        """
        try:
            # Import here to avoid hard dependency if not installed
            from tree_sitter_languages import get_parser
            
            parser = get_parser(language)
            tree = parser.parse(bytes(content, 'utf-8'))
            
            calls = []
            lines = content.splitlines()
            
            def visit_node(node):
                # Tree-sitter uses "call_expression" for most languages
                if node.type in ['call_expression', 'call']:
                    # Check if function name matches
                    function_node = node.child_by_field_name('function')
                    if function_node:
                        func_text = content[function_node.start_byte:function_node.end_byte]
                        
                        # ✅ Exact match or with module prefix (scanner.scan_logic_db)
                        if (symbol_name == func_text or 
                            func_text.endswith(f".{symbol_name}") or
                            func_text.endswith(f"::{symbol_name}")):
                            
                            line_num = node.start_point[0] + 1
                            if node.start_point[0] < len(lines):
                                context = lines[node.start_point[0]].strip()
                                calls.append((line_num, context))
                
                # Recurse
                for child in node.children:
                    visit_node(child)
            
            visit_node(tree.root_node)
            return calls
            
        except Exception as e:
            logger.debug(f"Tree-sitter parsing failed for {language}: {e}")
            return None


    def _find_calls_regex(self, content: str, symbol_name: str) -> List[tuple]:
        """
        Fallback: text regex to find calls.
        """
        calls = []
        lines = content.splitlines()
        
        # Pattern: symbol_name( or module.symbol_name( or module::symbol_name(
        pattern = re.compile(
            rf'(?:^|[^\w])({re.escape(symbol_name)})\s*\(',
            re.MULTILINE
        )
        
        for line_num, line in enumerate(lines, start=1):
            # Skip obvious comments
            stripped = line.strip()
            if (stripped.startswith('//') or 
                stripped.startswith('#') or 
                stripped.startswith('/*') or
                stripped.startswith('*')):
                continue
            
            # Skip definitions
            if (f'def {symbol_name}' in line or
                f'function {symbol_name}' in line or
                f'class {symbol_name}' in line):
                continue
            
            # Search pattern
            if pattern.search(line):
                calls.append((line_num, line.strip()))
        
        return calls
