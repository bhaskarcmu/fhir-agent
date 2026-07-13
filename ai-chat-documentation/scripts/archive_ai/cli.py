"""Command-line interface: ``archive-ai {sync,watch,status}``."""

from __future__ import annotations

import argparse
import sys

from . import pipeline, watcher
from .config import Config
from .discovery import DiscoveryError, find_sessions
from .publisher import Publisher, PublishError


def _publisher(config: Config) -> Publisher:
    return Publisher(config.archive_worktree, config.archive_subdir, config.branch, config.remote)


def cmd_sync(config: Config) -> int:
    result = pipeline.run(config)
    print(
        f"Processed {result.sessions_processed} session(s) "
        f"({result.sessions_excluded} excluded), wrote {result.files_written} file(s)."
    )
    if result.redactions:
        summary = ", ".join(f"{k}={v}" for k, v in sorted(result.redactions.items()))
        print(f"Redactions: {summary}")
    pub = _publisher(config)
    outcome = pub.publish(pipeline.commit_message())
    if outcome.status == "noop":
        print("No archive changes to commit.")
    elif outcome.status == "pushed":
        print(f"Committed and pushed {outcome.commit[:8]} to {config.remote}/{config.branch}.")
    elif outcome.status == "push_failed":
        print(f"Committed {outcome.commit[:8]} locally but push failed: {outcome.detail}")
        return 1
    return 0


def cmd_watch(config: Config) -> int:
    pub = _publisher(config)

    def on_burst(_changed):
        # Never let one failed burst kill the daemon; the next burst retries.
        try:
            result = pipeline.run(config)
            outcome = pub.publish(pipeline.commit_message())
            print(f"[watch] sessions={result.sessions_processed} publish={outcome.status}", flush=True)
        except Exception as exc:  # noqa: BLE001 - watcher must stay up
            print(f"[watch] error (will retry next burst): {exc}", flush=True)

    print(f"Watching {config.source_dir()} (debounce {config.debounce_seconds}s). Ctrl-C to stop.")
    try:
        watcher.watch(config, on_burst)
    except KeyboardInterrupt:
        print("\nStopped.")
    return 0


def cmd_status(config: Config) -> int:
    print(f"Source directory:  {config.source_dir()}")
    try:
        sessions = find_sessions(config)
        print(f"Sessions found:    {len(sessions)}")
    except DiscoveryError as exc:
        print(f"Sessions found:    ERROR — {exc}")
    running = config.lock_file.exists() and watcher._lock_alive(config.lock_file)
    print(f"Watcher:           {'running' if running else 'stopped'}")
    print(f"Archive worktree:  {config.archive_worktree}")
    pub = _publisher(config)
    try:
        branch = pub.current_branch()
        last = pub._git("log", "-1", "--format=%h %s", check=False).stdout.strip()
        print(f"Archive branch:    {branch}")
        print(f"Last commit:       {last or '(none)'}")
    except (PublishError, OSError) as exc:
        print(f"Archive branch:    ERROR — {exc}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="archive-ai", description="AI Conversation Archive")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("sync", help="process all sessions once, commit and push")
    sub.add_parser("watch", help="event-driven watcher (inotify)")
    sub.add_parser("status", help="show archive health")
    args = parser.parse_args(argv)

    config = Config.from_env()
    try:
        if args.command == "sync":
            return cmd_sync(config)
        if args.command == "watch":
            return cmd_watch(config)
        if args.command == "status":
            return cmd_status(config)
    except (DiscoveryError, PublishError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
