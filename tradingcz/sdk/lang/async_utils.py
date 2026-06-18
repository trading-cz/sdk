"""Async utilities — signal handlers, shutdown helpers."""

import asyncio
import signal


def setup_shutdown_handlers(shutdown_event: asyncio.Event) -> None:
    """Register SIGTERM/SIGINT handlers that set *shutdown_event*.

    Call once per process.  No-op on platforms without signal support.
    """
    loop = asyncio.get_running_loop()
    try:
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, shutdown_event.set)
    except NotImplementedError:
        pass


__all__ = ["setup_shutdown_handlers"]
