#!/usr/bin/env python3
"""The documentation says what the code does, and says it about things that exist.

Three checks, each written because the thing it catches actually happened.

**Anchors resolve.** Renaming an ADR's heading breaks every link to it, silently: a
markdown link to a missing fragment scrolls to the top of the page and looks like a bad
click. Four were broken when this was written, one of them from a rename in the same
commit that made the link.

**A citation points at something.** Code here cites `ADR-064`, `FR-18`, `UC-9.1b` in
docstrings, and a citation is only worth writing if a reader who follows it arrives
somewhere. `UC-2.7` was cited in a route for a use case nobody had written down.

**The architecture doc names every service.** Its catalogue said "six managers" while
thirteen modules sat in `managers/`, and three engines built during Phase 8b were in
nobody's table. A catalogue that lags the code is worse than no catalogue: it is read as
current.

Run by `just docs`, and by `just check` through it.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "doc"
DECISIONS = DOCS / "07-decisions.md"
REQUIREMENTS = DOCS / "02-requirements.md"
ARCHITECTURE = DOCS / "04-architecture.md"

#: Where code lives that is allowed to cite the documentation.
SOURCE = (
    ROOT / "backend" / "src",
    ROOT / "frontend" / "src" / "app",
    ROOT / "frontend" / "e2e",
    ROOT / "cli" / "src",
)
SOURCE_SUFFIXES = {".py", ".ts", ".html", ".scss"}

#: Services the architecture describes but this build has not written yet. Listed rather
#: than inferred: "not built" and "renamed and nobody updated the doc" look identical from
#: here, and only one of them is fine.
NOT_BUILT_YET = {
    "CommunityAccess",
    "EngagementManager",
    "ScoringEngine",
}

#: Not services. `ResourceAccess` is a layer, `ModelsAccess` is the SQLModel table
#: definitions, and neither belongs in a catalogue of business verbs.
NOT_A_SERVICE = {"ResourceAccess", "ModelsAccess"}


def anchor_of(heading: str) -> str:
    """The fragment GitHub gives a heading.

    Punctuation is dropped and spaces become hyphens — *without* collapsing runs of them,
    which is why an em dash leaves two hyphens behind. Getting that wrong makes this
    checker report nine links that are fine, which is how it read the first time.
    """
    plain = re.sub(r"[^\w\s-]", "", heading.strip().lower())
    return plain.replace(" ", "-")


def markdown_files() -> list[Path]:
    return sorted([*DOCS.glob("*.md"), ROOT / "README.md"])


def source_files() -> list[Path]:
    found: list[Path] = []
    for folder in SOURCE:
        if folder.exists():
            found += [
                path
                for path in folder.rglob("*")
                if path.suffix in SOURCE_SUFFIXES and "/api/" not in str(path)
            ]
    return found


def check_anchors(failures: list[str]) -> int:
    pages = {path.name: path.read_text(encoding="utf-8") for path in markdown_files()}
    anchors = {
        name: {anchor_of(one) for one in re.findall(r"^#{1,6}\s+(.*)$", text, re.M)}
        for name, text in pages.items()
    }
    checked = 0
    for name, text in pages.items():
        for target, fragment in re.findall(
            r"\]\((?:\./)?(?:doc/)?([\w.-]+\.md)#([\w-]+)\)", text
        ):
            if target not in anchors:
                continue
            checked += 1
            if fragment not in anchors[target]:
                failures.append(f"{name}: link to {target}#{fragment} — no such heading")

        # Same-page links, which are most of them: `07-decisions.md` is one long file of
        # decisions citing each other, and a rename breaks those first. Missing this was
        # how the checker passed a page whose own cross-references were broken.
        for fragment in re.findall(r"\]\(#([\w-]+)\)", text):
            checked += 1
            if fragment not in anchors[name]:
                failures.append(f"{name}: link to #{fragment} — no such heading in this page")
    return checked


def check_citations(failures: list[str]) -> int:
    decisions = {
        number for number in re.findall(r"^## (ADR-\d+)", DECISIONS.read_text(), re.M)
    }
    requirements = {
        one for one in re.findall(r"^\| ((?:FR|UC)-[\d.]+\w*) \|", REQUIREMENTS.read_text(), re.M)
    }
    checked = 0
    for path in source_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        where = path.relative_to(ROOT)
        for cited in set(re.findall(r"\bADR-\d{3}\b", text)):
            checked += 1
            if cited not in decisions:
                failures.append(f"{where}: cites {cited}, which is not a decision")
        # `UC-9.*` and the like are deliberate wildcards: a docstring saying it implements
        # a family is not claiming there is a use case with a star in its number.
        for cited in set(re.findall(r"\b((?:FR|UC)-\d+(?:\.\d+\w*)?)\b(?![.*\w])", text)):
            if cited.count(".") == 0 and cited.startswith("UC"):
                continue
            checked += 1
            if cited not in requirements:
                failures.append(f"{where}: cites {cited}, which is not a requirement")
    return checked


def check_service_catalogue(failures: list[str]) -> int:
    named = set(re.findall(r"\b([A-Z][a-zA-Z]+(?:Manager|Engine|Access))\b", ARCHITECTURE.read_text()))
    on_disk: dict[str, str] = {}
    for folder, suffix in (("managers", "Manager"), ("engines", "Engine"), ("access", "Access")):
        here = ROOT / "backend" / "src" / "quookly" / folder
        for path in sorted(here.glob("*.py")):
            if path.stem == "__init__":
                continue
            service = "".join(part.capitalize() for part in path.stem.split("_")) + suffix
            on_disk[service] = f"{folder}/{path.name}"

    for service, module in sorted(on_disk.items()):
        if service in NOT_A_SERVICE:
            continue
        if service not in named:
            failures.append(f"04-architecture.md never names {service} ({module})")

    for service in sorted(named - set(on_disk) - NOT_BUILT_YET - NOT_A_SERVICE):
        failures.append(
            f"04-architecture.md names {service}, which is not a module — renamed, or add it to "
            "NOT_BUILT_YET in this checker"
        )
    return len(on_disk)


def main() -> int:
    failures: list[str] = []
    links = check_anchors(failures)
    citations = check_citations(failures)
    services = check_service_catalogue(failures)

    if failures:
        print(f"Documentation: {len(failures)} problem(s).\n")
        for one in failures:
            print(f"  {one}")
        print()
        return 1

    print(
        f"Documentation: {links} links resolve, {citations} citations point at something, "
        f"{services} services are named."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
