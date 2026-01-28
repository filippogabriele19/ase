import sqlite3
import networkx as nx
from typing import Set, List, Dict, Optional


class DependencyGraph:
    """
    Enterprise-grade dependency graph utilizing NetworkX.
    Maps file dependencies to enable precise impact analysis.
    """
    
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.graph = nx.DiGraph()
        self.is_built = False
        # Map: 'core.graph' -> 'core/graph.py'
        self._module_to_path: Dict[str, str] = {}


    def _build_module_map(self, paths: List[str]) -> None:
        """Builds a map of available project modules."""
        for path_str in paths:
            if not path_str.endswith('.py'):
                continue
            
            # 1. Standard mapping: core/graph.py -> core.graph
            module_name = path_str[:-3].replace('/', '.').replace('\\', '.')
            self._module_to_path[module_name] = path_str
            
            # 2. __init__ support: core/planner/__init__.py -> core.planner
            if path_str.endswith('__init__.py'):
                pkg_name = path_str[:-12].replace('/', '.').replace('\\', '.')
                self._module_to_path[pkg_name] = path_str


    def _resolve_import(self, import_str: str) -> Optional[str]:
        """
        Resolves an import string (e.g., 'core.ast_patcher.ASTPatchError')
        to its corresponding physical file (e.g., 'core/ast_patcher.py').
        Uses 'Peel-Back' strategy to handle Class/Function imports.
        """
        parts = import_str.split('.')
        
        # Peel-Back Strategy:
        # Try: core.ast_patcher.ASTPatchError (No)
        # Try: core.ast_patcher (Yes! Found)
        for i in range(len(parts), 0, -1):
            candidate_module = ".".join(parts[:i])
            if candidate_module in self._module_to_path:
                return self._module_to_path[candidate_module]
                
        return None


    def build(self, from_artifacts: Optional[Dict[str, List[str]]] = None) -> None:
        """
        Refreshes the graph structure from the SQLite database or from artifact data.
        
        Args:
            from_artifacts: Optional dict mapping file paths to their import lists.
                           If provided, builds graph from artifacts instead of database.
        """
        self.graph.clear()
        self._module_to_path.clear()
        
        try:
            if from_artifacts is not None:
                # Build graph from temporary files (previous_artifacts)
                self._build_from_artifacts(from_artifacts)
            else:
                # Standard build from database
                self._build_from_database()
            
            self.is_built = True
            print(f"[Graph] Built with {self.graph.number_of_nodes()} files and {self.graph.number_of_edges()} dependencies.")
            
        except sqlite3.Error as e:
            print(f"[Graph] Database error during build: {e}")
            self.is_built = False
        except Exception as e:
            print(f"[Graph] Error during build: {e}")
            self.is_built = False


    def _build_from_database(self) -> None:
        """Builds the graph by scanning the SQLite database."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            
            # 1. Load Files & Build Module Map
            cursor.execute("SELECT id, path FROM files")
            rows = cursor.fetchall()
            
            id_to_path = {}
            all_paths = []
            
            for row in rows:
                file_id = row['id']
                path_str = row['path']
                
                self.graph.add_node(path_str)
                id_to_path[file_id] = path_str
                all_paths.append(path_str)
            
            self._build_module_map(all_paths)


            # 2. Add Edges (Imports)
            cursor.execute("SELECT source_file_id, module_name FROM imports")
            
            resolved_count = 0
            unresolved = set()
            
            for row in cursor.fetchall():
                source_id = row['source_file_id']
                import_str = row['module_name'] # e.g., "core.ast_patcher.ASTPatchError"
                
                if source_id not in id_to_path:
                    continue
                
                importer_path = id_to_path[source_id]
                
                # Intelligent resolution
                target_path = self._resolve_import(import_str)
                
                if target_path:
                    # Avoid self-loops
                    if target_path != importer_path:
                        self.graph.add_edge(importer_path, target_path)
                        resolved_count += 1
                else:
                    unresolved.add(import_str)


            print(f"[Graph] Resolved {resolved_count} imports (Peel-back strategy active).")
            
            # Debug: Filter known standard libraries
            std_libs = {'typing', 'os', 'sys', 'pathlib', 'json', 'sqlite3', 'networkx', 'hashlib', 'abc', 'enum'}
            filtered_unresolved = [u for u in unresolved if u.split('.')[0] not in std_libs]
            
            if filtered_unresolved:
                print(f"[Graph] Unresolved (excluding stdlib): {', '.join(list(filtered_unresolved)[:5])}")


    def _build_from_artifacts(self, artifacts: Dict[str, List[str]]) -> None:
        """
        Builds the graph from temporary files (previous_artifacts).
        
        Args:
            artifacts: Dict mapping file paths to lists of imported module names.
                      Structure: {'core/graph.py': ['networkx', 'sqlite3', 'core.planner'], ...}
        """
        all_paths = list(artifacts.keys())
        
        # 1. Add all nodes
        for path_str in all_paths:
            self.graph.add_node(path_str)
        
        # 2. Build module map
        self._build_module_map(all_paths)
        
        # 3. Add edges based on imports
        resolved_count = 0
        unresolved = set()
        
        for importer_path, imports in artifacts.items():
            if importer_path not in self.graph:
                continue
            
            for import_str in imports:
                # Intelligent resolution
                target_path = self._resolve_import(import_str)
                
                if target_path:
                    # Avoid self-loops
                    if target_path != importer_path:
                        self.graph.add_edge(importer_path, target_path)
                        resolved_count += 1
                else:
                    unresolved.add(import_str)
        
        print(f"[Graph] Resolved {resolved_count} imports from artifacts (Peel-back strategy active).")
        
        # Debug
        std_libs = {'typing', 'os', 'sys', 'pathlib', 'json', 'sqlite3', 'networkx', 'hashlib', 'abc', 'enum'}
        filtered_unresolved = [u for u in unresolved if u.split('.')[0] not in std_libs]
        
        if filtered_unresolved:
            print(f"[Graph] Unresolved (excluding stdlib): {', '.join(list(filtered_unresolved)[:5])}")


    def get_callers_of(self, file_path: str) -> Set[str]:
        """Direct reverse dependencies: Who imports me?"""
        if not self.is_built: self.build()
        if not self.graph.has_node(file_path): return set()
        return set(self.graph.predecessors(file_path))


    def get_dependencies_of(self, file_path: str) -> Set[str]:
        """Direct forward dependencies: Who do I import?"""
        if not self.is_built: self.build()
        if not self.graph.has_node(file_path): return set()
        return set(self.graph.successors(file_path))


    def get_impacted_files(self, file_path: str) -> List[str]:
        """Transitive reverse dependencies (Ripple Effect)."""
        if not self.is_built: self.build()
        if not self.graph.has_node(file_path): return []
        return list(nx.ancestors(self.graph, file_path))


    def get_critical_path_score(self) -> Dict[str, float]:
        """PageRank score."""
        if not self.is_built: self.build()
        if self.graph.number_of_nodes() == 0: return {}
        return nx.pagerank(self.graph)
