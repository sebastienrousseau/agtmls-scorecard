# SPDX-FileCopyrightText: 2026 Sebastien Rousseau
# SPDX-License-Identifier: Apache-2.0 OR MIT
"""Allow `python -m agtmls_scorecard`."""

import sys

from agtmls_scorecard.cli import main

if __name__ == "__main__":
    sys.exit(main())
