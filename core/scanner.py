import sqlite3
import hashlib
import os
import logging
from pathlib import Path
from parsers import get_parser

# Use standard logging instead of print where possible
logger = logging.getLogger(__name__)

def init_db(db_path: Path):
    """Initializes the database with V2 schema."""
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    cursor.executescript("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            type TEXT,
            size_bytes INTEGER,
            last_modified REAL,
            hash TEXT,
            docstring TEXT,
            content_preview TEXT,
            lines_count INTEGER,
            is_generated BOOLEAN DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_files_path ON files(path);

        CREATE TABLE IF NOT EXISTS symbols (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            kind TEXT NOT NULL,
            line_start INTEGER,
            line_end INTEGER,
            docstring TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_symbols_name ON symbols(name);

        CREATE TABLE IF NOT EXISTS imports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_file_id INTEGER NOT NULL,
            module_name TEXT NOT NULL,
            alias TEXT,
            FOREIGN KEY(source_file_id) REFERENCES files(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_imports_module ON imports(module_name);

        CREATE TABLE IF NOT EXISTS config_keys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            file_id INTEGER NOT NULL,
            key_path TEXT NOT NULL,
            value_type TEXT,
            FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE
        );
    """)
    conn.commit()
    return conn


def build_file_tree(root_path: str) -> dict:
    """Builds a nested dictionary representing the file tree structure."""
    root = Path(root_path)
    file_tree = {}
    
    # Directories to ignore
    ignore_dirs = {'.git', '.ase', '__pycache__', 'venv', 'node_modules'}
    
    for path in root.rglob("*"):
        # Skip ignore dirs
        if any(part in ignore_dirs for part in path.parts):
            continue
            
        parts = path.relative_to(root).parts
        
        # Navigate/Create dictionary
        current = file_tree
        for part in parts[:-1]:
            current = current.setdefault(part, {})
        
        if path.is_file():
            current[parts[-1]] = {
                "type": "file", 
                "rel_path": str(path.relative_to(root)).replace("\\", "/")
            }
        else:
            current.setdefault(parts[-1], {})
            
    return file_tree


def scan_logic_db(path: str = ".", db_filename: str = "ase.db"):
    """
    Executes incremental project scanning.
    Compares file hashes with DB to skip redundant work.
    """
    ASE_DIR = ".ase"
    base_path = Path(path).resolve()
    ase_path = base_path / ASE_DIR
    ase_path.mkdir(parents=True, exist_ok=True)
    
    db_path = ase_path / db_filename
    conn = init_db(db_path)
    cursor = conn.cursor()
    
    print(f"🔍 Scanning project to DB: {db_path}")

    # 1. Load current state from DB (Path -> (ID, Hash))
    cursor.execute("SELECT id, path, hash FROM files")
    db_state = {row[1]: {'id': row[0], 'hash': row[2]} for row in cursor.fetchall()}
    
    ignore_dirs = {'.git', 'venv', 'node_modules', '__pycache__', '.idea', '.vscode', 'build', 'dist', '.ase'}
    
    scanned_count = 0
    skipped_count = 0
    updated_count = 0
    
    current_files_on_disk = set()

    # 2. Iterate files on disk
    for file_path in base_path.rglob("*"):
        if any(part in ignore_dirs for part in file_path.parts): continue
        if not file_path.is_file(): continue

        try:
            rel_path = str(file_path.relative_to(base_path)).replace("\\", "/")
            current_files_on_disk.add(rel_path)
            
            # Hash Calculation
            file_bytes = file_path.read_bytes()
            current_hash = hashlib.md5(file_bytes).hexdigest()
            file_size = len(file_bytes)
            mtime = file_path.stat().st_mtime
            
            # Incremental Logic
            existing_record = db_state.get(rel_path)
            
            if existing_record:
                if existing_record['hash'] == current_hash:
                    # HASH MATCH: File unchanged -> SKIP
                    skipped_count += 1
                    continue
                else:
                    # HASH MISMATCH: File changed -> UPDATE
                    # First clear old symbols/imports to avoid duplicates
                    file_id = existing_record['id']
                    cursor.execute("DELETE FROM symbols WHERE file_id=?", (file_id,))
                    cursor.execute("DELETE FROM imports WHERE source_file_id=?", (file_id,))
                    cursor.execute("DELETE FROM config_keys WHERE file_id=?", (file_id,))
                    
                    updated_count += 1
            else:
                # NEW FILE -> INSERT
                file_id = None
                scanned_count += 1

            # Parsing (Only if New or Updated)
            ext = file_path.suffix.lower()
            parser = get_parser(ext)
            
            if not parser:
                # If no parser but file changed, update hash in DB anyway (generic file)
                # Create a dummy object
                result = type('obj', (object,), {'docstring': '', 'content_preview': '', 'lines_count': 0, 'is_generated': False, 'symbols': [], 'imports': [], 'config_keys': []})()
            else:
                result = parser.parse(file_path)

            if file_id:
                # UPDATE
                cursor.execute("""
                    UPDATE files 
                    SET size_bytes=?, last_modified=?, hash=?, docstring=?, content_preview=?, lines_count=?, is_generated=?
                    WHERE id=?
                """, (file_size, mtime, current_hash, result.docstring, result.content_preview, result.lines_count, result.is_generated, file_id))
            else:
                # INSERT
                cursor.execute("""
                    INSERT INTO files (path, type, size_bytes, last_modified, hash, docstring, content_preview, lines_count, is_generated)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (rel_path, ext, file_size, mtime, current_hash, result.docstring, result.content_preview, result.lines_count, result.is_generated))
                file_id = cursor.lastrowid

            # Insert Symbols/Imports (Common for Insert and Update)
            if result.symbols:
                cursor.executemany("INSERT INTO symbols (file_id, name, kind, line_start, line_end, docstring) VALUES (?, ?, ?, ?, ?, ?)", 
                                   [(file_id, s.name, s.kind, s.line_start, s.line_end, s.docstring) for s in result.symbols])
            
            if result.imports:
                cursor.executemany("INSERT INTO imports (source_file_id, module_name, alias) VALUES (?, ?, ?)", 
                                   [(file_id, i.module, i.alias) for i in result.imports])
            
            if result.config_keys:
                cursor.executemany("INSERT INTO config_keys (file_id, key_path, value_type) VALUES (?, ?, ?)", 
                                   [(file_id, k.key_path, k.value_type) for k in result.config_keys])

            if (scanned_count + updated_count) % 50 == 0:
                print(f"   ...processed {scanned_count + updated_count} files")
                conn.commit()

        except Exception as e:
            print(f"❌ Error scanning {file_path.name}: {e}")

    # 3. Cleanup (Files deleted from disk)
    deleted_count = 0
    for db_path_str, info in db_state.items():
        if db_path_str not in current_files_on_disk:
            cursor.execute("DELETE FROM files WHERE id=?", (info['id'],))
            deleted_count += 1

    conn.commit()
    conn.close()
    
    total_processed = scanned_count + updated_count
    print(f"✨ Scan Complete! New: {scanned_count}, Updated: {updated_count}, Skipped: {skipped_count}, Deleted: {deleted_count}")
    return db_path, True
