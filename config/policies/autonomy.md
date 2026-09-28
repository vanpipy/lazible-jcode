# Autonomy Policy (v1)

## Levels

| Level | Meaning | Implementation in jcode |
| --- | --- | --- |
| **L0 Silent** | Agent is read-only; any write action must be confirmed by a human | `[hooks].pre_tool` + `~/.local/bin/jcode-tool-policy` |
| **L1 Conservative** | Ambient disabled; locally reversible manual operations; inline swarm spawn | `[ambient].enabled = false`, `[agents].swarm_spawn_mode = "inline"` |
| **L2 Autonomous** | Ambient + proactive + allow_api_keys; headless swarm spawn; local desktop notifications | `[ambient].enabled = true`, `[agents].swarm_spawn_mode = "headless"`, `[safety].desktop_notifications = true` |
| **L3 Unattended** | L2 + remote push (ntfy / email / telegram), so notifications reach you even when away | `[safety].ntfy_topic != null`, `[safety].email_enabled = true`, `[safety].telegram_enabled = true` |

## Repo defaults

- `autonomous.toml` = L2 (the only profile)
- Base (no overlay) = L1: `ambient.enabled=false`, `swarm_spawn_mode=inline`, `compaction.mode=semantic`, `memory_rerank_cadence=1` (the research tilt is baked in here)
- The L0 hardened variant (pre_tool gate) is not yet a profile here : `~/.local/bin/jcode-tool-policy` needs a custom policy (allowlist / y-N prompt). For L0, write `[hooks].pre_tool` into base or a local override by hand.
- L3 is not part of a profile : for L3 you must set `safety.ntfy_topic` / `email_enabled` / `telegram_enabled` individually via `JCODE_SAFETY_*` environment variables. The omission from the autonomous overlay is intentional: remote push destinations are personal/sensitive values and must never enter a commit.

## Switching discipline

- Before stepping away: run `./scripts/use-profile` and configure your ntfy topic
- When you return (and no longer need ambient): run `./scripts/use-profile-reset`
- Do not perform irreversible operations under L2/L3: merges, deploys, or pushes to protected branches

## Not yet implemented

- There is no per-working-directory autonomy mechanism : all sessions currently share the same config. The long-term direction is for each repo to override the autonomy level in `.jcode/config.local.toml` (gitignored), read by jcode at startup. This repo does not implement it yet; waiting on jcode source support.