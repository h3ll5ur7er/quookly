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
def violating_line(relative_path: str, source: str) -> Iterator[None]:
    """Append a line to a module that already exists, then put it back.

    Needed where the contract names specific modules: planting a *new* module would not
    be covered by it, and the test would pass without the guard ever firing.
    """
    path = PACKAGE_ROOT / relative_path
    original = path.read_text()
    path.write_text(original + source)
    try:
        yield
    finally:
        path.write_text(original)


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

    def test_the_orm_may_not_escape_the_access_layer(self) -> None:
        """ADR-018: if business logic imported SQLModel, the datastore would be domain."""
        with violating_module(
            "engines/_violation_probe.py",
            "from sqlmodel import SQLModel\n\n__all__ = ['SQLModel']\n",
        ):
            result = lint_imports()
        assert_rejected(result, "an engine importing the ORM")

    def test_a_rule_engine_may_not_reach_resource_access(self) -> None:
        """Rule engines take their inputs as arguments; that is what makes them testable.

        The probe goes into a real rule engine rather than a new module, because the
        contract now names the rule engines one at a time — a fresh module would not be
        covered by it, and a test that passes by not being watched proves nothing.
        """
        with violating_line(
            "engines/measure.py", "\nfrom quookly import access as _probe  # noqa: F401\n"
        ):
            result = lint_imports()
        assert_rejected(result, "a rule engine importing resource access")

    def test_a_capability_engine_may(self) -> None:
        """`InterpretationEngine` mediates a model, so it reaches resource access by
        design (ADR-003). It is absent from the contract deliberately, and this asserts
        that the absence is the reason rather than an oversight in the rule itself."""
        source = (PACKAGE_ROOT / "engines" / "interpretation.py").read_text()
        assert "from quookly.access import" in source
        assert lint_imports().returncode == 0

    def test_a_client_may_not_reach_resource_access(self) -> None:
        """A route that reads the database itself has no manager to hold the use case.

        The layers contract allows a layer to skip one below it, so this rule needs a
        contract of its own -- and it is the rule most easily broken by a route that only
        needs "one quick lookup".
        """
        with violating_module(
            "routes/_violation_probe.py",
            "from quookly import access\n\n__all__ = ['access']\n",
        ):
            result = lint_imports()
        assert_rejected(result, "a route importing resource access")

    def test_a_manager_may_not_call_another_manager(self) -> None:
        """A use case that needs another use case has not been decomposed (ADR-002).

        The probe goes into a real manager, because the contract names them one at a
        time: a fresh module would not be covered, and a test that passes by not being
        watched proves nothing. Two managers wanting to talk is the signal for an event —
        cooking publishes `MealCooked` rather than reaching into the pantry itself.
        """
        with violating_line(
            "managers/pantry.py",
            "\nfrom quookly.managers import recipe as _probe  # noqa: F401\n",
        ):
            result = lint_imports()
        assert_rejected(result, "a manager importing another manager")

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
