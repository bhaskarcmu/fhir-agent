# AI Chat Documentation

This directory contains archived AI-assisted development conversations and
the supporting scripts used to collect, process, validate, commit and push
them.

## Documentation

- [`docs/REQUIREMENTS.md`](docs/REQUIREMENTS.md) — approved v1 requirements for
  the Claude Code conversation archiver.
- [`docs/DESIGN.md`](docs/DESIGN.md) — concise design and testing plan.

## Directory structure

- `docs/` contains the requirements and design documentation.
- `raw/` contains original conversation data copied from supported AI tools.
- `markdown/` contains readable exports generated from the raw data.
- `manifests/` contains synchronisation state and archival metadata.
- `scripts/` contains collection, filtering and publication scripts.
- `logs/` contains local synchronisation logs and is not committed.

## Branch policy

This documentation is maintained on the `ai-chat-history` branch.

The branch began from `main` so that the archived conversations retain the
repository context that existed when the archive was created. Automated chat
archive commits must be made only from the dedicated archive worktree.

This branch is not intended to be merged into `main`.
