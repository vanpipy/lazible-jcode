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
| `serena`     | Code intelligence (symbols, refs, rename)         | `uvx serena-agent start-mcp-server --project <path>` |

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

A serena usage skill lives at `~/.jcode/skills/serena/SKILL.md` (optional,
per-user). It encodes the when-to-use rules and the boundary with
jcode-native `read`/`grep`/`edit`.

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
| Find a symbol and its references     | `serena` MCP                                  |
| Run a one-off `git log`              | `bash` (jcode-native)                         |
| Run a structured batch of git ops    | `git` MCP                                     |
| Edit a few lines in one file         | `edit` / `apply_patch` (jcode-native)         |
| Edit by symbol across multiple files | `serena` MCP (with explicit scope prompt)     |
| Query a local SQLite database        | `bash` + `sqlite3` (jcode-native, see above)  |

The rule of thumb: **structured and batched** -> MCP, **small and
one-off** -> jcode-native. MCP is the wrong tool when you would use it
once and then never again.

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