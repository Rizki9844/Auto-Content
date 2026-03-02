"""
Plugin Architecture — Phase 4.5

Provides a lightweight, event-driven hook system that lets external or
built-in plugins react to pipeline events without modifying core code.

Lifecycle hooks (events):
    on_content_generated  — fires after Gemini content passes quality checks
    on_video_rendered     — fires after video file is created & verified
    on_uploaded           — fires after successful upload to any platform
    on_pipeline_complete  — fires at the very end of a successful pipeline run
    on_error              — fires when the pipeline catches an unrecoverable error

Usage (register a plugin):
    from src.plugins import registry

    @registry.hook("on_uploaded")
    def my_uploaded_handler(event):
        print(f"Uploaded to {event['platform']}: {event['url']}")

Usage (fire an event from core):
    from src.plugins import registry
    registry.fire("on_uploaded", platform="youtube", video_id="abc123", ...)

Built-in plugins are auto-discovered from ``src/plugins/builtin_*.py`` files.
Custom plugins can be loaded via the ``PLUGINS`` env var (comma-separated
dotted module paths).
"""

from src.plugins.registry import PluginRegistry  # noqa: F401

# Singleton used by the entire application
registry = PluginRegistry()


def init_plugins() -> None:
    """Discover & register all built-in + user-configured plugins.

    Called once at pipeline startup (from ``src.main``).
    Safe to call multiple times — idempotent after first load.
    """
    registry.discover_builtin()
    registry.load_from_env()

