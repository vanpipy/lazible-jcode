# AGENTS.md — lazible-jcode

Project-level instructions for any jcode agent working in this repo. Mirrors the
upstream jcode repo's `AGENTS.md` style: focused on workflow, paths, and
non-obvious gotchas. Anything an agent needs to know but cannot infer from the
code lives here.

## Layout

- Skills live under `skills/<name>/SKILL.md` (no `SKILL.md` outside a skill dir).
  Symlink the entire `skills/` directory into `~/.jcode/skills/` to install them
  for the current user.
- The four "live-copied" skills (`auto-swarm-planner`, `git-expert`, `rn-dev`,
  `optimization`) are byte-equivalent copies of the corresponding files in a
  real `~/.jcode/skills/` install. Treat them as upstream artifacts: do not
  rewrite their semantics; if a local divergence is needed, add a `local-*`
  skill beside them instead.
- The `swarm/` directory carries three distinct artifacts that are **not**
  skills (no `SKILL.md` frontmatter, not auto-loaded by trigger):
  - `swarm/swarm-prompt.md` — root-session + worker coordination rules (model
    routing, spawn hygiene, verification, decomposition, anti-patterns,
    workspace isolation). Loaded when you construct spawn calls.
  - `swarm/roles/<name>.md` — six worker persona templates (`reviewer`,
    `implementer`, `investigator`, `migrator`, `test-writer`, `doc-writer`).
  - `swarm/prompt-overlay.md` — the **enhanced default main-agent prompt**.
    Symlinked to `~/.jcode/prompt-overlay.md` by `scripts/install.sh`. jcode
    reads it at session start and concatenates it onto the base system prompt
    (see `crates/jcode-base/src/prompt.rs::load_prompt_overlay_files_from_dir`).
    Purpose: turn the default main agent into a swarm-coordinator-first agent
    by adding model routing, spawn-when rules, hygiene, decomposition order,
    and verification anti-patterns to the *main* prompt. Worker-only concerns
    (worktree paths, output schema, per-role workflow) belong in the worker
    prompt, not here.
  Install all three via `scripts/install.sh` (default behavior). Old
  `skills/copy-from-jcode/copy-from-jcode.sh --install` path still works but
  is no longer the recommended way.
- Config templates under `config/*.example` are **reference only**. Live config
  lives in `~/.jcode/`. Use `skills/copy-from-jcode/copy-from-jcode.sh` to pull
  a machine's `~/.jcode/` into this repo.
- `config/config.toml` is a sanitized live snapshot. It contains personal
  keybindings, model names, and `[launch_hotkeys].entries[].dir` paths, but
  no API keys or OAuth tokens. Do not add secrets there.
- `config/mcp.json` is **deliberately not committed**. The live
  `~/.jcode/mcp.json` carries MCP server tokens; `config/mcp.json.example` is
  the only safe place to reference its shape.
- Installer lives at `scripts/install.sh` (repo-level wrapper) and
  `skills/install-jcode/jcode-install.sh` (standalone binary installer).
  The wrapper does two things in order:
  1. Calls the standalone installer to install the jcode binary + PATH.
  2. Symlinks the overlay + swarm config into `~/.jcode/`. Flags:
     `--no-overlay` (skip step 2), `--overlay <path>` (custom overlay file),
     `--refresh` (force overwrite mismatched symlinks, backup non-symlinks),
     `--install-skills` (also symlink `skills/<name>`),
     `--skip-binary` (only run step 2), `--dry-run` (plan only).

## Commit conventions

- One skill per commit when possible.
- One swarm role per commit is preferred when iterating on a single role's
  prompt. Bundle multiple roles only when intentionally rotating the whole set.
- Keep commit subjects under 72 chars; body explains *why*, not *what*.
- `type(scope): summary` style. e.g. `feat(install): add --dry-run flag`.
- When porting a skill from upstream jcode, use `chore(skills): import <name>
  from ~/.jcode/skills` and add a one-line note about why (version bump,
  local divergence, etc.).
- Swarm config (`swarm/swarm-prompt.md`, `roles/*.md`) uses `feat(swarm): ...`
  or `chore(swarm): ...` scope; bundle them with their corresponding script
  changes when the script depends on the new shape.
- The main-agent overlay (`swarm/prompt-overlay.md`) uses `feat(overlay): ...`
  scope. Bundling it with installer changes is preferred so the install
  flow stays consistent.

## Things an agent must not do

- **Do not** commit anything under `config/` that is not an `.example` file or
  the sanitized `config.toml`. Live secrets belong in `~/.jcode/` and must
  never reach git. The `.gitignore` already excludes live mcp.json; respect it.
- **Do not** modify upstream jcode's skill semantics when porting. Keep
  `description`, `skill-type`, `version`, and `type` aligned with upstream so
  search-by-embedding still hits the same triggers.
- **Do not** add `README.md` files inside skill directories. jcode's loader
  indexes only `SKILL.md`; extra READMEs are dead weight.
- **Do not** add `package.json`, `Cargo.toml`, or any build manifest here.
  This repo has no build step; everything is shipped as-is.
- **Do not** rewrite a "live-copied" skill's content to fix upstream bugs. Fix
  it upstream first, then re-run `copy-from-jcode.sh` to refresh. Diverging
  silently makes the next re-sync non-trivial.

## Logs / state

- No runtime state lives in this repo.
- The standalone installer writes nothing outside `~/.jcode/builds/`,
  `~/.local/bin/`, and the user's shell rc files (path lines, idempotent).

## Verification before push

Before pushing any commit, run:

```bash
bash -n scripts/install.sh
bash -n scripts/uninstall.sh
bash -n skills/install-jcode/jcode-install.sh
bash -n skills/copy-from-jcode/copy-from-jcode.sh
# Optional but recommended: a dry-run
bash scripts/install.sh --dry-run
```

All four must pass with no syntax errors. The `--dry-run` must print a plan
without writing to disk.