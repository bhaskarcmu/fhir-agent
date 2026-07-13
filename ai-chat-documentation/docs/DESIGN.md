# AI Conversation Archive — Design (v1)

Concise design for the requirements in [REQUIREMENTS.md](REQUIREMENTS.md).

## Overview

A small, deterministic Python tool that runs as a background daemon in the Ona
workspace. It watches Claude Code's local JSONL session files with Linux
inotify, converts changed sessions into a normalised model, renders redacted
Markdown + a raw copy, and auto-commits and pushes them to the
`ai-chat-history` branch of the existing public repo. It is ordinary local
software — once installed it does not depend on any AI assistant to run.

## Data flow

```
~/.claude/projects/<cwd>/*.jsonl   (append-only source, held open)
        │  inotify: create / moved_to / close_write / modify
        ▼
   Debounce (quiet window, default 15s; reset on new events)
        │
        ▼
   Parser  → normalised Conversation(turns[], tool_events[])
        │      (typed-field classification; ignores thinking/tool_result/meta)
        ▼
   Redactor (regex; redact-and-continue) ── applied to ALL output below
        ▼
   Writer:  raw/claude-code/<id>.jsonl   (redacted copy, source of truth)
            markdown/claude-code/<id>.md (derived, regenerated each run)
            INDEX.md                     (regenerated)
        │  (tmp file + atomic rename)
        ▼
   Publisher:  git -C <archive worktree>
               pull --rebase → stage ai-chat-documentation/
               → commit if non-empty → push origin/ai-chat-history
```

## Components

| Module | Responsibility |
|---|---|
| `discovery` | Resolve the source project dir (`CLAUDE_CONVERSATION_DIR` override; exclude self). |
| `parser` | JSONL → normalised `Conversation`/`Turn`/`ToolEvent`; tolerate partial last line. |
| `redactor` | Apply built-in + user regex patterns; redact-and-continue; count matches. |
| `renderer` | `Conversation` → Markdown; regenerate `INDEX.md`. Renderer never reads raw JSONL. |
| `writer` | Atomic writes (tmp + rename) of raw copy, Markdown, index. |
| `publisher` | Branch/worktree guard, rebase, stage-scoped commit, auto-push, retry-on-fail. |
| `watcher` | inotify loop + debounce + lock; calls the pipeline per burst. |
| `cli` | `watch` / `sync` / `status`. |

## Key design decisions and why

- **Parse off typed fields, not regex.** Claude Code's JSONL is already
  structurally typed, so prompt/response/tool classification is a deterministic
  switch. This avoids the prompt-corruption failures seen in the earlier
  regex-based Cline exporter.
- **Separate parse → model → render.** The renderer only sees the normalised
  model, so parser defects can't masquerade as rendering defects and future
  importers can reuse the renderer unchanged.
- **Full regeneration + empty-diff check instead of an incremental manifest.**
  Each run re-derives everything; the publisher commits only when the staged
  diff is non-empty. This is idempotent and far simpler than content-hash
  tracking, at negligible cost for this data volume.
- **inotify + debounce.** One user interaction writes several file events;
  `modify` is watched because the active file is appended to without closing.
  The debounce collapses a burst into a single commit. No polling → negligible
  idle CPU.
- **Redact everything, including raw.** Since the branch is public, the raw
  copy is redacted too; nothing unfiltered ever reaches GitHub. Redaction is
  non-blocking so archiving never stalls or loses turns.
- **Auto-push, always, with retry.** Durability is the whole point: a workspace
  crash must not lose history. Push failures keep the local commit and retry on
  the next burst — no duplicates, no force-push.
- **Strict worktree/branch isolation.** All Git runs through
  `git -C <archive worktree>`, stage-scoped to `ai-chat-documentation/`, guarded
  by a branch check, and structurally incapable of opening a PR or touching
  `main`.

## Normalised model (shape)

```
Conversation: id, source, title, created_at, updated_at, turns[], metadata
Turn:         index, prompt, response|None, status(complete|incomplete),
              tool_events[]
ToolEvent:    name, input_summary, result_summary
```

## Failure handling (summary)

| Situation | Behaviour |
|---|---|
| Source file mid-write (partial JSON) | Skip the bad line; retry next burst; never overwrite last good output. |
| Secret pattern match | Redact inline and continue. |
| Push fails / remote ahead | Keep local commit, log, retry next burst; never force-push. |
| Wrong branch / missing worktree | Refuse, log, exit non-zero. |
| Watcher dies | Supervisor/lifecycle restarts it; startup `sync` catches missed changes. |

## Testing (developer test suite, run during implementation)

Automated with `pytest`, fully offline (no GitHub):

- **Parser units** over sanitised fixtures: multi-turn, tool_use/result,
  incomplete trailing turn, prompt containing XML/regex/markdown fences, and a
  truncated final line. Assert prompt/response/order/status; assert no
  tool_result or thinking block ever becomes a turn.
- **Redactor units:** each built-in pattern is masked; matched value never
  appears in output or logs.
- **Renderer units:** section ordering (prompt → response → collapsed tools →
  metadata) and INDEX rows.
- **Publisher integration:** in a temp dir, `git init` a work repo **and a
  local bare repo as the remote**; run the publisher; assert exactly one commit,
  the bare remote received it, and a second run with no change is a no-op. This
  exercises the real commit+push path with no network.
- **Watcher integration:** write to a temp source dir and assert the debounce
  fires one pipeline run per burst.
- **End-to-end:** fixture project dir → `sync` → verify every visible
  prompt/response appears once, no internal events leak, and a clean rerun
  produces no commit.

## Layout (planned)

```
ai-chat-documentation/
├── docs/            REQUIREMENTS.md, DESIGN.md
├── scripts/
│   └── archive_ai/  discovery, parser, redactor, renderer, writer,
│                    publisher, watcher, cli
│   └── tests/       pytest suite + fixtures
├── config/          redaction-patterns.txt, exclusions.txt (optional)
├── raw/claude-code/ redacted source copies
├── markdown/claude-code/  rendered transcripts
├── INDEX.md
└── logs/            local logs (not committed)
```
