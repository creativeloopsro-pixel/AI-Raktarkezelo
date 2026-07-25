"""Permission-scoped plugin SDK and built-in plugin registry."""

from app.plugins import builtin as _builtin  # noqa: F401, E402
from app.plugins.manifest import PluginManifest
from app.plugins.registry import plugin_registry

__all__ = ["PluginManifest", "plugin_registry"]
