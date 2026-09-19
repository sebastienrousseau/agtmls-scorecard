<!-- SPDX-FileCopyrightText: 2026 Sebastien Rousseau -->
<!-- SPDX-License-Identifier: Apache-2.0 OR MIT -->

# Changelog

## Unreleased

### Added

- Scores a repository against the AgtMLS rubric, reporting **score** and
  **coverage** separately. A high score at low coverage is a true statement
  about a small part of the rubric, and printing only the first is how a
  scorecard becomes flattery.
- Four result states. `unverified` never counts as a pass, and constructing an
  exemption without a reason raises.
- Six of ten categories implemented: correctness, security, documentation,
  release engineering, maintainability, governance. The other four are
  declared as placeholders so they count against coverage rather than
  disappearing.
- `--fail-under` and `--min-coverage`, which are meant to be used together.
- Sixteen tests, including both directions of every false positive found on
  the first run: a link inside a code span, prose containing brackets, a
  suppression with a trailing reason, and a rubric that describes TODOs.

### Known

This repository scored 5.7/10 at 38% coverage on its own rubric when first
written, which is a fair description of a repository a few hours old.
