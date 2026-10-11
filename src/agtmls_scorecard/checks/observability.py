# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Category 6 — Observability & Diagnostics.

The previous placeholder said this category "needs a running process to
inspect". Most of it does not. Whether a tool can emit JSON, whether its
findings carry stable identifiers, whether a gate stops at the first failure
or collects them all — each of those is a property of the source, and each is
the difference between a failure someone can act on and a failure someone
reruns hoping for better luck.

What genuinely needs a process stays `unverified`: that a traceback never
reaches a user as the primary error is a claim about every input, and a
static read sees only the inputs someone thought of.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..model import Result, Status
from ..repo import Repo

TITLE = "Observability & Diagnostics"

JSON_FLAG = re.compile(r'--json\b|"json"|log[_-]format')
LOG_FORMAT = re.compile(r'--log-format|log_format|structured[_\s]log|RUST_LOG|tracing::|logging\.')
#: A finding identifier of the shape PREFIX-CLASS-NNN, the shape a tool can
#: suppress, a policy can reference and a changelog can deprecate.
RULE_ID = re.compile(r"\b[A-Z]{2,6}-[A-Z]{2,8}-\d{3}\b")
#: Returning on the first failure costs one fix per round trip.
COLLECTS = re.compile(
    r"(errors|failures|problems|findings)\s*(:\s*list|=\s*\[\])"
    r"|\.append\((?:Result|Finding|error|failure|problem)"
    r"|collect::<Vec<",
)
VERSION_FLAG = re.compile(r'--version|"-V"|version_flag|CARGO_PKG_VERSION|__version__')
TELEMETRY = re.compile(
    r"\b(posthog|segment\.io|mixpanel|amplitude|sentry_sdk|datadog|analytics\.track)\b"
    r"|telemetry\.(send|report|emit)",
    re.IGNORECASE,
)
OFFLINE_TEST = re.compile(r"offline|no[_-]network|network[_-]isolat|--offline", re.IGNORECASE)
HISTORY = re.compile(r"history|trend|\.jsonl|runs/|previous[_\s]run", re.IGNORECASE)


def _sources(repo: Repo):
    return repo.by_suffix(".py", ".rs", ".js", ".ts")


def _any_source(repo: Repo, pattern: re.Pattern) -> str | None:
    for path in _sources(repo):
        if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            return str(path.relative_to(repo.root))
    return None


def _structured_output(repo: Repo) -> Result:
    title = "Machine-readable output is available"
    if repo.kind == "docs" or not repo.has_cli:
        return Result("6.1", title, Status.NOT_APPLICABLE,
                      "no command whose output another program would parse")
    where = _any_source(repo, LOG_FORMAT) or _any_source(repo, JSON_FLAG)
    if where:
        return Result("6.1", title, Status.PASS, f"structured output in {where}")
    if repo.emits_json:
        return Result("6.1", title, Status.PASS, "speaks JSON natively")
    return Result("6.1", title, Status.FAIL,
                  "no JSON or structured-log path: every consumer has to parse prose")


def _doctor(repo: Repo) -> Result:
    title = "A doctor command diagnoses a broken install"
    if repo.kind == "docs" or not repo.has_cli:
        return Result("6.2", title, Status.NOT_APPLICABLE,
                      "ships no installable command to diagnose")
    doctor = [p for p in _sources(repo) if "doctor" in p.name.lower()]
    if not doctor:
        if _any_source(repo, re.compile(r'"doctor"|\bdoctor\b\s*=|sub\.add_parser\("doctor"')):
            return Result("6.2", title, Status.PASS, "a doctor subcommand exists")
        return Result("6.2", title, Status.FAIL,
                      "no doctor: a broken install reports whatever failed first")
    tested = any(
        "doctor" in p.read_text(encoding="utf-8", errors="replace")
        for p in repo.files
        if "test" in p.name.lower() or "smoke" in p.name.lower()
    )
    if not tested:
        return Result("6.2", title, Status.FAIL,
                      f"{doctor[0].name} exists but no test exercises it; a diagnostic "
                      "nobody has seen diagnose anything is untested code")
    return Result("6.2", title, Status.PASS, f"{doctor[0].name}, exercised by a test")


def _collects_failures(repo: Repo) -> Result:
    title = "Every failure is reported, not just the first"
    if not repo.runs_checks:
        return Result("6.3", title, Status.NOT_APPLICABLE,
                      "runs no suite of independent checks to collect failures from")
    where = _any_source(repo, COLLECTS)
    if where:
        return Result("6.3", title, Status.PASS, f"failures accumulate in {where}")
    return Result("6.3", title, Status.FAIL,
                  "nothing accumulates failures: a gate that returns on the first "
                  "costs one fix per CI round trip")


def _rule_ids(repo: Repo) -> Result:
    title = "Findings carry stable machine-readable identifiers"
    for path in _sources(repo) + repo.by_suffix(".toml", ".json", ".md"):
        matches = RULE_ID.findall(path.read_text(encoding="utf-8", errors="replace"))
        if len(set(matches)) >= 3:
            return Result("6.4", title, Status.PASS,
                          f"{len(set(matches))} rule id(s), e.g. {sorted(set(matches))[0]}")
    return Result("6.4", title, Status.NOT_APPLICABLE,
                  "this repository emits no findings to identify")


def _sarif(repo: Repo) -> Result:
    title = "SARIF output for anything that produces findings"
    emits_findings = any(
        len(set(RULE_ID.findall(p.read_text(encoding="utf-8", errors="replace")))) >= 3
        for p in _sources(repo)
    )
    if not emits_findings:
        return Result("6.5", title, Status.NOT_APPLICABLE, "produces no findings")
    if re.search(r"sarif", repo.workflow_text + "".join(
        p.read_text(encoding="utf-8", errors="replace") for p in _sources(repo)
    ), re.IGNORECASE):
        return Result("6.5", title, Status.PASS, "SARIF is emitted")
    return Result("6.5", title, Status.FAIL,
                  "findings exist but no SARIF: they cannot reach code scanning, "
                  "so they are only visible to whoever reads the log")


def _timing_surfaced(repo: Repo) -> Result:
    title = "Timing is recorded per check and surfaced"
    if not repo.runs_checks:
        return Result("6.6", title, Status.NOT_APPLICABLE, "runs no check suite to time")
    where = _any_source(repo, re.compile(r"perf_counter|Instant::now|duration_s|elapsed"))
    if where:
        return Result("6.6", title, Status.PASS, f"per-item timing in {where}")
    return Result("6.6", title, Status.FAIL,
                  "nothing is timed, so a gate that doubles in cost does so silently")


def _version_flag(repo: Repo) -> Result:
    title = "--version reports the build"
    if repo.kind == "docs" or not repo.has_cli:
        return Result("6.8", title, Status.NOT_APPLICABLE, "no command to ask")
    where = _any_source(repo, VERSION_FLAG)
    if where:
        return Result("6.8", title, Status.PASS, f"version surface in {where}")
    return Result("6.8", title, Status.FAIL,
                  "no --version: a bug report cannot say which build produced it")


def _trends(repo: Repo) -> Result:
    title = "Results are persisted across runs"
    if not repo.runs_checks:
        return Result("6.9", title, Status.NOT_APPLICABLE, "produces no run to trend")
    where = _any_source(repo, HISTORY)
    if where:
        return Result("6.9", title, Status.PASS, f"run history written by {where}")
    return Result("6.9", title, Status.FAIL,
                  "nothing persists between runs, so no trend is visible until "
                  "someone notices the absolute number is bad")


def _telemetry(repo: Repo) -> Result:
    title = "No telemetry, and it is verifiable"
    self_path = Path(__file__).resolve()
    offenders = [
        str(p.relative_to(repo.root)) for p in _sources(repo)
        if p.resolve() != self_path and TELEMETRY.search(p.read_text(encoding="utf-8", errors="replace"))
    ]
    if offenders:
        return Result("6.10", title, Status.FAIL,
                      f"telemetry client in {offenders[0]}")
    if OFFLINE_TEST.search(repo.workflow_text):
        return Result("6.10", title, Status.PASS,
                      "no telemetry client, and CI exercises an offline path")
    return Result("6.10", title, Status.FAIL,
                  "no telemetry client found, but nothing proves it: absence today "
                  "is a code review, not a control. An offline test is the control")


def run(repo: Repo) -> list[Result]:
    return [
        _structured_output(repo),
        _doctor(repo),
        _collects_failures(repo),
        _rule_ids(repo),
        _sarif(repo),
        _timing_surfaced(repo),
        Result("6.7", "A traceback never reaches the user as the primary error",
               Status.UNVERIFIED,
               "a claim about every input; a static read sees only the inputs "
               "someone already thought of"),
        _version_flag(repo),
        _trends(repo),
        _telemetry(repo),
    ]
