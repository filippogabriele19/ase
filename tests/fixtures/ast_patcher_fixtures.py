import ast
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import Mock, MagicMock


class ASTFixtures:
    """Collection of AST fixtures for testing ast_patcher functionality."""

    @staticmethod
    def create_simple_function() -> ast.FunctionDef:
        """Create a simple function AST node."""
        return ast.parse("def foo(x):\n    return x + 1").body[0]

    @staticmethod
    def create_function_with_decorator() -> ast.FunctionDef:
        """Create a function with decorators."""
        code = "@decorator\ndef foo(x):\n    return x"
        return ast.parse(code).body[0]

    @staticmethod
    def create_class_definition() -> ast.ClassDef:
        """Create a simple class definition."""
        code = "class MyClass:\n    def method(self):\n        pass"
        return ast.parse(code).body[0]

    @staticmethod
    def create_nested_function() -> ast.FunctionDef:
        """Create a function with nested function."""
        code = "def outer():\n    def inner():\n        pass\n    return inner"
        return ast.parse(code).body[0]

    @staticmethod
    def create_lambda_expression() -> ast.Lambda:
        """Create a lambda expression."""
        return ast.parse("lambda x: x + 1").body[0].value

    @staticmethod
    def create_list_comprehension() -> ast.ListComp:
        """Create a list comprehension."""
        return ast.parse("[x for x in range(10)]").body[0].value

    @staticmethod
    def create_dict_comprehension() -> ast.DictComp:
        """Create a dict comprehension."""
        return ast.parse("{x: x**2 for x in range(10)}").body[0].value

    @staticmethod
    def create_set_comprehension() -> ast.SetComp:
        """Create a set comprehension."""
        return ast.parse("{x for x in range(10)}").body[0].value

    @staticmethod
    def create_generator_expression() -> ast.GeneratorExp:
        """Create a generator expression."""
        return ast.parse("(x for x in range(10))").body[0].value

    @staticmethod
    def create_if_statement() -> ast.If:
        """Create an if statement."""
        code = "if x > 0:\n    y = 1\nelse:\n    y = 2"
        return ast.parse(code).body[0]

    @staticmethod
    def create_for_loop() -> ast.For:
        """Create a for loop."""
        code = "for i in range(10):\n    print(i)"
        return ast.parse(code).body[0]

    @staticmethod
    def create_while_loop() -> ast.While:
        """Create a while loop."""
        code = "while x > 0:\n    x -= 1"
        return ast.parse(code).body[0]

    @staticmethod
    def create_try_except() -> ast.Try:
        """Create a try-except block."""
        code = "try:\n    x = 1\nexcept Exception:\n    pass"
        return ast.parse(code).body[0]

    @staticmethod
    def create_with_statement() -> ast.With:
        """Create a with statement."""
        code = "with open('file') as f:\n    pass"
        return ast.parse(code).body[0]

    @staticmethod
    def create_binary_operation() -> ast.BinOp:
        """Create a binary operation."""
        return ast.parse("x + y").body[0].value

    @staticmethod
    def create_unary_operation() -> ast.UnaryOp:
        """Create a unary operation."""
        return ast.parse("-x").body[0].value

    @staticmethod
    def create_comparison() -> ast.Compare:
        """Create a comparison operation."""
        return ast.parse("x > y").body[0].value

    @staticmethod
    def create_boolean_operation() -> ast.BoolOp:
        """Create a boolean operation."""
        return ast.parse("x and y").body[0].value

    @staticmethod
    def create_function_call() -> ast.Call:
        """Create a function call."""
        return ast.parse("foo(x, y, z=1)").body[0].value

    @staticmethod
    def create_attribute_access() -> ast.Attribute:
        """Create an attribute access."""
        return ast.parse("obj.attr").body[0].value

    @staticmethod
    def create_subscript() -> ast.Subscript:
        """Create a subscript operation."""
        return ast.parse("lst[0]").body[0].value

    @staticmethod
    def create_slice() -> ast.Subscript:
        """Create a slice operation."""
        return ast.parse("lst[1:5]").body[0].value

    @staticmethod
    def create_assignment() -> ast.Assign:
        """Create an assignment statement."""
        return ast.parse("x = 1").body[0]

    @staticmethod
    def create_augmented_assignment() -> ast.AugAssign:
        """Create an augmented assignment."""
        return ast.parse("x += 1").body[0]

    @staticmethod
    def create_annotated_assignment() -> ast.AnnAssign:
        """Create an annotated assignment."""
        return ast.parse("x: int = 1").body[0]

    @staticmethod
    def create_multiple_assignment() -> ast.Assign:
        """Create a multiple assignment."""
        return ast.parse("x = y = z = 1").body[0]

    @staticmethod
    def create_tuple_unpacking() -> ast.Assign:
        """Create tuple unpacking assignment."""
        return ast.parse("x, y = 1, 2").body[0]

    @staticmethod
    def create_import_statement() -> ast.Import:
        """Create an import statement."""
        return ast.parse("import os").body[0]

    @staticmethod
    def create_from_import() -> ast.ImportFrom:
        """Create a from-import statement."""
        return ast.parse("from os import path").body[0]

    @staticmethod
    def create_return_statement() -> ast.Return:
        """Create a return statement."""
        return ast.parse("return x").body[0]

    @staticmethod
    def create_yield_statement() -> ast.Expr:
        """Create a yield statement."""
        return ast.parse("yield x").body[0]

    @staticmethod
    def create_raise_statement() -> ast.Raise:
        """Create a raise statement."""
        return ast.parse("raise ValueError('error')").body[0]

    @staticmethod
    def create_assert_statement() -> ast.Assert:
        """Create an assert statement."""
        return ast.parse("assert x > 0").body[0]

    @staticmethod
    def create_delete_statement() -> ast.Delete:
        """Create a delete statement."""
        return ast.parse("del x").body[0]

    @staticmethod
    def create_pass_statement() -> ast.Pass:
        """Create a pass statement."""
        return ast.parse("pass").body[0]

    @staticmethod
    def create_break_statement() -> ast.Break:
        """Create a break statement."""
        return ast.parse("while True:\n    break").body[0].body[0]

    @staticmethod
    def create_continue_statement() -> ast.Continue:
        """Create a continue statement."""
        return ast.parse("while True:\n    continue").body[0].body[0]

    @staticmethod
    def create_expression_statement() -> ast.Expr:
        """Create an expression statement."""
        return ast.parse("x + 1").body[0]

    @staticmethod
    def create_complex_nested_structure() -> ast.Module:
        """Create a complex nested AST structure."""
        code = """
class MyClass:
    def __init__(self):
        self.value = 0
    
    def method(self, x):
        if x > 0:
            for i in range(x):
                self.value += i
        return self.value
    
    @property
    def prop(self):
        return self.value
"""
        return ast.parse(code)

    @staticmethod
    def create_empty_module() -> ast.Module:
        """Create an empty module."""
        return ast.parse("")

    @staticmethod
    def create_module_with_docstring() -> ast.Module:
        """Create a module with docstring."""
        return ast.parse('"""Module docstring"""\nx = 1')

    @staticmethod
    def create_function_with_annotations() -> ast.FunctionDef:
        """Create a function with type annotations."""
        code = "def foo(x: int, y: str) -> bool:\n    return True"
        return ast.parse(code).body[0]

    @staticmethod
    def create_async_function() -> ast.AsyncFunctionDef:
        """Create an async function."""
        code = "async def foo():\n    await bar()"
        return ast.parse(code).body[0]

    @staticmethod
    def create_async_for() -> ast.AsyncFor:
        """Create an async for loop."""
        code = "async def foo():\n    async for item in items:\n        pass"
        return ast.parse(code).body[0].body[0]

    @staticmethod
    def create_async_with() -> ast.AsyncWith:
        """Create an async with statement."""
        code = "async def foo():\n    async with manager:\n        pass"
        return ast.parse(code).body[0].body[0]

    @staticmethod
    def create_walrus_operator() -> ast.NamedExpr:
        """Create a walrus operator expression."""
        return ast.parse("(x := 5)").body[0].value

    @staticmethod
    def create_starred_expression() -> ast.Starred:
        """Create a starred expression."""
        return ast.parse("*x").body[0].value

    @staticmethod
    def create_formatted_string() -> ast.JoinedStr:
        """Create an f-string."""
        return ast.parse("f'value: {x}'").body[0].value


class EdgeCaseFixtures:
    """Collection of edge case fixtures for testing."""

    @staticmethod
    def create_deeply_nested_structure(depth: int = 10) -> ast.Module:
        """Create a deeply nested structure."""
        code = "x = 1"
        for i in range(depth):
            code = f"if True:\n    {code}"
        return ast.parse(code)

    @staticmethod
    def create_large_list_literal(size: int = 1000) -> ast.List:
        """Create a large list literal."""
        elements = ", ".join(str(i) for i in range(size))
        return ast.parse(f"[{elements}]").body[0].value

    @staticmethod
    def create_many_function_definitions(count: int = 100) -> ast.Module:
        """Create many function definitions."""
        code = "\n".join(f"def func_{i}():\n    pass" for i in range(count))
        return ast.parse(code)

    @staticmethod
    def create_circular_reference_like_structure() -> Tuple[ast.FunctionDef, ast.FunctionDef]:
        """Create structures that reference each other."""
        code = """
def foo():
    return bar()

def bar():
    return foo()
"""
        module = ast.parse(code)
        return module.body[0], module.body[1]

    @staticmethod
    def create_node_with_all_fields() -> ast.FunctionDef:
        """Create a node with all possible fields populated."""
        code = """
@decorator
def foo(x: int, *args, y: str = 'default', **kwargs) -> bool:
    '''Docstring'''
    return True
"""
        return ast.parse(code).body[0]

    @staticmethod
    def create_empty_containers() -> Dict[str, Any]:
        """Create various empty containers."""
        return {
            "empty_list": ast.parse("[]").body[0].value,
            "empty_dict": ast.parse("{}").body[0].value,
            "empty_set": ast.parse("set()").body[0].value,
            "empty_tuple": ast.parse("()").body[0].value,
        }

    @staticmethod
    def create_special_values() -> Dict[str, Any]:
        """Create special value nodes."""
        return {
            "none": ast.parse("None").body[0].value,
            "true": ast.parse("True").body[0].value,
            "false": ast.parse("False").body[0].value,
            "ellipsis": ast.parse("...").body[0].value,
        }

    @staticmethod
    def create_numeric_literals() -> Dict[str, Any]:
        """Create various numeric literals."""
        return {
            "int": ast.parse("42").body[0].value,
            "float": ast.parse("3.14").body[0].value,
            "complex": ast.parse("1+2j").body[0].value,
            "negative": ast.parse("-42").body[0].value,
        }

    @staticmethod
    def create_string_literals() -> Dict[str, Any]:
        """Create various string literals."""
        return {
            "simple": ast.parse("'hello'").body[0].value,
            "double": ast.parse('"hello"').body[0].value,
            "triple": ast.parse("'''hello'''").body[0].value,
            "raw": ast.parse("r'hello'").body[0].value,
            "bytes": ast.parse("b'hello'").body[0].value,
        }


class MockFixtures:
    """Collection of mock objects for testing."""

    @staticmethod
    def create_mock_visitor() -> Mock:
        """Create a mock AST visitor."""
        mock = Mock()
        mock.visit = MagicMock(return_value=None)
        mock.generic_visit = MagicMock(return_value=None)
        return mock

    @staticmethod
    def create_mock_transformer() -> Mock:
        """Create a mock AST transformer."""
        mock = Mock()
        mock.visit = MagicMock(return_value=None)
        mock.generic_visit = MagicMock(return_value=None)
        return mock

    @staticmethod
    def create_mock_node() -> Mock:
        """Create a mock AST node."""
        mock = Mock(spec=ast.AST)
        mock.lineno = 1
        mock.col_offset = 0
        return mock

    @staticmethod
    def create_mock_context() -> Dict[str, Any]:
        """Create a mock context dictionary."""
        return {
            "filename": "test.py",
            "module_name": "test_module",
            "source": "x = 1",
            "options": {},
        }


class HelperFunctions:
    """Helper functions for test data creation."""

    @staticmethod
    def get_all_node_types() -> List[type]:
        """Get all AST node types."""
        return [
            getattr(ast, name)
            for name in dir(ast)
            if isinstance(getattr(ast, name), type)
            and issubclass(getattr(ast, name), ast.AST)
            and name[0].isupper()
        ]

    @staticmethod
    def count_nodes(node: ast.AST) -> int:
        """Count total number of nodes in an AST."""
        count = 1
        for child in ast.walk(node):
            if child is not node:
                count += 1
        return count

    @staticmethod
    def get_node_depth(node: ast.AST) -> int:
        """Get the maximum depth of an AST."""
        if not list(ast.iter_child_nodes(node)):
            return 1
        return 1 + max(
            HelperFunctions.get_node_depth(child)
            for child in ast.iter_child_nodes(node)
        )

    @staticmethod
    def find_nodes_of_type(node: ast.AST, node_type: type) -> List[ast.AST]:
        """Find all nodes of a specific type."""
        return [n for n in ast.walk(node) if isinstance(n, node_type)]

    @staticmethod
    def compare_ast_structures(node1: ast.AST, node2: ast.AST) -> bool:
        """Compare two AST structures for equality."""
        if type(node1) != type(node2):
            return False
        if isinstance(node1, ast.AST):
            for field, value1 in ast.iter_fields(node1):
                value2 = getattr(node2, field, None)
                if isinstance(value1, list):
                    if not isinstance(value2, list) or len(value1) != len(value2):
                        return False
                    if not all(
                        HelperFunctions.compare_ast_structures(v1, v2)
                        for v1, v2 in zip(value1, value2)
                    ):
                        return False
                elif isinstance(value1, ast.AST):
                    if not HelperFunctions.compare_ast_structures(value1, value2):
                        return False
                else:
                    if value1 != value2:
                        return False
            return True
        return node1 == node2

    @staticmethod
    def get_source_from_ast(node: ast.AST) -> str:
        """Get source code from AST node."""
        try:
            return ast.unparse(node)
        except Exception:
            return ""

    @staticmethod
    def create_test_data_summary() -> Dict[str, int]:
        """Create a summary of available test data."""
        return {
            "ast_fixtures": len([m for m in dir(ASTFixtures) if m.startswith("create_")]),
            "edge_case_fixtures": len(
                [m for m in dir(EdgeCaseFixtures) if m.startswith("create_")]
            ),
            "mock_fixtures": len([m for m in dir(MockFixtures) if m.startswith("create_")]),
            "helper_functions": len(
                [m for m in dir(HelperFunctions) if not m.startswith("_")]
            ),
        }