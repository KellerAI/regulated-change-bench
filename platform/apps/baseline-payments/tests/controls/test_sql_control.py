import ast
from pathlib import Path

import pytest

import payments

SQL_METHODS = {"execute", "executemany", "executescript"}


def module_constants(tree):
    """Names bound exactly once in the module, at top level, to a string literal."""
    top_level = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                top_level[node.targets[0].id] = node.value.value
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            bindings[node.id] = bindings.get(node.id, 0) + 1
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            for name in node.names:
                bindings[name] = bindings.get(name, 0) + 2
    return {name: value for name, value in top_level.items() if bindings.get(name) == 1}


def statement_text(node, constants):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in constants:
        return constants[node.id]
    return None


def classify(call, constants):
    """None when the call is a parameterized statement, otherwise the reason it is not."""
    method = call.func.attr
    if call.keywords or any(isinstance(arg, ast.Starred) for arg in call.args):
        return "arguments cannot be analysed"
    if not call.args:
        return "no statement"
    sql = statement_text(call.args[0], constants)
    if sql is None:
        return "statement is not a string literal or module constant"
    placeholders = sql.count("?")
    if method == "executescript":
        return None if len(call.args) == 1 and placeholders == 0 else "script with parameters"
    if len(call.args) > 2:
        return "too many arguments"
    if method == "executemany" and len(call.args) != 2:
        return "executemany without parameters"
    if placeholders and len(call.args) != 2:
        return "placeholders without parameters"
    if not placeholders and len(call.args) == 2:
        return "parameters without placeholders"
    params = call.args[1] if len(call.args) == 2 else None
    if isinstance(params, (ast.Tuple, ast.List)) and len(params.elts) != placeholders:
        return "parameter count differs from placeholders"
    return None


def scan(path):
    tree = ast.parse(path.read_text(), filename=str(path))
    constants = module_constants(tree)
    called = set()
    sites = []
    problems = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in SQL_METHODS:
            called.add(id(node.func))
            sites.append(node.lineno)
            reason = classify(node, constants)
            if reason is not None:
                problems.append(f"{path.name}:{node.lineno}: {reason}")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            names = [arg.value for arg in node.args if isinstance(arg, ast.Constant)]
            if any(name in SQL_METHODS for name in names):
                problems.append(f"{path.name}:{node.lineno}: {names} looked up dynamically")
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in SQL_METHODS and id(node) not in called:
            problems.append(f"{path.name}:{node.lineno}: {node.attr} used without a direct call")
    return sites, problems


@pytest.mark.control(obligation="SEC-1", coverage="exhaustive", domain="payments.sql_call_sites")
def test_sql_statements_are_parameterized():
    package = Path(payments.__file__).parent
    all_sites = {}
    all_problems = []
    for path in sorted(package.rglob("*.py")):
        sites, problems = scan(path)
        if sites:
            all_sites[path.name] = sites
        all_problems.extend(problems)
    assert "store.py" in all_sites
    assert "audit.py" in all_sites
    assert all_problems == []
