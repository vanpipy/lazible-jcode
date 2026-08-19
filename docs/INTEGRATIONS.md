# Integrations (MCP server stack)

This bundle recommends a small set of **local-only** MCP servers for coding
workflows. None of them require external API credentials; all run on your
machine and only touch your local filesystem, repos, and databases.

The config template lives at [`config/mcp.json.example`](../config/mcp.json.example).
Copy it to `~/.jcode/mcp.json` (global) or `<repo>/.jcode/mcp.json`
(per-project) and adjust paths.

## Recommended stack

| Server       | Purpose                                          | Invocation                                          |
| ------------ | ------------------------------------------------ | --------------------------------------------------- |
| `filesystem` | Scoped file I/O, safer than unrestricted bash   | `npx -y @modelcontextprotocol/server-filesystem`    |
| `git`        | Structured local git ops (log/blame/diff/branch) | `npx -y @cyanheads/git-mcp-server`                  |
| `serena`     | Code intelligence (symbols, refs, rename) — see workspace caveat below | `uvx serena-agent start-mcp-server --project <path>` |

`puppeteer` (browser automation, local Chromium) is an optional add-on
when you need e2e coverage. Drop it from the stack if you do not.

### Why no sqlite MCP

Verified 2026-08-16: every sqlite MCP server currently published on npm
(`mcp-sqlite`, `sqlite-mcp`, `mcp-server-sqlite`) either fails the
JSON-RPC handshake or produces no output on stdout — none of them are
usable through jcode today. Until that changes, use jcode-native `bash`
with the `sqlite3` CLI:

```bash
sqlite3 path/to/db.sqlite ".tables"
sqlite3 path/to/db.sqlite ".schema <table>"
sqlite3 path/to/db.sqlite "SELECT * FROM <table> LIMIT 10;"
```

The `bash` route is also safer than any MCP wrapper would be: the
`sqlite3` CLI's exit codes are direct, and the SQL text is visible in
the artifact's `validation` field.

## When to use each server

### filesystem

Use for any **bulk read or write that would otherwise involve many shell
calls**. The scoping flag (`--root <path>`) is the safety boundary; do not
add a parent directory you do not want the agent to see.

Prefer filesystem MCP over `bash` for `cat`/`sed`/`echo` style edits when
the operation is **scoped, structured, or large**. Plain `bash` is still
fine for one-off shell pipelines.

### git

Use for **structured repository queries** that would otherwise require a
long `git log`/`git diff` invocation with custom formatting.

The git MCP is **not** a replacement for `git commit` / `git push`. Use
the native shell command for state-changing operations so the agent
feels the exit status directly. The MCP shines for read-only inspection
across many files (e.g., "find every commit touching `crates/X`").

`@cyanheads/git-mcp-server` registers 28 tools including `git_log`,
`git_blame`, `git_diff`, `git_branch`, `git_status`, and `git_show`.

### serena

Use for **code navigation in non-trivial codebases**: finding symbols,
finding all references before a rename, getting a file's structural
overview, replacing a function body by symbol rather than by line range.

Serena uses tree-sitter and **does not require per-language LSP binaries**
to be installed. Supported out of the box: Python, TypeScript, Java, Go,
and a few others. For Rust or other less-covered languages, fall back to
`read` + targeted `agentgrep`.

### Silent startup (no browser)

By default serena opens a web dashboard in the default browser every
time the MCP server starts. The bundle's `config/mcp.json.example`
passes `--open-web-dashboard false` to suppress the auto-open while
keeping the dashboard reachable on `http://127.0.0.1:24282/dashboard/`
for manual inspection. To re-enable the auto-open (e.g. during local
debugging), drop the flag from the serena `args` list in
`~/.jcode/mcp.json` or `<project>/.jcode/mcp.json`.

If you prefer the dashboard entirely disabled (no port listening at
all), swap `--open-web-dashboard false` for `--enable-web-dashboard
false`. Both flags override the equivalent setting in
`~/.serena/serena_config.yml`.

A serena usage skill lives at `~/.jcode/skills/serena/SKILL.md` (optional,
per-user). It encodes the when-to-use rules and the boundary with
jcode-native `read`/`grep`/`edit`.

### Serena and workspaces

jcode spawns workspace-using workers (`implementer`, `test-writer`,
`doc-writer`, `migrator`) into per-project workspaces
(`$TMPDIR/jcode/<repo>-<short-sha>/ws-<label>/`) but **inherits the
project's MCP config** (extension point A4) into those workers — serena
starts with the same `--project <main-repo>` path it had in the main
session. After a worker edits files in the workspace, serena's
tree-sitter index is **anchored to the main repo HEAD**, not the
worker's branch. `find_symbol` / `find_referencing_symbols` /
`rename_symbol` will return results from main, silently missing the
worker's edits. The same caveat applies to folder-backing workspaces
(no git, but the worker cwd is still outside serena's project root).

The `reviewer` / `investigator` root-cwd roles also benefit from
serena but the caveat is different: they read in root cwd without
editing, so serena's structural views match what they see. They can
trust serena's call graph and references directly.

Worker pattern:

- **Before editing**: serena is fine for code-intelligence exploration
  of the main repo (reading the call graph you're about to modify,
  finding all references pre-rename).
- **After editing**: do **not** trust serena's symbol index for files
  you have just modified. Use jcode-native `read <file>` +
  `agentgrep <pattern>` against the workspace path.
- **Verification of intent**: when you need to confirm "did my edit land
  the way I expect?", re-read the file via `read` or grep via
  `agentgrep <workspace-absolute-path>/<file>`. Do not ask serena.

The bundle ships `extension.sh mcp worktree-hint <ws-path>` to
make the staleness check mechanical. Workers should run it at spawn
start (output line still says `worktree` for backward compat, but
accepts the workspace path):

```bash
# Inside the worker workspace, or from root before drafting the spawn:
extension.sh mcp worktree-hint "$WORKSPACE_PATH"
# Output is line-oriented; grep for the status line:
#   serena: live (project=...)                          ← editing in main repo
#   serena: stale (sees <main-repo> only; worktree edits invisible)
#   serena: not-configured                              ← no serena in MCP config
# Exit 0 always (informational, not a gate).
```

This subcommand does NOT fix the underlying engine limitation
(per-spawn MCP project rebind); it gives the worker a deterministic
detection path and a recommended verification fallback.

## When **not** to use any of these

- **External API needs** (GitHub, GitLab, hosted DBs, hosted search).
  These require tokens and belong in a separate config layer with proper
  secret handling.
- **Operations needing network egress** other than `fetch` (the optional
  add-on). Default-local is the rule; explicit opt-in for anything that
  crosses the network boundary.
- **Codebase-wide indexing or full-text search at terabyte scale**. The
  local stack is for working repos; if your data exceeds local indexing
  comfort, use a hosted service with proper auth.

## Boundary with jcode-native tools

jcode already provides built-in tools that overlap with this stack.
Default to jcode-native when the operation is small or one-off:

| Task                                 | Default choice                                |
| ------------------------------------ | --------------------------------------------- |
| Read a single file                   | `read` (jcode-native)                         |
| Read 50+ files or a directory tree   | `filesystem` MCP                              |
| Find a literal string across files   | `agentgrep` (jcode-native)                    |
| Find a symbol and its references     | `serena` MCP (main repo only — see workspace caveat) |
| Verify workspace edits match expectations | `read` + `agentgrep` (NOT serena — see workspace caveat) |
| Run a one-off `git log`              | `bash` (jcode-native)                         |
| Run a structured batch of git ops    | `git` MCP                                     |
| Edit a few lines in one file         | `edit` / `apply_patch` (jcode-native)         |
| Edit by symbol across multiple files | `serena` MCP (with explicit scope prompt)     |
| Query a local SQLite database        | `bash` + `sqlite3` (jcode-native, see above)  |

The rule of thumb: **structured and batched** -> MCP, **small and
one-off** -> jcode-native. MCP is the wrong tool when you would use it
once and then never again.

## Serena usage example (refactor log: extracting `_scratch_root`)

The bundle's own refactor log gives a concrete before/after of how
serena compares to native tools on a real task. Recorded 2026-08-18.

### Task

Pull the per-project scratch-root path-computation (git toplevel +
non-git hashed-abs-path fallback chain, ~50 lines) out of
`cmd_scratch_dir` and into a dedicated `_scratch_root` helper, leaving
`cmd_scratch_dir` as a thin `case` dispatcher.

### Steps with serena

| Step | Serena call | Native equivalent | Difference |
| --- | --- | --- | --- |
| Locate function | `find_symbol cmd_scratch_dir` | `grep -n 'cmd_scratch_dir() {'` | serena gives `kind`, 0-based line range, 1 JSON line; grep gives one line per match with false positives from `cmd_scratch_dir root` call sites |
| List callers | `find_referencing_symbols cmd_scratch_dir` | `grep -n 'cmd_scratch_dir'` | serena groups by symbol (3 `Variable` + 1 `Function` + 1 `File`), 0 false positives, snippets around each; grep returns 6 lines + self + comments |
| File overview | `get_symbols_overview scripts/extension.sh` | `sed -n 620,800p` (180 lines) | serena lists all 24 top-level functions in the file with locations; sed shows raw text |
| Insert new function | `insert_before_symbol cmd_scratch_dir --body …` | `edit_file` with anchor line numbers | serena resolves symbol location internally; `edit_file` needs the line number maintained by hand |
| Replace function body | `replace_symbol_body cmd_scratch_dir --body …` | `sed` large-block replace or `apply_patch` | serena replaces the body span (lines 626–723) atomically; sed needs exact `old_string`/`new_string` quoting |

### Outcome

- **Net diff**: +13 / −5 = +8 lines, clean separation of concerns.
- **AST verified**: `get_symbols_overview` after the edit lists
  `_scratch_root` as a distinct `Function` symbol with exactly one
  caller (`cmd_scratch_dir` at line 682).
- **Behavior verified**: `bash -n`, `preflight`, workspace E2E
  (init / add-slot / overlap-reject / destroy / clean), and
  `scratch-dir clean` (dry-run + `--yes`) all pass.
- **One caught regression**: a body-literal backslash escape (JSON
  `\$` decoding into the file as `\$` instead of `$`) turned a benign
  awk regex into one that would match a literal `$`. Caught by
  `od -c` byte-level comparison against the pre-edit file before
  commit. Fixed with one `replace_content` call. **serena validates
  structure, not shell semantics — stay alert to special characters
  when writing bodies.**

### When serena did **not** help

- **Awk-regex escaping**: same issue as above. serena moves text but
  does not parse shell.
- **Cross-file fan-out for tiny edits**: 1-character changes in a
  single file are cheaper via `edit` than via `find_symbol` →
  `replace_symbol_body`.
- **Initial discovery of "what to refactor"**: serena surfaces
  structure but does not decide whether a function should be split.
  That's the engineer's call.

The lesson is not "always serena" but "**serena for the 30-second
symbolic edit; native for the 5-second line edit**." Reach for serena
when the change is structural and you can name the symbol; reach for
native when the change is local and you can name the line.

## Verification

After editing the MCP config, run:

```bash
# 1. JSON parses
python3 -c "import json; json.load(open('~/.jcode/mcp.json'))"

# 2. jcode sees the servers
mcp list

# 3. Each server actually speaks JSON-RPC (smoke test)
python3 - <<'PY'
import json, subprocess, time, select
def smoke(cmd):
    p = subprocess.Popen(cmd, stdin=PIPE, stdout=PIPE, stderr=PIPE, text=True, bufsize=1)
    p.stdin.write(json.dumps({"jsonrpc":"2.0","id":1,"method":"initialize",
        "params":{"protocolVersion":"2024-11-05","capabilities":{},
                  "clientInfo":{"name":"smoke","version":"1"}}})+"\n")
    p.stdin.flush()
    r,_,_ = select.select([p.stdout],[],[],15)
    ok = r and json.loads(p.stdout.readline()).get("result",{}).get("serverInfo",{}).get("name")
    p.terminate(); p.wait(timeout=3)
    return ok

print("filesystem:", smoke(["npx","-y","@modelcontextprotocol/server-filesystem","."]))
print("git:       ", smoke(["npx","-y","@cyanheads/git-mcp-server"]))
print("serena:    ", smoke(["uvx","serena-agent","start-mcp-server","--project","."]))
PY
```

If a server fails to start, check the command path (`which npx`,
`which uvx`) and that the package is reachable from your network at
first fetch. Local-only does not mean offline: `npx`/`uvx` fetch packages
on first run, then cache them.

First-run timeout note: jcode retries MCP servers with a ~30s backoff
window. First-time `uvx`/`npx` invocations can take longer than that on
cold caches. If a server shows "failed to initialize: Request timeout"
on first `mcp reload`, run it once directly (the smoke script above)
to warm the cache, then `mcp reload` again.

## Per-project override

To enable a different MCP stack for a single repo without touching the
global config, drop a `mcp.json` into `<repo>/.jcode/`. jcode merges
project-level entries over global ones by server name.

Verified 2026-08-16: copying `config/mcp.json.example` to
`.jcode/mcp.json` and running `mcp reload` makes all three recommended
servers (filesystem, git, serena) available in the per-project scope.

See `EXTENSIONS.md` for the full extension surface; MCP servers are
extension point **A4**.