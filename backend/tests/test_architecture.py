"""The iDesign call rules are enforced by the build, not by review (ADR-008, NFR-10).

These tests guard the guard. The first asserts the codebase conforms; the rest assert the
contracts would actually catch a violation, because a layering contract that silently
matches nothing is worse than no contract at all.

Contracts covering individual services — manager independence, rule-engine purity — are
added alongside those services, because import-linter treats a contract naming a
non-existent module as an error rather than a no-op.
"""

import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = BACKEND_ROOT / "src" / "quookly"

_RUN_LINTER = "import sys; from importlinter.cli import lint_imports; sys.exit(lint_imports())"


def lint_imports() -> subprocess.CompletedProcess[str]:
    """Run import-linter over the backend package."""
    return subprocess.run(
        [sys.executable, "-c", _RUN_LINTER],
        cwd=BACKEND_ROOT,
        capture_output=True,
        text=True,
    )


@contextmanager
def violating_module(relative_path: str, source: str) -> Iterator[None]:
    """Place a module inside the package for the duration of the test, then remove it."""
    path = PACKAGE_ROOT / relative_path
    path.write_text(source)
    try:
        yield
    finally:
        path.unlink(missing_ok=True)


def assert_rejected(result: subprocess.CompletedProcess[str], what: str) -> None:
    """Assert import-linter rejected the code by breaking a contract.

    A non-zero exit alone is not enough: the linter also exits non-zero when it errors,
    which would let a broken test suite masquerade as a working guard.
    """
    assert result.returncode != 0, f"import-linter accepted {what}:\n{result.stdout}"
    assert "Broken contracts" in result.stdout, (
        f"import-linter failed for {what}, but not by breaking a contract:\n"
        f"{result.stdout}\n{result.stderr}"
    )


class TestArchitectureContracts:
    def test_the_codebase_conforms(self) -> None:
        result = lint_imports()
        assert result.returncode == 0, (
            f"import-linter reported violations:\n{result.stdout}\n{result.stderr}"
        )

    def test_resource_access_may_not_import_a_manager(self) -> None:
        """Calls flow downward. Access sits below managers and must never reach up."""
        with violating_module(
            "access/_violation_probe.py",
            "from quookly import managers\n\n__all__ = ['managers']\n",
        ):
            result = lint_imports()
        assert_rejected(result, "a resource access service importing a manager")

    def test_an_engine_may_not_import_a_manager(self) -> None:
        """Engines are below managers and never call upward."""
        with violating_module(
            "engines/_violation_probe.py",
            "from quookly import managers\n\n__all__ = ['managers']\n",
        ):
            result = lint_imports()
        assert_rejected(result, "an engine importing a manager")

    def test_a_utility_may_not_import_a_manager(self) -> None:
        """A utility that reaches into the layers stops being usable by all of them."""
        with violating_module(
            "utilities/_violation_probe.py",
            "from quookly import managers\n\n__all__ = ['managers']\n",
        ):
            result = lint_imports()
        assert_rejected(result, "a utility importing a manager")

    def test_contracts_may_not_import_the_rest_of_the_package(self) -> None:
        """`contracts` is what lets the layers share types without importing each other."""
        with violating_module(
            "contracts/_violation_probe.py",
            "from quookly import access\n\n__all__ = ['access']\n",
        ):
            result = lint_imports()
        assert_rejected(result, "a contract importing resource access")

    def test_a_new_top_level_package_cannot_escape_the_rules(self) -> None:
        """The layers contract is exhaustive, so an undeclared package is a failure."""
        probe = PACKAGE_ROOT / "_rogue_layer"
        probe.mkdir(exist_ok=True)
        (probe / "__init__.py").write_text('"""Undeclared package."""\n')
        try:
            result = lint_imports()
        finally:
            (probe / "__init__.py").unlink(missing_ok=True)
            probe.rmdir()
        assert_rejected(result, "a package belonging to no declared layer")
