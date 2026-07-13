import os
import tempfile
import unittest
from pathlib import Path

from archive_ai.watcher import Debouncer, LockError, acquire_lock, release_lock


class DebouncerTest(unittest.TestCase):
    def test_burst_collapses_to_single_dispatch(self):
        d = Debouncer(quiet_seconds=15)
        d.add("a", now=0)
        d.add("b", now=5)      # new event resets the window
        self.assertFalse(d.due(now=19))   # 5 + 15 = 20, not yet
        self.assertTrue(d.due(now=20))
        self.assertEqual(d.pop(), {"a", "b"})
        self.assertFalse(d.pending)
        self.assertFalse(d.due(now=100))  # nothing pending after pop

    def test_seconds_until_due(self):
        d = Debouncer(quiet_seconds=10)
        self.assertIsNone(d.seconds_until_due(now=0))
        d.add("x", now=0)
        self.assertAlmostEqual(d.seconds_until_due(now=3), 7.0)
        self.assertEqual(d.seconds_until_due(now=99), 0.0)


class LockTest(unittest.TestCase):
    def setUp(self):
        self.lock = Path(tempfile.mkdtemp()) / "watcher.lock"

    def test_acquire_blocks_second_instance(self):
        acquire_lock(self.lock)
        with self.assertRaises(LockError):
            acquire_lock(self.lock)
        release_lock(self.lock)
        acquire_lock(self.lock)  # free again
        release_lock(self.lock)

    def test_stale_lock_is_reclaimed(self):
        self.lock.parent.mkdir(parents=True, exist_ok=True)
        self.lock.write_text(f"{2**31 - 1}\n0\nwatch\n", encoding="utf-8")  # dead pid
        acquire_lock(self.lock)  # should reclaim without raising
        self.assertEqual(int(self.lock.read_text().splitlines()[0]), os.getpid())
        release_lock(self.lock)


if __name__ == "__main__":
    unittest.main()
