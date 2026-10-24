"""Make this checkout importable under its installed collection namespace."""

import sys
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for name, path in (
    ('ansible_collections', ROOT.parent.parent),
    ('ansible_collections.hferreira23', ROOT.parent),
    ('ansible_collections.hferreira23.pihole', ROOT),
):
    package = ModuleType(name)
    package.__path__ = [str(path)]
    sys.modules.setdefault(name, package)
