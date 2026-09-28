"""Shared TOML utilities for lazible-jcode scripts.

The standard library has tomllib (read-only) but no writer in 3.11+ : and
tomli_w is unavailable in PEP 668 environments. This module implements a
small, lossy but predictable TOML emitter used by:

  - scripts/use-profile        (merge base + overlay → live)
  - scripts/snapshot-config    (live → repo with masking)

Lossy means: comments are dropped (TOML spec doesn't define how to
preserve them in a parsed dict), and section ordering is normalized to
(scalars → list-of-scalars → subtables → arrays-of-tables). That's fine
for our use : config files in this repo are commit-author-generated, not
machine-edited, so the round-trip never has to preserve human formatting.
"""
from __future__ import annotations


def scalar(v):
    """Format a primitive Python value as a TOML scalar."""
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return repr(v)
    if isinstance(v, str):
        if '\n' in v or '"' in v:
            esc = v.replace('\\', '\\\\').replace('"""', r'\"\"\"')
            return f'"""{esc}"""'
        return f'"{v}"'
    raise TypeError(f'bad scalar: {type(v)}')


def value(v):
    """Format any TOML value: scalar or list-of-scalar."""
    if isinstance(v, (str, int, float, bool)):
        return scalar(v)
    if isinstance(v, list) and all(not isinstance(x, dict) for x in v):
        if not v:
            return '[]'
        return '[' + ', '.join(value(x) for x in v) + ']'
    raise TypeError(f'bad value: {type(v)}')


def is_aot(v):
    """True if v is a list-of-dicts (array-of-tables)."""
    return isinstance(v, list) and len(v) > 0 and all(isinstance(x, dict) for x in v)


def emit_table(d, prefix, out):
    """Recursively emit a table (dict) at the given TOML path prefix."""
    scalars = {}
    subtables = {}
    list_scalars = {}
    for k, v in d.items():
        if isinstance(v, dict):
            subtables[k] = v
        elif is_aot(v):
            subtables[k] = v
        elif isinstance(v, list):
            list_scalars[k] = v
        else:
            scalars[k] = v
    for k, v in scalars.items():
        out.append(f'{k} = {value(v)}')
    for k, v in list_scalars.items():
        out.append(f'{k} = {value(v)}')
    for k, v in subtables.items():
        new_prefix = f'{prefix}.{k}' if prefix else k
        if is_aot(v):
            emit_array(new_prefix, v, out)
        else:
            out.append(f'[{new_prefix}]')
            emit_table(v, new_prefix, out)


def emit_array(name, arr, out):
    """Emit an array-of-tables: name is 'foo.bar' (no brackets)."""
    for item in arr:
        out.append(f'[[{name}]]')
        for k, v in item.items():
            if isinstance(v, dict):
                continue
            out.append(f'{k} = {value(v)}')
        for k, v in item.items():
            if isinstance(v, dict):
                out.append(f'[{name}.{k}]')
                emit_table(v, f'{name}.{k}', out)
            elif is_aot(v):
                emit_array(f'{name}.{k}', v, out)


def emit(data):
    """Emit a full top-level dict as TOML string."""
    top_scalars = {}
    top_lists = {}
    top_tables = {}
    top_aots = {}
    for k, v in data.items():
        if is_aot(v):
            top_aots[k] = v
        elif isinstance(v, dict):
            top_tables[k] = v
        elif isinstance(v, list):
            top_lists[k] = v
        else:
            top_scalars[k] = v

    out = []
    for k, v in top_scalars.items():
        out.append(f'{k} = {value(v)}')
    for k, v in top_lists.items():
        out.append(f'{k} = {value(v)}')
    for k, v in top_tables.items():
        out.append(f'[{k}]')
        emit_table(v, k, out)
    for k, v in top_aots.items():
        emit_array(k, v, out)
    return '\n'.join(out) + '\n'


def merge(base, overlay):
    """Deep-merge: overlay sections override base sections.

    Mutates `base` in place. Lists are replaced wholesale (not merged).
    """
    for k, v in overlay.items():
        if k in base and isinstance(base[k], dict) and isinstance(v, dict):
            merge(base[k], v)
        else:
            base[k] = v
    return base


# --- secret masking (used by snapshot-config) -----------------------------

SECRET_KEYS = {
    'api_key', 'api-key', 'apikey',
    'token', 'bearer',
    'password', 'secret',
    'ntfy_topic', 'telegram_bot_token', 'telegram_chat_id',
    'discord_bot_token', 'discord_channel_id', 'discord_bot_user_id',
    'email_password', 'email_to', 'email_from',
    'jade_relay_token', 'jade_relay_token_id', 'jade_relay_user_id',
    'bing_api_key',
}


def mask_value(v):
    """Mask a single string value if non-empty."""
    if isinstance(v, str) and v and not v.startswith('~') and v != '""':
        return '~/<PLACEHOLDER>'
    return v


def mask_secrets(obj):
    """Recursively replace SECRET_KEYS string values with PLACEHOLDER."""
    if isinstance(obj, dict):
        return {k: (mask_value(v) if k.lower() in SECRET_KEYS else mask_secrets(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask_secrets(x) for x in obj]
    return obj