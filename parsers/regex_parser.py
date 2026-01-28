import re
from pathlib import Path
from .base import LanguageParser, ParseResult, Symbol, Import

class RegexParser(LanguageParser):
    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult()
        
        try:
            content = self._read_content_safely(file_path)
            lines = content.splitlines()
            result.lines_count = len(lines)
            result.content_preview = self._generate_preview(content)
            
        except (UnicodeDecodeError, IOError) as e:
            result.content_preview = f"Error reading file: {str(e)}"
            return result

        # --- DEPENDENCY PATTERNS ---
        dep_patterns = [
            re.compile(r"import\s+.*?from\s+['\"](.*?)['\"]"), # ES6
            re.compile(r"require\s*\(['\"](.*?)['\"]\)")       # CommonJS
        ]

        # --- STRUCTURE PATTERNS ---
        class_pattern = re.compile(r'class\s+(\w+)(?:\s+extends\s+(\w+))?')
        
        # Heuristic Regex for JS/TS/Java/C# functions
        func_pattern = re.compile(
            r'(?:(?:static|async|public|private|protected)\s+)*'
            r'([\w<>\s\[\]]+)?'    # Optional Type
            r'\s+(\w+)\s*'          # Function Name
            r'\(([^)]*)\)'          # Arguments
        )

        arrow_pattern = re.compile(r'(?:const|let|var)\s+(\w+)\s*=\s*\(([^)]*)\)\s*=>')

        # --- DEPENDENCY EXTRACTION ---
        # Use set for deduplication
        found_deps = set()
        for pattern in dep_patterns:
            matches = pattern.findall(content)
            for m in matches:
                # Basic path cleanup
                dep_name = m.split('/')[-1].replace('.js', '').replace('.ts', '').replace('.dart', '')
                found_deps.add(dep_name)
        
        for dep in found_deps:
            result.imports.append(Import(module=dep))

        # --- LINE-BY-LINE SYMBOL SCAN ---
        for i, line in enumerate(lines, 1):
            line_str = line.strip()
            if not line_str or line_str.startswith(('//', '/*', '*')):
                continue

            # 1. Classes
            c_match = class_pattern.search(line_str)
            if c_match:
                name = c_match.group(1)
                # extends = c_match.group(2) # Not used in flat model for now
                result.symbols.append(Symbol(
                    name=name,
                    kind="CLASS",
                    line_start=i,
                    line_end=i, # End line unknown with regex
                    docstring=""
                ))
                continue

            # 2. Arrow Functions
            a_match = arrow_pattern.search(line_str)
            if a_match:
                name = a_match.group(1)
                result.symbols.append(Symbol(
                    name=name,
                    kind="FUNCTION",
                    line_start=i,
                    line_end=i,
                    docstring=""
                ))
                continue

            # 3. Standard Functions
            f_match = func_pattern.search(line_str)
            if f_match:
                name = f_match.group(2)
                # Filter common keywords that look like functions
                if name not in {'if', 'for', 'while', 'switch', 'catch', 'return', 'new', 'await', 'function'}:
                    result.symbols.append(Symbol(
                        name=name,
                        kind="FUNCTION",
                        line_start=i,
                        line_end=i,
                        docstring=""
                    ))

        return result
