"""
Tests for tools/context_pruner.py — multi-language function extraction.
"""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from tools.context_pruner import extract_function_context, extract_error_window


class TestPythonExtraction:
    def test_extracts_function_containing_change(self):
        code = """
def foo():
    x = 1
    y = 2
    return x + y

def bar():
    a = 10
    return a
""".strip()
        result = extract_function_context(code, [3], file_path="test.py")
        assert "foo" in result
        assert "bar" not in result

    def test_extracts_class_containing_change(self):
        code = """
class MyClass:
    def method(self):
        return 42
""".strip()
        result = extract_function_context(code, [3], file_path="test.py")
        assert "MyClass" in result or "method" in result

    def test_empty_changed_lines(self):
        result = extract_function_context("def foo(): pass", [], file_path="test.py")
        assert result == ""


class TestJSExtraction:
    def test_extracts_named_function(self):
        code = """function calculateTotal(items) {
    let sum = 0;
    for (const item of items) {
        sum += item.price;
    }
    return sum;
}

function otherFunc() {
    return 42;
}"""
        result = extract_function_context(code, [3], file_path="app.js")
        assert "calculateTotal" in result
        # otherFunc should NOT be included
        assert "otherFunc" not in result

    def test_extracts_arrow_function(self):
        code = """const add = (a, b) => {
    const result = a + b;
    console.log(result);
    return result;
    // trailing
}"""
        result = extract_function_context(code, [2], file_path="util.ts")
        assert "add" in result


class TestGoExtraction:
    def test_extracts_go_function(self):
        code = """func main() {
    fmt.Println("hello")
    doWork()
    cleanup()
}

func helper() {
    return
}"""
        result = extract_function_context(code, [2], file_path="main.go")
        assert "main" in result


class TestJavaExtraction:
    def test_extracts_java_method(self):
        code = """public class Calculator {
    public int add(int a, int b) {
        int result = a + b;
        System.out.println(result);
        return result;
    }

    public int subtract(int a, int b) {
        return a - b;
    }
}"""
        result = extract_function_context(code, [3], file_path="Calculator.java")
        assert "add" in result or "Calculator" in result


class TestFallback:
    def test_unknown_extension_falls_back_to_window(self):
        code = "line1\nline2\nline3\nline4\nline5\n"
        result = extract_function_context(code, [3], file_path="data.txt")
        assert "line3" in result

    def test_error_window(self):
        code = "\n".join(f"line {i}" for i in range(1, 51))
        result = extract_error_window(code, 20, 25, window=5)
        assert "line 20" in result
        assert "line 25" in result
        # Should not include content lines far outside the window
        # Use "\nline 1\n" to avoid matching "line 1" in the header
        assert "\nline 1\n" not in result
        assert "\nline 2\n" not in result
