# AI Conversation Archive — Requirements (v1)

Status: Approved for implementation.
Scope: First release supports **Claude Code** only. Cline and other assistants
are out of scope for v1.

## 1. Purpose

Automatically archive Claude Code conversations (prompts, responses, and a
summary of tool activity) from the local VS Code / Ona environment into a
durable, human-readable Git record, so that no development history is lost if a
workspace crashes, is rebuilt, or is deleted. The archive must require **no
manual step** during normal use.

## 2. Repository and isolation model

- Single existing repository: `bhaskarcmu/fhir-agent` (public).
- The archive lives on branch **`ai-chat-history`**, worked from the dedicated
  worktree **`/workspaces/.ai-chat-history`**. Files live under
  `ai-chat-documentation/`.
- The archive tooling and its output are committed **directly** to
  `ai-chat-history` and pushed to `origin/ai-chat-history`.
- The tool must **never** open a Pull Request, **never** merge into `main`, and
  **never** write to the application worktree (`/workspaces/fhir-agent`).
- Because the repository is **public**, all committed content is filtered in
  real time (see §7). Filtering is a strong seatbelt, not a guarantee — the
  session-exclusion list (§7) is the authoritative opt-out for anything that
  must never be published. Treat prompts as public-by-default.

## 3. Source of truth (Claude Code storage — confirmed by discovery)

- Sessions: `~/.claude/projects/<encoded-cwd>/<session-id>.jsonl`, one
  append-only JSONL file per session; the file is named by a stable session
  UUID.
- Records are typed. Visible prompts are `type:"user"` with
  `message.content[0].type == "text"` (they also carry `promptSource`). Tool
  results are `type:"user"` with a `tool_result` block and a `toolUseResult`
  field. Assistant output is `type:"assistant"` with `thinking` / `text` /
  `tool_use` content blocks. Turns chain via `parentUuid` / `promptId`.
- Sessions are stored per working directory. The active file is held open and
  appended to; its final line may be a partial JSON object mid-write.

## 4. Functional requirements

### 4.1 Discovery
- Locate Claude Code sessions under `~/.claude/projects/<encoded-cwd>/*.jsonl`.
- Support env override `CLAUDE_CONVERSATION_DIR` pointing at a project dir
  (used by tests and non-standard installs).
- Exclude the archive worktree's own project dir so the tool never archives
  conversations about itself.
- Fail loudly if no source directory is found.

### 4.2 Parsing (deterministic, off typed fields — no regex prompt extraction)
- **Prompt** = a `user` record whose first content block is `text`.
- **Response** = the subsequent `assistant` `text` blocks concatenated, up to
  the next user prompt.
- **Tool event** = an `assistant` `tool_use` (tool name + short input summary)
  paired to its matching `tool_result`.
- **Ignored:** `thinking` blocks, `queue-operation`, `attachment`,
  `file-history-snapshot`, `ai-title` / `last-prompt` / `custom-title`,
  `pr-link`, and any `isSidechain:true` records.
- Turns are ordered by `parentUuid` / `promptId`. A trailing prompt with no
  response is marked **incomplete**.
- A partial/unparseable final line (active session mid-write) is skipped, not
  fatal.

### 4.3 Raw preservation (redacted)
- Copy each session to `raw/claude-code/<session-id>.jsonl`, passed through the
  redactor (§7) first. Redacted raw remains the re-render source of truth;
  Markdown is fully regenerated from it each run.

### 4.4 Markdown + index
- One file per session: `markdown/claude-code/<session-id>.md` containing, in
  order: title → per-turn **Prompt** / **Response** → collapsed `<details>`
  block of tool activity → archive metadata (session id, timestamps, turn
  count, status).
- Large tool output must never appear before the response.
- Regenerate `INDEX.md`: newest first, one row per conversation (updated time,
  assistant, title link, turn count, status).

### 4.5 Event-driven watcher (inotify — no polling)
- Watch the source project dir with Linux **inotify** for `create`,
  `moved_to`, `close_write`, and `modify` (the active `.jsonl` is appended to
  without closing, so `modify` is required).
- **Debounce:** after an event, wait for a quiet window (default **15s**,
  `AI_ARCHIVE_DEBOUNCE_SECONDS`), resetting on new events, so one conversation
  burst produces one commit.
- Serialize runs with a lock file; process only affected sessions when
  resolvable, otherwise full rescan.

### 4.6 Publishing (automatic, unconditional)
- Always operate via `git -C /workspaces/.ai-chat-history`; stage only
  `ai-chat-documentation/`.
- Stage `ai-chat-documentation/` → commit if the staged diff is non-empty →
  `git pull --rebase` (requires a clean tree, hence after commit) → **push to
  `origin/ai-chat-history` automatically**.
- Commit message: `Archive Claude Code conversations: <UTC timestamp>`.
- Refuse to run if the branch is not `ai-chat-history` or the worktree is
  missing.
- On push failure: keep the local commit, log it, retry on the next burst.
  Never lose data; never create duplicate commits; never force-push.

### 4.7 CLI + auto-start
- `archive-ai watch` — the inotify daemon (primary mode).
- `archive-ai sync` — one-shot: process all sessions, commit, push (used at
  startup catch-up and by tests).
- `archive-ai status` — watcher state, source dir, last pushed commit,
  redaction counts, last error.
- **Auto-start** via an Ona automations **service** (`aiChatArchiveWatcher`,
  triggered `postEnvironmentStart`): runs `scripts/autostart.sh`, which does a
  `sync` catch-up then `exec`s the foreground `watch`. Ona supervises the
  service and restarts it on crash; the watcher lock prevents duplicates. No
  manual terminal required.

## 5. Non-goals (v1)
Hosted web UI; replacing Claude Code's local history; real-time token
streaming; exporting hidden reasoning; content-hash incremental manifest;
importer/renderer versioning + reprocessing; Cline importer; encryption; PHI
detection; PR/merge workflows.

## 6. Security / privacy — deliberately simple

Because the repo is public, filtering is applied in real time to **all**
committed content, but kept minimal:

- **Redact-and-continue** (never block, never lose data): matches are replaced
  with `‹redacted:CATEGORY›` before any file is written or committed. Applied to
  prompts, responses, tool summaries, and raw content.
- **Built-in patterns** (extensible): Anthropic `sk-ant-…`, OpenAI `sk-…`,
  GitHub `ghp_/gho_/ghs_/github_pat_…`, AWS `AKIA…`,
  `-----BEGIN … PRIVATE KEY-----`, `Authorization: Bearer …`, credentials in
  URLs (`scheme://user:pass@…`), and `.env`-style assignments whose key name
  contains `TOKEN`/`SECRET`/`PASSWORD`/`API_KEY`.
- **User patterns:** additional regexes, one per line, in
  `ai-chat-documentation/config/redaction-patterns.txt` (optional).
- **Session exclusion:** `ai-chat-documentation/config/exclusions.txt`, one
  session id per line — excluded sessions are never rendered or committed. This
  is the authoritative opt-out for sensitive conversations.
- **Logging:** log a per-session redaction count + category, never the matched
  value.
- Regex filtering catches structured secrets, not free-form PHI or business
  secrets in prose. This is a healthcare repo — do not enter PHI into prompts.

## 7. Acceptance criteria (v1)
1. Watcher auto-starts and survives workspace restart (startup `sync` catches
   missed changes).
2. Changes are detected via inotify with no polling.
3. Within ~15–30s of a conversation going quiet, Markdown + INDEX + redacted
   raw are written, committed, and **pushed automatically** to
   `ai-chat-history`.
4. Every visible prompt and final response appears exactly once; no tool
   result, thinking block, reminder, or environment record appears as a turn.
5. Multi-turn order is correct; incomplete sessions are marked.
6. Structured secrets are redacted; excluded sessions are absent entirely.
7. No PR is created; `main` is never modified.
8. Re-running with no source change produces no commit.
9. The developer test suite (see DESIGN.md §Testing) passes.
