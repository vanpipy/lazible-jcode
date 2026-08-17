# Linux Environment Support

What lazible-jcode needs from a Linux host, what it auto-detects, and
how to recover when something is missing. The bundle is **Linux-only**;
macOS / Windows / WSL are not in scope for this repository.

For a fresh host, run these two checks in order:

```bash
scripts/install.sh                      # runs env_probe() as step 0
scripts/extension.sh doctor --env       # session-start environment snapshot
```

If both pass, the bundle is correctly wired. If either fails, the
table below tells you which dep is missing and how to fix it.

---

## Required vs. optional

| Tool / condition     | Required? | Failure mode if missing                              | Detect command                    |
| ---                  | ---       | ---                                                 | ---                              |
| bash ≥ 4             | yes       | install.sh exits 3 with "bash < 4 detected"         | `bash --version`                 |
| git                  | yes       | install.sh exits 3 with "git not on PATH"           | `command -v git`                 |
| `$HOME` writable     | yes       | install.sh exits 3 with "HOME does not exist"       | `[[ -w "$HOME" ]]`               |
| `/tmp` writable      | yes       | install.sh exits 3 with "/tmp not writable"         | `[[ -w /tmp ]]`                  |
| curl **or** wget     | yes       | install.sh exits 3 with "neither curl nor wget"     | `command -v curl`                |
| python3 **or** jq    | optional  | extension.sh `mcp info` + `artifact validate` report "unavailable" instead of failing | `command -v python3` |
| `~/.local/bin` on PATH | optional  | new shells won't find `jcode`; warning at install   | `echo "$PATH"`                   |
| `git` ≥ 2.7          | yes (for `swarm-sweep`) | `--porcelain` output assumed; older git may mis-format | `git --version`        |
| `sha256sum`          | optional  | scratch-dir hash falls back to `cksum` (non-cryptographic, warns) | `command -v sha256sum` |

---

## Linux distro notes

Tested-friendly assumptions (bash 4+, GNU coreutils, GNU sed) hold for
every maintained distro since Ubuntu 16.04 / Debian 9 / RHEL 7. If you
are running something older than that, the bundle will likely fail and
you should update.

| Distro / family | Notes |
| --- | --- |
| **Debian / Ubuntu** | Standard path. `apt install python3` if missing. |
| **RHEL / CentOS / Fedora** | `dnf install python3` or `yum install python3`. Python 3 on RHEL 7 needs EPEL. |
| **Arch / Manjaro** | `pacman -S python` if missing. |
| **Alpine** | `apk add python3 bash` (Alpine ships busybox ash by default; bundle's `#!/usr/bin/env bash` requires real bash). Without python3, extension.sh JSON checks degrade gracefully — see "JSON tooling" below. |
| **NixOS / Guix** | Bundle assumes `/usr/bin/env` resolves to a real PATH. On NixOS you may need to wrap the script or run inside a dev shell with `bash` and `python3` available. |

---

## Path conventions

### Scratch dir

Bundle workers create scratch dirs under:

```
${LAZIBLE_TMPDIR:-/tmp}/jcode/<repo>-<short-sha>/wt-<label>/
```

- Default root is `/tmp`. Override with `LAZIBLE_TMPDIR=/some/path` for
  hosts where `/tmp` is small, slow, or ephemeral.
- `<repo>` is the repo's basename (e.g. `lazible-jcode`).
- `<short-sha>` is the first 8 hex chars of `git rev-parse HEAD` when
  inside a git repo; a sha256-derived 8-char key when not (e.g. when
  using `git worktree` from a detached state). The non-git fallback
  uses python3 / jq / sha256sum / cksum — last-resort cksum warns
  because collisions are easier.
- `wt-<label>` is one per worktree-using worker (3 of 6 roles:
  `implementer`, `test-writer`, `doc-writer`; see
  `swarm-prompt.md` §11).

### `~/.local/bin`

Standard Linux user-local binary path. install.sh puts `jcode` and the
`swarm-sweep` helper here. Most distros add it to PATH via
`~/.profile` or `~/.bashrc`; if yours doesn't, add:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

install.sh prints a warning if it's missing. New shells won't find
`jcode` until you fix PATH or source the profile.

### `~/.jcode/`

The bundle's config dir, populated by install.sh step 2 + 3. Holds
prompt overlays, swarm prompt, role templates, and (optionally) your
mcp.json. install.sh **never** touches `config.toml`, sessions, cache,
or auth — those belong to jcode itself.

---

## JSON tooling

Most bundle scripts that parse JSON (`extension.sh mcp info`,
`extension.sh artifact validate`, `extension.sh scratch-dir` hash
fallback, `extension.sh doctor` A4 row) prefer `python3` and fall back
to `jq`. If neither is present, the affected command reports
**"unavailable"** and exits 0 (informational, not failure) rather than
silently producing a wrong answer.

```bash
command -v python3 || command -v jq || \
  echo "install one: apt install python3 / dnf install python3 / apk add python3"
```

Python 3.6+ works. No third-party packages needed.

---

## Network access

install.sh step 1 calls `https://jcode.sh/install` to fetch the jcode
binary if `jcode` isn't already on PATH. This requires:

- HTTPS egress to `jcode.sh`
- No MITM proxy (or one configured in `HTTPS_PROXY` env)

If you're behind a corporate proxy:

```bash
export HTTPS_PROXY=http://proxy.example.com:8080
bash scripts/install.sh
```

If `jcode.sh` is unreachable but you already have `jcode` somewhere,
just put it on `PATH` and re-run install.sh — step 1 is a no-op when
`jcode` is found.

---

## Color / output behavior

All bundle scripts respect:

| Condition             | Behavior                              |
| ---                   | ---                                   |
| `NO_COLOR` env set    | plain output, no ANSI                 |
| stdout not a tty      | plain output (capture / pipe friendly) |
| `TERM=dumb`           | plain output (CI / minimal emulators) |
| otherwise             | colored output (cyan / yellow / red)  |

Disable color explicitly:

```bash
NO_COLOR=1 bash scripts/install.sh
```

This is the [no-color.org](https://no-color.org) standard; bundle
scripts follow it.

---

## Bundle verification

Two commands summarize the environment at a glance:

```bash
scripts/extension.sh doctor         # A1-A10 per-axis status table
scripts/extension.sh doctor --env   # 13-row env snapshot (bash, git, JSON tool, ...)
```

`doctor --env` always exits 0 — failures are reported as `missing`
rows that you can grep for:

```bash
scripts/extension.sh doctor --env | grep missing
```

Sample output on a working Linux host:

```
CHECK                          STATUS
-----                          ------
bash >= 4                      5.3.9(1)-release
git                            /usr/bin/git
HOME                           /home/you
HOME writable                  yes
/tmp writable                  yes
LAZIBLE_TMPDIR                 (unset, defaults to /tmp)
curl or wget                   curl: /usr/bin/curl
JSON tool                      python3: /usr/bin/python3
sha256sum                      /usr/bin/sha256sum
jcode                          /home/you/.local/bin/jcode
~/.local/bin on PATH           yes
NO_COLOR env                   (unset; color OK)
TERM                           xterm-256color
```

If any of `bash`, `git`, `HOME writable`, `/tmp writable`, or
`curl or wget` says `missing`, the bundle cannot work on that host —
fix the listed dep and re-run.

---

## Recovery cheat sheet

| Symptom                                              | Likely cause                                  | Fix                                                   |
| ---                                                  | ---                                           | ---                                                   |
| install.sh: "bash < 4 detected"                      | host runs bash 3 (RHEL 7 with `bash` package) | `dnf install bash` (gets bash 4+) or upgrade OS       |
| install.sh: "git not on PATH"                        | git not installed                             | `apt install git` / `dnf install git`                  |
| install.sh: "HOME does not exist"                    | `$HOME` unset or wrong                        | `export HOME=/home/you`                                |
| install.sh: "/tmp not writable"                      | unusual fs layout                             | `export LAZIBLE_TMPDIR=/some/path && bash scripts/install.sh` |
| install.sh: "neither curl nor wget"                  | no HTTP client                                | `apt install curl`                                     |
| `extension.sh mcp info`: "no python3/jq"             | python3 missing                               | install python3 (preferred) or jq                      |
| `swarm-sweep`: "no stale" but you have stale trees   | worktrees under `wt-<label>` but path doesn't match either regex | run `swarm-sweep --help` to confirm the matched patterns; paths must end in `/jcode/<repo>-<sha>/wt-<label>/` or `/swarm-<user>/<repo>/wt-<label>/` |
| New shells can't find `jcode`                        | `~/.local/bin` not on PATH                    | `echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc` |
| install.sh prints raw escape codes                   | `TERM=dumb` not set but terminal can't render | `export TERM=xterm-256color` or `unset NO_COLOR`     |
| Behind corporate proxy: install fails on `curl`      | no HTTPS_PROXY                                | `export HTTPS_PROXY=http://proxy:port && bash scripts/install.sh` |