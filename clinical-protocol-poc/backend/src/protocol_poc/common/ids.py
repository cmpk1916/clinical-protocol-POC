import secrets
import threading
import time

_ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_lock = threading.Lock()
_last_value = -1


def _encode(value: int) -> str:
    characters = ["0"] * 26
    for index in range(25, -1, -1):
        characters[index] = _ALPHABET[value & 31]
        value >>= 5
    return "".join(characters)


def new_id() -> str:
    """Return a monotonic, lexicographically sortable 26-character ULID."""
    global _last_value
    with _lock:
        timestamp = time.time_ns() // 1_000_000
        candidate = (timestamp << 80) | secrets.randbits(80)
        _last_value = max(candidate, _last_value + 1)
        return _encode(_last_value)
