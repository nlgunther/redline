"""Fast, non-cryptographic hashing for exact-match lookups.

64 bits is comfortably enough at paragraph granularity: for a few thousand
paragraphs, the birthday-bound collision probability is on the order of
1e-13. A cryptographic hash (SHA-256) would buy adversarial-collision
resistance, which is irrelevant here -- nobody is trying to craft a
paragraph that fools the matcher. Callers verify true text equality on
every hit anyway (cheap, and removes any dependency on this bound being
exactly right), so hash strength only affects lookup-table efficiency,
not correctness.
"""

import hashlib


def light_hash(text: str, digest_size: int = 8) -> bytes:
    """Hash normalized text for use as a dict key.

    Example:
        light_hash("hello world")  # -> 8-byte digest
    """
    return hashlib.blake2b(text.encode("utf-8"), digest_size=digest_size).digest()
