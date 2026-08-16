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
| `git`        | Structured local git ops (log/blame/diff/branch) | `uvx mcp-server-git`                                |
| `serena`     | Code intelligence (symbols, refs, rename)         | `uvx serena-agent start-mcp-server --project <path>` |
| `sqlite`     | Local SQLite query and inspection                | `npx -y mcp-sqlite`                                  |

`puppeteer` (browser automation, local Chromium) is an optional add-on
when you need e2e coverage. Drop it from the stack if you do not.

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

### serena

Use for **code navigation in non-trivial codebases**: finding symbols,
finding all references before a rename, getting a file's structural
overview, replacing a function body by symbol rather than by line range.

Serena uses tree-sitter and **does not require per-language LSP binaries**
to be installed. Supported out of the box: Python, TypeScript, Java, Go,
and a few others. For Rust or other less-covered languages, fall back to
`read` + targeted `grep`.

A serena usage skill lives at `~/.jcode/skills/serena/SKILL.md` (optional,
per-user). It encodes the when-to-use rules and the boundary with
jcode-native `read`/`grep`/`edit`.

### sqlite

Use for **inspecting a local database** during debugging or analysis
without leaving the agent context. Point `--db-path` at the actual file
(e.g., `db.sqlite`, `app.db`, `test.db`).

Do not use sqlite MCP as a substitute for an application-level migration
tool. It is a read/inspect surface, not a migration surface.

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

# 3. Each server connects cleanly
#    (re-run after the first invocation; jcode lazily starts stdio servers)
```

If a server fails to start, check the command path (`which npx`,
`which uvx`) and that the package is reachable from your network at
first fetch. Local-only does not mean offline: `npx`/`uvx` fetch packages
on first run, then cache them.

## Per-project override

To enable a different MCP stack for a single repo without touching the
global config, drop a `mcp.json` into `<repo>/.jcode/`. jcode merges
project-level entries over global ones by server name.

See `EXTENSIONS.md` for the full extension surface; MCP servers are
extension point **A4**.