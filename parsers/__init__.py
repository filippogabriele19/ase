from .python_parser import PythonParser
from .regex_parser import RegexParser
from .config_parser import ConfigParser

# --- ENTERPRISE MODULES (Placeholder) ---
# These modules are dynamically loaded only if an Enterprise license is present.
# Otherwise, we use Open Source fallbacks (Regex) or ignore the file.
# from ase_enterprise.parsers import JavaTreeSitterParser
# from ase_enterprise.parsers import CobolParser
# from ase_enterprise.parsers import PLSQLParser

# 1. Singleton Instances
_PYTHON_PARSER = PythonParser()
_REGEX_PARSER = RegexParser()
_CONFIG_PARSER = ConfigParser()

# 2. Extension -> Parser Mapping
_PARSERS_MAP = {
    # --- TIER A: SUPPORTED (Open Source) ---
    # Python (Full AST Support)
    '.py': _PYTHON_PARSER,
    
    # C-Style & Web (Regex Heuristics)
    '.js': _REGEX_PARSER,
    '.jsx': _REGEX_PARSER,
    '.ts': _REGEX_PARSER,
    '.tsx': _REGEX_PARSER,
    '.dart': _REGEX_PARSER,
    '.php': _REGEX_PARSER,
    '.go': _REGEX_PARSER,
    '.rs': _REGEX_PARSER,
    
    # --- TIER B: ENTERPRISE PREVIEW (Limited Support in OSS) ---
    # --- LEGACY & MAINFRAME (Enterprise Only) ---
    # These files are ignored in the OSS version.
    # '.java': None,         # Enterprise
    # '.cs': None,           # Enterprise
    # '.cbl': None,          # Enterprise
    # '.cob': None,          # Enterprise
    # '.pl': None,           # Enterprise
    # '.f90': None,          # Enterprise
    # '.c': None,            # Enterprise
    # '.cpp': None,          # Enterprise

    # Config / Data
    '.json': _CONFIG_PARSER,
    '.yaml': _CONFIG_PARSER,
    '.yml': _CONFIG_PARSER,
    '.env': _CONFIG_PARSER,
    '.toml': _CONFIG_PARSER,
    '.ini': _CONFIG_PARSER,
    '.xml': _CONFIG_PARSER,
    '.md': _CONFIG_PARSER,
    '.txt': _CONFIG_PARSER,
    '.sql': _CONFIG_PARSER, # Enterprise: uses PLSQLParser for Stored Procedures
}

def get_parser(extension: str):
    """
    Factory method: Returns the appropriate parser for the given extension.
    """
    return _PARSERS_MAP.get(extension.lower())
