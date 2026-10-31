"""Sizes are characters/UTF-8 bytes, never token estimates. No prompt text stored."""
import json
import math
import re
from email.utils import parsedate_to_datetime

RATE_HEADERS = ('Retry-After', 'X-RateLimit-Limit-Requests',
                'X-RateLimit-Remaining-Requests', 'X-RateLimit-Reset-Requests',
                'X-RateLimit-Limit-Tokens', 'X-RateLimit-Remaining-Tokens',
                'X-RateLimit-Reset-Tokens')


def size(value):
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, separators=(',', ':'))
    return {'characters': len(text), 'utf8_bytes': len(text.encode('utf-8'))}


def request_sizes(messages, blocks):
    return {'context_block_sizes': {key: size(value) for key, value in blocks.items()},
            'message_sizes': [{'role': m['role'], **size(m['content'])} for m in messages]}


def content_sizes(content):
    result = {'message_content_size': size(content), 'reasoning_prefix_size': None}
    text = content.strip()
    if '</think>' in text and not text.startswith(('{', '```', r'{\"')):
        end = len(content) - len(content.lstrip()) + text.index('</think>') + len('</think>')
        result['reasoning_prefix_size'] = size(content[:end])
    return result


def numeric_usage(usage):
    result = {}
    def visit(node, path=(), depth=0):
        if not isinstance(node, dict) or depth > 4: return
        for key, value in node.items():
            if len(result) >= 64: return
            if not isinstance(key, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,63}', key): continue
            current = path + (key,)
            if (type(value) is int and value >= 0) or (type(value) is float and value >= 0 and math.isfinite(value)):
                result['.'.join(current)] = value
            elif isinstance(value, dict): visit(value, current, depth+1)
    visit(usage)
    return result or None


def rate_headers(headers, secret=''):
    """Explicit seven-header allowlist, with numeric/duration/HTTP-date values only."""
    result = {name: None for name in RATE_HEADERS}
    for name in RATE_HEADERS:
        value = headers.get(name) if headers is not None else None
        if not isinstance(value, str) or len(value) > 128 or (secret and secret in value): continue
        value = value.strip()
        if any(ord(c) < 32 or ord(c) > 126 for c in value): continue
        numeric = re.fullmatch(r'\d+(?:\.\d+)?', value)
        duration = 'Reset-' in name and re.fullmatch(r'(?:\d+(?:\.\d+)?(?:ms|s|m|h|d))+', value)
        date = False
        if name == 'Retry-After' or 'Reset-' in name:
            try: date = parsedate_to_datetime(value).tzinfo is not None
            except (ValueError, TypeError, OverflowError): pass
        if numeric or duration or date: result[name] = value
    return result
