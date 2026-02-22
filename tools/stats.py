"""Ontology statistics — symbol usage, operator distribution, layer breakdown."""
import json
import sys
import io
from collections import Counter
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

LAYERS_DIR = Path(__file__).parent.parent / "layers"


def collect_symbols(obj):
    """Recursively collect all symbols from a triple or nested structure."""
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, list):
        syms = []
        for item in obj:
            syms.extend(collect_symbols(item))
        return syms
    return []


def main():
    files = sorted(LAYERS_DIR.glob("*.jsonl"))
    symbol_counts = Counter()
    operator_counts = Counter()
    layer_counts = {}

    for f in files:
        count = 0
        with open(f, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                triple = json.loads(line)
                count += 1
                symbols = collect_symbols(triple)
                symbol_counts.update(symbols)
                if len(triple) == 3:
                    operator_counts[triple[1]] += 1
        layer_counts[f.stem] = count

    # Layer breakdown
    print("=== Layers ===")
    total = 0
    for name, count in sorted(layer_counts.items()):
        print(f"  {name}: {count}")
        total += count
    print(f"  TOTAL: {total}")

    # Operator distribution
    print("\n=== Operators (middle position) ===")
    for op, count in operator_counts.most_common():
        print(f"  {op}: {count}")

    # Top symbols
    print(f"\n=== Unique symbols: {len(symbol_counts)} ===")
    print("\nTop 30:")
    for sym, count in symbol_counts.most_common(30):
        print(f"  {sym}: {count}")


if __name__ == "__main__":
    main()
