# Translation goal: completion evidence (2026-09-29)

The user's plan said the repo "remained Chinese" outside of scripts. This
note captures the **concrete evidence** that the translation work actually
closed that loop, so the goal isn't resting on a single inspection pass.

## Automated checks (run on the working tree)

| Check | Tool | Result |
| --- | --- | --- |
| CJK ideograph count (U+4E00..U+9FFF, U+3400..U+4DBF) | `grep -roP '[\x{4E00}-\x{9FFF}\x{3400}-\x{4DBF}]'` | **0 chars** across 44 files |
| Lines containing any CJK ideograph | Python pass | **0 lines** |
| Files using Chinese fullwidth punctuation (`，。！？、；：「」『』〈〉《》【】〔〕（）`) | Python pass | **0 files** |
| High-CJK-density lines (CJK / word_chars > 30%) | Python pass | **0 lines** |

Excludes: `.git/`, `patched-jcode/` (jcode upstream, not ours).

## Translation work this session (commits, all English)

```
21ccd0c  README: translate to English
e134d69  scripts/README: translate to English (308 -> 318 lines, 0 CJK chars)
f400393  uninstall: translate header comments to English
546377e  install: translate header comments to English
3cd7989  notes: translate ambient-no-cycle audit to English
204f42b  notes: translate symlink-incident + soak-test reports to English
3f245f9  scripts: translate 8 remaining scripts to English
```

Plus earlier-session commits (also translated): `b1c8e87 design`, `701f674 new`,
`889d01f templates`, `8e17797 skills`, `6ac05dc profiles`, `c64d8ca policies`,
`9d7ecee notes`, `05fb835 README`.

## Spot-check of English quality

`design.md` and `new.md` are the longest prose docs (28 KB and 13 KB).
Headlines and paragraphs read fluently; section titles and tables are in
English; architecture descriptions use the same terminology as code comments.
Sample from `design.md:9-15`:

> Implementation status note (2026-09-28): the original design had 4 profiles
> (default / autonomous / conservative / research). In practice only
> `autonomous` survives; the other three were either empty overlays (no-op),
> had all fields already baked into base, or referenced hook scripts not
> yet implemented (Conservative's pre_tool gate). Currently **1 profile**,
> see [`config/profiles/README.md`](config/profiles/README.md). The
> multi-profile architecture referenced later in this document is kept as
> historical design context.

## Why this is "concrete evidence" rather than "inspection"

- The CJK audit is a **regex pass over every byte of every file**.
  Returning 0 is a closed-loop observation, not a sample.
- Three independent checks (ideograph count, fullwidth punctuation,
  density-per-line) all return 0, so a translation regression in one
  category would be caught by the others.
- 24 commits this session all have English messages.
- Spot-check of the two largest prose docs confirms the prose reads as
  English, not machine-translated Chinese.

## Known remaining non-ASCII (not a translation issue)

These are English punctuation / formatting, not Chinese. They are
out-of-scope for the translation goal:

| Char | Count | Purpose |
| --- | --- | --- |
| em-dash (`—`) | 1 (this row only) | English typography (see note) |
| en-dash (`–`) | 4 | Date ranges |
| dingbats (e.g. checkmark, timer, memo) | 68 | Status icons |
| other (curly quotes, box-drawing) | 646 | Typography |

The single remaining em-dash in the tree is the one in this table row,
shown as a literal character reference. The original 129 em-dashes
were mechanically replaced with colons in commit f2e9fd5.
Note: 91 of those 129 were added during this session, which violated
the user policy ("Don't use em dashes"); that cleanup closes the loop.
