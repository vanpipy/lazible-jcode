# testlib.sh : shared by scripts/test and scripts/doc-check
#
# This file is sourced, never executed. It holds the helpers that both test
# scripts need.
#
# It is deliberately NOT part of common.sh. common.sh is what the installer
# and the uninstaller source, and it sets `set -euo pipefail`. The test
# scripts drive commands that are EXPECTED to fail, so they cannot run
# under errexit, and a shared helper must not change how a script that
# sources it behaves.
#
# Sourcing is safe here because $0 is always the entry script, not this
# file. Nothing in this file reads $0.

# shellcheck shell=bash
# The variables below are consumed by whichever script sources this file,
# which shellcheck cannot see. They are deliberately not exported.
# shellcheck disable=SC2034

# The fingerprint of a tree: every path with its type and content.
#
# Content is hashed, not just the size, so a change that keeps the same
# length still shows up. state.json is exactly that case: a different
# timestamp of exactly the same length.
#
# A symlink's TARGET is part of the fingerprint, and so is the content
# behind it. Otherwise a link retargeted at a different file, or a file
# changed behind a link that points out of the tree, would be invisible.
#
# It lives here rather than in either test script because both of them
# use it, and a copy that drifts from its original would let the two
# suites disagree about the same tree.
tree_fingerprint() {
    local root="$1"
    if [[ ! -e "$root" && ! -L "$root" ]]; then
        echo "(absent)"
        return 0
    fi
    ( cd "$root" && find . -mindepth 1 | sort | while read -r p; do
        if [[ -L "$p" ]]; then
            echo "l $p -> $(readlink "$p")"
            if [[ -f "$p" ]]; then
                echo "l $p content $(sha256sum < "$p" | cut -d' ' -f1)"
            elif [[ -d "$p" ]]; then
                echo "l $p dir $(cd "$p" && find . -mindepth 1 -type f -exec sha256sum {} \; | sort | sha256sum | cut -d' ' -f1)"
            fi
        elif [[ -d "$p" ]]; then
            echo "d $p"
        elif [[ -f "$p" ]]; then
            echo "f $p $(sha256sum < "$p" | cut -d' ' -f1)"
        else
            echo "? $p"
        fi
    done )
}
