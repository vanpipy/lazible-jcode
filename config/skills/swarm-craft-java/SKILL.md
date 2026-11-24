---
name: swarm-craft-java
description: The Java pieces - the idioms, the version floors and the traps, one section per topic. Read in any lane that changes Java code, before it changes it.
---

# The Java pieces

## 0. How to use this Skill

The `swarm-engineering` skill owns the **process** — what a lane does, what it
reports — and the `swarm-craft-shared` Skill owns the **shared pieces** that hold in every
language. This Skill owns the **idioms**: the Java rules that are not generic,
the version floors they carry, and the traps this language has shipped.

Read the piece that matches what you are changing, before you change it. A
brief names the piece: "read §6 of the Java craft before you touch the error
handling". Everything here is checkable — if a rule cannot be checked, treat
it as advice rather than guidance.

## 1. The surface: layout, packaging, the version floor

* `src/main/java` and `src/test/java`; `maven` or the `./gradlew` wrapper.
* The floor is declared in the build file: Java 17 (records, `sealed`) or
  Java 21 (`switch` patterns, virtual threads).
* `maven.compiler.release` or a Gradle `toolchain` pins the API level.
* One public class per file, and the file name is the class name.
* Package by feature, not by layer: `com.example.billing` beats
  `com.example.service`.

## 2. Typing

* A raw `List` erases the type argument; the compiler warns.
* `var` for a local whose type is on the right, not where the type matters.
* `Optional<T>` for a return that may be absent — never a field or a
  parameter, and never `get()`; use `orElse`, `orElseGet`, `orElseThrow`.
* No nullness in the type system, unlike TypeScript's `strictNullChecks`.
* `equals` is on the object, `==` is on the reference.
* Primitives (`int`, `long`) over boxed `Integer` — the box adds a null.

## 3. Data modelling

* `record` (Java 16) for a value object: the accessor is `id()`, not `getId()`.
* A record is shallowly immutable — copy a `List` field with `List.copyOf`.
* Validate in the compact constructor, so an invalid record cannot exist.
* `sealed interface` (Java 17) for a closed hierarchy; a Java 21 pattern
  `switch` over it must be exhaustive.
* `enum` for a closed set of constants — not a `String` or an `int`.
* No setters on a value object: a change produces a new value.

## 4. Collections and the standard library

* `Arrays.asList` is fixed-size: `add` throws `UnsupportedOperationException`.
* `Collections.unmodifiableList` is a view, not a copy — the backing list
  still changes.
* `List.of`, `Set.of`, `Map.of` are immutable and reject `null`;
  `List.copyOf` is a copy, `new ArrayList<>(...)` is mutable.
* `ArrayList` by default; `LinkedList` costs a node per element.
* `HashMap` has no iteration order; `ConcurrentHashMap` for a shared map.

## 5. Iteration and laziness

* A stream is lazy: nothing runs until a terminal operation.
* A stream is single-use; a second terminal operation throws
  `IllegalStateException`.
* `stream.toList()` (Java 16) returns an unmodifiable list; `add` throws.
* `IntStream` and `LongStream` for primitives — a `Stream<Integer>` boxes.
* `Stream.iterate(seed, f)` and `Stream.generate(supplier)` are infinite.
* `peek` is for debugging; on a parallel stream it may not run at all.
* `forEach` does not keep order on a parallel stream; `forEachOrdered` does.

## 6. Errors

* Checked exceptions are part of the signature — Java throws where Go
  returns an error and Rust returns a `Result`.
* Catch the narrowest type, and keep the cause in the new exception.
* A `finally` that returns or throws discards the exception in flight.
* `catch (InterruptedException e)` restores the flag:
  `Thread.currentThread().interrupt()`.
* `assert` is off unless the JVM runs with `-ea`.

## 7. Resources

* try-with-resources for every `Closeable` or `AutoCloseable` — it is
  Java's `with`, and the resource closes even when the body throws.
* The resource list closes in reverse order; a close failure is suppressed.
* Declare the resource in the resource list, not in the try body.
* `AutoCloseable` for your own resource; `Closeable` only when it also
  throws `IOException`.
* `close()` must be idempotent and must not throw on the normal path.

## 8. Files and paths

* `Path` and `Files`, never a string a path was glued onto;
  `Path.of("a", "b")` (Java 11) joins the segments.
* `FileReader` uses the platform default charset; `Files.readString` and
  `Files.newBufferedReader` decode UTF-8.
* Atomic write: write to a temp file beside the target, then
  `Files.move(tmp, target, ATOMIC_MOVE, REPLACE_EXISTING)`.
* `Files.exists` is false when it cannot determine, even on a denied read.
* A path from outside: `toRealPath()`, then check `startsWith(root)`.

## 9. The shell and the outside world

* `ProcessBuilder` with a list of arguments — never a shell string.
* A non-zero exit is not an exception — read `process.exitValue()`.
* `Process` implements `AutoCloseable` (Java 9+); try-with-resources closes
  the streams.
* Drain the output stream while the process runs, or the pipe buffer fills
  and it blocks.
* `redirectErrorStream(true)` merges stderr into stdout.
* `System.exit` only in `main`; a library must not exit the process.

## 10. Time and clocks

* `Instant.now()` for a timestamp; it is UTC-based.
* `Clock` for "now": inject it; a test passes `Clock.fixed(instant, UTC)`.
* `LocalDate.now()` uses the default zone — pass a `ZoneId` or a `Clock`.
* Store UTC, convert at the edge; `LocalDateTime` has no zone.
* `Period` for months and years, `Duration` for seconds — a month is not
  30 days.
* `System.nanoTime()` for a duration, `currentTimeMillis()` for a
  wall-clock stamp.

## 11. Concurrency

* `synchronized` for mutual exclusion; `ReentrantLock` when you need
  `tryLock` or a fair queue.
* Lock a private final object, never `this` — it locks the whole instance.
* `volatile` gives visibility, not atomicity: `count++` loses updates.
* `ExecutorService` for a pool (AutoCloseable since Java 19+);
  `CompletableFuture` for composition.
* A `CompletableFuture` nobody joins fails silently — always join it.
* Java 21 virtual threads are the answer to goroutines; Java 17 has none.

## 12. Testing

* JUnit 5: `assertEquals(expected, actual)` — expected first.
* `@TempDir` for the filesystem; never write into the repository.
* `@ParameterizedTest` with `@CsvSource` for one behaviour, many inputs.
* `assertThrows` for the failure path, asserting the type and the message.
* Fake at the edge — a fixed `Clock`, a fake server — not the class under
  test.
* Run `mvn test` or `./gradlew test` in the pipeline; a test outside it is
  not a test.

## 13. The command line

* No CLI parser in the standard library: use picocli or commons-cli, one
  subcommand per verb.
* `public static void main(String[] args)` is the entry point.
* Exit 0 on success, a documented non-zero on failure, `System.exit(code)`
  only in `main`.
* Diagnostics on stderr, results on stdout — one diagnostic per failure.
* Convert the arguments at the boundary, into a typed record.

## 14. Performance

* Measure before you change: JFR for a profile, JMH for a microbenchmark.
* JMH warms the JIT up before it measures; a hand-rolled loop measures the
  warm-up.
* `+=` on a `String` in a loop allocates on every pass — use
  `StringBuilder` or `String.join`.
* `ArrayList<Integer>` boxes every element; `IntStream` and `int[]` do not.
* The big win is complexity — an O(n²) loop beats constant-factor tuning.

## 15. Style, naming and documentation comments

* `camelCase` for methods and fields, `PascalCase` for types,
  `UPPER_SNAKE_CASE` for `static final` constants.
* No underscores in method or field names, except the constants.
* Javadoc on the public surface: the parameters, the return value, the
  failure modes.
* `@param`, `@return`, `@throws` on the public surface; doclint must pass.
* A comment explains why; the code says what. Delete commented-out code.

## 16. Dependencies and environments

* Declare in `pom.xml` or `build.gradle` and pin every version, plugins
  included.
* The build file is a program, unlike `pyproject.toml` or `go.mod`.
* `./gradlew`, never a system `gradle`; commit the wrapper (`gradlew`,
  `gradlew.bat`).
* Maven resolves by nearest wins, Gradle by highest — check the tree.
* Test-only dependencies belong in the test scope.
* A dependency you cannot explain is a dependency you cannot remove.

## 17. Logging and diagnostics

* One logging facade: SLF4J with a backend, or `java.util.logging`.
* `LoggerFactory.getLogger(X.class)` per class, never a string literal.
* Configure the appender once, at the entry point.
* Pass the throwable, not its message: `logger.error("cannot close", e)`.
* Parameterised messages: `logger.debug("id={}", id)`, never
  `logger.debug("id=" + id)`.
* No `System.out.println` in library code, and no `printStackTrace()`.

## 18. Security

* Secrets come from the environment or a secret store, never from source.
* `SecureRandom` for tokens and keys; `new Random()` is not a secret.
* `MessageDigest.isEqual` for a constant-time comparison.
* `ObjectInputStream.readObject` executes code — it is Java's `pickle`.
* XML: disable DTDs and external entities, or you have an XXE hole.
* SQL: `PreparedStatement` with placeholders, never a concatenated string.
* A path from outside: normalise it and check it stays under the root.
* Do not log secrets, tokens or whole payloads.

## 19. The common traps

A checklist, not a style guide — each line is a bug that has shipped:

* `==` on strings instead of `equals`.
* `equals` without `hashCode` — they travel together.
* `Integer` compared with `==`: true up to 127, false from 128.
* A getter handing out a mutable collection.
* A `finally` that returns or throws, swallowing the exception in flight.
* `String` concatenation in a loop.
* `LocalDate.now()` with the default time zone.
* `SimpleDateFormat` shared between threads.
* A mutable `static` field, shared across every test.
* A resource opened inside a try body, so nothing closes it.
