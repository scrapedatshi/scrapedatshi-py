"""
scrapedatshi._templates
~~~~~~~~~~~~~~~~~~~~~~~~
Template strings for the ``scrapedatshi init`` CLI command.

Split into focused submodules to keep cli.py slim:
    _env.py      — .env, .gitignore, and README templates
    _examples.py — all example scripts (the _EXAMPLES dict)
"""

from scrapedatshi._templates._env import (
    ENV_TEMPLATE,
    GITIGNORE_TEMPLATE,
    README_TEMPLATE,
)
from scrapedatshi._templates._examples import EXAMPLES

__all__ = ["ENV_TEMPLATE", "GITIGNORE_TEMPLATE", "README_TEMPLATE", "EXAMPLES"]
