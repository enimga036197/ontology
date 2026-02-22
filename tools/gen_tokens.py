"""One-time token generation: adds 'token' field to symbols.json.

Uses cryptographic randomness (secrets module) — no PRNG seed, no
deterministic pattern, no structural information. Run once, commit
the result. The build script reads tokens from symbols.json.
"""

import json
import secrets
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

SYMBOLS_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "symbols.json"
)


def random_token(used):
    """Generate a 6-digit token using digits 1-9, cryptographically random."""
    while True:
        token = "".join(str(secrets.randbelow(9) + 1) for _ in range(6))
        if token not in used:
            return token


def main():
    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    used = set()
    # Preserve any existing tokens
    for info in data.values():
        if "token" in info:
            used.add(info["token"])

    assigned = 0
    for glyph, info in data.items():
        if "token" not in info:
            info["token"] = random_token(used)
            used.add(info["token"])
            assigned += 1

    with open(SYMBOLS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"Assigned {assigned} new tokens ({len(used)} total)")
    print(f"Written to {SYMBOLS_FILE}")


if __name__ == "__main__":
    main()
