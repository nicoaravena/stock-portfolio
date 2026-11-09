import ast
from pathlib import Path

DOMAIN = Path(__file__).parents[2] / "src" / "stock_portfolio" / "domain"
FORBIDDEN = {"django", "ninja", "pydantic"}


def test_domain_has_no_framework_imports():
    """The domain must stay plain Python so it can be used and tested alone."""
    modules = sorted(DOMAIN.glob("*.py"))
    assert modules, f"no domain modules found in {DOMAIN}"
    for module in modules:
        for node in ast.walk(ast.parse(module.read_text())):
            if isinstance(node, ast.Import):
                roots = {alias.name.split(".")[0] for alias in node.names}
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots = {node.module.split(".")[0]}
            else:
                continue
            assert not roots & FORBIDDEN, f"{module.name} imports {roots & FORBIDDEN}"
