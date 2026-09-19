# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 9 — Maintainability & Code Health."""

from __future__ import annotations

import re

from ..model import Result, Status
from ..repo import Repo

TITLE = "Maintainability & Code Health"

#: Above this, a file is doing more than one job or has stopped being read.
LINE_CEILING = 500
SOURCE = (".rs", ".py", ".js", ".mjs", ".ts")
#: Backtick spans and string literals. Anything inside one is being shown,
#: not asserted.
QUOTED = re.compile(r"`[^`]*`|\"[^\"]*\"|'[^']*'")


def _linters(repo: Repo) -> Result:
    if repo.kind == "rust":
        present = repo.exists(".rustfmt.toml", "rustfmt.toml") and "clippy" in repo.workflow_text
        detail = ".rustfmt.toml and clippy in CI" if present else "no rustfmt config or no clippy in CI"
    elif repo.kind == "python":
        present = repo.exists(".pre-commit-config.yaml", "ruff.toml", ".ruff.toml") or "ruff" in (
            repo.read("pyproject.toml") or ""
        )
        detail = "linter configured" if present else "no ruff or pre-commit configuration"
    elif repo.kind == "node":
        package = repo.read("package.json") or ""
        present = any(k in package for k in ("eslint", "biome", "oxlint")) or repo.exists(".eslintrc.json")
        detail = "linter configured" if present else "no linter in package.json"
    else:
        return Result("9.1", "One formatter, one linter, enforced", Status.NOT_APPLICABLE,
                      "no source code to lint")
    return Result("9.1", "One formatter, one linter, enforced",
                  Status.PASS if present else Status.FAIL, detail)


def _suppressions(repo: Repo) -> Result:
    """An `allow` without a reason beside it is a silenced finding."""
    patterns = (
        re.compile(r"#\[allow\(([^)]+)\)\]"),
        re.compile(r"#\s*noqa(?::\s*\S+)?"),
        re.compile(r"//\s*eslint-disable"),
        re.compile(r"#\s*type:\s*ignore"),
    )
    bare: list[str] = []
    for path in repo.by_suffix(*SOURCE):
        lines = (path.read_text(encoding="utf-8", errors="replace")).splitlines()
        for index, line in enumerate(lines):
            if not any(p.search(line) for p in patterns):
                continue
            # A suppression inside a quoted string is test data describing one,
            # not one in force here.
            if re.search(r'["\']\s*[^"\']*(noqa|eslint-disable|type:\s*ignore)', line):
                continue
            # A reason counts wherever it sits: trailing prose on the same
            # line, a parenthetical after the token, or the comment above.
            # Requiring it to follow a second `#` rejected
            # `# noqa: E402  (needs ROOT on the path first)`, which is a
            # perfectly good reason.
            above = lines[index - 1] if index else ""
            trailing = ""
            for pattern in patterns:
                match = pattern.search(line)
                if match:
                    trailing = line[match.end():]
                    break
            if re.search(r"[A-Za-z]{4,}\s+[A-Za-z]{2,}", trailing) or re.search(
                r"(reason|because|SAFETY|deliberate)", above, re.IGNORECASE
            ):
                continue
            bare.append(f"{path.relative_to(repo.root)}:{index + 1}")
    if not bare:
        return Result("9.1b", "No unjustified lint suppression", Status.PASS, "none found")
    return Result("9.1b", "No unjustified lint suppression", Status.FAIL,
                  f"{len(bare)} without a reason, e.g. {bare[0]}")


def _unsafe(repo: Repo) -> Result:
    if repo.kind != "rust":
        return Result("9.4", "Unsafe code forbidden", Status.NOT_APPLICABLE,
                      f"{repo.kind} project; no unsafe to forbid")
    sources = repo.by_suffix(".rs")
    entry = [p for p in sources if p.name in ("lib.rs", "main.rs")]
    forbidding = [
        p for p in entry
        if "forbid(unsafe_code)" in p.read_text(encoding="utf-8", errors="replace")
    ]
    workspace = "unsafe_code = \"forbid\"" in (repo.read("Cargo.toml") or "")
    if workspace or (entry and len(forbidding) == len(entry)):
        return Result("9.4", "Unsafe code forbidden", Status.PASS,
                      "workspace lint" if workspace else f"{len(forbidding)} crate root(s)")
    return Result("9.4", "Unsafe code forbidden", Status.FAIL,
                  f"{len(entry) - len(forbidding)} crate root(s) do not forbid unsafe")


def _file_size(repo: Repo) -> Result:
    oversized = []
    for path in repo.by_suffix(*SOURCE):
        count = path.read_text(encoding="utf-8", errors="replace").count("\n")
        if count > LINE_CEILING:
            oversized.append(f"{path.relative_to(repo.root)} ({count})")
    if not oversized:
        return Result("9.7", f"No source file over {LINE_CEILING} lines", Status.PASS,
                      f"largest under {LINE_CEILING}")
    return Result("9.7", f"No source file over {LINE_CEILING} lines", Status.FAIL,
                  f"{len(oversized)}: {', '.join(oversized[:3])}")


def _todos(repo: Repo) -> Result:
    loose = []
    # A marker is a task when it opens a comment, optionally followed by a
    # colon or an owner: `# FIXME: x`, `// HACK(seb)`. Matching the bare word
    # anywhere flags every line that *discusses* such markers -- including the
    # pattern below and this very comment, which is how the check first failed
    # against its own source, twice.
    marker = re.compile(r"(?:#|//|/\*|<!--)\s*(TODO|FIXME|XXX|HACK)\b\s*[:(]?")
    linked = re.compile(r"(#\d+|issues?/\d+|[A-Z]+-\d+)")
    # Source and config only. A TODO in prose is usually a document about
    # TODOs -- this tool's own rubric says "Every TODO links to a tracked
    # issue", and flagged itself for saying so.
    for path in repo.by_suffix(*SOURCE, ".toml", ".yml"):
        for index, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines()):
            # A marker inside backticks or a string literal is being quoted,
            # not raised: documentation showing the form, or a test fixture.
            bare = QUOTED.sub("", line)
            if marker.search(bare) and not linked.search(bare):
                loose.append(f"{path.relative_to(repo.root)}:{index + 1}")
    if not loose:
        return Result("9.10", "Every TODO links to a tracked issue", Status.PASS, "none unlinked")
    return Result("9.10", "Every TODO links to a tracked issue", Status.FAIL,
                  f"{len(loose)} unlinked, e.g. {loose[0]}")


def run(repo: Repo) -> list[Result]:
    return [
        _linters(repo),
        _suppressions(repo),
        Result("9.2", "No logic duplicated across repositories", Status.UNVERIFIED,
               "cross-repository comparison; this tool scores one repository at a time"),
        Result("9.3", "Type checking enforced", Status.UNVERIFIED,
               "presence of mypy or clippy::pedantic does not prove it gates the build"),
        _unsafe(repo),
        Result("9.5", "Single source of truth for duplicated lists", Status.UNVERIFIED,
               "identifying which two lists are meant to agree needs intent, not pattern matching"),
        Result("9.6", "Cyclomatic complexity ceiling", Status.UNVERIFIED,
               "no language-agnostic complexity measure is implemented here"),
        _file_size(repo),
        Result("9.8", "Consistent style across the tree", Status.UNVERIFIED,
               "a formatter check in CI covers this; running it is the formatter's job, not this tool's"),
        Result("9.9", "Dead code and unused dependencies removed", Status.UNVERIFIED,
               "needs cargo-udeps or vulture, which are build-environment tools"),
        _todos(repo),
    ]
