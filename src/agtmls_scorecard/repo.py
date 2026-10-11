# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""What a check can see: the repository under inspection."""

from __future__ import annotations

import functools
import re
import subprocess
from pathlib import Path

#: Directories no check should read. Scoring a repository by what is in its
#: build output would reward a dirty tree.
IGNORED = {
    ".git", "target", "node_modules", "__pycache__", ".venv", "dist", "build",
    "pkg", "pkg-node",
    # Vendored and generated: committed, but not authored here. Judging a
    # repository on the line length of a wasm-bindgen shim rewards nothing.
    "vendor", "generated", "_generated",
}
#: Files that say they are generated, wherever they sit.
GENERATED_MARKER = "@generated"


class Repo:
    """A repository, with the reads a check needs and a cache in front."""

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    @property
    def name(self) -> str:
        return self.root.name

    def exists(self, *relative: str) -> bool:
        return any((self.root / r).exists() for r in relative)

    def read(self, relative: str) -> str | None:
        path = self.root / relative
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    @functools.cached_property
    def files(self) -> list[Path]:
        """Tracked-ish files: everything not in an ignored directory."""
        return sorted(
            p
            for p in self.root.rglob("*")
            if p.is_file() and not p.is_symlink() and not (IGNORED & set(p.relative_to(self.root).parts))
        )

    def by_suffix(self, *suffixes: str) -> list[Path]:
        """Authored files with these extensions.

        A file carrying a generated-code marker is excluded: its author is a
        tool, and the tool is not the thing being scored.
        """
        wanted = {s.lower() for s in suffixes}
        out = []
        for path in self.files:
            if path.suffix.lower() not in wanted:
                continue
            head = path.read_text(encoding="utf-8", errors="replace")[:400]
            if GENERATED_MARKER in head or "Do not edit" in head or "DO NOT EDIT" in head:
                continue
            out.append(path)
        return out

    @functools.cached_property
    def workflows(self) -> dict[str, str]:
        """Workflow file contents, by filename."""
        directory = self.root / ".github" / "workflows"
        if not directory.is_dir():
            return {}
        return {
            p.name: p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(directory.glob("*.yml")) + sorted(directory.glob("*.yaml"))
        }

    @property
    def workflow_text(self) -> str:
        return "\n".join(self.workflows.values())

    @functools.cached_property
    def kind(self) -> str:
        """rust | python | node | docs — decides which criteria apply."""
        if (self.root / "Cargo.toml").exists():
            return "rust"
        if (self.root / "pyproject.toml").exists():
            return "python"
        if (self.root / "package.json").exists():
            return "node"
        return "docs"

    @functools.cached_property
    def has_cli(self) -> bool:
        """Does this repository ship something a person types at a prompt?

        Half of category 4 and category 6 only mean anything for a command.
        Asking a WASM module for `--version`, or a GitHub Action for a
        `doctor` subcommand, produces findings nobody can act on -- and a
        scorer that cries wolf is one people switch off, which scores nothing
        while looking like it scores everything.
        """
        # A Cargo workspace keeps its binary in a member crate, so reading only
        # the root manifest reported agtmls-core -- which ships agtmls-cli --
        # as having no command at all.
        if any(
            p.name == "main.rs" or (p.parent.name == "bin" and p.suffix == ".rs")
            for p in self.files
        ):
            return True
        if any("[[bin]]" in (p.read_text(encoding="utf-8", errors="replace"))
               for p in self.files if p.name == "Cargo.toml"):
            return True
        if "[project.scripts]" in (self.read("pyproject.toml") or ""):
            return True
        package = self.read("package.json") or ""
        if re.search(r'"bin"\s*:', package):
            return True
        for path in self.by_suffix(".py", ".rs", ".js", ".ts"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"add_parser\(|Command::new\(|\.command\(", text):
                return True
        return False

    @functools.cached_property
    def emits_json(self) -> bool:
        """Does anything here produce JSON for another program to read?"""
        if "serde_json" in (self.read("Cargo.toml") or ""):
            return True
        for path in self.by_suffix(".py", ".rs", ".js", ".ts"):
            text = path.read_text(encoding="utf-8", errors="replace")
            if re.search(r"json\.dumps|JSON\.stringify|serde_json::|to_string_pretty|json!\(", text):
                return True
        return False

    @functools.cached_property
    def runs_checks(self) -> bool:
        """Does this repository run a suite of independent checks of its own?

        Criteria about collecting every failure, timing each one and keeping a
        trend are about a gate. A library has none of those things and is not
        worse for it.
        """
        if self.exists("checks.json", "Makefile", "justfile", "tox.ini", "noxfile.py"):
            return True
        return any(
            re.search(r"run[_-]all[_-]checks|validate-|conformance|check[_-]suite", p.name)
            for p in self.files
        )

    def git(self, *args: str) -> str:
        try:
            proc = subprocess.run(
                ["git", *args],
                cwd=self.root,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
                timeout=30,
            )
            return proc.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            return ""

    @functools.cached_property
    def action_uses(self) -> list[tuple[str, str]]:
        """(file, `uses:` reference) for every action in every workflow."""
        found: list[tuple[str, str]] = []
        for name, text in self.workflows.items():
            for match in re.finditer(r"uses:\s*([^\s#]+)", text):
                found.append((name, match.group(1)))
        return found
