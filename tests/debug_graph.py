import argparse
import json
import csv
import sys
import os
from pathlib import Path
from typing import Dict, List, Set, Tuple, Optional
import networkx as nx

# Add root to path for imports
sys.path.insert(0, str(Path(__file__).parent))

# FIX 1: Import corretto
from core.graph import DependencyGraph

# Mock MermaidGenerator se non esiste, per evitare crash
try:
    from utils.mermaid_gen import MermaidGenerator
except ImportError:
    class MermaidGenerator:
        def generate_from_graph(self, graph):
            return "Mermaid generator not found."

class DebugGraph:
    """Debug utilities for analyzing dependency graphs."""
    
    def __init__(self, graph: Optional[nx.DiGraph] = None):
        """Initialize debug graph with optional networkx DiGraph."""
        self.graph = graph or nx.DiGraph()
        self.mermaid_gen = MermaidGenerator()
    
    def load_from_db(self, db_path_str: str = None):
        """Load dependency graph from SQLite DB."""
        # FIX 3: Default path intelligente
        if not db_path_str:
            db_path_str = str(Path(".ase/ase.db").resolve())
            
        print(f"Loading graph from: {db_path_str}")
        
        try:
            dep_graph = DependencyGraph(db_path_str)
            # FIX 2: Chiamata esplicita a build()
            dep_graph.build()
            self.graph = dep_graph.graph
            return True
        except Exception as e:
            print(f"Error loading graph: {e}")
            return False
    
    def get_statistics(self) -> Dict:
        """Get graph statistics."""
        stats = {
            "node_count": self.graph.number_of_nodes(),
            "edge_count": self.graph.number_of_edges(),
            "density": nx.density(self.graph) if self.graph.number_of_nodes() > 0 else 0,
            "is_dag": nx.is_directed_acyclic_graph(self.graph) if self.graph.number_of_nodes() > 0 else False,
        }
        
        if self.graph.number_of_nodes() > 0:
            stats["connected_components"] = nx.number_weakly_connected_components(self.graph)
        
        return stats
    
    def detect_cycles(self) -> List[List[str]]:
        """Detect circular dependencies using simple cycles."""
        try:
            cycles = list(nx.simple_cycles(self.graph))
            return cycles
        except Exception:
            return []
    
    def analyze_dependency_path(self, source: str, target: str) -> Optional[List[str]]:
        """Analyze shortest dependency path between two nodes."""
        try:
            if source not in self.graph or target not in self.graph:
                return None
            path = nx.shortest_path(self.graph, source, target)
            return path
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None
    
    def impact_analysis(self, node: str) -> Dict[str, Set[str]]:
        """Analyze impact of a node using ancestors and descendants."""
        if node not in self.graph:
            return {"ancestors": set(), "descendants": set()}
        
        return {
            "ancestors": list(nx.ancestors(self.graph, node)),
            "descendants": list(nx.descendants(self.graph, node)),
        }
    
    def get_node_dependencies(self, node: str) -> Dict[str, List[str]]:
        """Get direct dependencies and dependents of a node."""
        if node not in self.graph:
            return {"dependencies": [], "dependents": []}
        
        return {
            "dependencies": list(self.graph.successors(node)),
            "dependents": list(self.graph.predecessors(node)),
        }
    
    def export_to_csv(self, output_path: str):
        """Export graph to CSV format."""
        with open(output_path, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["source", "target"])
            for source, target in self.graph.edges():
                writer.writerow([source, target])
    
    def export_to_json(self, output_path: str):
        """Export graph to JSON format."""
        data = {
            "nodes": list(self.graph.nodes()),
            "edges": [{"source": s, "target": t} for s, t in self.graph.edges()],
            "statistics": self.get_statistics(),
        }
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2)
    
    def export_to_mermaid(self, output_path: str):
        """Export graph to Mermaid format."""
        # Simple fallback implementation if mermaid_gen is limited
        content = ["graph TD"]
        for u, v in self.graph.edges():
            # Sanitize names for mermaid
            safe_u = u.replace('/', '_').replace('.', '_').replace('-', '_')
            safe_v = v.replace('/', '_').replace('.', '_').replace('-', '_')
            content.append(f"    {safe_u}[{u}] --> {safe_v}[{v}]")
        
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content))

    def print_statistics(self):
        """Print graph statistics to console."""
        stats = self.get_statistics()
        print("\n=== Graph Statistics ===")
        for key, value in stats.items():
            print(f"{key}: {value}")
    
    def print_cycles(self):
        """Print detected cycles to console."""
        cycles = self.detect_cycles()
        print("\n=== Circular Dependencies ===")
        if cycles:
            print(f"Found {len(cycles)} cycles!")
            for i, cycle in enumerate(cycles[:10], 1): # Show max 10
                print(f"Cycle {i}: {' -> '.join(cycle)} -> {cycle[0]}")
            if len(cycles) > 10:
                print(f"...and {len(cycles)-10} more.")
        else:
            print("No circular dependencies detected.")
    
    def print_node_analysis(self, node: str):
        """Print analysis for a specific node."""
        if node not in self.graph:
            print(f"Node '{node}' not found in graph.")
            # Suggest similar nodes
            similar = [n for n in self.graph.nodes() if node in n]
            if similar:
                print(f"Did you mean: {', '.join(similar[:3])}?")
            return
        
        print(f"\n=== Analysis for '{node}' ===")
        
        deps = self.get_node_dependencies(node)
        print(f"Direct dependencies (Importa): {len(deps['dependencies'])}")
        for d in deps['dependencies'][:5]: print(f"  -> {d}")
        
        print(f"Direct dependents (Importato da): {len(deps['dependents'])}")
        for d in deps['dependents'][:5]: print(f"  <- {d}")
        
        impact = self.impact_analysis(node)
        print(f"Total Impact (se si rompe questo, rompi anche): {len(impact['ancestors'])} files")

def main():
    parser = argparse.ArgumentParser(description="Debug dependency graph")
    parser.add_argument("--db", type=str, help="Path to ase.db (default: .ase/ase.db)")
    parser.add_argument("--stats", action="store_true", help="Show graph statistics")
    parser.add_argument("--cycles", action="store_true", help="Detect circular dependencies")
    parser.add_argument("--node", type=str, help="Analyze specific node")
    parser.add_argument("--path", type=str, nargs=2, metavar=("SOURCE", "TARGET"), help="Find dependency path")
    
    args = parser.parse_args()
    
    debug = DebugGraph()
    if not debug.load_from_db(args.db):
        sys.exit(1)
    
    if args.stats:
        debug.print_statistics()
    
    if args.cycles:
        debug.print_cycles()
    
    if args.node:
        debug.print_node_analysis(args.node)
    
    if args.path:
        source, target = args.path
        path = debug.analyze_dependency_path(source, target)
        if path:
            print(f"\nShortest path from '{source}' to '{target}':")
            print(" -> ".join(path))
        else:
            print(f"No path found from '{source}' to '{target}'")

    if not (args.stats or args.cycles or args.node or args.path):
        print("No action specified. Use --stats, --node <file>, --cycles, or --path.")

if __name__ == "__main__":
    main()
