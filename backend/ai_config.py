"""Read a server-side OpenAI key, including the same source used by ATLAS."""
from pathlib import Path
import os
import re


def read_key_file(path):
    try:
        target = Path(path)
        if target.stat().st_size > 16384:
            return ''
        content = target.read_text(encoding='utf-8-sig').strip()
        keys = set(re.findall(r'sk-[A-Za-z0-9_-]{20,}', content))
        return keys.pop() if len(keys) == 1 else ''
    except (OSError, UnicodeError, ValueError):
        return ''


def resolve_openai_key(values=None):
    values = os.environ if values is None else values
    if values.get('OPENAI_API_KEY_FILE'):
        return read_key_file(values['OPENAI_API_KEY_FILE'])
    for key in ('OPENAI_API_KEY', 'GPT_LUNA_API'):
        value = str(values.get(key) or '').strip()
        if value:
            return value
    return ''
