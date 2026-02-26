"""Check why new primality laws don't participate in collisions."""
import sqlite3, json, sys, io, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import flatten_positions, generate_templates_for_pattern

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(ROOT, "sets", os.environ.get("ONTOLOGY_SET", "main"))
eng = sqlite3.connect(os.path.join(SET_DIR, "engine.db"))
ec = eng.cursor()

for pid in [282, 283, 284, 285]:
    ec.execute("SELECT triple, shape FROM patterns WHERE id = ?", (pid,))
    triple_json, shape = ec.fetchone()
    expr = json.loads(triple_json)
    positions = list(flatten_positions(expr))
    templates = list(generate_templates_for_pattern(expr))

    print(f"P{pid}: shape={shape}")
    print(f"  {len(positions)} leaf positions → {len(templates)} template hashes")

    # Check if ANY template is shared
    shared_count = 0
    for tmpl_json, _ in templates[:20]:  # sample first 20
        ec.execute("SELECT COUNT(*) FROM template_hashes WHERE template = ?", (tmpl_json,))
        cnt = ec.fetchone()[0]
        if cnt > 1:
            shared_count += 1
            print(f"  SHARED ({cnt}): {tmpl_json[:120]}")

    if shared_count == 0:
        print(f"  NO templates shared with other patterns (checked 20/{len(templates)})")
    print()

# Also check: what are the shapes of ALL seed patterns?
ec.execute("SELECT DISTINCT shape, COUNT(*) FROM patterns WHERE origin='seed' GROUP BY shape ORDER BY COUNT(*) DESC")
print("Shape distribution (seed patterns):")
for shape, cnt in ec.fetchall():
    print(f"  {cnt:3d}× {shape}")
