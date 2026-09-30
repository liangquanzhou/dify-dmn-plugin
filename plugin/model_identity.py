"""RFC 8785 content identity; separate expected digest avoids self-reference."""
import hashlib
import hmac
import re
from typing import Any

import rfc8785

from evaluator import TableError


def model_identity(table: dict[str, Any], expected_sha256: Any = None) -> str:
    if expected_sha256 is None:
        expected = ''
    elif isinstance(expected_sha256, str):
        if len(expected_sha256) > 256:
            raise TableError('INVALID_INPUT', '$.expected_sha256', 'Expected SHA-256 input exceeds the 256-character configuration limit')
        expected = expected_sha256.strip().lower()
    else:
        raise TableError('INVALID_INPUT', '$.expected_sha256', 'Expected SHA-256 must be a 64-character hexadecimal string or empty')
    if expected and re.fullmatch('[0-9a-f]{64}', expected) is None:
        raise TableError('INVALID_INPUT', '$.expected_sha256', 'Expected SHA-256 must be a 64-character hexadecimal string or empty')
    try:
        canonical = rfc8785.dumps(table)
    except rfc8785.CanonicalizationError:
        raise TableError('INVALID_INPUT', '$.table_json', 'The table cannot be canonicalized under RFC 8785') from None
    digest = hashlib.sha256(canonical).hexdigest()
    if expected and not hmac.compare_digest(digest, expected):
        raise TableError('HASH_MISMATCH', '$.expected_sha256', 'The canonical table SHA-256 does not match the configured version lock')
    return digest
