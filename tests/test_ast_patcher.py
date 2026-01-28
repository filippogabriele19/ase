from __future__ import annotations

import ast
import json
import re
import unittest
from typing import List, Set
from unittest.mock import patch, MagicMock

from core.ast_patcher import (
    ASTPatchError,
    parse_llm_json_list,
    DefinitionCollector,
    collect_definitions,
    DeletionTransformer,
    delete_definitions,
    extract_function_source,
    extract_imports_source,
    inject_import_at_top,
)


class TestASTPatchError(unittest.TestCase):
    """Test ASTPatchError exception class."""

    def test_is_runtime_error(self):
        """ASTPatchError should be a RuntimeError."""
        self.assertTrue(issubclass(ASTPatchError, RuntimeError))

    def test_can_raise_and_catch(self):
        """ASTPatchError should be raisable and catchable."""
        with self.assertRaises(ASTPatchError):
            raise ASTPatchError("test error")

    def test_error_message(self):
        """ASTPatchError should preserve error message."""
        msg = "custom error message"
        with self.assertRaises(ASTPatchError) as cm:
            raise ASTPatchError(msg)
        self.assertEqual(str(cm.exception), msg)


class TestParseLLMJsonList(unittest.TestCase):
    """Test parse_llm_json_list function."""

    def test_pure_json_list(self):
        """Should parse pure JSON list."""
        result = parse_llm_json_list('["a", "b", "c"]')
        self.assertEqual(result, ["a", "b", "c"])

    def test_fenced_json_block(self):
        """Should parse JSON in fenced code block."""
        result = parse_llm_json_list('```json\n["x", "y"]\n```')
        self.assertEqual(result, ["x", "y"])

    def test_json_embedded_in_text(self):
        """Should extract JSON embedded in text."""
        result = parse_llm_json_list('Here is the list: ["item1", "item2"]')
        self.assertEqual(result, ["item1", "item2"])

    def test_empty_string(self):
        """Should return empty list for empty string."""
        self.assertEqual(parse_llm_json_list(""), [])

    def test_whitespace_only(self):
        """Should return empty list for whitespace-only string."""
        self.assertEqual(parse_llm_json_list("   \n\t  "), [])

    def test_none_input(self):
        """Should return empty list for None input."""
        self.assertEqual(parse_llm_json_list(None), [])

    def test_invalid_json(self):
        """Should return empty list for invalid JSON."""
        self.assertEqual(parse_llm_json_list("{not valid json}"), [])

    def test_json_with_non_string_elements(self):
        """Should return empty list if list contains non-strings."""
        self.assertEqual(parse_llm_json_list('[1, 2, 3]'), [])
        self.assertEqual(parse_llm_json_list('["a", 1, "b"]'), [])

    def test_json_object_not_list(self):
        """Should return empty list if JSON is object, not list."""
        self.assertEqual(parse_llm_json_list('{"key": "value"}'), [])

    def test_empty_json_list(self):
        """Should return empty list for empty JSON array."""
        self.assertEqual(parse_llm_json_list('[]'), [])

    def test_single_element_list(self):
        """Should parse single-element list."""
        self.assertEqual(parse_llm_json_list('["single"]'), ["single"])

    def test_list_with_special_characters(self):
        """Should handle strings with special characters."""
        result = parse_llm_json_list('["hello\\nworld", "tab\\there"]')
        self.assertEqual(result, ["hello\nworld", "tab\there"])

    def test_list_with_unicode(self):
        """Should handle unicode characters."""
        result = parse_llm_json_list('["café", "日本語", "🎉"]')
        self.assertEqual(result, ["café", "日本語", "🎉"])

    def test_multiple_fenced_blocks(self):
        """Should extract from first valid fenced block."""
        raw = '```json\n["first"]\n```\n```json\n["second"]\n```'
        result = parse_llm_json_list(raw)
        self.assertIn(result, [["first"], ["second"]])

    def test_whitespace_in_json(self):
        """Should handle JSON with extra whitespace."""
        result = parse_llm_json_list('  [  "a"  ,  "b"  ]  ')
        self.assertEqual(result, ["a", "b"])


class TestDefinitionCollector(unittest.TestCase):
    """Test DefinitionCollector class."""

    def test_collect_function_def(self):
        """Should collect function definitions."""
        source = "def foo(): pass\ndef bar(): pass"
        tree = ast.parse(source)
        collector = DefinitionCollector()
        collector.visit(tree)
        self.assertEqual(collector.definitions, {"foo", "bar"})

    def test_collect_async_function_def(self):
        """Should collect async function definitions."""
        source = "async def async_foo(): pass"
        tree = ast.parse(source)
        collector = DefinitionCollector()
        collector.visit(tree)
        self.assertEqual(collector.definitions, {"async_foo"})

    def test_collect_class_def(self):
        """Should collect class definitions."""
        source = "class MyClass: pass\nclass AnotherClass: pass"
        tree = ast.parse(source)
        collector = DefinitionCollector()
        collector.visit(tree)
        self.assertEqual(collector.definitions, {"MyClass", "AnotherClass"})

    def test_collect_mixed_definitions(self):
        """Should collect mixed function and class definitions."""
        source = """
def func1(): pass
class Class1: pass
async def async_func(): pass
class Class2: pass
def func2(): pass
"""
        tree = ast.parse(source)
        collector = DefinitionCollector()
        collector.visit(tree)
        expected = {"func1", "Class1", "async_func", "Class2", "func2"}
        self.assertEqual(collector.definitions, expected)

    def test_collect_nested_definitions(self):
        """Should collect nested definitions."""
        source = """
class Outer:
    def inner_method(self): pass
    class InnerClass: pass
"""
        tree = ast.parse(source)
        collector = DefinitionCollector()
        collector.visit(tree)
        self.assertIn("Outer", collector.definitions)
        self.assertIn("inner_method", collector.definitions)
        self.assertIn("InnerClass", collector.definitions)

    def test_empty_source(self):
        """Should handle empty source."""
        tree = ast.parse("")
        collector = DefinitionCollector()
        collector.visit(tree)
        self.assertEqual(collector.definitions, set())

    def test_no_definitions(self):
        """Should return empty set when no definitions."""
        source = "x = 1\ny = 2"
        tree = ast.parse(source)
        collector = DefinitionCollector()
        collector.visit(tree)
        self.assertEqual(collector.definitions, set())


class TestCollectDefinitions(unittest.TestCase):
    """Test collect_definitions function."""

    def test_collect_definitions_basic(self):
        """Should collect definitions from source string."""
        source = "def foo(): pass\nclass Bar: pass"
        result = collect_definitions(source)
        self.assertEqual(result, {"foo", "Bar"})

    def test_collect_definitions_empty(self):
        """Should return empty set for empty source."""
        result = collect_definitions("")
        self.assertEqual(result, set())

    def test_collect_definitions_syntax_error(self):
        """Should raise SyntaxError for invalid source."""
        with self.assertRaises(SyntaxError):
            collect_definitions("def foo(: pass")

    def test_collect_definitions_complex(self):
        """Should handle complex nested structures."""
        source = """
def outer():
    def inner(): pass
    class Local: pass

class MyClass:
    def method(self): pass
    async def async_method(self): pass
"""
        result = collect_definitions(source)
        self.assertIn("outer", result)
        self.assertIn("MyClass", result)
        self.assertIn("inner", result)
        self.assertIn("Local", result)
        self.assertIn("method", result)
        self.assertIn("async_method", result)


class TestDeletionTransformer(unittest.TestCase):
    """Test DeletionTransformer class."""

    def test_delete_function(self):
        """Should delete function by name."""
        source = "def foo(): pass\ndef bar(): pass"
        tree = ast.parse(source)
        transformer = DeletionTransformer(["foo"])
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        result = ast.unparse(new_tree)
        self.assertIn("bar", result)
        self.assertNotIn("foo", result)

    def test_delete_class(self):
        """Should delete class by name."""
        source = "class Foo: pass\nclass Bar: pass"
        tree = ast.parse(source)
        transformer = DeletionTransformer(["Foo"])
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        result = ast.unparse(new_tree)
        self.assertIn("Bar", result)
        self.assertNotIn("Foo", result)

    def test_delete_async_function(self):
        """Should delete async function by name."""
        source = "async def foo(): pass\nasync def bar(): pass"
        tree = ast.parse(source)
        transformer = DeletionTransformer(["foo"])
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        result = ast.unparse(new_tree)
        self.assertIn("bar", result)
        self.assertNotIn("foo", result)

    def test_delete_nonexistent(self):
        """Should not fail when deleting nonexistent name."""
        source = "def foo(): pass"
        tree = ast.parse(source)
        transformer = DeletionTransformer(["nonexistent"])
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        result = ast.unparse(new_tree)
        self.assertIn("foo", result)

    def test_delete_empty_list(self):
        """Should handle empty deletion list."""
        source = "def foo(): pass"
        tree = ast.parse(source)
        transformer = DeletionTransformer([])
        new_tree = transformer.visit(tree)
        ast.fix_missing_locations(new_tree)
        result = ast.unparse(new_tree)
        self.assertIn("foo", result)


class TestDeleteDefinitions(unittest.TestCase):
    """Test delete_definitions function."""

    def test_delete_definitions_basic(self):
        """Should delete definitions from source."""
        source = "def foo(): pass\ndef bar(): pass"
        result = delete_definitions(source, ["foo"])
        self.assertIn("bar", result)
        self.assertNotIn("foo", result)

    def test_delete_definitions_empty_names(self):
        """Should return source unchanged for empty names."""
        source = "def foo(): pass"
        result = delete_definitions(source, [])
        self.assertEqual(result, source)

    def test_delete_definitions_none_names(self):
        """Should return source unchanged for None names."""
        source = "def foo(): pass"
        result = delete_definitions(source, None)
        self.assertEqual(result, source)

    def test_delete_definitions_all(self):
        """Should delete all definitions."""
        source = "def foo(): pass\ndef bar(): pass"
        result = delete_definitions(source, ["foo", "bar"])
        self.assertEqual(result.strip(), "")

    def test_delete_definitions_preserves_other_code(self):
        """Should preserve non-definition code."""
        source = "x = 1\ndef foo(): pass\ny = 2"
        result = delete_definitions(source, ["foo"])
        self.assertIn("x = 1", result)
        self.assertIn("y = 2", result)
        self.assertNotIn("foo", result)

    def test_delete_definitions_syntax_error(self):
        """Should raise SyntaxError for invalid source."""
        with self.assertRaises(SyntaxError):
            delete_definitions("def foo(: pass", ["foo"])


class TestExtractFunctionSource(unittest.TestCase):
    """Test extract_function_source function."""

    def test_extract_simple_function(self):
        """Should extract simple function source."""
        source = "def foo():\n    return 42"
        result = extract_function_source(source, "foo")
        self.assertIsNotNone(result)
        self.assertIn("def foo", result)
        self.assertIn("return 42", result)

    def test_extract_class(self):
        """Should extract class source."""
        source = "class MyClass:\n    pass"
        result = extract_function_source(source, "MyClass")
        self.assertIsNotNone(result)
        self.assertIn("class MyClass", result)

    def test_extract_async_function(self):
        """Should extract async function source."""
        source = "async def foo():\n    await something()"
        result = extract_function_source(source, "foo")
        self.assertIsNotNone(result)
        self.assertIn("async def foo", result)

    def test_extract_nonexistent(self):
        """Should return None for nonexistent function."""
        source = "def foo(): pass"
        result = extract_function_source(source, "nonexistent")
        self.assertIsNone(result)

    def test_extract_from_invalid_source(self):
        """Should return None for invalid source."""
        result = extract_function_source("def foo(: pass", "foo")
        self.assertIsNone(result)

    def test_extract_function_with_body(self):
        """Should extract function with complex body."""
        source = """def complex_func(x, y):
    result = x + y
    if result > 10:
        return result
    else:
        return 0"""
        result = extract_function_source(source, "complex_func")
        self.assertIsNotNone(result)
        self.assertIn("complex_func", result)
        self.assertIn("result = x + y", result)

    def test_extract_nested_function(self):
        """Should extract nested function."""
        source = """def outer():
    def inner():
        pass"""
        result = extract_function_source(source, "inner")
        self.assertIsNotNone(result)
        self.assertIn("def inner", result)

    def test_extract_class_with_methods(self):
        """Should extract class with methods."""
        source = """class MyClass:
    def method(self):
        pass"""
        result = extract_function_source(source, "MyClass")
        self.assertIsNotNone(result)
        self.assertIn("class MyClass", result)
        self.assertIn("def method", result)

    def test_extract_empty_source(self):
        """Should return None for empty source."""
        result = extract_function_source("", "foo")
        self.assertIsNone(result)


class TestExtractImportsSource(unittest.TestCase):
    """Test extract_imports_source function."""

    def test_extract_simple_imports(self):
        """Should extract simple imports."""
        source = "import os\nimport sys\ndef foo(): pass"
        result = extract_imports_source(source)
        self.assertIn("import os", result)
        self.assertIn("import sys", result)

    def test_extract_from_imports(self):
        """Should extract from imports."""
        source = "from typing import List\nfrom os import path\ndef foo(): pass"
        result = extract_imports_source(source)
        self.assertIn("from typing import List", result)
        self.assertIn("from os import path", result)

    def test_extract_no_imports(self):
        """Should return empty string when no imports."""
        source = "def foo(): pass\nx = 1"
        result = extract_imports_source(source)
        self.assertEqual(result, "")

    def test_extract_mixed_imports(self):
        """Should extract mixed import types."""
        source = """import os
from typing import List
import sys
from collections import defaultdict
def foo(): pass"""
        result = extract_imports_source(source)
        self.assertIn("import os", result)
        self.assertIn("from typing import List", result)
        self.assertIn("import sys", result)
        self.assertIn("from collections import defaultdict", result)

    def test_extract_imports_invalid_source(self):
        """Should return empty string for invalid source."""
        result = extract_imports_source("def foo(: pass")
        self.assertEqual(result, "")

    def test_extract_imports_empty_source(self):
        """Should return empty string for empty source."""
        result = extract_imports_source("")
        self.assertEqual(result, "")

    def test_extract_imports_with_future(self):
        """Should extract __future__ imports."""
        source = "from __future__ import annotations\nimport os"
        result = extract_imports_source(source)
        self.assertIn("from __future__ import annotations", result)
        self.assertIn("import os", result)

    def test_extract_imports_preserves_order(self):
        """Should preserve import order."""
        source = "import a\nimport b\nimport c"
        result = extract_imports_source(source)
        lines = result.strip().split("\n")
        self.assertEqual(len(lines), 3)
        self.assertIn("import a", lines[0])
        self.assertIn("import b", lines[1])
        self.assertIn("import c", lines[2])


class TestInjectImportAtTop(unittest.TestCase):
    """Test inject_import_at_top function."""

    def test_inject_into_empty_file(self):
        """Should inject import into empty file."""
        result = inject_import_at_top("", "import os")
        self.assertIn("import os", result)

    def test_inject_after_existing_imports(self):
        """Should inject after existing imports."""
        source = "import sys\ndef foo(): pass"
        result = inject_import_at_top(source, "import os")
        lines = result.strip().split("\n")
        self.assertIn("import sys", result)
        self.assertIn("import os", result)

    def test_inject_empty_import(self):
        """Should return source unchanged for empty import."""
        source = "def foo(): pass"
        result = inject_import_at_top(source, "")
        self.assertEqual(result, source)

    def test_inject_whitespace_only_import(self):
        """Should return source unchanged for whitespace-only import."""
        source = "def foo(): pass"
        result = inject_import_at_top(source, "   \n  ")
        self.assertEqual(result, source)

    def test_inject_with_shebang(self):
        """Should inject after shebang."""
        source = "#!/usr/bin/env python\nimport sys"
        result = inject_import_at_top(source, "import os")
        self.assertIn("#!/usr/bin/env python", result)
        self.assertIn("import os", result)

    def test_inject_with_docstring(self):
        """Should inject after module docstring."""
        source = '"""Module docstring."""\nimport sys'
        result = inject_import_at_top(source, "import os")
        self.assertIn('"""Module docstring."""', result)
        self.assertIn("import os", result)

    def test_inject_no_existing_imports(self):
        """Should inject at beginning when no imports exist."""
        source = "def foo(): pass"
        result = inject_import_at_top(source, "import os")
        self.assertIn("import os", result)
        self.assertIn("def foo", result)

    def test_inject_multiple_imports(self):
        """Should inject multiple import lines."""
        source = "import sys"
        new_imports = "import os\nimport json"
        result = inject_import_at_top(source, new_imports)
        self.assertIn("import sys", result)
        self.assertIn("import os", result)
        self.assertIn("import json", result)

    def test_inject_into_invalid_source(self):
        """Should handle invalid source gracefully."""
        source = "def foo(: pass"
        result = inject_import_at_top(source, "import os")
        self.assertIn("import os", result)

    def test_inject_preserves_code(self):
        """Should preserve all code after injection."""
        source = "import sys\n\ndef foo():\n    return 42\n\nx = 1"
        result = inject_import_at_top(source, "import os")
        self.assertIn("def foo", result)
        self.assertIn("return 42", result)
        self.assertIn("x = 1", result)

    def test_inject_with_comments(self):
        """Should handle comments correctly."""
        source = "# This is a comment\nimport sys"
        result = inject_import_at_top(source, "import os")
        self.assertIn("# This is a comment", result)
        self.assertIn("import os", result)

    def test_inject_multiline_import(self):
        """Should handle multiline imports."""
        source = "from typing import (\n    List,\n    Dict\n)"
        result = inject_import_at_top(source, "import os")
        self.assertIn("import os", result)
        self.assertIn("from typing import", result)

    def test_inject_from_import(self):
        """Should inject from imports."""
        source = "import sys"
        result = inject_import_at_top(source, "from os import path")
        self.assertIn("from os import path", result)
        self.assertIn("import sys", result)


class TestIntegration(unittest.TestCase):
    """Integration tests combining multiple functions."""

    def test_collect_and_delete_workflow(self):
        """Should collect definitions and delete them."""
        source = """
def func1(): pass
def func2(): pass
class MyClass: pass
"""
        definitions = collect_definitions(source)
        self.assertEqual(definitions, {"func1", "func2", "MyClass"})

        result = delete_definitions(source, ["func1"])
        remaining = collect_definitions(result)
        self.assertEqual(remaining, {"func2", "MyClass"})

    def test_extract_and_inject_workflow(self):
        """Should extract imports and inject them."""
        source = """import os
import sys

def foo(): pass
"""
        imports = extract_imports_source(source)
        self.assertIn("import os", imports)
        self.assertIn("import sys", imports)

        new_source = "def bar(): pass"
        result = inject_import_at_top(new_source, imports)
        self.assertIn("import os", result)
        self.assertIn("import sys", result)
        self.assertIn("def bar", result)

    def test_extract_function_and_inject_into_new_file(self):
        """Should extract function and inject into new file."""
        source = """import os

def my_function():
    return os.path.exists('.')
"""
        func_source = extract_function_source(source, "my_function")
        self.assertIsNotNone(func_source)

        imports = extract_imports_source(source)
        new_file = inject_import_at_top("", imports)
        new_file = inject_import_at_top(new_file, func_source)

        self.assertIn("import os", new_file)
        self.assertIn("def my_function", new_file)

    def test_complex_refactoring_workflow(self):
        """Should handle complex refactoring workflow."""
        source = """from typing import List
import os

def helper(): pass
def main(): pass
class Processor: pass
"""
        # Collect all definitions
        all_defs = collect_definitions(source)
        self.assertEqual(all_defs, {"helper", "main", "Processor"})

        # Delete helper
        source_without_helper = delete_definitions(source, ["helper"])
        remaining = collect_definitions(source_without_helper)
        self.assertEqual(remaining, {"main", "Processor"})

        # Extract imports
        imports = extract_imports_source(source_without_helper)
        self.assertIn("from typing import List", imports)
        self.assertIn("import os", imports)

        # Extract main function
        main_source = extract_function_source(source_without_helper, "main")
        self.assertIsNotNone(main_source)


class TestEdgeCases(unittest.TestCase):
    """Test edge cases and boundary conditions."""

    def test_very_large_json_list(self):
        """Should handle very large JSON lists."""
        large_list = json.dumps([f"item_{i}" for i in range(1000)])
        result = parse_llm_json_list(large_list)
        self.assertEqual(len(result), 1000)

    def test_deeply_nested_classes(self):
        """Should handle deeply nested class definitions."""
        source = """
class A:
    class B:
        class C:
            class D:
                pass
"""
        defs = collect_definitions(source)
        self.assertIn("A", defs)
        self.assertIn("B", defs)
        self.assertIn("C", defs)
        self.assertIn("D", defs)

    def test_unicode_in_function_names(self):
        """Should handle unicode in function names."""
        source = "def café(): pass"
        defs = collect_definitions(source)
        self.assertIn("café", defs)

    def test_very_long_function_body(self):
        """Should extract function with very long body."""
        lines = ["def long_func():"]
        for i in range(100):
            lines.append(f"    x{i} = {i}")
        source = "\n".join(lines)
        result = extract_function_source(source, "long_func")
        self.assertIsNotNone(result)
        self.assertIn("def long_func", result)

    def test_special_characters_in_strings(self):
        """Should handle special characters in string literals."""
        source = r'''def foo():
    s = "hello\nworld\t\r"
    return s'''
        result = extract_function_source(source, "foo")
        self.assertIsNotNone(result)

    def test_raw_strings_and_f_strings(self):
        """Should handle raw strings and f-strings."""
        source = r'''def foo():
    raw = r"C:\path\to\file"
    formatted = f"value: {42}"
    return raw, formatted'''
        result = extract_function_source(source, "foo")
        self.assertIsNotNone(result)

    def test_decorators_on_functions(self):
        """Should extract functions with decorators."""
        source = """@decorator
@another_decorator
def decorated_func():
    pass"""
        result = extract_function_source(source, "decorated_func")
        self.assertIsNotNone(result)
        self.assertIn("@decorator", result)

    def test_type_hints_in_functions(self):
        """Should extract functions with type hints."""
        source = """def typed_func(x: int, y: str) -> bool:
    return True"""
        result = extract_function_source(source, "typed_func")
        self.assertIsNotNone(result)
        self.assertIn("int", result)
        self.assertIn("str", result)

    def test_lambda_expressions(self):
        """Should handle lambda expressions in source."""
        source = """x = lambda a: a + 1
def foo(): pass"""
        defs = collect_definitions(source)
        self.assertIn("foo", defs)

    def test_walrus_operator(self):
        """Should handle walrus operator in source."""
        source = """def foo():
    if (n := len([1, 2, 3])) > 2:
        return n"""
        result = extract_function_source(source, "foo")
        self.assertIsNotNone(result)


if __name__ == "__main__":
    unittest.main()