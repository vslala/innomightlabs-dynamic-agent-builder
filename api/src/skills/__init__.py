"""
Skills module: package-based skill registry and user configuration.

Skills are discovered from a directory (e.g. skills/) containing one folder
per skill. Each skill has config.json, optional schema.json, and a tools/ folder.
"""

from .router import router as skills_router

__all__ = ["skills_router"]
