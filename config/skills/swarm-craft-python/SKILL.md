---
name: swarm-craft-python
description: The Python pieces - the idioms, the version floors and the traps, one section per topic. Read in any lane that changes Python code, before it changes it.
---
# The Python pieces

## 0. How to use this Skill

The `swarm-engineering` skill owns the **process** — what a lane does, what it
reports — and the `swarm-craft-shared` Skill owns the **shared pieces** that hold in every
language. This Skill owns the **idioms**: the Python rules that are not generic,
the version floors they carry, and the traps this language has shipped.

Read the piece that matches what you are changing, before you change it. A
brief names the piece: "read §6 of the Python craft before you touch the error
handling". Everything here is checkable — if a rule cannot be checked, treat it
as advice rather than guidance.

## 1. The surface: layout, packaging, the version floor

* `src/` layout, `pyproject.toml` for metadata and dependencies, one
  distribution per package.
* Declare the version floor in `pyproject.toml` and keep the code inside it.
  `X | Y` in an annotation is evaluated at runtime on Python 3.9, so it needs
  either Python 3.10 or `from __future__ import annotations`.
* Run a module as `python -m package.module`, and guard the entry point with
  `if __name__ == "__main__":` so importing the module does not run it.
* Expose command line tools through `console_scripts` entry points, not through
  a hand-written `setup.py`.

## 2. Typing

* Annotate the public surface. Internals may stay looser.
* Use the built-in generics (`list[str]`, `dict[str, int]`) rather than
  `typing.List`; use `X | None` on 3.10+, `Optional[X]` below that.
* `Any` is a hole in the type system. Use it only where you genuinely cannot
  type the boundary, and narrow it immediately.
* `Protocol` describes behaviour without inheritance; `TypedDict` describes a
  JSON-shaped mapping; a dataclass describes a value you own.
* `cast` silences a checker. Without a comment naming the invariant it
  guarantees, it is a lie to the next reader.

## 3. Data modelling

* `@dataclass(frozen=True, slots=True)` for a value object;
  `__post_init__` for validation, so an invalid object cannot exist.
* `NamedTuple` when you want tuple behaviour and named fields.
* `Enum` for a closed set; `StrEnum` on Python 3.11+.
* Never a mutable default argument — `def f(items=[])` shares one list across
  every call. Use `None` and build inside.
* Validate once at construction, not at every use site.

## 4. Collections and the standard library

* `Counter`, `defaultdict`, `deque`, `namedtuple` — reach for them before
  writing the loop.
* `itertools` for the iteration you would otherwise hand-roll; `functools` for
  the wrappers you would otherwise hand-roll.
* `heapq` for a top-k, `bisect` for a sorted insert, `lru_cache` for
  memoisation — always with a bounded cache.
* `pathlib` over `os.path`; `datetime` over `time` when the calendar matters.
* `dict` preserves insertion order. `OrderedDict` only when the ordering
  semantics themselves are the point.

## 5. Iteration and laziness

* A comprehension for building a collection, a generator for streaming a
  sequence. Do not build a list to iterate it once.
* `zip(..., strict=True)` on Python 3.10+ turns unequal lengths into an error
  instead of a silent truncation.
* `enumerate` instead of a manual counter.
* `itertools.groupby` needs the input sorted by the grouping key first — the
  classic trap, and the reason a "counting" result comes out wrong.

## 6. Errors

* Catch the narrowest exception that can actually happen. `except Exception`
  belongs only at a boundary that must not crash the process.
* `raise ValueError("bad row") from err` keeps the cause. `from None` hides it
  deliberately, and only where that is the point.
* A custom exception carries the context it needs; do not use `str(e)` for
  control flow.
* `assert` is not a runtime check. It is removed under `-O`, so it validates
  nothing in production.
* Prefer trying the operation and catching the specific failure over testing a
  condition that another thread can change in between.

## 7. Resources

* `with` for every resource: files, locks, sockets, cursors, temporary
  directories.
* `contextlib.contextmanager` for a small reusable scope; `ExitStack` when the
  number of resources varies.
* `tempfile.TemporaryDirectory()` over `mkdtemp()` — it cleans up after
  itself, including when the body raises.

## 8. Files and paths

* `Path` objects, and `read_text(encoding="utf-8")`. The platform default
  encoding is not a contract.
* Write atomically when a reader may see a partial file: write to a temporary
  file in the same directory, then `os.replace`.
* `newline=""` when reading CSV; write `"\n"` when writing text.
* `Path.write_text` adds no trailing newline. Decide deliberately, because
  every other tool will decide differently.

## 9. The shell and the outside world

* `subprocess.run([...], check=True, capture_output=True, text=True)` — an
  argument list, never a shell string.
* `check=True` turns a non-zero exit into an exception. Handle it where you can
  react to it.
* Pass `env=` explicitly instead of mutating `os.environ` for the whole
  process.

## 10. Time and clocks

* `datetime.now(timezone.utc)`. Store UTC; convert at the edge.
* `time.monotonic()` for a duration; `time.time()` only for a wall-clock stamp.
* Take "now" as an argument so the code can be tested at a fixed moment.

## 11. Concurrency

* `threading` for I/O-bound work in one process; `multiprocessing` for
  CPU-bound work, because of the GIL.
* `asyncio` when there are many concurrent waits. One event loop per process.
* `concurrent.futures` for a simple pool, rather than hand-rolled threads.
* Never share a plain list between threads. Use a queue, or give one owner the
  list and let the others ask.
* A blocking call inside a coroutine blocks the whole loop. Push it to an
  executor.

## 12. Testing

* `unittest` from the standard library, or `pytest`; one test module per source
  module.
* `tmp_path` or `TemporaryDirectory` for the filesystem. A test that writes
  into the repository is a test that fails in someone else's checkout.
* `unittest.mock` at the edges — assert on the call, not on the internals.
* Table-driven cases (`pytest.mark.parametrize`, or `subTest`) for one behaviour
  across many inputs.
* Deterministic: seed the randomness, freeze the clock, keep the network out.
* Assert on the behaviour. If the wording is the contract, pin the wording and
  say in the test why.

## 13. The command line

* `argparse`; one subcommand per verb.
* Exit 0 on success, a documented non-zero on failure, and the message on
  stderr.
* The usage line names the real syntax, optional arguments included.
* Offer `--json` for machine consumers, and keep the human output stable.

## 14. Performance

* `cProfile` or `timeit` before you optimise; a line profiler for the hot
  function.
* `__slots__` for many small instances; `dataclass(slots=True)` on 3.10+.
* Avoid `+=` on a string in a loop — build a list and `''.join` it.
* The big wins are almost always algorithmic, or not doing the work at all.

## 15. Style, naming and docstrings

* PEP 8: `snake_case` for functions and variables, `PascalCase` for classes,
  `UPPER_CASE` for constants.
* One leading underscore marks a name as internal. Two are name mangling, and
  are almost never what you meant.
* A module docstring says what the module is for. A function docstring says
  what the caller must know — the contract, not the type, which the signature
  already carries.
* Keep the docstring next to the code it describes, and keep it true.

## 16. Dependencies and environments

* Declare dependencies in `pyproject.toml`; pin them in the lock file; review
  the lock file diff when it changes.
* One environment per project. Never install into the system interpreter.
* A dependency you cannot explain is a dependency you cannot remove.

## 17. Logging and diagnostics

* `logging.getLogger(__name__)`. Configure logging once, at the entry point —
  never inside a library.
* `logger.exception(...)` inside an `except` block keeps the traceback.
* No `print` in library code.
* `warnings.warn` for a condition the caller can act on; an exception for a
  broken contract.

## 18. Security

* `secrets` for tokens and keys; `os.environ` for configuration. No secret as
  a default value.
* `hmac`/`hashlib` for integrity, and `secrets.compare_digest` for a
  constant-time comparison.
* `ast.literal_eval` instead of `eval`; `json.loads` instead of `pickle` for
  anything untrusted — `pickle` executes code.
* `tempfile` for temporary files, and a restrictive mode when the file holds
  anything sensitive.
* Normalise a path that came from outside and check that it stays under the
  root.

## 19. The common traps

A checklist, not a style guide — each line is a bug that has shipped:

* A mutable default argument.
* A late-binding closure over a loop variable.
* `is` where `==` was meant, and `==` where `is` was meant.
* A local name shadowing a builtin: `id`, `type`, `list`, `input`, `filter`.
* `except:` or `except Exception: pass`.
* `if x == None` instead of `if x is None`.
* Mutating a collection while iterating it.
* A `dict.get(key, expensive())` default, which is evaluated even on a hit.
* `datetime.now()` with no timezone.
* `float` for money, where `decimal.Decimal` belongs.
* Reporting every `OSError` as "not found" — a permission error is not a
  missing file.
* Module-level mutable state shared between tests.
* `if flag == True`.
