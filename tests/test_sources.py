"""The package stays on the standard library and does not import a model."""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "src" / "vesper_bind"
BANNED_ROOTS = {
    "socket",
    "ssl",
    "http",
    "urllib",
    "requests",
    "httpx",
    "urllib3",
    "openai",
    "anthropic",
    "xai",
    "grok",
    "subprocess",
    "tkinter",
    "PyQt5",
    "PyQt6",
    "wx",
    "gi",
}
BANNED_CALLS = {
    "system",
    "popen",
    "execv",
    "execve",
    "execl",
    "execle",
    "execlp",
    "execlpe",
    "execvp",
    "execvpe",
    "spawnv",
    "spawnve",
    "posix_spawn",
    "posix_spawnp",
}


def test_sources_import_neither_network_nor_models() -> None:
    files = sorted(ROOT.glob("*.py"))
    assert files
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".", 1)[0]
                    assert root not in BANNED_ROOTS, f"{path.name} imports {alias.name}"
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                root = module.split(".", 1)[0]
                assert root not in BANNED_ROOTS, f"{path.name} imports {module}"
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if isinstance(node.func.value, ast.Name) and node.func.value.id == "os":
                    assert node.func.attr not in BANNED_CALLS, path.name
