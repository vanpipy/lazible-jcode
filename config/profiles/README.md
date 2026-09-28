# Profiles

`new.md` §2 envisions a profiles directory. The jcode source **has no profile concept** : only
single-field pins like `agents.swarm_model` / `JCODE_TOOL_PROFILE`.

This repo defines a profile as a **TOML overlay**, merged by `scripts/use-profile` at shell time
into `~/.jcode/config.toml`. jcode itself never reads `config/profiles/`.

## List

| Name | Purpose | Autonomy level |
| --- | --- | --- |
| `autonomous.toml` | Enable ambient + headless swarm + desktop notify + audit hook | L2 |

> **There is only one profile.** The earlier `default` / `research` profiles were removed : the former was an empty
> overlay (no-op, `use-profile-reset` already cleans back to base), and the latter had every field already baked
> into base, making the overlay a no-op.

L0 (pre_tool gate) and L3 (remote push) are intentionally **not** profiles : the former needs a custom
policy script (`~/.local/bin/jcode-tool-policy`), and the latter requires sensitive values
(`safety.ntfy_topic` / `email_enabled` / `telegram_enabled`) that must not enter git.
When needed, write them by hand or fill them in via `JCODE_*` environment variables.

## Switching

```bash
./scripts/use-profile                  # default argument = autonomous
./scripts/use-profile-reset            # pull a clean base from git HEAD
```

⚠️ `use-profile-reset` is only needed after base has been polluted by an overlay. If you stay on
autonomous, no reset is required.

## Design constraints

- The overlay only covers fields; it **cannot delete fields**
- Do not place sensitive values (api_key / token); use `~/<PLACEHOLDER>` placeholders, filled in via environment variables
- Every field name must exist in the jcode schema at `jcode-config-types/src/lib.rs`; otherwise `apply_env_overrides` will ignore unknown keys at jcode startup