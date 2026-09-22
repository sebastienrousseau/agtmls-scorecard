# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 4 — API & Developer Experience.

The previous placeholder said this needed "the CLI surface enumerated and each
command invoked". Enumerating it does not need invoking it: an argparse
`add_parser` call and a clap `#[command]` attribute both name a subcommand in
the source, and a flag either appears beside it or does not.

Invoking every subcommand to read its `--help` would mean executing the
repository being scored, which is not a thing a scorer should do to an
arbitrary checkout. So the checks that need execution stay `unverified`, and
the ones that are a property of the declared surface are decided.

The distinction that matters throughout: a flag existing **somewhere** in the
repository is not the criterion. `--json` on one subcommand out of thirty-five
is the state agtmls was actually in, and a check that accepted it would have
reported developer experience as solved.
"""

from __future__ import annotations

import re

from ..model import Result, Status
from ..repo import Repo

TITLE = "API & Developer Experience"

#: How a subcommand is declared, per ecosystem.
SUBCOMMAND = re.compile(
    r"""add_parser\(\s*["']([a-z][a-z0-9-]*)["']"""      # argparse
    r"""|\.subcommand\(\s*Command::new\(\s*["']([a-z][a-z0-9-]*)["']"""  # clap builder
    r"""|\.command\(\s*["']([a-z][a-z0-9-]*)["']"""      # commander / yargs
)
#: Commands that destroy or overwrite something the user did not hand us.
DESTRUCTIVE = ("install", "uninstall", "remove", "clean", "reset", "sync", "apply",
               "write", "publish", "delete", "prune", "import")
EXIT_TAXONOMY = re.compile(r"EXIT_[A-Z_]+\s*=\s*\d|ExitCode::|exit_code|exit-codes")
#: A remediation names something to do, not only something that is wrong.
REMEDY = re.compile(r"\brun\b|\buse\b|\bsee\b|\bset\b|\btry\b|\badd\b|\bpass\b|\breinstall\b")
#: "FAIL: 3 issue(s)" is a tally printed under the errors that already
#: explained themselves. Asking it to repeat a remedy would make every summary
#: line worse, so tallies leave the denominator.
TALLY = re.compile(r"\{[^}]+\}[^\"']{0,40}\(s\)")
SEMVER_TOOL = re.compile(r"cargo-semver-checks|semver-checks|griffe|api-extractor|apidiff|gorelease")
COMPLETION_DIRS = ("completions", "completion", "contrib/completions")


def _subcommands(repo: Repo) -> dict[str, str]:
    """Declared subcommand -> the file that declares it."""
    found: dict[str, str] = {}
    for path in repo.by_suffix(".py", ".rs", ".js", ".ts"):
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in SUBCOMMAND.finditer(text):
            name = next(g for g in match.groups() if g)
            found.setdefault(name, str(path.relative_to(repo.root)))
    return found


def _cli_text(repo: Repo) -> str:
    return "".join(
        p.read_text(encoding="utf-8", errors="replace")
        for p in repo.by_suffix(".py", ".rs", ".js", ".ts")
    )


def _no_cli(criterion: str, title: str) -> Result:
    return Result(criterion, title, Status.NOT_APPLICABLE,
                  "no subcommand surface was found to hold to this")


def _json_coverage(repo: Repo) -> Result:
    title = "Machine-readable output on the commands that produce data"
    commands = _subcommands(repo)
    if not commands:
        return _no_cli("4.1", title)
    text = _cli_text(repo)
    if "--json" not in text and '"json"' not in text:
        return Result("4.1", title, Status.FAIL,
                      f"{len(commands)} subcommand(s) and no --json anywhere")
    # Count the flag against the surface rather than asking whether it exists.
    flags = len(re.findall(r"--json\b", text))
    if flags * 2 < len(commands):
        return Result("4.1", title, Status.FAIL,
                      f"--json appears {flags} time(s) across {len(commands)} subcommand(s); "
                      "a flag on a minority of the surface is not a machine interface")
    return Result("4.1", title, Status.PASS,
                  f"--json across {flags} of {len(commands)} subcommand(s)")


def _dry_run(repo: Repo) -> Result:
    title = "Destructive commands offer a dry run"
    commands = _subcommands(repo)
    if not commands:
        return _no_cli("4.2", title)
    destructive = sorted(n for n in commands if any(d in n for d in DESTRUCTIVE))
    if not destructive:
        return Result("4.2", title, Status.NOT_APPLICABLE,
                      "no subcommand named for a destructive action")
    if "--dry-run" not in _cli_text(repo):
        return Result("4.2", title, Status.FAIL,
                      f"destructive subcommand(s) {', '.join(destructive)} with no --dry-run: "
                      "the only way to find out what happens is for it to happen")
    return Result("4.2", title, Status.PASS,
                  f"--dry-run available beside {', '.join(destructive)}")


def _refuses_to_clobber(repo: Repo) -> Result:
    title = "No command overwrites user data without refusing or backing up"
    commands = _subcommands(repo)
    if not commands or not any(any(d in n for d in DESTRUCTIVE) for n in commands):
        return Result("4.3", title, Status.NOT_APPLICABLE, "nothing destructive declared")
    text = _cli_text(repo)
    guarded = re.search(r"--force\b", text) and re.search(r"backup|\.bak\b|refus", text, re.IGNORECASE)
    if not guarded:
        return Result("4.3", title, Status.FAIL,
                      "no --force/backup pairing: a destructive command with no refusal "
                      "path overwrites by default")
    tested = any(
        re.search(r"backup|refus|clobber|overwrit", p.read_text(encoding="utf-8", errors="replace"),
                  re.IGNORECASE)
        for p in repo.files
        if "test" in p.name.lower() or "smoke" in p.name.lower()
    )
    if not tested:
        return Result("4.3", title, Status.FAIL,
                      "a refusal path exists but no test drives it; an untested refusal "
                      "is the one that stops working quietly")
    return Result("4.3", title, Status.PASS, "refusal and backup, exercised by a test")


def _exit_codes(repo: Repo) -> Result:
    title = "Exit codes are a documented taxonomy"
    if repo.kind == "docs" or not repo.has_cli:
        return Result("4.4", title, Status.NOT_APPLICABLE, "no command to exit")
    declared = EXIT_TAXONOMY.search(_cli_text(repo))
    documented = any(
        re.search(r"exit code", p.read_text(encoding="utf-8", errors="replace"), re.IGNORECASE)
        for p in repo.by_suffix(".md")
    )
    if declared and documented:
        return Result("4.4", title, Status.PASS, "named exit codes, and documented")
    if declared:
        return Result("4.4", title, Status.FAIL,
                      "exit codes are named in code but documented nowhere, so no caller "
                      "can branch on them without reading the source")
    return Result("4.4", title, Status.FAIL,
                  "0 and 1 by accident: a caller cannot tell 'it failed' from "
                  "'you typed it wrong'")


def _remediation(repo: Repo) -> Result:
    title = "Error messages name a remediation"
    messages: list[str] = []
    for path in repo.by_suffix(".py", ".rs"):
        text = path.read_text(encoding="utf-8", errors="replace")
        messages.extend(re.findall(r'["\'](?:FAIL|ERROR|error)[:\s][^"\']{15,}["\']', text))
    messages = [m for m in messages if not TALLY.search(m)]
    if len(messages) < 5:
        return Result("4.5", title, Status.UNVERIFIED,
                      f"only {len(messages)} error string(s) found; too few to judge a habit")
    with_remedy = [m for m in messages if REMEDY.search(m)]
    share = len(with_remedy) / len(messages)
    if share < 0.4:
        bare = [m.strip("\"'")[:60] for m in messages if not REMEDY.search(m)][:2]
        return Result("4.5", title, Status.FAIL,
                      f"{len(with_remedy)} of {len(messages)} error message(s) suggest an "
                      f"action; the rest state a problem and stop, e.g. "
                      + "; ".join(repr(b) for b in bare))
    return Result("4.5", title, Status.PASS,
                  f"{len(with_remedy)} of {len(messages)} error message(s) name an action")


def _completions(repo: Repo) -> Result:
    title = "Shell completions are generated, not hand-written"
    if repo.kind == "docs":
        return Result("4.6", title, Status.NOT_APPLICABLE, "no executable")
    present = [d for d in COMPLETION_DIRS if (repo.root / d).is_dir()]
    if not present:
        return Result("4.6", title, Status.NOT_APPLICABLE,
                      "ships no completions; this criterion grades how they are "
                      "produced, not whether they exist")
    generator = any(
        "completion" in p.name.lower() and re.search(r"--check|--write", p.read_text(encoding="utf-8", errors="replace"))
        for p in repo.by_suffix(".py", ".rs")
    )
    if not generator:
        return Result("4.6", title, Status.FAIL,
                      f"{present[0]}/ is hand-written: it will drift from the CLI "
                      "the first time a flag changes")
    return Result("4.6", title, Status.PASS, f"{present[0]}/ generated with a --check mode")


def _semver_gate(repo: Repo) -> Result:
    title = "Public API changes are gated by a semver-diff tool"
    if repo.kind == "docs":
        return Result("4.9", title, Status.NOT_APPLICABLE, "no public API")
    if SEMVER_TOOL.search(repo.workflow_text):
        return Result("4.9", title, Status.PASS, "an API-diff tool runs in CI")
    return Result("4.9", title, Status.FAIL,
                  "nothing compares the public API between releases, so a breaking "
                  "change ships as a patch")


def run(repo: Repo) -> list[Result]:
    return [
        _json_coverage(repo),
        _dry_run(repo),
        _refuses_to_clobber(repo),
        _exit_codes(repo),
        _remediation(repo),
        _completions(repo),
        Result("4.7", "Every subcommand has help with an example", Status.UNVERIFIED,
               "reading --help means executing the repository under inspection, "
               "which a scorer should not do to an arbitrary checkout"),
        Result("4.8", "Config resolution order is documented and tested", Status.UNVERIFIED,
               "which sources configure a tool, and in what order, is intent this "
               "tool cannot infer from a source tree"),
        _semver_gate(repo),
        Result("4.10", "Install works from a clean machine by every documented path",
               Status.UNVERIFIED,
               "needs a container per documented install method"),
    ]
