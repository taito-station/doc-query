import ast
from pathlib import Path

NETWORK_MODULES = {
    "urllib", "http", "requests", "httpx", "aiohttp",
    "socket", "socketserver", "xmlrpc", "grpc",
    "websocket", "ftplib", "smtplib", "poplib",
    "imaplib", "nntplib", "telnetlib",
}


def test_docq_has_no_network_imports():
    docq_root = Path(__file__).resolve().parent.parent / "docq"
    violations = []

    for path in sorted(docq_root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top_level = alias.name.split(".")[0]
                    if top_level in NETWORK_MODULES:
                        violations.append(f"{path}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                if node.module is None:
                    continue
                top_level = node.module.split(".")[0]
                if top_level in NETWORK_MODULES:
                    violations.append(f"{path}: from {node.module} import ...")

    assert not violations, "docq に禁止されたネットワーク系 import が見つかりました:\n" + "\n".join(violations)
