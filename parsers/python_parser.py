import ast
from pathlib import Path
from .base import LanguageParser, ParseResult, Symbol, Import

class PythonParser(LanguageParser):
    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult()
        
        try:
            content = self._read_content_safely(file_path)
            result.lines_count = len(content.splitlines())
            result.content_preview = self._generate_preview(content)
            
            tree = ast.parse(content, filename=str(file_path))
            result.docstring = ast.get_docstring(tree) or ""
            
        except (SyntaxError, UnicodeDecodeError, ValueError) as e:
            # If AST parsing fails, we still save the preview and error message
            if not result.content_preview:
                result.content_preview = f"Error reading file: {str(e)}"
            return result

        # Manual Visitor pattern to populate lists
        for node in tree.body:
            # 1. Imports
            if isinstance(node, ast.Import):
                for n in node.names:
                    result.imports.append(Import(module=n.name, alias=n.asname))
            
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                for n in node.names:
                    full_import = f"{module}.{n.name}" if module else n.name
                    result.imports.append(Import(module=full_import, alias=n.asname))

            # 2. Top-Level Functions
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                result.symbols.append(self._create_symbol_from_func(node))

            # 3. Classes and Methods
            elif isinstance(node, ast.ClassDef):
                # Add the class itself
                result.symbols.append(Symbol(
                    name=node.name,
                    kind="CLASS",
                    line_start=node.lineno,
                    line_end=node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                    docstring=ast.get_docstring(node) or ""
                ))
                
                # Add methods as symbols (optionally qualified)
                for item in node.body:
                    if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        method_sym = self._create_symbol_from_func(item)
                        method_sym.kind = "METHOD" # Distinguish methods from pure functions
                        # Optional: Qualify name (ClassName.method)
                        # method_sym.name = f"{node.name}.{item.name}" 
                        result.symbols.append(method_sym)

            # 4. Global Variables (Assignments)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        result.symbols.append(Symbol(
                            name=target.id,
                            kind="VARIABLE",
                            line_start=node.lineno,
                            line_end=node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
                            docstring=""
                        ))

        return result

    def _create_symbol_from_func(self, node) -> Symbol:
        """
        Helper to convert an AST function node into a Symbol.
        
        Handles function and async function nodes, accounting for decorators
        in the line range calculation to ensure complete source extraction.
        """
        # Calculate line_start accounting for decorators
        line_start = node.lineno
        if hasattr(node, 'decorator_list') and node.decorator_list:
            # Get the line number of the first decorator
            line_start = node.decorator_list[0].lineno
        
        return Symbol(
            name=node.name,
            kind="FUNCTION",
            line_start=line_start,
            line_end=node.end_lineno if hasattr(node, 'end_lineno') else node.lineno,
            docstring=ast.get_docstring(node) or ""
        )
