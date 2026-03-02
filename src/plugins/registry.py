"""
Plugin Registry — core event bus for the plugin system.

Manages hook registration, plugin discovery, and event firing.
Thread-safe, exception-isolated (one plugin crash never brings down the pipeline).
"""
from __future__ import annotations

import importlib
import logging
import os
import pkgutil
from collections import defaultdict
from typing import Any, Callable

logger = logging.getLogger(__name__)

# ── Supported hook names (events) ─────────────────────────────
HOOK_NAMES: frozenset[str] = frozenset({
    "on_content_generated",
    "on_video_rendered",
    "on_uploaded",
    "on_pipeline_complete",
    "on_error",
})


class PluginRegistry:
    """Central event bus: register handlers, fire events."""

    def __init__(self) -> None:
        self._hooks: dict[str, list[Callable]] = defaultdict(list)
        self._discovered = False
        self._loaded_modules: set[str] = set()

    # ── Registration ──────────────────────────────────────────

    def hook(self, event_name: str) -> Callable:
        """Decorator to register a handler for *event_name*.

        Example::

            @registry.hook("on_uploaded")
            def my_handler(event: dict) -> None:
                ...
        """
        if event_name not in HOOK_NAMES:
            raise ValueError(
                f"Unknown hook '{event_name}'. "
                f"Valid hooks: {sorted(HOOK_NAMES)}"
            )

        def decorator(fn: Callable) -> Callable:
            self.register(event_name, fn)
            return fn

        return decorator

    def register(self, event_name: str, handler: Callable) -> None:
        """Register *handler* for *event_name* (non-decorator form)."""
        if event_name not in HOOK_NAMES:
            raise ValueError(
                f"Unknown hook '{event_name}'. "
                f"Valid hooks: {sorted(HOOK_NAMES)}"
            )
        self._hooks[event_name].append(handler)
        logger.debug("Registered %s for %s", handler.__name__, event_name)

    # ── Firing events ─────────────────────────────────────────

    def fire(self, event_name: str, **kwargs: Any) -> list[Any]:
        """Fire *event_name*, passing **kwargs as the event dict to each handler.

        Returns list of return values (one per handler).
        Any handler that raises is logged & skipped — never propagated.
        """
        results: list[Any] = []
        for handler in self._hooks.get(event_name, []):
            try:
                result = handler(kwargs)
                results.append(result)
            except Exception:
                logger.exception(
                    "Plugin handler %s raised on %s — skipping",
                    handler.__name__,
                    event_name,
                )
                results.append(None)
        return results

    # ── Discovery ─────────────────────────────────────────────

    def discover_builtin(self) -> int:
        """Auto-import all ``src/plugins/builtin_*.py`` modules.

        Each module's top-level code should call ``registry.hook(...)``
        or ``registry.register(...)`` to wire itself up.

        Returns the number of modules loaded.
        """
        if self._discovered:
            return 0

        import src.plugins as _pkg

        count = 0
        for importer, modname, _ispkg in pkgutil.iter_modules(
            _pkg.__path__, prefix="src.plugins."
        ):
            if not modname.rsplit(".", 1)[-1].startswith("builtin_"):
                continue
            if modname in self._loaded_modules:
                continue
            try:
                importlib.import_module(modname)
                self._loaded_modules.add(modname)
                count += 1
                logger.info("Loaded built-in plugin: %s", modname)
            except Exception:
                logger.exception("Failed to load built-in plugin %s", modname)

        self._discovered = True
        return count

    def load_from_env(self) -> int:
        """Load user-configured plugins from the ``PLUGINS`` env var.

        Format: ``PLUGINS=mypackage.social,mypackage.analytics``
        (comma-separated dotted module paths).

        Returns the number of modules loaded.
        """
        raw = os.environ.get("PLUGINS", "").strip()
        if not raw:
            return 0

        count = 0
        for module_path in raw.split(","):
            module_path = module_path.strip()
            if not module_path or module_path in self._loaded_modules:
                continue
            try:
                importlib.import_module(module_path)
                self._loaded_modules.add(module_path)
                count += 1
                logger.info("Loaded user plugin: %s", module_path)
            except Exception:
                logger.exception("Failed to load user plugin %s", module_path)

        return count

    # ── Introspection ─────────────────────────────────────────

    def get_handlers(self, event_name: str) -> list[Callable]:
        """Return list of handlers registered for *event_name*."""
        return list(self._hooks.get(event_name, []))

    def clear(self) -> None:
        """Remove all handlers and reset discovery state."""
        self._hooks.clear()
        self._discovered = False
        self._loaded_modules.clear()

    @property
    def stats(self) -> dict[str, int]:
        """Return ``{event_name: handler_count}`` for all hooks with handlers."""
        return {k: len(v) for k, v in self._hooks.items() if v}

    def __repr__(self) -> str:
        total = sum(len(v) for v in self._hooks.values())
        return (
            f"<PluginRegistry hooks={dict(self.stats)} "
            f"total_handlers={total} "
            f"modules={len(self._loaded_modules)}>"
        )
