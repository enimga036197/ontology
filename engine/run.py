"""Run the collision engine step by step.

Processes the ontology in depth order, discovering structural patterns
via hash collision, compounding each step's output into the next.

Usage: python engine/run.py [--steps N]
"""

import argparse
import json
import sqlite3
import sys
import io
import os

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

# Add parent to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    create_engine_db,
    seed_vocabulary,
    ingest_triples,
    find_collisions,
    process_collisions,
    validate_step,
    build_glyph_to_token_map,
    ONTOLOGY_DB,
    ENGINE_DB,
)


def get_max_depth(ontology_conn):
    c = ontology_conn.cursor()
    c.execute("SELECT MAX(depth) FROM triples")
    return c.fetchone()[0] or 0


def get_used_tokens(engine_conn):
    c = engine_conn.cursor()
    c.execute("SELECT token FROM vocabulary")
    return {row[0] for row in c.fetchall()}


def print_collision_detail(result, token_to_glyph):
    """Pretty-print a single collision discovery."""
    template = result["template"]

    def detok(expr):
        if isinstance(expr, str):
            if expr.startswith("_"):
                return expr
            g = token_to_glyph.get(expr, expr[:6])
            return g
        if isinstance(expr, list):
            return [detok(e) for e in expr]
        return expr

    glyph_tmpl = detok(template)

    # Format variables
    var_strs = []
    for var_name, values in result["variables"].items():
        glyph_vals = [token_to_glyph.get(v, v[:6]) for v in values]
        var_strs.append(f"{var_name} ∈ {{{', '.join(glyph_vals)}}}")

    print(f"    {result['token']} ← {json.dumps(glyph_tmpl, ensure_ascii=False)}")
    print(f"      {result['members']} instances | {' ; '.join(var_strs)}")


def run(max_steps=None):
    # Connect to ontology
    if not os.path.exists(ONTOLOGY_DB):
        print(f"ERROR: {ONTOLOGY_DB} not found. Run tools/build_db.py first.")
        sys.exit(1)

    ontology_conn = sqlite3.connect(ONTOLOGY_DB)
    glyph_map = build_glyph_to_token_map(ontology_conn)
    token_to_glyph = {v: k for k, v in glyph_map.items()}

    max_depth = get_max_depth(ontology_conn)
    if max_steps is not None:
        max_depth = min(max_depth, max_steps - 1)

    print(f"=== Collision Engine ===")
    print(f"Ontology: {ONTOLOGY_DB}")
    print(f"Engine DB: {ENGINE_DB}")
    print(f"Depth range: 0 → {max_depth}")
    print(f"Vocabulary: {len(glyph_map)} seed tokens")
    print()

    # Create fresh engine DB
    engine_conn = create_engine_db()
    seed_vocabulary(engine_conn, ontology_conn)

    total_collisions = 0
    total_derived = 0

    for step in range(max_depth + 1):
        print(f"--- Step {step} (depth {step}) ---")

        # Ingest ontology triples at this depth
        ingested = ingest_triples(engine_conn, ontology_conn, glyph_map, step)
        print(f"  Ingested: {ingested} seed triples")

        # Count total patterns available
        c = engine_conn.cursor()
        c.execute("SELECT COUNT(*) FROM patterns WHERE step <= ?", (step,))
        total_patterns = c.fetchone()[0]
        print(f"  Total patterns available: {total_patterns}")

        # Find collisions
        collision_groups = find_collisions(engine_conn, step)
        print(f"  Collision groups found: {len(collision_groups)}")

        # Process collisions
        used_tokens = get_used_tokens(engine_conn)
        results = process_collisions(engine_conn, collision_groups, step, used_tokens)

        if results:
            print(f"  Discoveries:")
            for r in results:
                print_collision_detail(r, token_to_glyph)
            total_collisions += len(results)
            total_derived += sum(r["members"] for r in results)

        # Validate
        validations = validate_step(engine_conn, ontology_conn, glyph_map, step)
        matched = sum(1 for v in validations if v["ontology_matches"] > 0)
        if validations:
            print(f"  Validation: {matched}/{len(validations)} discoveries have ontology correlates")

        print()

    # Summary
    print(f"=== Engine Summary ===")
    c = engine_conn.cursor()
    c.execute("SELECT COUNT(*) FROM vocabulary WHERE origin = 'seed'")
    seed_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM vocabulary WHERE origin = 'derived'")
    derived_count = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM patterns WHERE origin = 'seed'")
    seed_patterns = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM patterns WHERE origin = 'derived'")
    derived_patterns = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM collisions")
    total_coll = c.fetchone()[0]

    print(f"  Vocabulary: {seed_count} seed + {derived_count} derived = {seed_count + derived_count}")
    print(f"  Patterns: {seed_patterns} seed + {derived_patterns} derived = {seed_patterns + derived_patterns}")
    print(f"  Collisions: {total_coll} total across all steps")
    print(f"  Engine DB: {ENGINE_DB}")

    # Show step-by-step collision counts
    print(f"\n=== Collisions by Step ===")
    c.execute("SELECT step, COUNT(*), SUM(member_count) FROM collisions GROUP BY step ORDER BY step")
    for step_num, count, members in c.fetchall():
        print(f"  Step {step_num}: {count} collisions ({members} total members)")

    engine_conn.close()
    ontology_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run collision engine")
    parser.add_argument("--steps", type=int, default=None, help="Max steps to run")
    args = parser.parse_args()
    run(max_steps=args.steps)
