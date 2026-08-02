#!/usr/bin/env bash
set -u
root="$(cd "$(dirname "$0")/.." && pwd)"
failed=0
while IFS= read -r script; do
  if ! bash -n "$script"; then
    printf 'FAIL: bash -n %s\n' "${script#"$root"/}"
    failed=1
  fi
done < <(find "$root" -type f -name '*.sh' -not -path '*/.git/*' -not -path '*/.jcode/*' | sort)
if ! (cd "$root" && python3 -m unittest discover tests/); then
  failed=1
fi
if (( failed == 0 )); then
  printf 'PASS: all shell syntax checks and Python tests\n'
else
  printf 'FAIL: smoke test suite\n'
fi
exit "$failed"
