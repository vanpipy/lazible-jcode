# Scripts

Every script is standalone and safe to read top to bottom. Run any of them with
`--help`.

```text
scripts/
├── install             install / uninstall
├── uninstall
├── snapshot-config     pull the live config into the repo
├── sync-skills         reconcile config/skills/ with ~/.jcode/skills/
├── diff-live-base      show live vs repo config drift
├── verify-sanitized    pre-commit leak check
├── install-shell-env   manage the jcode env block in ~/.zshrc and ~/.bashrc
├── jcode-audit-log     the post_tool observer hook
└── _lib_toml.py        shared TOML emitter + secret mask (snapshot-config only)
```

## `install`

Installs configuration into `~/.jcode` and `~/.local/bin`. It does not build
jcode.

```bash
./scripts/install              # install
./scripts/install --dry-run    # show what would happen
./scripts/install --help
```

Phases: preflight, config, skills, shell env, audit hook, CLIs, prompts,
`~/AGENTS.md`, verify, state.

Design rules:

- repo is the source of truth for skills, prompts and CLIs. They are rewritten
  every install, so nothing under `~/.jcode/` can drift.
- `~/AGENTS.md` is written only when absent.
- `~/.jcode/config.toml` must not be a symlink. A symlink would let a write land
  in the repo base, which is exactly the incident recorded in
  [`../notes/symlink-incident.md`](../notes/symlink-incident.md).
- nothing outside `~/.jcode`, `~/.local/bin`, `~/.local/share`, `~/.zshrc` and
  `~/.bashrc` is touched.

Exit codes: `0` ok, `1` preflight failed, `6` verify failed.

## `uninstall`

```bash
./scripts/uninstall --dry-run
./scripts/uninstall              # CLIs, audit hook, prompts, state
./scripts/uninstall --full --yes # also config.toml, skills, shell env
```

Never removes `~/.local/bin/jcode` (this repo never installed it), `~/AGENTS.md`,
or runtime state under `~/.jcode/{ambient,state,sessions,logs,goals}/`.

## `snapshot-config`

Pulls the live `~/.jcode/config.toml` into `config/config.toml`, masking secrets
on the way. The reverse of `install`.

```bash
./scripts/snapshot-config            # default: preview, print the diff, write nothing
./scripts/snapshot-config --diff     # structural drift only, no masking, no write
./scripts/snapshot-config --apply    # write config/config.toml in the repo
```

Comments and section order are not preserved: the file is re-emitted from the
parsed TOML. Review the diff before committing.

## `sync-skills`

Reconciles `config/skills/` with `~/.jcode/skills/`.

```bash
./scripts/sync-skills                      # report differences
./scripts/sync-skills --to-home --apply    # repo → live
./scripts/sync-skills --from-home --apply  # live → repo
```

Direction is explicit because `install` already pushes repo → live
authoritatively. `--from-home --apply` is how you adopt a skill you edited in
place.

## `diff-live-base`

Prints every leaf where `~/.jcode/config.toml` and `config/config.toml` differ.
After a `snapshot-config` or an `install` it should report zero.

## `verify-sanitized`

Pre-commit check. Fails on: unparseable config, hardcoded `/home/<user>` paths,
a sensitive key holding a real value, a symlinked live config. Warns on: live
vs repo drift.

```bash
./scripts/verify-sanitized
```

## `install-shell-env`

Manages the marked `# >>> lazible-jcode >>>` block in `~/.zshrc` and
`~/.bashrc`. The block sets `JCODE_OPENROUTER_MODEL`.

```bash
./scripts/install-shell-env --remove   # preview removal
./scripts/install-shell-env --remove --apply
```

## `jcode-audit-log`

The `post_tool` observer. Appends one line per tool call to
`~/.jcode/audit.log`:

```text
[ts] event=tool tool=bash status=ok duration_ms=12 output_bytes=480 cwd=/path
```

It is fire-and-forget: jcode does not wait on it and it cannot block anything.
This is the whole log, not a rotation of a structured journal.

## `_lib_toml.py`

Small TOML emitter plus a secret masker. Only `snapshot-config` imports it. The
output is lossy: comments are dropped and sections are reordered. That is
acceptable because the result lands in git and gets reviewed.