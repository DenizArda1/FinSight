#Shared SEC client setup and reentrant preparation locking

from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
from threading import RLock, local

from dotenv import load_dotenv

from src.ingestion.edgar import EdgarClient


ROOT = Path(__file__).resolve().parents[2]
_LOCK = RLock()
_LOCAL = local()


@contextmanager
def preparation_lock():
    path = ROOT / "financial_data" / ".preparation.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        if getattr(_LOCAL, "active", False):
            yield
            return
        with path.open("a") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            _LOCAL.active = True
            try:
                yield
            finally:
                _LOCAL.active = False
                fcntl.flock(handle, fcntl.LOCK_UN)


def sec_client(refresh=False):
    load_dotenv(ROOT / ".env")
    return EdgarClient(os.environ.get("SEC_USER_AGENT", ""), ROOT / "financial_data/raw", refresh)
