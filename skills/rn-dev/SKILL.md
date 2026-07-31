---
name: rn-dev
description: Universal React Native + Android development guide. Covers modular 3-tier architecture, debug gates, toolchain, pre-commit CI gates, Detox E2E, build variants, and reusable patterns. Use when user requests RN / native / Android / TypeScript / modularization / business modules / add-to-cart / pricing / adding dependencies / writing components / hooks / tests / debugging / building / committing / refactoring / fixing / migration.
skill-type: domain
version: 4.0
type: skill
skill-role: guidance
---

# rn-dev

Universal React Native + Android development guide. Apply on any RN project; project-specific conventions live in AGENTS.md.

## When to Use

- Writing or refactoring RN/TypeScript code (modules, views, hooks, components)
- Adding npm dependencies, especially native modules
- Designing or migrating to 3-tier module architecture
- Writing unit tests or Detox E2E
- Debugging build failures, HMR issues, native module problems
- Pre-commit checks or troubleshooting CI failures

## Slash Command

```
/rn-dev <task>
```

Examples: `/rn-dev add unit tests for the payment module` · `/rn-dev migrate business module to 3-tier pattern`

---

# 1. Project Identification

Quick scan (in order):

1. `package.json` → RN / React / TS versions, packageManager field
2. `android/gradle.properties` → `newArchEnabled`
3. `android/` and/or `ios/` presence → target platforms
4. Debug gate constants file (typically `app/config/env.ts`) → 4 constants: `IS_DEBUG`, `SHOULD_LOG`, `IS_DEV_MODE`, `__DEV__`
5. Test entries: `npm test`, `npm run e2e:*`, Detox config
6. Module directory: `app/modules/<domain>/` or `src/domains/<domain>/`

---

# 2. Modular 3-Tier Architecture

## 2.1 Structure

```
┌─────────────────────────────────────────────────────────────┐
│  index.ts        Public API (singleton + read-only hook)    │
├─────────────────────────────────────────────────────────────┤
│  store.ts        State mirror (zustand)                     │
│                  Mirrors class private state; persists      │
├─────────────────────────────────────────────────────────────┤
│  class.ts        Business source of truth (OO class)        │
│                  Private state + invariants + methods       │
└─────────────────────────────────────────────────────────────┘
```

| File | Responsibility | Hard Constraints |
|------|----------------|------------------|
| `class.ts` | Private state + business methods + invariants | **MUST NOT** import `react`, `react-native`, view layer, Toast, or Navigation |
| `store.ts` | Mirror class state via `subscribe → setState` | **Zero exports**; only side effect is hydrating the class |
| `index.ts` | Singleton + read-only hook + (optional) types | **Expose only 2-3 symbols**: `{xxx}` singleton + `useXxx<T>(selector)` hook; no mutation API |

## 2.2 HMR-Safe Singleton

```ts
const KEY = Symbol.for('@<module>/class');
const X = (globalThis as any)[KEY] as ClassX | undefined
  ?? ((globalThis as any)[KEY] = new ClassX());
export {X as <name>};
```

Plain `export const x = new Xxx()` instantiates multiple times under HMR, corrupting state.

## 2.3 Singleton Method Invocation

```ts
import {shopcart} from '@/modules/shopcart';
shopcart.addToCart(item);            // ✅ this is safe
const {addToCart} = shopcart;        // ❌ destructuring loses this
shopcart.addToCart.bind(shopcart);   // ❌ forbidden
```

Destructuring an ES class method drops `this`. **Always call through the singleton.**

## 2.4 Dependency Direction (One-Way, Acyclic)

```
Views (views + components)
    ↓
View Models (hooks)
    ↓
Modules (modules/<domain>)
    ↓
Infrastructure (packages/pillars-*, lib)
```

`class.ts` MUST NOT depend upward; `store.ts` only mirrors, never invokes business methods.

## 2.5 Rich Subdirectory Structure

Beyond the basic triplet, complex modules may add:

| Subdirectory | Purpose |
|--------------|---------|
| `ports/` | Dependency-inversion boundary (HttpClient / Tracker / Repository interfaces) |
| `creation/` | Command side (create / update / cancel) |
| `ops/` | Operation side (parallel to creation) |
| `query/` | Read-only queries |
| `cache.ts`, `cart-switch.ts`, `switch.ts` | Tightly-coupled helpers |

Core triplet (`class.ts` / `store.ts` / `state.ts` / `index.ts`) is always present; extras are optional and **must not invert-depend on the core**.

---

# 3. State & Persistence

## 3.1 Mirror + Persist + Hydration

```ts
const useStore = create<XxxMirror>()(
  persist(
    () => ({state: xxx.snapshot()}),
    {
      name: '<module>_vN',                              // versioned; bump forces reset
      storage: createJSONStorage(() => mmkvStorage('<module>')),
      skipHydration: true,                              // hydrate manually after infra ready
      onRehydrateStorage: () => rehydrated => {
        if (rehydrated?.state) xxx.hydrate(rehydrated.state);
      },
    },
  ),
);

xxx.subscribe(next => useStore.setState({state: next}));
```

Call `persist.rehydrate()` explicitly from `bootstrap` after infrastructure is ready.

## 3.2 Read-Only Hook with Selector Fallback

```ts
const FALLBACK: XxxState = {/* stable reference */};
export function useXxx<T>(selector: (s: XxxState) => T): T {
  return useStore(s => selector(s.state ?? FALLBACK));
}
```

The fallback must be a stable reference; otherwise hydration-edge `undefined` causes Object.is inequality and infinite re-renders.

## 3.3 Cross-Module Snapshot Access

When a business method needs data from another module, call its singleton's `snapshot()` (NOT the hook):

```ts
const coupons = otherModule.snapshot().slots[idx]?.coupons ?? [];
```

`snapshot()` returns a deep copy safe for mutation; `getState()` returns a shared reference. Cross-module boundaries always use `snapshot()`.

---

# 4. Debug Gates (4-Constant Template)

| Constant | Typical Formula | Meaning |
|----------|-----------------|---------|
| `IS_DEBUG` | `ENV ∈ debug env set` | **Master gate**: DebugFAB / DevBridge / Mock / testID injection |
| `SHOULD_LOG` | `ENV ∉ release env set` | Console + diagnostic logs (prod: error only) |
| `IS_DEV_MODE` | alias of `IS_DEBUG` | — |
| `__DEV__` | Metro `--dev true` | Metro internal only; do not depend on this in business code |

**Truth-table pattern** (any project):

| ENV | IS_DEBUG | SHOULD_LOG |
|-----|----------|------------|
| dev/test/uat | ✅ | ✅ |
| pre/prod | ❌ | ❌ |

**Integration rules**:

1. Business code reads the project's debug constants; **never** read `__DEV__` or `ENV` directly
2. New debug entry → register on DevBridge (programmatic) **and** DebugFAB menu (UI)
3. `class.ts` and infrastructure packages MUST NOT read debug constants; let App layer inject
4. DevBridge handlers must be idempotent
5. Production logs: only `error` level; others silenced when `SHOULD_LOG=false`

---

# 5. User Feedback

All `Alert.alert` / `Modal.alert` calls in business code are **forbidden**. Route through `notify`:

| API | Use Case | Underlying |
|-----|----------|------------|
| `notify.info(msg)` | Single button, default title "Notice" | `Modal.alert('Notice', msg)` |
| `notify.warn(title, msg)` | Single button, semantic title | `Modal.alert(title, msg)` |
| `notify.error(msg)` | Transient error, auto-dismiss | `showToast(msg, 'long')` |
| `notify.confirm(opts)` | Two buttons; `onConfirm` may be async | `Modal.confirm(...)` |

Wrap calls with `useNotifyGuard` to prevent rapid-fire duplicate toasts.

When multiple slots fail concurrently, merge into a single `notify.error(failures[0])` to avoid toast stacking.

---

# 6. Toolchain

| Concern | Tool | Notes |
|---------|------|-------|
| State management | `zustand` + `react-native-mmkv` | MMKV is 30x faster than AsyncStorage; bridge via `mmkvStorage('<domain>')` |
| Network | `axios` + interceptors | Request signing / response unwrap / error normalization; **`initApi()` must register first, unconditionally** |
| Path aliases | `babel-plugin-module-resolver` | `@/` → `src/`, `@pos/<pkg>` → monorepo packages |
| E2E | `detox` 20.x | Happy-path runs against **real BFF**; mocks only for edge cases |
| Linting | `eslint` + `eslint-plugin-local-rules` | Project-specific local rules |
| Formatting | `prettier` | JSON / MD / YAML only |
| Pre-commit | `husky` + `lint-staged` | Auto-runs `eslint --fix` on staged `.ts`/`.tsx` |
| Commits | `@commitlint/cli` + `@commitlint/config-conventional` | Enforced by Husky hook |

**Babel module-resolver example**:

```js
plugins: [
  ['module-resolver', {
    root: ['./'],
    alias: {'@': './src', '@pos/<pkg>': './packages/<pkg>'},
  }],
],
```

Restart Metro after adding new aliases.

---

# 7. Native Dependency Pitfalls

## 7.1 Transitive Native Dependencies (Pitfall #1)

After installing any package with native code, **inspect `package.json#dependencies`** and add every native sub-dependency as a direct root dependency. RN autolinking does NOT process transitive deps.

Example: installing `react-native-vision-camera` requires `react-native-worklets-core`, `react-native-reanimated`, etc. all pinned in root `package.json`. Then `cd android && ./gradlew clean`.

## 7.2 RN 0.79.x CMake Pinning (Pitfall #2)

| Package | Pin Version | Reason |
|---------|-------------|---------|
| `react-native-quick-base64` | `2.2.2` | RN 0.79.x CMake macro signature |
| `react-native-quick-crypto` | `1.1.3` | Same |

Lift these pins after upgrading to RN 0.80+.

## 7.3 Bootstrap Independent try/catch (Pitfall #3)

Every init step in `bootstrap.ts` MUST have its own `try/catch`. **Network/HTTP initialization MUST run unconditionally** (never inside a catch branch):

```ts
// ✅ Correct
try { await initAuth(); } catch (e) { logger.error(e); }
try { await initKvStore(); } catch (e) { logger.error(e); }
await initApi();   // unconditional

// ❌ Wrong
try {
  await initAuth(); await initKvStore(); await initApi();
} catch (e) { logger.error(e); }
```

## 7.4 tsc Stdio Injection (Pitfall #4)

In AI agent environments, tsc interprets file descriptor numbers (`'1'`, `'2'`) as paths. Always redirect:

```bash
node_modules/.bin/tsc --noEmit > /tmp/tsc_out.txt \
  && echo "✓ No TS errors" || cat /tmp/tsc_out.txt
```

## 7.5 Native Library Conflicts

Symptom:

```
2 files found with path 'lib/.../libhermestooling.so'
```

**Cause**: RN main version duplicates Android test native libs with some third-party libraries (Vision Camera, worklets-core).

**Fix**: Cannot rely on app-level `packaging.jniLibs.pickFirsts`. Must keep `pickFirsts` configuration in root `android/build.gradle` `mergeDebugAndroidTestNativeLibs` task.

---

# 8. Testing & CI Gates

## 8.1 Pre-Commit Three Gates

```bash
# 1. TypeScript (Pitfall #4 redirect)
node_modules/.bin/tsc --noEmit > /tmp/tsc_out.txt && echo "✓" || cat /tmp/tsc_out.txt

# 2. ESLint (errors only)
npm run lint 2>&1 | grep " error " | grep -v "warning"

# 3. Jest (--no-coverage for speed)
node_modules/.bin/jest --no-coverage
```

| Check | Pass Condition |
|-------|----------------|
| TypeScript | No **new** errors (pre-existing must be documented, not increasing) |
| ESLint | No **new** errors |
| Jest | No **new** failures |

`--no-verify` is forbidden. Feature commits and CI fixes must not share a commit.

## 8.2 Unit Test Coverage ≥ 90%

```
Effective Coverage = Covered Paths / Total Logical Paths (including hidden)
```

| Range | Verdict | Action |
|-------|---------|--------|
| 100% | Complete | Pass |
| 90-99% | Acceptable | Document gaps for follow-up |
| < 90% | Fail | **Add tests before commit** |

**Hidden-path checklist**: each truth-table combo in `a && b`, `switch` `default`, `null/undefined/''` boundaries, async `await` throws, catch inside `try/catch` callbacks.

## 8.3 Detox `isHardenedBuild` Gating (4 Locations)

| File | Gated Content |
|------|---------------|
| `android/app/build.gradle` | Detox + AppCompat test dependencies |
| `android/build.gradle` | `mergeDebugAndroidTestNativeLibs.pickFirsts` |
| `android/settings.gradle` | Detox local Maven source |
| `scripts/postinstall.js` | Detox must not be in required deps |

When `isHardenedBuild = true` (pre/prod), Detox is entirely skipped.

## 8.4 Selector / POM Rules

- One POM per screen; selectors clustered at top
- Use stable `by.id(...)` only; **`by.text()` forbidden**
- Prefer explicit `testID` in source; fall back to `accessibilityLabel`-derived IDs

## 8.5 Real BFF vs Mock BFF

- Happy-path business flows **must** use real BFF
- Mocks only for edge cases (timeout / 5xx / malformed envelope)
- Use `X-E2E-Source: detox` header for routing / log differentiation
- Prefer `uat` over `dev`/`test` as the e2e primary environment (closest to prod, schema frozen, infra consistent)

---

# 9. Build Variants

| ENV | buildType | Signing | Backend | Detox |
|-----|-----------|---------|---------|-------|
| dev | Debug | debug.keystore | dev-gateway | ✅ |
| test | Debug | debug.keystore | test-gateway | ✅ |
| uat | Debug | debug.keystore | uat-gateway | ✅ |
| pre | Release | release.keystore | pre-gateway | ❌ |
| prod | Release | release.keystore | prod-gateway | ❌ |

Universal APK only for debug envs; release envs emit single-arch splits (arm64-v8a / x86_64). Version format: `{env}-build.{BUILD_NUMBER}` (uniquely incremented per CI build).

---

# 10. Commit Style

- **Total ≤ 3 lines** (subject + body + footer)
- Subject: `{type}({scope}): …` — one line stating what + why
- Body: ≤ 2 lines for motivation / side effects
- Detailed context goes in PR description / issue, not commit body
- Conventional commits enforced via commitlint + Husky

---

# 11. Anti-Patterns

| ❌ Don't | ✅ Do |
|----------|-------|
| `Alert.alert(...)` directly in business code | Use `notify.info/warn/error/confirm` |
| `const {method} = x; method()` | `x.method()` (this-safe) |
| `import {create} from 'zustand'` in `class.ts` | Use `store.ts`; class holds methods only |
| Export `useXxxStore` / `getXxxState()` | Read-only `useXxx<T>(selector)` |
| Read `__DEV__` / `ENV` directly | Read project debug constants |
| `by.text(...)` selector | `by.id(...)` testID |
| Mock BFF for happy-path | Real BFF |
| One `try {} catch {}` for all init steps | Each step independent; network init unconditional |
| `tsc --noEmit 2>&1` | Redirect to `/tmp/tsc_out.txt` |
| Manually edit `package-lock.json` | Let `npm install` manage it |
| Commit with < 90% coverage | Add tests or document gaps |
| `commit --no-verify` | Pass all three gates first |
| Comments explaining WHAT / history | No comments by default |
| class extends Component | Functional + Hooks |
| Default-export components | `export function` named exports |

---

# 12. Common Pitfalls (10)

| # | Symptom | Root Cause | Fix |
|---|---------|------------|-----|
| 1 | Native package installed but doesn't work | RN autolinking doesn't process transitive deps | Inspect package deps; add native sub-deps to root |
| 2 | `quick-base64` / `quick-crypto` link failure | RN 0.79.x CMake macro compatibility | Pin `2.2.2` / `1.1.3` |
| 3 | One init failure breaks all subsequent inits | Top-level `try/catch` in bootstrap | Per-step try/catch; network init unconditional |
| 4 | tsc reports paths `'1'`/`'2'` as errors | AI env: file descriptor numbers as paths | `tsc ... > /tmp/out.txt` |
| 5 | Native package installed but inactive | Autolinking didn't rebuild | `./gradlew clean` + rebuild |
| 6 | E2E: `adb: no devices/emulators found` | adb not connected | `adb devices` to verify |
| 7 | `Cannot find module 'detox'` | dev deps not installed | `npm ci --include=dev` |
| 8 | `2 files found with path 'libhermestooling.so'` | Vision Camera + worklets + RN conflict | Keep `mergeDebugAndroidTestNativeLibs.pickFirsts` |
| 9 | Release build fails on Detox | `isHardenedBuild` gate broken | Run gating test; check 4 gate locations |
| 10 | `notify.xxx` triggers repeatedly | Missing `notifyGuard` | Wrap with `useNotifyGuard` |

---

# 13. Pattern Library

## 13.1 Stateful Multi-Slot Module

**Use case**: Cart, multi-session, multi-tab — "multiple isomorphic instances" state.

```ts
const N = 4;                              // slot count
interface Slot { items: Item[]; dirty: boolean; /* ... */ }
interface State { slots: Slot[]; activeIndex: number; }
```

**Universal invariants**:
- Empty slot ⇒ no external identifier (order code, serial number)
- Non-empty slot ⇒ external identifier is stable (same session, not reset)
- Any change ⇒ `dirty=true`, triggers sync watcher

**API shape**:
```ts
class XxxImpl {
  add(item: Item, targetIndex?: number): boolean;
  addMany(entries: Item[], targetIndex?: number): boolean;
  addById(id: string): boolean;                    // lookup-dependent
  remove(index: number, id: string): {ok: boolean; pendingCleanup: string | null};
  changeQty(index: number, id: string, qty: number): {ok: boolean; pendingCleanup: string | null};
  clear(index: number): boolean;
  moveItem(from: number, to: number, id: string): boolean;
  markClean(index: number): boolean;
}
```

**Test coverage**: out-of-bounds index, empty items, duplicate IDs, quantity accumulation, invariants, indirect-entry lookup failure → `false` (no throw).

## 13.2 Persistence Snapshot + Reverse Projection

**Use case**: "Sold-out item still settleable in cart" / offline-readable business rules.

```ts
function captureSnapshot(item: Item): Snapshot { /* 1:1 field copy */ }
function fromSnapshot(s: Snapshot): Item { /* tolerant of legacy fields */ }
```

- On add: `captureSnapshot` → store in cart slot's snapshot field
- On change/remove: use `fromSnapshot(snapshot)` for validation (no runtime lookup)
- `compositeKey = domainKey@variantKey` (e.g. `item_code@measure_id`) to distinguish same entity with multiple variants
- On schema change: bump `name` version in persist config to force reset

## 13.3 BFF-Driven Reactive Pipeline

**Use case**: Cart / form changes trigger server-side pricing / recommendation / risk.

```ts
function useXxxWatcher(): void {
  // 1. Subscribe to multiple stores
  const triggers = useStoreA() + useStoreB() + useStoreC();
  const debounceRef = useRef(setTimeout);
  const lastHashRef = useRef<Map<K, string>>();

  useEffect(() => {
    debounceRef.current && clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      const jobs = compute(triggers);            // derive N requests
      await Promise.allSettled(jobs.map(async j => {
        try {
          const result = await callBff(j.request);
          store.commitSuccess(j.key, result);
        } catch (e) {
          lastHashRef.current.delete(j.key);      // failure → retryable
          store.commitError(j.key, e);
        }
      }));
    }, DEBOUNCE_MS);
  }, [triggers]);
}
```

**Invariants**:
- **Dedup**: hash unchanged → no re-request
- **Retryable failure**: on error, delete hash so next change retries automatically
- **Non-blocking**: skip global loading overlay; merge multi-slot failures into one toast
- **Concurrency-safe**: `beginCalc(key) → seq` serializes; stale responses discarded

## 13.4 Mutual Exclusion UI

**Use case**: Multiple discounts mutually exclusive (promotion vs coupon); let user choose.

```ts
function useMutualExclusionPrompt(index: number): void {
  const isExclusive = useXxx(s => s.slots[index]?.result?.isExclusive === true);
  const resolution = useXxx(s => s.slots[index]?.resolution ?? null);
  const promptedRef = useRef<string>('');

  useEffect(() => {
    if (!isExclusive || resolution !== null) return;
    const key = `${index}:${seq}`;
    if (promptedRef.current === key) return;     // dedupe within same calc
    promptedRef.current = key;

    void notify.confirm({
      title: 'Choose One',
      message: 'A vs B: pick one',
      confirmText: 'Pick A',
      cancelText: 'Pick B',
      onConfirm: () => store.resolve(index, 'A'),
      onCancel: () => store.resolve(index, 'B'),
    });
  }, [index, isExclusive, resolution, seq]);
}
```

Composition changes auto-reset resolution so user re-prompted with fresh options.

## 13.5 Multi-Source Pure Function Composer

**Use case**: Order creation merges "items + member + coupons + promotions" into BFF body DTO.

```ts
function compose<TIn, TOut>(input: TIn): TOut {
  const out = [
    ...section1(input),    // skip zeros / missing IDs
    ...section2(input),    // same
    section3(input),       // single entry, may be null
  ].filter(notNull);
  return out;
}
```

**Design principles**:
- **Pure**: no React / IO / SQLite dependencies
- **Non-mutating**: returns new array / object
- **Skip rules**: zero discount / missing ID / equivalent pricing → omit
- **Fixed output order**: deterministic for BFF parsing / test assertions
- **Format normalization**: BigDecimal `.toFixed(2)` strings, `String(id)` for IDs
- **Generic + non-cast**: accept minimal field set, caller passes compatible types

## 13.6 Startup-Time Explicit Dependency Injection

**Use case**: Business module needs external deps (HTTP client / tracker / repository) but stays unit-testable.

```ts
// class.ts
export function bindXxxRepository(repo: XxxRepository): void {
  (globalThis as any)[Symbol.for('@xxx/repo')] = repo;
}
function getRepo(): XxxRepository {
  return (globalThis as any)[Symbol.for('@xxx/repo')];
}

// bootstrap.ts (in init order)
import {bindXxxRepository} from '@/modules/xxx';
import {createHttpRepo} from '@/infra/xxx';
bindXxxRepository(createHttpRepo(getApi()));
```

Dependency inversion lets the module stay decoupled from concrete implementations; tests can inject mock repos.

---

# 14. Tips

- **Check public API first**: `cat <module>/index.ts` to see exposed symbols before modifying
- **Dependency direction mantra**: views → hooks → modules → infrastructure
- **Three-commit rule**: `feat` (feature) + `test` (coverage) + `fix` (spec pass) — one each, never mixed
- **Debug gate checklist**: 4 locations — app entry / DevBridge / DebugFAB / test code
- **BigDecimal always string**: `.toFixed(2)` + `String(id)`; never trust JS Number for money
- **Persist schema change = bump version**: avoids legacy snapshots breaking new schema
- **Babel alias added → Metro restart**: otherwise alias doesn't take effect
- **Bootstrap init order**: auth → kv → api (unconditional) → tracker → business bindings
- **Bootstrap routing: `./gradlew clean`**: after native package install; otherwise stale autolinking
- **Multi-repository cross-refs**: `<repo-prefix>/<path>` format for multi-repo projects
- **Swarm Mode**: when a task touches ≥ 3 modules with independent subtasks (cross-package refactor, parallel audit, split into parallel PRs), **escalate to `/auto-swarm-planner`**. Do not spawn workers yourself — that is the planner's job. Each worker spawned by the planner still follows this rn-dev skill inside its own scope.