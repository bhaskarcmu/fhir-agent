"""Event-driven watcher: real inotify via ``inotifywait``, plus a testable
debounce core and a single-instance lock.

The debounce logic is separated from the event source and takes an injected
clock so it can be unit-tested without real filesystem timing.
"""

from __future__ import annotations

import errno
import os
import select
import signal
import subprocess
import time
from pathlib import Path

INOTIFY_EVENTS = "create,close_write,modify,moved_to"


class Debouncer:
    """Collapse a burst of events into one dispatch after a quiet window."""

    def __init__(self, quiet_seconds: float):
        self.quiet_seconds = quiet_seconds
        self._pending: set[str] = set()
        self._deadline: float | None = None

    def add(self, key: str, now: float) -> None:
        self._pending.add(key)
        self._deadline = now + self.quiet_seconds

    @property
    def pending(self) -> bool:
        return bool(self._pending)

    def seconds_until_due(self, now: float) -> float | None:
        if self._deadline is None:
            return None
        return max(0.0, self._deadline - now)

    def due(self, now: float) -> bool:
        return bool(self._pending) and self._deadline is not None and now >= self._deadline

    def pop(self) -> set[str]:
        keys, self._pending = self._pending, set()
        self._deadline = None
        return keys


# --- single-instance lock ---------------------------------------------

class LockError(RuntimeError):
    pass


def acquire_lock(lock_file: Path) -> Path:
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    if lock_file.exists():
        if _lock_alive(lock_file):
            raise LockError(f"Watcher already running (lock: {lock_file}).")
        lock_file.unlink(missing_ok=True)  # stale
    fd = os.open(lock_file, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    with os.fdopen(fd, "w") as fh:
        fh.write(f"{os.getpid()}\n{time.time()}\nwatch\n")
    return lock_file


def release_lock(lock_file: Path) -> None:
    lock_file.unlink(missing_ok=True)


def _lock_alive(lock_file: Path) -> bool:
    try:
        pid = int(lock_file.read_text(encoding="utf-8").splitlines()[0])
    except (ValueError, IndexError, OSError):
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError as exc:
        return exc.errno == errno.EPERM  # exists but not ours


# --- inotify loop ------------------------------------------------------

def watch(config, on_burst) -> None:
    """Block, dispatching ``on_burst()`` once per debounced burst.

    ``on_burst`` is called with the set of changed session paths. Runs an
    initial dispatch (startup catch-up) before entering the event loop.
    """
    source = config.source_dir()
    lock = acquire_lock(config.lock_file)
    proc = None
    try:
        on_burst(set())  # startup catch-up
        # stdbuf -oL forces line-buffered output: inotifywait block-buffers its
        # stdout when piped, which would otherwise delay/hide MODIFY events on
        # the active session file (Claude appends to it while holding it open).
        proc = subprocess.Popen(
            ["stdbuf", "-oL", "inotifywait", "-m", "-q",
             "-e", INOTIFY_EVENTS, "--format", "%w%f", str(source)],
            stdout=subprocess.PIPE, text=True,
        )
        deb = Debouncer(config.debounce_seconds)
        while True:
            timeout = deb.seconds_until_due(time.monotonic())
            ready, _, _ = select.select([proc.stdout], [], [], timeout)
            if ready:
                line = proc.stdout.readline()
                if not line:
                    break  # inotifywait exited
                path = line.strip()
                if path.endswith(".jsonl"):
                    deb.add(path, time.monotonic())
            if deb.due(time.monotonic()):
                deb.pop()
                on_burst(set())  # full regeneration; burst content is advisory
    finally:
        if proc and proc.poll() is None:
            proc.send_signal(signal.SIGTERM)
        release_lock(lock)
