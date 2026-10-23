# Autonomy Policy

## Levels

| Level | Meaning | How it is expressed |
| --- | --- | --- |
| **L0 Silent** | Read-only. Any write needs a human. | `[hooks].pre_tool` + `jcode-tool-policy` |
| **L1 Conservative** | Ambient off. Locally reversible work only. Inline swarm spawn. | `ambient.enabled = false`, `agents.swarm_spawn_mode = "inline"` |
| **L2 Autonomous** | Ambient on, headless swarm, desktop notifications. | `ambient.enabled = true`, `agents.swarm_spawn_mode = "headless"`, `safety.desktop_notifications = true` |
| **L3 Unattended** | L2 plus remote notification (ntfy / email / telegram). | `safety.ntfy_topic`, `safety.email_enabled = true`, `safety.telegram_enabled = true` |

## Current level

This repo ships **L2**. `config/config.toml` is the single source of truth.
There is no profile overlay: the file you read is the file that runs.

| Setting | Value | Why |
| --- | --- | --- |
| `ambient.enabled` | `true` | The ambient cycle is the point of the setup |
| `ambient.allow_api_keys` | `true` | Ambient cycles need provider access |
| `ambient.min_interval_minutes` | `5` | Fast enough to be useful |
| `ambient.max_interval_minutes` | `30` | `jcode-l2-check` fails above 60 |
| `ambient.visible` | `false` | Runs the cycle directly instead of spawning a kitty window and waiting for TUI interaction (`runner.rs:891`) |
| `agents.swarm_spawn_mode` | `headless` | Workers must not pop a terminal |
| `safety.desktop_notifications` | `true` | Local notification only |

L3 is deliberately not configured here. The notification destinations are
personal values and must never enter git. Set them through `JCODE_SAFETY_*`
environment variables instead.

## Changing the level

Autonomy is a config edit, not a flag. Edit `config/config.toml`, then:

```bash
./scripts/install
```

To go quiet for a while, set `ambient.enabled = false` and reinstall. To go
back, set it to `true`.

## What the shipped gate actually enforces

`jcode-tool-policy` is the L0 hardened variant in practice. It blocks `git push`
outright and blocks commits on `ambient/*` branches that have no active goal.
It does not implement an allowlist or a y/N prompt. See
[`git.md`](git.md) for the exact table.

## Not implemented

There is no per-working-directory autonomy mechanism. Every session shares the
same `~/.jcode/config.toml`. The long-term direction is a gitignored
`.jcode/config.local.toml` per repo, read by jcode at startup. That needs
jcode source support and is not implemented here.
