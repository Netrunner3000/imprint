"""Architecture contracts for Imprint's package-per-agent structure."""

from __future__ import annotations

import ast
import importlib
from pathlib import Path

from agents.catalog import AGENT_SPECS, AGENTS_BY_KEY, workspace_map


ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = ROOT / "agents"


def test_every_catalog_agent_owns_a_project_directory():
    for spec in AGENT_SPECS:
        project = ROOT / Path(*spec.package.split("."))
        assert project.is_dir(), spec.key
        assert (project / "__init__.py").is_file(), spec.key
        for document in ("README.md", "TODO.md", "SUGGESTIONS.md"):
            path = project / document
            assert path.is_file(), f"{spec.key} does not own {document}"
            assert len(path.read_text(encoding="utf-8").strip()) > 80, path


def test_agent_public_packages_are_importable():
    for spec in AGENT_SPECS:
        module = importlib.import_module(spec.package)
        assert module is not None


def test_every_visible_agent_owns_runtime_code():
    """A project cannot be documentation around implementation left elsewhere."""
    for spec in AGENT_SPECS:
        if not spec.panel:
            continue
        project = ROOT / Path(*spec.package.split("."))
        runtime = [path for path in project.glob("*.py") if path.name != "__init__.py"]
        assert runtime, f"{spec.key} has no owned runtime module"


def test_catalog_is_unique_and_drives_visible_workspaces():
    keys = [spec.key for spec in AGENT_SPECS]
    assert len(keys) == len(set(keys))
    assert set(keys) == set(AGENTS_BY_KEY)
    listed = [key for keys in workspace_map().values() for key in keys]
    assert listed == [spec.key for spec in AGENT_SPECS if spec.workspace]


def test_router_only_returns_catalog_agent_keys():
    from agents.router import ROUTES, RouterAgent

    router = RouterAgent()
    for key, keywords in ROUTES:
        assert key in AGENTS_BY_KEY
        assert keywords
        assert router.classify(keywords[0]) == key
    assert router.classify("an ambiguous request") in AGENTS_BY_KEY


def test_legacy_flat_agent_modules_are_gone():
    legacy = sorted(AGENTS_DIR.glob("*_agent.py"))
    legacy += [AGENTS_DIR / "audiobook_connector.py"] \
        if (AGENTS_DIR / "audiobook_connector.py").exists() else []
    assert not legacy, f"flat modules bypass package ownership: {legacy}"


def test_agents_do_not_import_another_agents_private_module():
    violations = []
    for source in AGENTS_DIR.glob("*/agent.py"):
        owner = source.parent.name
        tree = ast.parse(source.read_text(encoding="utf-8"), filename=str(source))
        for node in ast.walk(tree):
            module = node.module if isinstance(node, ast.ImportFrom) else None
            if not module or not module.startswith("agents."):
                continue
            parts = module.split(".")
            if len(parts) >= 3 and parts[1] != owner and parts[2] == "agent":
                violations.append(f"{source}: imports {module}")
    assert not violations, "\n".join(violations)


def test_frozen_build_bundles_agent_project_documents():
    spec = (ROOT / "Imprint.spec").read_text(encoding="utf-8")
    assert 'for _project_doc in ("README.md", "TODO.md", "SUGGESTIONS.md")' in spec
    assert 'f"agents/{_agent_project.name}"' in spec
