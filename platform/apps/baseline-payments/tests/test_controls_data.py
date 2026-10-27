import ast
import fnmatch
import json

from support import platform_root

IGNORED_PARTS = {"__pycache__", ".pytest_cache", "out", "build", ".DS_Store"}


def load(name):
    return json.loads((platform_root() / "controls" / "payments" / name).read_text())


def app_files():
    root = platform_root()
    app = root / "apps" / "baseline-payments"
    paths = [p for p in app.rglob("*") if p.is_file()]
    paths += [p for p in (root / "controls" / "payments").iterdir() if p.is_file()]
    for path in paths:
        ignored = not IGNORED_PARTS.isdisjoint(path.parts) or path.suffix == ".pyc"
        if not ignored and not any(part.endswith(".egg-info") for part in path.parts):
            yield path.relative_to(root).as_posix()


def test_every_file_belongs_to_exactly_one_component():
    components = load("components.json")
    unmatched = []
    ambiguous = []
    for rel in app_files():
        matches = [glob for glob in components if fnmatch.fnmatch(rel, glob)]
        if not matches:
            unmatched.append(rel)
        if len(matches) > 1:
            ambiguous.append((rel, matches))
    assert unmatched == []
    assert ambiguous == []


def test_component_entries_are_complete():
    for glob, entry in load("components.json").items():
        assert entry["component"].startswith("payments."), glob
        assert isinstance(entry["security_sensitive"], bool), glob


def declared_markers():
    found = {}
    controls_dir = platform_root() / "apps" / "baseline-payments" / "tests" / "controls"
    for path in sorted(controls_dir.glob("test_*.py")):
        for node in ast.parse(path.read_text()).body:
            if not isinstance(node, ast.FunctionDef):
                continue
            for decorator in node.decorator_list:
                if isinstance(decorator, ast.Call) and getattr(decorator.func, "attr", None) == "control":
                    fields = {kw.arg: kw.value.value for kw in decorator.keywords}
                    found[f"tests/controls/{path.name}::{node.name}"] = fields
    return found


def test_registry_matches_test_markers():
    assert load("control-registry.json") == declared_markers()


def test_registry_coverage_labels():
    for test_id, entry in load("control-registry.json").items():
        assert entry["coverage"] in {"exhaustive", "sample"}, test_id
        assert entry["domain"].startswith("payments."), test_id


def test_access_policy_is_fully_specified():
    policy = load("access-policy.json")
    for role in policy["roles"]:
        row = policy["matrix"][role]
        assert sorted(row) == sorted(policy["actions"]), role
        assert all(isinstance(value, bool) for value in row.values()), role


def test_inventory_entries_have_owner_and_classification():
    inventory = load("asset-inventory.json")
    for entry in inventory["integrations"]:
        assert entry["owner"]
        assert entry["data_classification"] in inventory["classifications"]
