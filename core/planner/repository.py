import sqlite3
import re
from pathlib import Path
from typing import List, Optional, Dict, Any
from .schemas import SymbolInfo
from core.graph import DependencyGraph


class PlannerRepository:
    """
    Repository layer for the Planner to access and analyze the codebase.
    Handles database connections, project statistics, and dependency graphs.
    """
    
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.graph = DependencyGraph(db_path)
        self.graph.build()


    def _get_db_connection(self) -> sqlite3.Connection:
        """Open and validate DB connection."""
        if not self.db_path.exists():
            raise FileNotFoundError(
                f"Database not found: {self.db_path}\n"
                f"Run 'ase scan' first to index the project."
            )
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        
        # Validate schema
        try:
            tables = {row['name'] for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )}
            required = {'files', 'symbols'} # imports is optional if not yet used
            if not required.issubset(tables):
                pass # Can log a warning but don't block if imports is missing
        except Exception:
            conn.close()
            raise
            
        return conn


    def get_project_summary(self) -> str:
        """Get high-level project structure for LLM context."""
        conn = self._get_db_connection()
        try:
            cursor = conn.execute("""
                SELECT path 
                FROM files 
                WHERE path NOT LIKE '%test%' 
                AND path NOT LIKE '%__pycache__%'
                ORDER BY path 
                LIMIT 50
            """)
            files = [row['path'] for row in cursor.fetchall()]
        finally:
            conn.close()


        # Group by top-level directory
        structure = {}
        for filepath in files:
            parts = filepath.split('/')
            top_dir = parts[0] if len(parts) > 1 else 'root'
            if top_dir not in structure:
                structure[top_dir] = []
            structure[top_dir].append(filepath)


        # Format nicely
        summary = "PROJECT STRUCTURE:\n"
        for directory, paths in sorted(structure.items()):
            summary += f"\n{directory}/\n"
            for path in paths[:10]:  # Limit per directory
                summary += f" - {path}\n"
            if len(paths) > 10:
                summary += f" ... and {len(paths) - 10} more files\n"
        
        return summary


    def get_file_stats(self, file_id: int, symbols: List[SymbolInfo] = None) -> Dict[str, Any]:
        """Get file statistics."""
        conn = self._get_db_connection()
        try:
            file_row = conn.execute(
                "SELECT path, content_preview FROM files WHERE id = ?", 
                (file_id,)
            ).fetchone()
        finally:
            conn.close()


        if not file_row:
            return {}


        stats = {
            "path": file_row['path'],
            "total_symbols": 0,
            "total_lines": 0
        }
        
        if symbols:
            # Count lines (approximate from last symbol)
            stats["total_lines"] = max([s.line_end or s.line_start for s in symbols], default=0)
            stats["total_symbols"] = len(symbols)
            
            # Count by type
            type_counts = {}
            for symbol in symbols:
                type_counts[symbol.kind] = type_counts.get(symbol.kind, 0) + 1
            stats["symbols_by_type"] = type_counts
            
        return stats


    def get_dependent_files(self, file_id: int) -> List[str]:
        """Find files that import from this file."""
        conn = self._get_db_connection()
        try:
            # Check if imports table exists first
            table_check = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='imports'"
            ).fetchone()
            
            if not table_check:
                return []


            cursor = conn.execute(
                """
                SELECT DISTINCT f.path
                FROM imports i
                JOIN files f ON i.file_id = f.id
                WHERE i.imported_from = (
                    SELECT path FROM files WHERE id = ?
                )
                """,
                (file_id,)
            )
            return [row['path'] for row in cursor.fetchall()]
        except Exception:
            return []
        finally:
            conn.close()


    def get_file_id(self, path: str) -> Optional[int]:
        """Resolves a file path to its DB ID using exact match."""
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM files WHERE path = ?", (path,))
            row = cursor.fetchone()
            return row['id'] if row else None
        finally:
            conn.close()


    def get_all_symbols(self, file_id: int) -> List[SymbolInfo]:
        """Retrieves ALL symbols for a file without filtering."""
        conn = self._get_db_connection()
        try:
            cursor = conn.cursor()
            query = """
                SELECT name, kind, line_start, line_end, docstring 
                FROM symbols 
                WHERE file_id = ?
                ORDER BY line_start ASC
            """
            cursor.execute(query, (file_id,))
            rows = cursor.fetchall()
            
            return [
                SymbolInfo(
                    name=row['name'],
                    kind=row['kind'],
                    line_start=row['line_start'],
                    line_end=row['line_end'],
                    docstring=row['docstring']
                ) for row in rows
            ]
        finally:
            conn.close()


    def get_symbols_filtered(self, file_id: int, entity_types: List[str] = None) -> List[SymbolInfo]:
        """
        Replicates the SQL logic of _fetch_symbols_filtered.
        Filters by kind (function, class, etc.) directly in the DB.
        """
        conn = self._get_db_connection()
        try:
            where_clauses = ["file_id = ?"]
            params = [file_id]
            
            if entity_types:
                type_mapping = {
                     'function': ['FUNCTION', 'METHOD'],
                     'class': ['CLASS'],
                     'variable': ['VARIABLE'],
                     'method': ['METHOD']
                }
                db_kinds = []
                for et in entity_types:
                    db_kinds.extend(type_mapping.get(et, [et]))
                
                # Remove duplicates
                db_kinds = list(set(db_kinds))
                
                if db_kinds:
                    placeholders = ','.join('?' * len(db_kinds))
                    where_clauses.append(f"kind IN ({placeholders})")
                    params.extend(db_kinds)
            
            query = f"""
                SELECT name, kind, line_start, line_end, docstring
                FROM symbols
                WHERE {' AND '.join(where_clauses)}
                ORDER BY line_start
            """
            
            cursor = conn.execute(query, params)
            rows = cursor.fetchall()
            
            return [
                SymbolInfo(
                    name=row['name'],
                    kind=row['kind'],
                    line_start=row['line_start'],
                    line_end=row['line_end'],
                    docstring=row['docstring']
                ) for row in rows
            ]
        finally:
            conn.close()


    def get_context_for_task(self, files: List[str]) -> List[str]:
        """
        Get expanded context for a task by including all callers/importers of the given files.
        Uses networkx graph traversal to find all files that depend on the input files.
        
        Args:
            files: List of file paths to get context for
            
        Returns:
            Deduplicated list containing original files plus all discovered callers
        """
        context = set(files)
        
        for file_path in files:
            callers = self.graph.get_callers_of(file_path)
            context.update(callers)
        
        return list(context)
    
    def search_symbols_by_name(self, query_names: List[str]) -> Dict[str, str]:
        """
        Search for a list of names (functions/classes) across the entire DB.
        Returns a dictionary: { 'symbol_name': 'path/to/file.py' }.
        Use this to tell the Planner where things are located.
        """
        if not query_names:
            return {}
            
        conn = self._get_db_connection()
        try:
            placeholders = ','.join('?' * len(query_names))
            sql = f"""
                SELECT s.name, f.path
                FROM symbols s
                JOIN files f ON s.file_id = f.id
                WHERE s.name IN ({placeholders})
                GROUP BY s.name  -- Take the first match if multiple exist
            """
            cursor = conn.execute(sql, query_names)
            return {row['name']: row['path'] for row in cursor.fetchall()}
        except Exception:
            return {}
        finally:
            conn.close()


    def find_file_by_name(self, filename: str) -> Optional[str]:
        """
        Find the full path of a file given its name (or ending part).
        E.g., "scanner.py" -> "core/scanner.py"
        """
        conn = self._get_db_connection()
        try:
            # Search paths ending with /filename or exactly matching filename
            query = """
            SELECT path FROM files 
            WHERE path LIKE ? OR path = ?
            """
            rows = conn.execute(query, (f"%/{filename}", filename)).fetchall()
            
            if not rows:
                return None
                
            # Filter backups and tests to prioritize source code
            valid_paths = []
            for row in rows:
                p = row['path']
                if not any(x in p for x in ['.ase', 'backups', 'tests', 'venv']):
                    valid_paths.append(p)
            
            if valid_paths:
                # Pick the shortest path (often most relevant: core/scanner.py vs core/utils/old/scanner.py)
                return min(valid_paths, key=len)
                
            return rows[0]['path'] if rows else None
            
        finally:
            conn.close()


    def load_previous_artifacts(self, artifact_paths: List[str]) -> Dict[str, Any]:
        """
        Load and parse temporary files (previous_artifacts) as if they were the real project state.
        Builds a representation equivalent to standard scan.
        
        Args:
            artifact_paths: List of paths to temporary files to load
            
        Returns:
            Dictionary containing:
            - 'files': List of files with metadata
            - 'symbols': Dictionary file_path -> list of symbols
            - 'dependencies': Graph of dependencies between files
        """
        if not artifact_paths:
            return {
                'files': [],
                'symbols': {},
                'dependencies': {}
            }
        
        result = {
            'files': [],
            'symbols': {},
            'dependencies': {}
        }
        
        for artifact_path in artifact_paths:
            path_obj = Path(artifact_path)
            
            if not path_obj.exists():
                continue
            
            try:
                content = path_obj.read_text(encoding='utf-8')
                relative_path = str(path_obj)
                
                # Add file to list
                result['files'].append({
                    'path': relative_path,
                    'size': len(content),
                    'lines': len(content.splitlines())
                })
                
                # Parse symbols from content
                symbols = self._extract_symbols_from_content(content, relative_path)
                result['symbols'][relative_path] = symbols
                
                # Extract dependencies (import statements)
                dependencies = self._extract_dependencies_from_content(content)
                result['dependencies'][relative_path] = dependencies
                
            except Exception as e:
                # Silent log for unreadable files
                continue
        
        return result
    
    def save_artifacts_for_next_loop(self, artifacts: Dict[str, Any], output_dir: Path) -> List[str]:
        """
        Save temporary files (artifacts) for the next loop.
        Creates physical files that can be loaded by the next loop.
        
        Args:
            artifacts: Dictionary containing files to save
            output_dir: Directory where to save temporary files
            
        Returns:
            List of paths to saved files
        """
        output_dir.mkdir(parents=True, exist_ok=True)
        saved_paths = []
        
        if not artifacts:
            return saved_paths
        
        # Save files contained in artifacts
        for file_path, content in artifacts.items():
            if isinstance(content, str):
                # It is the file content
                output_path = output_dir / Path(file_path).name
                try:
                    output_path.write_text(content, encoding='utf-8')
                    saved_paths.append(str(output_path))
                except Exception:
                    continue
            elif isinstance(content, dict):
                # It is a dictionary with metadata
                if 'content' in content:
                    output_path = output_dir / Path(file_path).name
                    try:
                        output_path.write_text(content['content'], encoding='utf-8')
                        saved_paths.append(str(output_path))
                    except Exception:
                        continue
        
        return saved_paths
    
    def get_artifacts_metadata(self, artifact_paths: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Extract metadata from temporary files without loading full content.
        Useful for next loop planning.
        
        Args:
            artifact_paths: List of paths to temporary files
            
        Returns:
            Dictionary with metadata for each file
        """
        metadata = {}
        
        for artifact_path in artifact_paths:
            path_obj = Path(artifact_path)
            
            if not path_obj.exists():
                continue
            
            try:
                content = path_obj.read_text(encoding='utf-8')
                
                metadata[str(path_obj)] = {
                    'size': len(content),
                    'lines': len(content.splitlines()),
                    'symbols': self._extract_symbols_from_content(content, str(path_obj)),
                    'dependencies': self._extract_dependencies_from_content(content)
                }
            except Exception:
                continue
        
        return metadata
    
    def merge_artifacts_with_scan(self, scan_data: Dict[str, Any], artifacts: Dict[str, Any]) -> Dict[str, Any]:
        """
        Merge scan data with temporary files from previous loop.
        Temporary files take precedence over scan data.
        
        Args:
            scan_data: Data from standard scan
            artifacts: Data from temporary files
            
        Returns:
            Unified dictionary with priority to temporary files
        """
        merged = {
            'files': [],
            'symbols': {},
            'dependencies': {}
        }
        
        # Add files from temporary (have priority)
        artifact_file_paths = {f['path'] for f in artifacts.get('files', [])}
        for file_info in artifacts.get('files', []):
            merged['files'].append(file_info)
        
        # Add files from scan that are not in temporary
        for file_info in scan_data.get('files', []):
            if file_info['path'] not in artifact_file_paths:
                merged['files'].append(file_info)
        
        # Merge symbols (priority to temporary)
        merged['symbols'].update(scan_data.get('symbols', {}))
        merged['symbols'].update(artifacts.get('symbols', {}))
        
        # Merge dependencies (priority to temporary)
        merged['dependencies'].update(scan_data.get('dependencies', {}))
        merged['dependencies'].update(artifacts.get('dependencies', {}))
        
        return merged
    
    def _extract_symbols_from_content(self, content: str, file_path: str) -> List[Dict[str, Any]]:
        """
        Extract symbols (functions, classes, variables) from file content.
        Simplified implementation based on regex matching.
        
        Args:
            content: File content
            file_path: File path (for logging)
            
        Returns:
            List of found symbols
        """
        symbols = []
        lines = content.splitlines()
        
        # Class pattern
        class_pattern = re.compile(r'^class\s+(\w+)(?:\(|:)')
        # Function/method pattern
        func_pattern = re.compile(r'^(?:\s*)def\s+(\w+)\s*\(')
        
        for line_num, line in enumerate(lines, 1):
            # Find classes
            class_match = class_pattern.match(line)
            if class_match:
                symbols.append({
                    'name': class_match.group(1),
                    'kind': 'CLASS',
                    'line_start': line_num,
                    'line_end': line_num,
                    'docstring': None
                })
            
            # Find functions/methods
            func_match = func_pattern.match(line)
            if func_match:
                symbols.append({
                    'name': func_match.group(1),
                    'kind': 'FUNCTION' if not line.startswith(' ') else 'METHOD',
                    'line_start': line_num,
                    'line_end': line_num,
                    'docstring': None
                })
        
        return symbols
    
    def _extract_dependencies_from_content(self, content: str) -> List[str]:
        """
        Extract dependencies (import statements) from file content.
        
        Args:
            content: File content
            
        Returns:
            List of imported modules/files
        """
        dependencies = []
        lines = content.splitlines()
        
        # Import statement patterns
        import_pattern = re.compile(r'^(?:from\s+[\w.]+\s+)?import\s+[\w.,\s*]+')
        from_pattern = re.compile(r'^from\s+([\w.]+)\s+import')
        
        for line in lines:
            line = line.strip()
            
            if import_pattern.match(line):
                # Extract module from "from X import Y"
                from_match = from_pattern.match(line)
                if from_match:
                    dependencies.append(from_match.group(1))
                elif line.startswith('import '):
                    # Extract module from "import X"
                    module = line.replace('import ', '').split(',')[0].strip()
                    dependencies.append(module)
        
        return list(set(dependencies))  # Remove duplicates
