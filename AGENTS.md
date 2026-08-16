# AGENTS.md — lazible-jcode

Project-level instructions for any jcode agent working in this repo.
Focused on workflow, paths, and non-obvious gotchas. Anything you cannot
infer from the code itself lives here.

## What this repo is

A **prompt store + installer** for jcode customizations. The shipped
content is the markdown under `swarm/` and `AGENTS.md`, plus the
two shell scripts that install and uninstall them. There is **no
build step, no test suite, no CI**. Editing markdown is the primary
work. The bundle is generic — no project-specific terms, no per-machine
state, no Sages / tick-era / Smart Postman / DAG-stage terminology.

## Layout

| Path | Purpose | Touchable? |
| --- | --- | --- |
| `AGENTS.md` (this file) | Operating manual for any agent working here | yes |
| `README.md` | Project overview, quick start, repo table | yes |
| `docs/INSTALL.md` | Detailed install / uninstall / troubleshooting | yes |
| `scripts/install.sh` | 3-step installer. Symlinks `swarm/` + `AGENTS.md` into `~/.jcode/`, and `swarm-sweep` into `~/.local/bin/` | yes |
| `scripts/uninstall.sh` | Inverse. Flags: `--keep-binary`, `--purge`, `--yes` | yes |
| `scripts/swarm-sweep.sh` | Cleanup helper for stale swarm worktrees/branches (M2/M3 residue). Symlinked to `~/.local/bin/swarm-sweep` by install.sh | yes |
| `scripts/extension.sh` | Single entry point for per-project extension conventions (`role`, `verify`, `pre-merge`, `notify`, `pre-spawn` subcommands) | yes |
| `swarm/prompt-overlay.md` | Main-agent overlay. Loaded by jcode at session start | yes |
| `swarm/swarm-prompt.md` | Root + worker policy (model routing, spawn hygiene, decomposition) | yes |
| `swarm/ARCHITECTURE.md` | Human-readable star topology + contracts overview | yes |
| `swarm/roles/<name>.md` | Worker persona templates. **Exactly 6 roles**: `reviewer`, `implementer`, `investigator`, `migrator`, `test-writer`, `doc-writer` | yes |
| `config/config.toml` | Sanitized live snapshot from a real `~/.jcode/config.toml`. Reference only. | no |
| `config/config.toml.example` | Template for the above | yes |
| `config/mcp.json.example` | Schema reference for MCP servers layout | yes |
| `.gitignore` | Excludes `.bak.<ts>`, `.bak.*`, OS noise, the live `config/mcp.json` | yes |

There are no `scripts/lib/`, `tests/`, `jcode-patches/`, `experiments/`,
`docs/HEARTBEAT.md`, `docs/POSTMAN_PROTOCOL.md`, `skills/`, or
`swarm/role-templates/` directories. If you reach for one of those
paths, you are looking at the old layout — refer to the current files
above instead.

## Working in this repo

### Bootstrap a fresh machine

```bash
git clone https://github.com/vanpipy/lazible-jcode.git
cd lazible-jcode
./scripts/install.sh          # 3 steps, idempotent, overwrite-by-default
```

The installer symlinks the overlay into `~/.jcode/`. The real
`~/.jcode/config.toml`, runtime state, sessions, and auth are NOT
touched.

### Tear down

```bash
./scripts/uninstall.sh --keep-binary --yes        # remove symlinks, keep jcode
./scripts/uninstall.sh --keep-binary --purge --yes  # also wipe ~/.jcode/
./scripts/uninstall.sh --yes                       # remove symlinks + jcode binary
```

### Add a new role persona

1. Create `swarm/roles/<name>.md` using the same 8-section template as the others: `Persona`, `Position in swarm`, `Output contract (mandatory)`, `Scope`, `Workflow`, `Output schema`, `Skills to load`, `Anti-patterns`.
2. The `Output contract (mandatory)` section **must** list all 7 fields: `findings`, `evidence[]`, `edge_cases_considered[]`, `validation`, `open_questions[]`, `confidence`, `what_i_did_not_check[]`. The `Output schema` JSON block must include all 7 keys (plus `status` as the 8th field that lives at the top of the schema).
3. Update `swarm/ARCHITECTURE.md` topology to add the new worker node.
4. Update `swarm/prompt-overlay.md` worker-templates list (§11).
5. Re-run install; the new role auto-symlinks into `~/.jcode/roles/`.

### Edit the overlay

Touch `swarm/prompt-overlay.md` for any main-agent behavior change
(coordination mode, decision flow, invariants). Edit `swarm/swarm-prompt.md`
for worker-side policy (model routing, spawn hygiene, anti-patterns).
Keep them consistent: any invariant in one must appear in the other.

### Edit the install / uninstall scripts

Treat them as a pair. Anything added to `install.sh` steps must be
mirrored in `uninstall.sh`. After editing, run `bash -n` on both and
re-run the live install + idempotent rerun to confirm nothing broke.

### Edit docs

`README.md` is the user-facing entry point (quick start, layout,
file-purpose table). `docs/INSTALL.md` is the deeper reference
(troubleshooting, re-install semantics, flags). `AGENTS.md` (this file)
is the agent-facing operating manual. Do not duplicate content across
the three — point at the canonical location.

### Per-project customization (extension mechanisms)

The bundle exposes nine per-project extension points — files at
`<repo>/.jcode/<name>.{sh,md,json}/` that root invokes via
`scripts/extension.sh` (the bundle convention entry point) or
that jcode loads directly (jcode-native). Four are jcode-native;
five are bundle conventions:

| Convention | File | Loader | Purpose |
|---|---|---|---|
| Overlay (jcode-native) | `prompt-overlay.md` | jcode direct | Project coordination rules, role disables, preamble |
| Worker policy (jcode-native) | `swarm-prompt.md` | jcode direct | Override model routing / spawn hygiene / anti-patterns |
| Skills (jcode-native) | `skills/<name>/SKILL.md` | jcode direct | Auto-discovered per-project skill bundles |
| MCP servers (jcode-native) | `mcp.json` | jcode direct | Project-local MCP server registrations |
| Role override | `roles/<name>.md` | `extension.sh role <name>` | Specialize a role for the project (e.g. security reviewer) |
| Verify hook | `verify.sh` | `extension.sh verify` | Project-specific invariants (lint, JSDoc, no console.log) |
| Pre-merge hook | `pre-merge.sh` | `extension.sh pre-merge <branch> <base> <role>` | Cross-worker integration gate before merging |
| Notify hook | `notify.sh` | `extension.sh notify <status> <label> <artifact>` | Completion observability (bypass mode) |
| Pre-spawn hook | `pre-spawn.sh` | `extension.sh pre-spawn <label> <role> <count>` | Per-spawn env setup + KEY=VALUE exports |
| **Scratch dir** | (no file) | `extension.sh scratch-dir` | Canonical per-project worktree/scratch path under `$TMPDIR/jcode/<repo>-<short-sha>/` (not `~/.jcode/scratch/`) |

Discovery helpers for jcode-native points:
- `extension.sh skills list` — enumerate per-project skills
- `extension.sh mcp info` — show per-project MCP config status
- `extension.sh scratch-dir` — print canonical `$TMPDIR/jcode/<repo>-<short-sha>/` path
- `extension.sh scratch-dir clean [--yes]` — remove the per-project scratch dir (dry-run by default)
- `extension.sh artifact validate <path>` — validate a typed-artifact JSON against the 8-field contract

Pre-spawn gate (run before drafting a worker spawn prompt):
- `extension.sh preflight [--worktree P] [--project P]` — verify jcode on PATH, daemon reachable, bundle installed, paths writable, default model auth OK. Exit 0 = green, 3 = hard fail, 1 = warnings.

Model selection helpers:
- `extension.sh models list` — list jcode-known model names
- `extension.sh models probe <name>` — 1-token auth probe (`jcode run --model X ok`); exit 0 = OK, 4 = auth fail, 3 = unknown. Use BEFORE spawning to avoid wasted spawns on unauth'd models.

All ten live in `<repo>/.jcode/` (except the scratch dir which is
in `$TMPDIR` by design). Absence of any of them is not a failure;
root proceeds with the default behavior. Full 10×10 boundary-behavior
walkthrough lives in `docs/EXTENSIONS.md`.

## Spawn workflow (gotchas to avoid)

Before drafting a worker spawn prompt, run `extension.sh preflight`.
It catches the three failure modes below BEFORE a worker is spawned
(rather than after a wasted spawn prompt).

| # | Failure | Detection | Avoidance |
|---|---|---|---|
| P1 | Model auth fail — worker spawns, immediately errors on first API call, dies. Wastes ~30s + a worktree. | `extension.sh models probe <name>` does a 1-token call; exit 4 = bad credentials. | Run probe before drafting. If 4, try a different model (per swarm-prompt, fallback = inherit from root). |
| P2 | Scope ambiguity — worker `dm`s you with "what did you mean?", stalls waiting. | Pre-spawn checklist in §1 of overlay. | Write scope prompt tightly: enumerate `files_touched[]`, paste base SHA, state the gates explicitly. Worker emits `status: needs-info` if still ambiguous. |
| P3 | Path confusion — worker writes into `$TMPDIR/jcode/.../wt-<label>/`, root thinks it'll land in `<repo>` directly. | `extension.sh preflight --worktree <path>` validates writable parent. | The bundle's `$TMPDIR/jcode/<repo>-<short-sha>/` is the worker scratch; integration root copies into `<repo>` after artifact acceptance. |

### Quick spawn checklist

1. `extension.sh preflight` (exit 0).
2. `extension.sh models probe <model>` (exit 0) — if your chosen model is non-default.
3. `extension.sh scratch-dir` to print the canonical WT path.
4. Write spawn prompt with: `label`, `model`, `effort`, `worktree_path`,
   `base_commit`, `worker_branch`, `files_touched[]`, `scope_body`,
   `termination_template`, `required_skills[]`.
5. After worker emits artifact: read `findings` + `evidence[]` +
   `validation` + `open_questions[]` before integrating.

Skipping steps 1-2 is how you burn 5 minutes on a model that 401s on
the first call.

## Commit conventions

- `type(scope): summary` style. Example: `feat(roles): add security-reviewer`.
- Subject under 72 chars; body explains *why*, not *what*.
- One concept per commit. Bundle only when the second change is meaningless
  without the first (e.g. an installer flag + its docs).
- Scopes in this repo:
  - `install`, `uninstall`, `scripts` — installer changes
  - `overlay` — `swarm/prompt-overlay.md`
  - `swarm` — `swarm/swarm-prompt.md`, `swarm/ARCHITECTURE.md`
  - `roles` — `swarm/roles/*.md`
  - `readme`, `docs`, `agents` — documentation
  - `repo` — meta / cleanup / gitignore
  - `config` — config templates
- Common types: `feat`, `fix`, `refactor`, `chore`, `docs`.

## Things an agent must not do

- **Do not** commit anything under `config/` that is not `.example` or
  the sanitized `config.toml`. Live secrets belong in `~/.jcode/`.
  The `.gitignore` excludes the live `mcp.json`; respect it.
- **Do not** add a `package.json`, `Cargo.toml`, `pyproject.toml`, or
  any other build manifest. This repo has no build step.
- **Do not** introduce new directories. The 4 top-level dirs are
  `config/`, `docs/`, `scripts/`, `swarm/`. Adding `tests/`, `lib/`,
  `experiments/`, `examples/` reopens the surface area the cleanup
  closed.
- **Do not** add a 7th role. The 6 roles are deliberate; adding another
  dilutes the spawn decision the root makes. If you genuinely need a
  new role, document the case in the PR body.
- **Do not** rewrite the overlay's invariants, the `Output contract`
  fields, or the ARCHITECTURE topology in a way that breaks the existing
  6 roles. The contract is the spine.
- **Do not** add `.bak.<ts>` files to git. They are runtime artifacts.
- **Do not** introduce Sages / tick-era / Smart Postman / DAG-stage
  terminology. The bundle is deliberately generic; project-specific
  terms belong in the user-written `~/.jcode/AGENTS.md`, not here.
- **Do not** push to `origin/main` without an explicit user decision.
  This is the autonomy boundary. Surface the push plan in chat and
  wait for the user to pick the strategy (force-push / new branch / PR).

## Verification before push

Run the following locally on every commit that touches `scripts/`,
`swarm/`, or `docs/`:

```bash
# 1. Shell-script syntax
bash -n scripts/install.sh
bash -n scripts/uninstall.sh

# 2. Config-file parse
python3 -c "import json; json.load(open('config/mcp.json.example'))"
python3 -c "import tomllib; [tomllib.load(open(p, 'rb')) for p in ['config/config.toml', 'config/config.toml.example']]"

# 3. Help output matches the committed help text
bash scripts/install.sh --help
bash scripts/uninstall.sh --help

# 4. Role-schema contract (all 6 files have all 7+1 mandated fields)
python3 -c "
import json, sys
required = {'findings', 'evidence', 'edge_cases_considered', 'validation', 'open_questions', 'confidence', 'what_i_did_not_check', 'status'}
ok = True
for role in ['reviewer', 'implementer', 'investigator', 'migrator', 'test-writer', 'doc-writer']:
    path = f'swarm/roles/{role}.md'
    text = open(path).read()
    # Find ## Output schema heading, then extract the FIRST ```json ... ```
    # fence block that follows it. Robust against role-specific fields
    # (nested braces, extra keys) because we don't regex the JSON itself.
    idx = text.find('## Output schema')
    if idx < 0:
        print(f'{role}: NO schema heading'); ok = False; continue
    rest = text[idx:]
    fence_start = rest.find('\`\`\`json')
    if fence_start < 0:
        print(f'{role}: NO json fence'); ok = False; continue
    body_start = fence_start + len('\`\`\`json')
    fence_end = rest.find('\`\`\`', body_start)
    if fence_end < 0:
        print(f'{role}: NO closing fence'); ok = False; continue
    json_block = rest[body_start:fence_end].strip()
    try:
        obj = json.loads(json_block)
    except json.JSONDecodeError as e:
        print(f'{role}: JSON parse error {e}'); ok = False; continue
    missing = required - set(obj)
    if missing:
        print(f'{role}: missing {missing}'); ok = False
sys.exit(0 if ok else 1)
"

# 5. Live install smoke test (uses real ~/.jcode/ — safe: install.sh
#    does not touch config.toml, sessions, cache, etc.)
bash scripts/install.sh                          # first run
bash scripts/install.sh                          # idempotent rerun (should print 'unchanged' for all)
# Confirm both run with zero .bak.<ts> files created
find ~/.jcode -maxdepth 1 -name '*.bak.*' | wc -l   # should be 0

# 6. Per-project verify hook + extension surface check. See
#    "Per-project customization" above. Bundle's single entry point
#    for extension conventions is scripts/extension.sh.
scripts/extension.sh verify
scripts/extension.sh doctor  # informational only — surfaces what is
                             # wired up vs. what falls back to defaults.
                             # Use this to verify the bundle's own
                             # discovery helpers work in cwd.
```

All six must pass before any commit touching the installer or
swarm config is pushed. Step 6 only runs when the per-project hook
exists; absence is not a failure.

## Repo-specific gotchas

- **The overlay is generic.** If you find yourself adding project-specific
  terms (project names, team names, internal tool names), stop and
  push those to the user's own `~/.jcode/AGENTS.md` instead. This repo
  is a public bundle.
- **6 roles, fixed names.** The `swarm/roles/*.md` filenames are
  referenced verbatim from `swarm/prompt-overlay.md`, `swarm/ARCHITECTURE.md`,
  and the README. Renaming a role requires updating all three.
- **The 7+1-field contract is invariant.** Every role's JSON schema must
  contain `status`, `findings`, `evidence`, `edge_cases_considered`,
  `validation`, `open_questions`, `confidence`, `what_i_did_not_check`.
  The overlay's invariant 4 says so. Adding a 9th role-specific field
  to one role is fine (e.g. `risks`, `migration_plan`, `coverage`);
  removing any of the 8 contract fields from any role is a contract
  break.
- **Backup branches are safety nets, not stale branches.** `backup/pre-clear-2026-08-16`
  (HEAD `7bdb611`) and `backup/pre-rebuild-2026-08-16` (HEAD `bcc0b72`)
  hold the pre-cleanup states. Do not delete them. They are not
  pushed to `origin`; they exist only in this clone.
- **Live `~/.jcode/` is shared across machines.** The install creates
  symlinks INTO `~/.jcode/`. If you rebase this repo, the symlinks
  automatically re-target. If you delete the repo checkout, the
  symlinks dangle — uninstall first.
- **No sweep/cleanup cron.** The installer does not rotate `.bak.<ts>`
  files. The fast path in `overwrite_link` (skip backup when dst
  already links to src) prevents accumulation on idempotent reruns.
  Old `.bak.<ts>` files left over from installs against user-edited
  destinations are intentional and can be removed by hand.

## Logs / state

- No runtime state lives in this repo.
- The installer writes nothing outside `~/.local/bin/jcode`,
  `~/.local/bin/swarm-sweep`, and `~/.jcode/<overlay-files>`.
- Worker liveness, sessions, telemetry, and auth all live in
  `~/.jcode/`, not here.

## Cleanup: stale swarm worktrees

When a worker disappears (M3 silent disappearance) or forgets to emit
its artifact (M2), the worktree and branch it created sit in the repo
indefinitely. `swarm-sweep` cleans them up:

```bash
swarm-sweep              # dry-run, lists stale worktrees
swarm-sweep --yes        # actually remove them
swarm-sweep --max-age=3  # threshold in days (default: 7)
```

The script only touches worktrees whose path matches the swarm
convention `$TMPDIR/swarm-<user>/<repo>-<short-sha>/wt-<label>/`.
The main worktree and any manual feature worktrees are NEVER touched.

`swarm-sweep` is installed into `~/.local/bin/swarm-sweep` by
`scripts/install.sh` (step 1, alongside jcode). Removing it happens
via `scripts/uninstall.sh --yes`.
