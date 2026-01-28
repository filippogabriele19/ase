import libcst as cst
from typing import List


class RemovalTransformer(cst.CSTTransformer):
    """
    CST Transformer to remove specific functions or classes from the code
    while preserving formatting and comments of surrounding code.
    """
    def __init__(self, names_to_remove: List[str]):
        self.names = set(names_to_remove)


    def leave_FunctionDef(self, original_node: cst.FunctionDef, updated_node: cst.FunctionDef) -> cst.CSTNode:
        """Visit and optionally remove function definitions."""
        if original_node.name.value in self.names:
            return cst.RemoveFromParent()
        return updated_node


    def leave_ClassDef(self, original_node: cst.ClassDef, updated_node: cst.ClassDef) -> cst.CSTNode:
        """Visit and optionally remove class definitions."""
        if original_node.name.value in self.names:
            return cst.RemoveFromParent()
        return updated_node


def remove_definitions_cst(source_code: str, names: List[str]) -> str:
    """
    Removes function or class definitions using LibCST, preserving comments 
    and original formatting.
    
    Args:
        source_code: The original source code string
        names: List of function/class names to remove
        
    Returns:
        Modified source code string
        
    Raises:
        Exception: Propagates LibCST parsing or transformation errors
    """
    try:
        tree = cst.parse_module(source_code)
        transformer = RemovalTransformer(names)
        modified_tree = tree.visit(transformer)
        return modified_tree.code
    except Exception as e:
        print(f"⚠️ CST Error: {e}")
        # Fail safe: propagating the error is safer than returning corrupted code
        raise e
