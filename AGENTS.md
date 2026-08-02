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
- `swarm/ARCHITECTURE.md` — human-readable overview of the three goals
  (main = organizer, worker = executor, star topology), topology, contracts
  (invariants + output contract + cross-worker handoff), and the path map
  after install. Read this first if you are new to the swarm layout.
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
  `skills/install-jcode/jcode-install.sh` (standalone upstream binary installer).
  The wrapper is **linear and unconditional**: it runs 4 steps every time and
  overwrites the destination without prompting. Flags (all are *values*, not
  step toggles):
  - `--canary-version <v>` — pin the jcode tag the canary is built against.
  - `--clean` — pass through to `scripts/build-jcode-canary.sh --clean`: wipe
    the canary source-dir (`~/Project/jcode`) before cloning + applying patches.
    Use when a previous build left a polluted working tree and the patch fails
    to apply.
  Steps:
  1. Install jcode binary. If `jcode-patches/*.patch` exists, build a canary
     from those patches (via `scripts/build-jcode-canary.sh --replace-main`);
     otherwise call the standalone upstream installer. Either way, the result
     replaces `~/.local/bin/jcode` (the previous binary is backed up as
     `jcode.bak.<ts>`).
  2. Symlink overlay + swarm config (`swarm/prompt-overlay.md`,
     `swarm/swarm-prompt.md`, `swarm/roles/`) into `~/.jcode/`.
  3. Symlink each `skills/<name>/SKILL.md` directory into `~/.jcode/skills/<name>`.
  4. Symlink `AGENTS.md` into `~/.jcode/AGENTS.md`.
  Existing files at any destination are backed up to `<dst>.bak.<timestamp>`
  before being replaced.
- `jcode-patches/swarm-coordinator-first.system_prompt.md` is the source of
  truth for the rewritten base identity. The matching `.patch` file is
  generated from it against the upstream jcode HEAD at time of commit; see
  `docs/SELFDEV.md` §4 for the re-sync recipe when upstream drifts.
- `scripts/sync-jcode-source.sh` pulls the latest upstream jcode tag and
  re-applies every patch in `jcode-patches/`. Exits non-zero with a recovery
  recipe when a patch fails to apply.

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
bash -n scripts/build-jcode-canary.sh
bash -n scripts/sync-jcode-source.sh
bash -n skills/install-jcode/jcode-install.sh
bash -n skills/copy-from-jcode/copy-from-jcode.sh
# Verify the patch still applies to upstream jcode
git clone --depth 1 https://github.com/1jehuang/jcode.git /tmp/jcode-verify
(cd /tmp/jcode-verify && git apply --check jcode-patches/swarm-coordinator-first.patch)
rm -rf /tmp/jcode-verify
# Help output should match the committed help text
bash scripts/install.sh --help
```

All shell scripts must pass `bash -n`. The patch must apply cleanly. The
`--help` output must look correct (linear 4-step description, only `--canary-version`
flag).