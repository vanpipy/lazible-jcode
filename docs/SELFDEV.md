# Self-development (selfdev)

`selfdev` is the **third leg** of the lazible-jcode install flow. The other
two are:

1. **Binary install** — `scripts/install.sh` calls `jcode-install.sh` to put
   `jcode` on PATH.
2. **Overlay install** — symlinks `swarm/prompt-overlay.md` →
   `~/.jcode/prompt-overlay.md`. This is an *additional* prompt that jcode
   concatenates after its base system prompt (see
   `crates/jcode-base/src/prompt.rs::load_prompt_overlay_files_from_dir`).

The third leg rewrites the **base** system prompt itself, so the agent's
default behavior is swarm-coordinator-first without relying on overlay
position-weighting alone.

## Why a third leg?

The base system prompt (`crates/jcode-base/src/prompt/system_prompt.md`) is
embedded into the jcode binary at build time via Rust's `include_str!`. It is
**not a file jcode reads at runtime** — it is a string baked into the
`DEFAULT_SYSTEM_PROMPT` constant. No amount of overlay editing can change it.

Upstream's default identity line is:

```
You are a maximally proactive coding agent and assistant.
```

That instruction competes with our overlay's "coordinate, do not implement".
Even though the overlay sits after the base in the prompt, the base's "have
autonomy / persist / take initiative" framing tends to anchor model behavior
back to direct implementation.

`selfdev` rewrites the base so the default identity is:

```
You are a swarm-coordinator-first coding agent and assistant.
Default to planning, delegating, and integrating; implement directly only when scope is trivially small.
```

There is no competing anchor in the base anymore.

## What this repo ships

```
jcode-patches/
├── swarm-coordinator-first.system_prompt.md   # full replacement file
└── swarm-coordinator-first.patch              # unified diff against upstream HEAD

scripts/
├── build-jcode-canary.sh                      # clone + patch + cargo build + install
└── sync-jcode-source.sh                       # pull upstream + re-validate patch
```

The `.md` file is the source of truth (easy to read and review in a diff).
The `.patch` file is the same change in unified-diff format against the
upstream commit the patch was generated against, for `git apply`.

## Quick start: build a canary side-by-side

```bash
# 1. Build the canary (~5-10 min cargo build on first run)
./scripts/build-jcode-canary.sh --jcode-version v0.65.0

# 2. Try it
~/.local/bin/jcode-canary --version
~/.local/bin/jcode-canary run "say hello"

# 3. If it looks good, replace the main jcode binary
./scripts/build-jcode-canary.sh --jcode-version v0.65.0 --replace-main
```

The main `jcode` binary is backed up to `~/.local/bin/jcode.bak.<timestamp>`
before being overwritten, so you can roll back with:

```bash
mv ~/.local/bin/jcode.bak.<timestamp> ~/.local/bin/jcode
```

## One-shot install with selfdev

```bash
./scripts/install.sh \
    --enable-selfdev \
    --canary-version v0.65.0 \
    --replace-main-binary
```

This runs all four steps in order:
1. Install jcode binary via the upstream installer.
2. Symlink overlay + swarm config.
3. (opt-in) symlink skills.
4. Clone jcode, apply patch, build canary, replace main binary.

Without `--enable-selfdev`, step 4 is skipped (it's opt-in because it requires
the Rust toolchain and ~10 minutes of compile time).

## What the patch changes

See `jcode-patches/swarm-coordinator-first.system_prompt.md` for the full new
content. Summary of diffs against upstream:

| Section | Upstream | lazible-jcode |
|---|---|---|
| `## Identity` | "maximally proactive coding agent" | "swarm-coordinator-first coding agent" |
| `## Identity` | (no default-mode guidance) | Added 1-line note about when to implement directly |
| `## Identity` | (none) | Added provenance pointer back to lazible-jcode |
| `## Autonomy and persistence` | "Have autonomy. Persist to completing a task." | (kept) + added "Coordinate by default. Spawn workers for ≥3 files / ≥2 areas" |
| (new section) `## Spawn hygiene` | (none) | label / prompt / model+effort required on every spawn call |
| (new section) `## Verification before claiming done` | (scattered) | Consolidated: type check + lint + test + build, plus report verbatim |
| Other sections (`Tool call notes`, `Coding`, `User interaction`) | unchanged | unchanged |

The patch is small (one file, ~50 lines added, ~2 lines removed) so it can be
re-synced against upstream drift with low conflict risk.

## 4. Re-syncing against upstream

When upstream jcode cuts a new release, your local `source-dir` (at
`~/Project/jcode` by default) is stale. Re-sync with:

```bash
./scripts/sync-jcode-source.sh --target-version v0.66.0
```

What this does:

1. `git fetch --tags origin` inside `source-dir`.
2. Strategy `fetch+rebase` (default): reset to the target ref, clean any
   untracked files (including `target/`), then re-apply every patch in
   `jcode-patches/`.
3. If a patch no longer applies (upstream prompt has drifted), the script
   exits non-zero with a recovery recipe.

If the patch fails, regenerate it:

```bash
# 1. Get the upstream prompt file fresh
git clone --depth 1 --branch v0.66.0 https://github.com/1jehuang/jcode.git /tmp/jcode-upstream
cp /tmp/jcode-upstream/crates/jcode-base/src/prompt/system_prompt.md \
   /tmp/upstream-system_prompt.md

# 2. Edit jcode-patches/swarm-coordinator-first.system_prompt.md to merge
#    any new sections upstream added with our swarm-coordinator-first overrides.

# 3. Regenerate the .patch file
diff -u /tmp/upstream-system_prompt.md \
        /home/leroy/Project/lazible-jcode/jcode-patches/swarm-coordinator-first.system_prompt.md \
    | python3 -c '
import sys
lines = sys.stdin.read().splitlines(keepends=True)
content = "".join(lines[2:])
print("--- a/crates/jcode-base/src/prompt/system_prompt.md\n", end="")
print("+++ b/crates/jcode-base/src/prompt/system_prompt.md\n", end="")
print(content, end="")
' \
    > /home/leroy/Project/lazible-jcode/jcode-patches/swarm-coordinator-first.patch

# 4. Verify it applies
git apply --check /home/leroy/Project/lazible-jcode/jcode-patches/swarm-coordinator-first.patch

# 5. Commit the regenerated patch and re-build
cd ~/Project/jcode && git apply /home/leroy/Project/lazible-jcode/jcode-patches/swarm-coordinator-first.patch
./scripts/build-jcode-canary.sh --from-source --jcode-version v0.66.0 --replace-main
```

## 5. Layout

```
~/Project/jcode/                              # jcode source checkout (lazible-jcode does NOT manage this as a submodule;
                                              # scripts/build-jcode-canary.sh clones it on demand)
    └── crates/jcode-base/src/prompt/
            └── system_prompt.md              # patched on build

~/.local/bin/
    ├── jcode                                  # main binary (replaced by canary if --replace-main)
    ├── jcode-canary                           # side-by-side canary build
    └── jcode.bak.<timestamp>                  # backup of pre-replacement jcode (if --replace-main)

~/Project/lazible-jcode/
    └── jcode-patches/
            ├── swarm-coordinator-first.system_prompt.md
            └── swarm-coordinator-first.patch
```

## 6. When NOT to use selfdev

| Situation | Recommendation |
|---|---|
| You just want overlay-style swarm hints | Use the base `install.sh` — `--enable-selfdev` is opt-in for a reason |
| You're on a machine without Rust | Same as above |
| You ship jcode for other users via lazible-jcode | Other users should run `install.sh --enable-selfdev` themselves; you cannot ship a custom-built binary in this repo (license + size + drift) |
| You're prototyping a swarm prompt change | Edit `swarm/prompt-overlay.md` first — instant, no cargo build. Promote to a selfdev patch only when the change is stable and you want it baked into the base |

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| `error: required tool 'cargo' not found in PATH` | Install Rust via `rustup`: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs \| sh` |
| `error: patch no longer applies cleanly to upstream jcode` | The upstream prompt has drifted. See §4 (re-syncing). |
| `cargo build` fails with weird linker errors | Make sure `gcc`/`clang` and `pkg-config` are installed (Rust needs a C toolchain to link release binaries) |
| `error: expected built binary at .../target/release/jcode but it is missing` | Cargo build silently failed. Check `$SOURCE_DIR/target/release/build.log` or re-run with `--dry-run` first to confirm patch applied, then run `cargo build` manually to see the error |
| Build takes > 15 min | First-time builds of jcode pull and compile hundreds of crates. Subsequent incremental builds are < 1 min. |
| `~/.local/bin/jcode.bak.<timestamp>` accumulating | These are backups from `--replace-main`. Safe to delete once you've smoke-tested the canary: `rm ~/.local/bin/jcode.bak.*` |