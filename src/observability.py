"""Optional Langfuse tracing for FinSight runs."""

from contextlib import contextmanager
from contextvars import ContextVar
from functools import cache
import logging
import os
from pathlib import Path

from dotenv import dotenv_values

logger = logging.getLogger(__name__)
_active_client = ContextVar("langfuse_client", default=None)


@cache
def _get_client():
    try:
        local = dotenv_values(Path(__file__).resolve().parents[1] / ".env")
        settings = {
            field: (os.environ.get(key, local.get(key)) or "").strip()
            for field, key in (
                ("public_key", "LANGFUSE_PUBLIC_KEY"),
                ("secret_key", "LANGFUSE_SECRET_KEY"),
                ("base_url", "LANGFUSE_BASE_URL"),
            )
        }
        if not all(settings.values()):
            return None

        from langfuse import Langfuse, is_langfuse_span

        # The SDK flushes pending observations on process exit.
        return Langfuse(**settings, should_export_span=is_langfuse_span)
    except Exception as error:
        logger.warning("Could not initialize Langfuse (%s)", type(error).__name__)
        return None


@contextmanager
def trace_run(name):
    token = _active_client.set(_get_client())
    try:
        with observation(name, "chain") as span:
            yield span
    finally:
        _active_client.reset(token)


@contextmanager
def observation(name, kind, **attributes):
    client = _active_client.get()
    if client is None:
        yield None
        return

    try:
        scope = client.start_as_current_observation(name=name, as_type=kind, **attributes)
        span = scope.__enter__()
    except Exception as error:
        logger.warning("Could not start Langfuse observation (%s)", type(error).__name__)
        yield None
        return

    try:
        yield span
    except BaseException as error:
        update_observation(span, level="ERROR", status_message=type(error).__name__)
        raise
    finally:
        try:
            # Export the exception type above without attaching its message or stack.
            scope.__exit__(None, None, None)
        except Exception as error:
            logger.warning("Could not end Langfuse observation (%s)", type(error).__name__)


def update_observation(span, **attributes):
    if span is not None:
        try:
            span.update(**attributes)
        except Exception as error:
            logger.warning("Could not update Langfuse observation (%s)", type(error).__name__)
