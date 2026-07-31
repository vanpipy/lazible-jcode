#!/usr/bin/env bash
# jcode-install.sh — install jcode from a lazible-jcode checkout.
#
# Self-contained installer for jcode that lives next to the install-jcode skill.
# Modeled after the upstream jcode.sh/install script, but:
#   - defaults to downloading from GitHub releases (no jcode.sh dependency)
#   - works offline when given --local-artifact
#   - has --dry-run / --help / --from-source / --version flags
#
# Paths after install (mirrors upstream):
#   ~/.jcode/builds/versions/<version>/jcode     (immutable)
#   ~/.jcode/builds/stable/jcode                  (-> immutable)
#   ~/.jcode/builds/current/jcode                 (-> immutable)
#   ~/.local/bin/jcode                            (-> current, launcher)
#
# This file is deliberately idempotent: rerunning is safe.
set -euo pipefail

# ── constants ──────────────────────────────────────────────────────────────────
REPO="1jehuang/jcode"
RELEASE_METADATA_BASE="${JCODE_RELEASE_METADATA_BASE:-https://jcode.sh/releases}"
GITHUB_RELEASES_BASE="https://github.com/$REPO/releases"

# ── flag parsing ───────────────────────────────────────────────────────────────
DRY_RUN=0
FROM_SOURCE=0
LOCAL_ARTIFACT=""
PIN_VERSION=""
INSTALL_DIR="${JCODE_INSTALL_DIR:-$HOME/.local/bin}"
SKIP_PATH_CONFIG=0
SKIP_SERVER_RELOAD=0
NO_TELEMETRY="${JCODE_NO_TELEMETRY:-0}"
JCODE_INSTALL_CONVERSION_ID="${JCODE_INSTALL_CONVERSION_ID:-}"

print_help() {
  cat <<EOF
Usage: $0 [options]

Install jcode. By default downloads a prebuilt binary from GitHub releases and
symlinks it into ~/.local/bin/jcode.

Options:
  --version <v>        Install a specific version (e.g. v0.64.2). Default: latest.
  --install-dir <dir>  Launcher install dir. Default: \$HOME/.local/bin
  --from-source        Build from source instead of downloading. Requires git + cargo.
  --local-artifact <p> Use a local tarball/zip instead of downloading.
  --dry-run            Print the plan without writing anything.
  --skip-path          Do not edit shell rc files to add --install-dir to PATH.
  --skip-server-reload Do not reload a running jcode server.
  --no-telemetry       Skip install-funnel telemetry.
  -h, --help           Show this help and exit.

Environment:
  JCODE_INSTALL_DIR              Override install dir (same as --install-dir).
  JCODE_VERSION                  Pin a version (same as --version).
  JCODE_RELEASE_METADATA_BASE    Override release-metadata base URL.
  JCODE_NO_TELEMETRY=1           Skip install-funnel telemetry.
  DO_NOT_TRACK=1                 Same effect as --no-telemetry.
  JCODE_INSTALL_CONVERSION_ID    If set and a valid UUID v4, persist + report telemetry.

Exit codes:
  0  success
  1  invalid flag / argument
  2  unsupported platform
  3  download / verification failure
  4  source build failure
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version)        PIN_VERSION="${2:-}"; shift 2 ;;
    --install-dir)    INSTALL_DIR="${2:-}"; shift 2 ;;
    --from-source)    FROM_SOURCE=1; shift ;;
    --local-artifact) LOCAL_ARTIFACT="${2:-}"; shift 2 ;;
    --dry-run)        DRY_RUN=1; shift ;;
    --skip-path)      SKIP_PATH_CONFIG=1; shift ;;
    --skip-server-reload) SKIP_SERVER_RELOAD=1; shift ;;
    --no-telemetry)   NO_TELEMETRY=1; shift ;;
    -h|--help)        print_help; exit 0 ;;
    *) echo "error: unknown flag: $1" >&2; print_help >&2; exit 1 ;;
  esac
done

# ── helpers ────────────────────────────────────────────────────────────────────
info() { printf '\033[1;34m%s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m%s\033[0m\n' "$*" >&2; }
err()  { printf '\033[1;31merror: %s\033[0m\n' "$*" >&2; exit "${EXIT_CODE:-1}"; }

sha256_file() {
  file="$1"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$file" | awk '{print tolower($1)}'
  elif command -v shasum >/dev/null 2>&1; then
    shasum -a 256 "$file" | awk '{print tolower($1)}'
  elif command -v openssl >/dev/null 2>&1; then
    openssl dgst -sha256 "$file" | awk '{print tolower($NF)}'
  else
    return 1
  fi
}

valid_release_tag() {
  printf '%s' "$1" | grep -Eq '^v[0-9]+\.[0-9]+\.[0-9]+([+.-][[:alnum:].-]+)?$'
}

run() {
  if [[ "$DRY_RUN" == "1" ]]; then
    printf '[dry-run] %s\n' "$*"
  else
    "$@"
  fi
}

# ── platform detection ─────────────────────────────────────────────────────────
OS="$(uname -s)"
ARCH="$(uname -m)"
IS_TERMUX=0
IS_WINDOWS=0
if [[ -n "${TERMUX_VERSION:-}" ]] || [[ "${PREFIX:-}" = "/data/data/com.termux/files/usr" ]]; then
  IS_TERMUX=1
fi
case "$OS" in
  MINGW*|MSYS*|CYGWIN*) IS_WINDOWS=1 ;;
esac

case "$OS" in
  Linux)
    case "$ARCH" in
      x86_64)  ARTIFACT="jcode-linux-x86_64" ;;
      aarch64|arm64) ARTIFACT="jcode-linux-aarch64" ;;
      *) err "unsupported Linux architecture: $ARCH" ;;
    esac
    ;;
  Darwin)
    case "$ARCH" in
      arm64)   ARTIFACT="jcode-macos-aarch64" ;;
      x86_64)  ARTIFACT="jcode-macos-x86_64" ;;
      *) err "unsupported macOS architecture: $ARCH" ;;
    esac
    ;;
  *)
    if [[ "$IS_WINDOWS" != "1" ]]; then
      err "unsupported OS: $OS (try --from-source if you have git + cargo)"
    fi
    err "Windows is not handled by this script; use scripts/install.ps1 instead"
    ;;
esac

if [[ "$IS_TERMUX" == "1" ]]; then
  warn "Termux detected: make sure 'pkg install glibc patchelf' has been run"
fi

EXE=""
[[ "$IS_WINDOWS" == "1" ]] && EXE=".exe"

# ── version resolution ─────────────────────────────────────────────────────────
VERSION="${PIN_VERSION:-${JCODE_VERSION:-}}"
if [[ -z "$VERSION" ]]; then
  if [[ "$FROM_SOURCE" == "1" ]]; then
    VERSION="master"
  else
    if command -v curl >/dev/null 2>&1; then
      METADATA_VERSION=$(curl -fsSL --retry 2 --connect-timeout 10 \
        "$RELEASE_METADATA_BASE/latest/version" 2>/dev/null | tr -d '\r\n' || true)
      LATEST_URL=$(curl -fsSIL --retry 2 --connect-timeout 10 \
        -o /dev/null -w '%{url_effective}' "$GITHUB_RELEASES_BASE/latest" 2>/dev/null || true)
      case "$LATEST_URL" in
        */releases/tag/*) GITHUB_VERSION="${LATEST_URL##*/}" ;;
        *)                GITHUB_VERSION="" ;;
      esac
      if valid_release_tag "$GITHUB_VERSION"; then
        VERSION="$GITHUB_VERSION"
      elif valid_release_tag "$METADATA_VERSION"; then
        VERSION="$METADATA_VERSION"
        info "GitHub release lookup unavailable; using cached jcode.sh metadata ($VERSION)."
      fi
    fi
  fi
fi
[[ -n "$VERSION" ]] || err "failed to determine latest version"
if [[ "$VERSION" != "master" ]] && ! valid_release_tag "$VERSION"; then
  err "invalid version: $VERSION"
fi
VERSION_NUM="${VERSION#v}"

# ── announce plan ──────────────────────────────────────────────────────────────
info "Plan:"
info "  version:        $VERSION"
info "  os/arch:        $OS / $ARCH"
info "  artifact:       ${ARTIFACT}${EXE}"
info "  install dir:    $INSTALL_DIR"
info "  from source:    $FROM_SOURCE"
info "  local artifact: ${LOCAL_ARTIFACT:-<download from github>}"
info "  dry run:        $DRY_RUN"

if [[ "$DRY_RUN" == "1" ]]; then
  info "(dry-run) no changes made"
  exit 0
fi

# ── paths under ~/.jcode ───────────────────────────────────────────────────────
builds_dir="$HOME/.jcode/builds"
version_dir="$builds_dir/versions/$VERSION_NUM"
stable_dir="$builds_dir/stable"
current_dir="$builds_dir/current"
launcher="$INSTALL_DIR/jcode${EXE}"
bin_name="jcode${EXE}"

run mkdir -p "$INSTALL_DIR" "$version_dir" "$stable_dir" "$current_dir"

# ── download / extract / build ─────────────────────────────────────────────────
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

download_mode=""
downloaded_asset=""
src_bin=""

if [[ -n "$LOCAL_ARTIFACT" ]]; then
  if [[ ! -f "$LOCAL_ARTIFACT" ]]; then
    err "local artifact not found: $LOCAL_ARTIFACT"
  fi
  case "$LOCAL_ARTIFACT" in
    *.tar.gz) download_mode="tar"; downloaded_asset="${ARTIFACT}.tar.gz" ;;
    *)        download_mode="bin"; downloaded_asset="${ARTIFACT}${EXE}" ;;
  esac
  cp "$LOCAL_ARTIFACT" "$tmpdir/jcode.download"
fi

if [[ "$FROM_SOURCE" == "1" ]]; then
  info "Building from source..."
  command -v git   >/dev/null 2>&1 || err "git is required for --from-source"
  command -v cargo >/dev/null 2>&1 || err "cargo is required for --from-source"
  src_dir="$tmpdir/jcode-src"
  if [[ "$VERSION" == "master" ]]; then
    run git clone --depth 1 "https://github.com/$REPO.git" "$src_dir"
  else
    run git clone --depth 1 --branch "$VERSION" "https://github.com/$REPO.git" "$src_dir"
  fi
  run cargo build --release --manifest-path "$src_dir/Cargo.toml"
  src_bin="$src_dir/target/release/$bin_name"
  [[ -f "$src_bin" ]] || err "built binary not found: $src_bin"
else
  if [[ -z "$download_mode" ]]; then
    info "Downloading $VERSION..."
    if ! command -v curl >/dev/null 2>&1; then
      err "curl is required to download jcode"
    fi
    base="$GITHUB_RELEASES_BASE/download/$VERSION"
    found=0
    for candidate in "${ARTIFACT}.tar.gz" "${ARTIFACT}${EXE}"; do
      if curl -fsSL --retry 2 --connect-timeout 10 \
          "$base/$candidate" -o "$tmpdir/jcode.download" 2>/dev/null; then
        case "$candidate" in
          *.tar.gz) download_mode="tar" ;;
          *)        download_mode="bin" ;;
        esac
        downloaded_asset="$candidate"
        found=1
        break
      fi
    done
    [[ "$found" == "1" ]] || err "could not download a prebuilt for $ARTIFACT in $VERSION (use --from-source)"
  fi

  # verify SHA-256 when checksums are available
  if command -v curl >/dev/null 2>&1; then
    expected=""
    for sums_url in \
      "$RELEASE_METADATA_BASE/$VERSION/SHA256SUMS" \
      "$GITHUB_RELEASES_BASE/download/$VERSION/SHA256SUMS"; do
      sums=$(curl -fsSL --retry 2 --connect-timeout 10 "$sums_url" 2>/dev/null || true)
      expected=$(printf '%s\n' "$sums" | awk \
        -v asset="$downloaded_asset" \
        '$2 == asset || $2 == ("*" asset) { print tolower($1); exit }')
      if printf '%s' "$expected" | grep -Eq '^[0-9a-f]{64}$'; then
        break
      fi
      expected=""
    done
    if [[ -n "$expected" ]]; then
      actual=$(sha256_file "$tmpdir/jcode.download") || err "no sha256 tool available"
      [[ "$actual" == "$expected" ]] || err "SHA-256 mismatch ($actual != $expected)"
      info "Verified SHA-256"
    else
      warn "No SHA256SUMS found for $VERSION — skipping integrity check"
    fi
  fi

  if [[ "$download_mode" == "tar" ]]; then
    tar xzf "$tmpdir/jcode.download" -C "$tmpdir"
    src_bin="$tmpdir/${ARTIFACT}${EXE}"
    [[ -f "$src_bin" ]] || err "archive did not contain expected binary: ${ARTIFACT}${EXE}"
  else
    src_bin="$tmpdir/jcode.download"
  fi
fi

# ── install into ~/.jcode/builds/versions/<version>/ ───────────────────────────
run mv "$src_bin" "$version_dir/$bin_name"
run chmod +x "$version_dir/$bin_name"

# Termux ELF patchelf + custom launcher
if [[ "$IS_TERMUX" == "1" ]]; then
  glibc_dir="/data/data/com.termux/files/usr/glibc/lib"
  case "$ARCH" in
    aarch64|arm64) ld="$glibc_dir/ld-linux-aarch64.so.1" ;;
    x86_64)        ld="$glibc_dir/ld-linux-x86_64.so.2" ;;
  esac
  if [[ -x "$ld" ]] && command -v patchelf >/dev/null 2>&1; then
    run patchelf --set-interpreter "$ld" "$version_dir/$bin_name"
    info "Patched Termux glibc ELF interpreter: $ld"
  else
    warn "Termux: 'pkg install glibc patchelf' to fix dynamic linker"
  fi
fi

# ── update stable / current / launcher symlinks ────────────────────────────────
run ln -sfn "$version_dir/$bin_name" "$stable_dir/$bin_name"
printf '%s\n' "$VERSION_NUM" > "$builds_dir/stable-version"
run ln -sfn "$version_dir/$bin_name" "$current_dir/$bin_name"
printf '%s\n' "$VERSION_NUM" > "$builds_dir/current-version"

if [[ "$IS_TERMUX" == "1" ]]; then
  cat > "$launcher" <<EOF
#!/usr/bin/env bash
unset LD_PRELOAD
exec "$stable_dir/$bin_name" "\$@"
EOF
  run chmod +x "$launcher"
else
  run ln -sfn "$current_dir/$bin_name" "$launcher"
fi

# macOS quarantine strip on the freshly-installed binary
if [[ "$OS" == "Darwin" ]]; then
  xattr -d com.apple.quarantine "$version_dir/$bin_name" 2>/dev/null || true
fi

info "Installed: $version_dir/$bin_name"
info "Launcher:  $launcher"

# ── reload any running server (best-effort, like upstream) ─────────────────────
if [[ "$SKIP_SERVER_RELOAD" != "1" ]] && [[ -x "$launcher" ]]; then
  if "$launcher" server reload </dev/null >/dev/null 2>&1; then
    info "Reloaded running jcode server onto $VERSION (if one was active)"
  fi
fi

# ── PATH configuration ─────────────────────────────────────────────────────────
if [[ "$SKIP_PATH_CONFIG" != "1" ]]; then
  here="$(cd "$(dirname "$0")" && pwd)"
  lib="$here/../../scripts/lib/configure_path.sh"
  if [[ ! -f "$lib" ]]; then
    lib=""
  fi
  if [[ -n "$lib" ]]; then
    # shellcheck disable=SC1091
    . "$lib"
    if command -v jcode_configure_path >/dev/null 2>&1; then
      jcode_configure_path "$INSTALL_DIR"
    else
      warn "configure_path.sh not found at $lib — skipping PATH edit"
    fi
  else
    if ! echo "$PATH" | tr ':' '\n' | grep -qx "$INSTALL_DIR"; then
      warn "$INSTALL_DIR is not on PATH. Add it:  export PATH=\"$INSTALL_DIR:\$PATH\""
    fi
  fi
fi

info "✅ jcode $VERSION installed."
info "Run 'jcode --version' or 'jcode run \"say hello\"' to smoke-test."

if [[ -n "$JCODE_INSTALL_CONVERSION_ID" ]] && [[ "$NO_TELEMETRY" != "1" ]] \
   && [[ "${DO_NOT_TRACK:-0}" != "1" ]]; then
  curl -fsS --max-time 2 -H 'Content-Type: application/json' \
    --data "{\"id\":\"$JCODE_INSTALL_CONVERSION_ID\",\"event\":\"install_funnel\",\"version\":\"$VERSION_NUM\",\"source\":\"lazible-jcode\",\"install_method\":\"skill-script\"}" \
    https://telemetry.jcode.sh/v1/event >/dev/null 2>&1 || true
fi