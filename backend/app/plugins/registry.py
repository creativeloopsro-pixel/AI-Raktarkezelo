from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.plugins.sdk import PluginContext, PluginEvent

PluginHandler = Callable[["PluginContext", "PluginEvent"], dict[str, Any] | None]


class PluginHandlerNotFoundError(LookupError):
    pass


class PluginRegistry:
    def __init__(self) -> None:
        self._handlers: dict[tuple[str, str], PluginHandler] = {}

    def handler(
        self, plugin_key: str, event_type: str
    ) -> Callable[[PluginHandler], PluginHandler]:
        def decorator(callback: PluginHandler) -> PluginHandler:
            key = (plugin_key, event_type)
            if key in self._handlers:
                raise ValueError(
                    f"A plugin handler már regisztrálva van: {plugin_key}/{event_type}"
                )
            self._handlers[key] = callback
            return callback

        return decorator

    def get(self, plugin_key: str, event_type: str) -> PluginHandler:
        try:
            return self._handlers[(plugin_key, event_type)]
        except KeyError as exc:
            raise PluginHandlerNotFoundError(
                f"Nincs handler: {plugin_key}/{event_type}"
            ) from exc

    def supports(self, plugin_key: str, event_type: str) -> bool:
        return (plugin_key, event_type) in self._handlers

    def supports_manifest(self, plugin_key: str, events: list[str]) -> bool:
        return all(self.supports(plugin_key, event) for event in events)


plugin_registry = PluginRegistry()
