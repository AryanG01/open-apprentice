"""Moved to `open_apprentice.providers.spend` so learner processes (which may not import the evaluator) can run under
the same guard. This name stays an alias of that very module, so patches and imports through it keep working."""

import sys

from open_apprentice.providers import spend as _spend

sys.modules[__name__] = _spend
