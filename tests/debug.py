import sqlite3
import csv
import os
from pathlib import Path

def get_table_info(cursor, table_name):
    """Recupera i nomi delle colonne di una tabella."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns_info = cursor.fetchall()
    # columns_info è una lista di tuple (cid, name, type, notnull, dflt_value, pk)
    # Noi vogliamo solo i nomi (indice 1)
    return [col[1] for col in columns_info]

def export_table(cursor, table_name, output_filename, order_by=None):
    """Esporta una tabella intera adattandosi alle colonne esistenti."""
    print(f"\n📂 Exporting Table: {table_name}...")
    
    # 1. Ottieni colonne
    columns = get_table_info(cursor, table_name)
    if not columns:
        print(f"   ⚠️ Table {table_name} not found or empty schema.")
        return

    print(f"   Found columns: {columns}")

    # 2. Costruisci query dinamica
    query = f"SELECT {', '.join(columns)} FROM {table_name}"
    if order_by and order_by in columns:
        query += f" ORDER BY {order_by}"
    
    cursor.execute(query)
    rows = cursor.fetchall()

    # 3. Scrivi CSV
    with open(output_filename, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow(columns) # Header
        writer.writerows(rows)
        
    print(f"   ✅ Saved {len(rows)} rows to {output_filename}")

def export_project_structure():
    # 1. Locate the DB
    possible_paths = [
        Path(".ase/ase.db"),
        Path("../.ase/ase.db"),
        Path("ase.db"),
    ]
    
    db_path = None
    for p in possible_paths:
        if p.exists():
            db_path = p.resolve()
            break

    if not db_path:
        # Fallback: cerca ricorsivamente
        found = list(Path(".").rglob("ase.db"))
        if found:
            db_path = found[0].resolve()
        else:
            print("❌ No database found.")
            return

    print(f"✅ Using database: {db_path}")

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Esporta tabella FILES
        export_table(cursor, "files", "debug_files.csv", order_by="path")

        # Esporta tabella SYMBOLS
        export_table(cursor, "symbols", "debug_symbols.csv", order_by="file_id")

    except Exception as e:
        print(f"❌ Error exporting DB: {e}")
    finally:
        if 'conn' in locals(): conn.close()

if __name__ == "__main__":
    export_project_structure()
