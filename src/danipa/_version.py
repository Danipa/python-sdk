"""Package version.

``__version__`` is the single source hatch reads at build time. At runtime the
User-Agent reports the version from the INSTALLED package metadata, falling back
to ``__version__`` only when the distribution metadata is unavailable (e.g. the
source tree is on ``sys.path`` without an install).
"""

from __future__ import annotations

from functools import lru_cache
from importlib import metadata

__version__ = "0.3.0"


@lru_cache(maxsize=1)
def package_version() -> str:
    try:
        return metadata.version("danipa")
    except metadata.PackageNotFoundError:  # pragma: no cover - only without an install
        return __version__
