"""Validate ontology layer files."""
import json
import sys
from pathlib import Path

LAYERS_DIR = Path(__file__).parent.parent / "layers"

# Valid middle-position operators (all operators that appear in the operator slot of triples)
VALID_OPERATORS = {"⊨", "⌂", "≡", "↦", "ℒ", "=", "≠", "⊏", "⋔", "!", "?", "𝕧", "Ϛ", "ℛ", "⇒"}


def validate_triple(triple, file, line_num):
    """Validate a single triple. Returns list of errors."""
    errors = []
    if not isinstance(triple, list):
        errors.append(f"{file}:{line_num}: not a list")
        return errors
    if len(triple) != 3:
        errors.append(f"{file}:{line_num}: length {len(triple)}, expected 3")
        return errors

    subject, operator, obj = triple
    if not isinstance(subject, (str, list)):
        errors.append(f"{file}:{line_num}: subject must be string or list, got {type(subject).__name__}")
    if not isinstance(operator, str):
        errors.append(f"{file}:{line_num}: operator must be string, got {type(operator).__name__}")
    elif operator not in VALID_OPERATORS:
        errors.append(f"{file}:{line_num}: unknown operator '{operator}'")

    return errors


def validate_file(path):
    """Validate a single JSONL file. Returns (triple_count, errors)."""
    errors = []
    count = 0
    with open(path, "r", encoding="utf-8") as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                triple = json.loads(line)
            except json.JSONDecodeError as e:
                errors.append(f"{path.name}:{i}: invalid JSON: {e}")
                continue
            count += 1
            errors.extend(validate_triple(triple, path.name, i))
    return count, errors


def main():
    files = sorted(LAYERS_DIR.glob("*.jsonl"))
    if not files:
        print("No layer files found.")
        sys.exit(1)

    total = 0
    all_errors = []

    for f in files:
        count, errors = validate_file(f)
        total += count
        all_errors.extend(errors)
        status = "OK" if not errors else f"ERRORS: {len(errors)}"
        print(f"  {f.name}: {count} triples [{status}]")

    print(f"\nTotal: {total} triples across {len(files)} layers")

    if all_errors:
        print(f"\n{len(all_errors)} error(s):")
        for e in all_errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("All valid.")


if __name__ == "__main__":
    main()
