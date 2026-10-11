<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau -->
<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Changelog

## [0.0.3] - Unreleased

## [0.0.2] - 2026-10-11

### Added

- Scores a repository against the AgtMLS rubric, reporting **score** and
  **coverage** separately. A high score at low coverage is a true statement
  about a small part of the rubric, and printing only the first is how a
  scorecard becomes flattery.
- Four result states. `unverified` never counts as a pass, and constructing an
  exemption without a reason raises.
- **All ten categories implemented.** Performance, developer experience,
  observability and interoperability were whole-category placeholders, which
  meant 40 of the 100 criteria were invisible and a repository could read
  9.3/10 while nothing had asked whether it was fast, diagnosable, scriptable
  or conformant. Implementing them *lowered* every published score, which is
  what a measurement is supposed to be able to do.
- Capability detection (`has_cli`, `emits_json`, `runs_checks`), so a WASM
  module is not failed for having no `--version` and a GitHub Action is not
  failed for having no `doctor` subcommand. A scorer that cries wolf gets
  switched off, and a switched-off scorer scores nothing while looking like it
  scores everything.

### Fixed

- Criterion **2.10** had a checker that `run()` never called, so it was absent
  from every report this tool had ever produced — the exact defect the tool
  exists to catch, in itself. A test now asserts every category decides all
  ten of its criteria.
- Four false positives, each pinned in both directions: `git+https://` read as
  an invented URI scheme; a `SUPPORT.md` sentence saying a release is
  "unsupported, not deprecated" read as a deprecation; a changelog recording a
  past deprecation read as a live one; and `FAIL: {n} issue(s)` tallies
  counted as error messages missing a remediation.
- `--fail-under` and `--min-coverage`, which are meant to be used together.
- Forty-two tests, including both directions of every false positive found so
  far: a link inside a code span, prose containing brackets, a suppression
  with a trailing reason, a rubric that describes TODOs, a composed URI
  scheme, and prose denying a deprecation.

### Known

This repository scored 5.7/10 at 38% coverage on its own rubric when first
written, which is a fair description of a repository a few hours old. With all
ten categories implemented it scores 8.0/10 at 52%, and the eight repositories
of the ecosystem score 8.0-8.8 at 44-58% — down from a uniform 10.0 at 41-46%,
because the categories that used to be invisible can now fail.
