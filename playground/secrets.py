"""Exact credential redaction at output boundaries; credentials stay environment-only."""
import os


def redact_secrets(value):
    secret = os.environ.get('OPENROUTER_API_KEY')
    def walk(item):
        if isinstance(item, str):
            return item.replace(secret, '[REDACTED]') if secret else item
        if isinstance(item, dict):
            return {walk(k): walk(v) for k, v in item.items()}
        if isinstance(item, (list, tuple)):
            return [walk(v) for v in item]
        return item
    return walk(value)
