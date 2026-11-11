"""Execute ordinary or notebook-native top-level-await cells in offline tests."""
import ast
import asyncio
import inspect


def execute_cell(source, namespace, filename='notebook-test'):
    code = compile(source, filename, 'exec', flags=ast.PyCF_ALLOW_TOP_LEVEL_AWAIT)
    result = eval(code, namespace)
    if inspect.isawaitable(result):
        return asyncio.run(result)
    return result
