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

The bundle ships a **global** overlay + verification script that
applies to every project you work in. Most users want project-specific
behavior on top — for example, a repo may want to disable a worker
role, add a domain-specific skill, or enforce a project-only invariant.
**Five extension points** cover this without forking the bundle:

- **Per-project overlay** — `<repo>/.jcode/prompt-overlay.md`. jcode
  reads it with precedence over the global `~/.jcode/prompt-overlay.md`
  (the precedence is already in jcode's overlay loader; the bundle
  just lets you use it). Use this to add project-level coordination
  rules, disable a role for that repo, or prepend a project-specific
  preamble. The file does not need to be a full overlay — short
  additive instructions work best ("in this repo, never spawn a
  test-writer because the test harness is custom; always route
  test requests to the implementer").
- **Per-project worker policy** — `<repo>/.jcode/swarm-prompt.md`.
  jcode loads this with the same precedence as the overlay (project
  → global → built-in default). Lets the project override worker-side
  model routing, spawn hygiene, and anti-patterns. Documented in
  jcode's `crates/jcode-base/src/prompt.rs::load_swarm_prompt`.
- **Per-project role override** — `<repo>/.jcode/roles/<name>.md`.
  Bundle convention (NOT jcode-native): when root fills a spawn
  prompt, it reads `<cwd>/.jcode/roles/<name>.md` first and falls
  back to `~/.jcode/roles/<name>.md`. Use this to specialize a role
  for the project (e.g. a security-focused reviewer for a security
  project). File name MUST be one of the 6 existing roles — adding
  a 7th is a red line. Empty files fall back to global with a warning.
- **Per-project verify hook** — `<repo>/.jcode/verify.sh`. The
  bundle's verification command checks for it (see "Verification
  before push" below) and runs it after the schema check passes.
  Use this to enforce project-only invariants the bundle cannot
  know about (e.g. "no `console.log` in `src/`", "all public APIs
  must have JSDoc", "TODO comments need a linked issue"). The
  script must exit non-zero to fail the verification.
- **Per-project pre-merge hook** — `<repo>/.jcode/pre-merge.sh`.
  Bundle convention: root runs `./<repo>/.jcode/pre-merge.sh <branch>
  <base_commit> <role>` before merging any worker branch into the
  main worktree. Exit 0 to proceed; non-zero blocks the merge and
  surfaces stderr to the user. Use this for cross-worker integration
  gates the bundle's per-slice gates miss (e.g. "after all workers
  merge, run the full e2e suite once"). Hook timeout: 5 minutes;
  hook may NOT modify tracked files (worktree is read-only at
  integration time). Absence of the file is not a failure.

All five live in `<repo>/.jcode/` — committed with the project,
not the bundle. They have no effect on other projects. The bundle
intentionally ships no defaults for the hooks: they are opt-in
extensions the project author sets up if needed. A full scenario
walkthrough (8 axes × 7 sub-cases) lives in `docs/EXTENSIONS.md`.

The bundle does **not** install or symlink either file. install.sh
runs from the bundle checkout, not from the project cwd, so it
cannot know which project's `<cwd>/.jcode/` to read.

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

# 6. Per-project verify hook (opt-in, only runs if present). See
#    "Per-project customization" above. Bundle does NOT install this;
#    if the project author put one at ./.jcode/verify.sh, run it.
if [[ -x ./.jcode/verify.sh ]]; then
  ./.jcode/verify.sh
fi
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
