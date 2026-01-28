import json
import re
from pathlib import Path
from .base import LanguageParser, ParseResult, ConfigKey

class ConfigParser(LanguageParser):
    def parse(self, file_path: Path) -> ParseResult:
        result = ParseResult()
        
        try:
            # Safe read handled by base class (MAX_SIZE check included)
            content_full = self._read_content_safely(file_path)
            lines = content_full.splitlines()
            
            # Preview and Metrics
            result.lines_count = len(lines)
            result.content_preview = self._generate_preview(content_full)
            
            ext = file_path.suffix.lower()
            keys_found = []

            # --- KEY EXTRACTION ---
            
            # 1. Key/Value formats (.env, .ini, .properties)
            if ext in {'.env', '.ini', '.properties', '.conf'}:
                # Capture 'KEY='
                matches = re.findall(r'^\s*([A-Za-z0-9_.-]+)\s*=', content_full, re.MULTILINE)
                for k in matches:
                    keys_found.append(ConfigKey(k, "string"))
            
            # 2. JSON (.json)
            elif ext == '.json':
                try:
                    data = json.loads(content_full)
                    if isinstance(data, dict):
                        for k in data.keys():
                            val_type = type(data[k]).__name__ # 'str', 'dict', 'list'
                            keys_found.append(ConfigKey(k, val_type))
                            
                        # Special handling: package.json scripts
                        if "scripts" in data and isinstance(data["scripts"], dict):
                            for s_name in data["scripts"]:
                                keys_found.append(ConfigKey(f"scripts.{s_name}", "script"))
                except:
                    keys_found.append(ConfigKey("INVALID_JSON", "error"))

            # 3. YAML/TOML (Regex Heuristic)
            elif ext in {'.yaml', '.yml', '.toml'}:
                matches = re.findall(r'^([A-Za-z0-9_-]+)\s*:', content_full, re.MULTILINE)
                for k in matches:
                    keys_found.append(ConfigKey(k, "yaml_root"))

            # 4. Markdown (.md) - Headers
            elif ext == '.md':
                matches = re.findall(r'^(#{1,3})\s+(.*)', content_full, re.MULTILINE)
                for h_level, h_text in matches:
                    keys_found.append(ConfigKey(h_text.strip(), f"header_{len(h_level)}"))

            # 5. SQL
            elif ext == '.sql':
                matches = re.findall(r'CREATE\s+(?:TABLE|VIEW|PROCEDURE)\s+(?:IF NOT EXISTS\s+)?["`]?(\w+)["`]?\s*\(', content_full, re.IGNORECASE)
                for table in matches:
                    keys_found.append(ConfigKey(table, "sql_table"))

            # 6. XML
            elif ext == '.xml':
                matches = list(set(re.findall(r'<([a-zA-Z0-9_-]+)(?:\s|>)', content_full)))[:20]
                for tag in matches:
                    keys_found.append(ConfigKey(tag, "xml_tag"))

            # Assign to result
            # Cap at 100 keys to prevent DB bloat with large files
            result.config_keys = keys_found[:100]

        except Exception as e:
            # In case of error (e.g., binary), return partial empty result
            result.content_preview = f"Error parsing: {str(e)}"
            
        return result
