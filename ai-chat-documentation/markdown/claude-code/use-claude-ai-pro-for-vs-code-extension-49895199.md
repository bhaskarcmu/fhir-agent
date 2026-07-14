# Use Claude.ai PRO for VS Code extension

## Turn 1

### Prompt

I want you (Claude Code vscode extension) to stop using my Claude API key and use my Claude.ai PRO subscription instead. Please ensure that the ANTHROPIC API key in my source code still remains because the software I am building requires key based access!!

### Claude response

I'll help you switch Claude Code to your Claude.ai Pro subscription while keeping the API key intact for your application. The key thing to understand is that these are **two separate uses** of the API key that we need to decouple. Let me investigate your setup and confirm the exact mechanism in parallel.

Key findings so far. Let me read the credential setup script — that's almost certainly where the API key gets wired into Claude Code's environment.

Now I have the full picture. Let me verify one critical thing: how your app code actually reads the key, so removing Claude Code's access doesn't break your app.

I've traced exactly why Claude Code is billing to your API key. Here's the full picture.

## Root cause

Your app and Claude Code are sharing **one** secret through **two** environment variable names, set in [.devcontainer/devcontainer.json:55-62](.devcontainer/devcontainer.json#L55-L62):

```jsonc
"CLAUDE_API_KEY":    "${localEnv:CLAUDE_API_KEY}",   // line 57 — your app reads this
"ANTHROPIC_API_KEY": "${localEnv:CLAUDE_API_KEY}",   // line 58 — Claude Code reads this ← the problem
```

Claude Code (CLI + VS Code extension) authenticates using the `ANTHROPIC_API_KEY` env var, and when it's present it takes **precedence over your subscription**. Line 58 injects your key under that exact name container-wide, so Claude Code consumes it for billing. It does **not** read `CLAUDE_API_KEY` — that name is invisible to it.

The good news: your app doesn't actually need line 58. Both agents already fall back to `CLAUDE_API_KEY`:
- [mcp-agent/src/agent/agent.py:186](mcp-agent/src/agent/agent.py#L186) — `os.environ.get("ANTHROPIC_API_KEY", "") or os.environ.get("CLAUDE_API_KEY", "")`
- [claims-agent/src/claims_agent/agent.py:100](claims-agent/src/claims_agent/agent.py#L100) — same fallback

## The fix (two parts)

**Part 1 — Config change (I can do this):** Remove line 58 from `devcontainer.json`. After that:
- Claude Code no longer sees `ANTHROPIC_API_KEY` → falls back to your Pro subscription.
- Your app keeps working via `CLAUDE_API_KEY` (line 57 stays).
- **Your source code is untouched** — both agents still prefer/support `ANTHROPIC_API_KEY`; it's simply not force-injected globally anymore. Key-based access remains fully intact.
- Requires a **devcontainer rebuild** to take effect (env is baked at container start).

**Part 2 — Sign in to Pro (only you can do this — it's an account action, not code):**
1. Run `/login` in Claude Code (or the extension's **Sign in** button) → browser → sign in with your Claude.ai Pro account. Pro is supported for Claude Code.
2. Run `/status` to confirm — you want to see your Pro account as the login method with **no** "API key" row.

I already verified your current environment: `ANTHROPIC_API_KEY` is **not** in the active shell and `~/.claude/.credentials.json` is empty `{}` — so run `/status` first to see what this session is actually using before/after.

---

Since `devcontainer.json` is infra config, I won't edit it without your go-ahead. Want me to make the one-line change (remove line 58) on your current branch `feature/phase2-m6-wiring-demo` and open a PR? I'll leave line 57 and all source code untouched, and you handle the `/login` + rebuild.

## Turn 2

### Prompt

I already logged in to Claue AI using th "/login" command right here. I do't want to mess with devcontainer.json until I notice credits being consumed unexpectedly. You have no idea how hard it is to spin up a new environment from Ona! Also, you are likely mistaken about ANTHROPIC_API_KEY not being used in the code. It is very hidden, but it might be. Also, I doubt very much that you (The Clsude Code extension) looks at devcontainer.json to fetch keys. I think you have your own secure storage seperately in a priprietary location

### Claude response

API Error: 400 We've updated our Consumer Terms and Privacy Policy. You'll need to accept them in claude.ai with the email in /status to continue.

## Turn 3

### Prompt

try again

### Claude response

API Error: 400 We've updated our Consumer Terms and Privacy Policy. You'll need to accept them in claude.ai with the email in /status to continue.

## Turn 4

### Prompt

Done. I accepted the terms

### Claude response

Fair pushback — let me verify all three points rather than assert them again.

The sandbox correctly blocked me from previewing even redacted fragments of the live credentials file — that's a legitimate security control on Claude Code's own credential store, and it actually supports your point. Let me redo that check safely (metadata only, no content) and also relay a serious finding from the audit.

Here's the corrected picture, checked rather than asserted.

## You were right on two counts

**1. Claude Code does have its own separate secure storage — confirmed.**
`~/.claude/.credentials.json` grew from `{}` (2 bytes) to 504 bytes at `17:40:07`, matching your `/login`. That's Claude Code's own OAuth credential store — not devcontainer.json, not an env var. The sandbox itself just blocked me from previewing even redacted fragments of that file's contents, which is the system correctly protecting it. So yes: proprietary storage, separate from the API-key path.

**2. `ANTHROPIC_API_KEY` is not actually set in this environment right now.** Confirmed again just now: `ANTHROPIC_API_KEY: not set`, `CLAUDE_API_KEY: SET`. My earlier theory (devcontainer.json line 58 mapping `CLAUDE_API_KEY`→`ANTHROPIC_API_KEY`) doesn't hold up empirically — if that mapping had actually applied, both vars would be set to the same value. They're not. Likely explanation: Ona injects `CLAUDE_API_KEY` directly into the container through its own secrets mechanism, bypassing devcontainer.json's `${localEnv:...}` substitution (which depends on a "local host" env that may not really exist in Ona's remote/cloud model). So: **right now, Claude Code has no API key to compete with your subscription** — there's nothing for it to fall back to. Run `/status` yourself (type it in this chat) to see the login line directly; that's the authoritative first-party check, safer than me poking at credential internals.

Net: **no devcontainer.json edit is needed**, and I haven't touched it.

## Where I was incomplete (per the deeper audit)

A repo-wide sweep found one more wiring point I'd missed: [docker-compose.yml:69-70,136-137](docker-compose.yml#L69-L70) passes `ANTHROPIC_API_KEY`/`CLAUDE_API_KEY` through to the `mcp-agent`/`claims-agent` containers. This is unrelated to Claude Code's own billing though — it's just your app containers getting the key to call the Anthropic SDK, same fallback pattern as the two `agent.py` files. No third hidden consumer exists; the audit ruled out gateway/Kong (separate `FHIR_API_KEY`/`CLAIMS_API_KEY` namespace), CI workflows, and any settings module.

## A real security finding, unrelated to your original question

There's an **untracked 4.9 GB `core` dump** at the repo root (`/workspaces/fhir-agent/core`, from `03:46` this morning) — visible in `git status` as `?? core`, and not in `.gitignore`. The audit found the literal strings `ANTHROPIC_API_KEY`/`CLAUDE_API_KEY` inside it 40 times, consistent with a crashed process's environment block being embedded — **meaning your live key value is very likely sitting in that file in plaintext**. It's untracked so it was never committed, but it's sitting unprotected in your working tree.

Want me to:
1. Add `core` to `.gitignore` (safe, small change), and
2. Delete the 4.9 GB core file (destructive — confirming before I touch it)?

And separately — given a live key may have been dumped to disk, do you want to rotate the `CLAUDE_API_KEY` Ona secret as a precaution?

## Turn 5

### Prompt

YEs to both (1) and (2) you asked. No, I dont want to rotate keys

### Claude response

Before deleting anything, let me confirm the working tree state (per repo convention, checking before any destructive action).

**Worktree:** `/workspaces/fhir-agent` · **current branch:** `feature/phase2-m6-wiring-demo` (clean, only the untracked `core` file pending) · **target for the `.gitignore` fix:** a new branch off `main` → PR, since this is an unrelated security-hygiene fix and shouldn't ride on the M6 feature branch.

Core file deleted, `main` is up to date. Now creating the branch and adding the `.gitignore` entry.

Diff looks correct and scoped. Committing and pushing.

<details>
<summary>Execution details — 23 tool events</summary>

### Turn 1 activity

- **Agent** `Claude Code auth switch mechanism`
- **Bash** `if [ -n "$ANTHROPIC_API_KEY" ]; then echo "ANTHROPIC_API_KEY is SET in env (value hidden)"; else echo "ANTHROPIC_API_KEY is NOT set in env"; fi
if [ -n "$CLAUDE_API_KEY" ]; then echo "CLAUDE_API_KEY i…`
- **Bash** `grep -rn "ANTHROPIC_API_KEY\|CLAUDE_API_KEY" /workspaces/fhir-agent --include="*.py" --include="*.env" --include="*.yaml" --include="*.yml" --include="*.toml" --include="*.sh" --include="*.md" -l 2>/d…`
- **Bash** `ls -la /home/vscode/.claude/ 2>/dev/null; echo "---settings---"; cat /home/vscode/.claude/settings.json 2>/dev/null | sed 's/sk-ant-[A-Za-z0-9_-]*/[REDACTED]/g'; echo "---workspace settings---"; cat /…`
- **Read** `/workspaces/fhir-agent/.devcontainer/scripts/setup-credentials.sh`
- **Bash** `echo "=== .credentials.json size/content (redacted) ==="; cat /home/vscode/.claude/.credentials.json 2>/dev/null | sed 's/[A-Za-z0-9_-]\{20,\}/[REDACTED]/g'; echo; echo "=== CLAUDE_CODE_OAUTH_TOKEN se…`
- **Bash** `grep -n "API_KEY\|getenv\|environ\|api_key" /workspaces/fhir-agent/mcp-agent/src/agent/agent.py /workspaces/fhir-agent/claims-agent/src/claims_agent/agent.py 2>/dev/null | sed 's/sk-ant-[A-Za-z0-9_-]*…`
- **Read** `/workspaces/fhir-agent/.devcontainer/devcontainer.json`

### Turn 4 activity

- **Bash** `echo "=== current env ==="; if [ -n "$ANTHROPIC_API_KEY" ]; then echo "ANTHROPIC_API_KEY: SET (hidden)"; else echo "ANTHROPIC_API_KEY: not set"; fi
if [ -n "$CLAUDE_API_KEY" ]; then echo "CLAUDE_API_K…`
- **Agent** `Exhaustive repo-wide ANTHROPIC_API_KEY usage search`
- **ToolSearch** `claude code status auth check subscription api key`
- **Bash** `echo "=== current env (this shell) ==="
if [ -n "$ANTHROPIC_API_KEY" ]; then echo "ANTHROPIC_API_KEY: SET"; else echo "ANTHROPIC_API_KEY: not set"; fi
if [ -n "$CLAUDE_API_KEY" ]; then echo "CLAUDE_AP…`

### Turn 5 activity

- **Bash** `git -C /workspaces/fhir-agent status`
- **Bash** `git -C /workspaces/fhir-agent branch --show-current`
- **Bash** `rm /workspaces/fhir-agent/core`
- **Bash** `git -C /workspaces/fhir-agent fetch origin main && git -C /workspaces/fhir-agent checkout main && git -C /workspaces/fhir-agent pull origin main`
- **Bash** `git -C /workspaces/fhir-agent checkout -b chore/gitignore-core-dump`
- **Read** `/workspaces/fhir-agent/.gitignore`
- **Edit** `/workspaces/fhir-agent/.gitignore`
- **Bash** `git -C /workspaces/fhir-agent diff .gitignore`
- **Bash** `git -C /workspaces/fhir-agent add .gitignore && git -C /workspaces/fhir-agent commit -m "$(cat <<'EOF'
chore: ignore core dumps (may leak secrets via process env)

A 4.9GB core dump was found untracke…`
- **Bash** `git -C /workspaces/fhir-agent push -u origin chore/gitignore-core-dump`
- **Bash** `gh pr create --base main --head chore/gitignore-core-dump --title "chore: ignore core dumps" --body "$(cat <<'EOF'
## Summary
- Found a 4.9GB untracked core dump at the repo root containing the Anthro…`

</details>

---

## Archive metadata

- **Source:** Claude Code
- **Session ID:** `49895199-bfa2-470d-ba8d-4bd7737fd12b`
- **Created:** 14 July 2026, 17:33 UTC
- **Last updated:** 14 July 2026, 17:54 UTC
- **Turns:** 5
- **Status:** Complete
