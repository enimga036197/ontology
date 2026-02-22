"""Run the collision engine for N steps.

Every step sees the FULL ontology + all previous discoveries.
Step 0: 365 seed triples → collisions → new tokens
Step N: 365 seed + all derived from steps 0..N-1 → collisions → new tokens

Depth-from-root normalizes weight: foundation triples weigh most.

Usage: python engine/run.py [--steps N]
"""

import argparse
import json
import sqlite3
import sys
import io
import os
import time

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    create_engine_db,
    seed_vocabulary,
    ingest_all_triples,
    find_collisions,
    process_collisions,
    get_known_collision_keys,
    validate_step,
    build_glyph_to_token_map,
    ONTOLOGY_DB,
    ENGINE_DB,
)


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
            return token_to_glyph.get(expr, expr[:6])
        if isinstance(expr, list):
            return [detok(e) for e in expr]
        return expr

    glyph_tmpl = detok(template)

    var_strs = []
    for var_name, values in result["variables"].items():
        glyph_vals = [token_to_glyph.get(v, v[:6]) for v in values]
        unique = list(dict.fromkeys(glyph_vals))
        shown = unique[:6]
        suffix = f"...+{len(unique)-6}" if len(unique) > 6 else ""
        var_strs.append(f"{var_name}∈{{{','.join(shown)}{suffix}}}")

    print(f"    {result['token']} ← {json.dumps(glyph_tmpl, ensure_ascii=False)}")
    print(f"      {result['members']} inst | {' ; '.join(var_strs)}")


def run(num_steps=100):
    if not os.path.exists(ONTOLOGY_DB):
        print(f"ERROR: {ONTOLOGY_DB} not found. Run tools/build_db.py first.")
        sys.exit(1)

    ontology_conn = sqlite3.connect(ONTOLOGY_DB)
    glyph_map = build_glyph_to_token_map(ontology_conn)
    token_to_glyph = {v: k for k, v in glyph_map.items()}

    print(f"=== Collision Engine ===")
    print(f"Ontology: {ONTOLOGY_DB}")
    print(f"Engine DB: {ENGINE_DB}")
    print(f"Steps: {num_steps}")
    print(f"Seed vocabulary: {len(glyph_map)} tokens")
    print()

    # Create fresh engine DB
    engine_conn = create_engine_db()
    seed_vocabulary(engine_conn, ontology_conn)

    # Step 0: ingest ALL ontology triples
    ingested = ingest_all_triples(engine_conn, ontology_conn, glyph_map)
    print(f"Ingested all {ingested} ontology triples at step 0")
    print()

    # Track known collisions for deduplication
    known_keys = get_known_collision_keys(engine_conn)

    step_stats = []

    for step in range(num_steps):
        t0 = time.time()

        # Count patterns
        c = engine_conn.cursor()
        c.execute("SELECT COUNT(*) FROM patterns")
        total_patterns = c.fetchone()[0]

        # Find collisions across ALL patterns
        collision_groups = find_collisions(engine_conn)

        # Process — only NEW collisions get tokens
        used_tokens = get_used_tokens(engine_conn)
        results = process_collisions(engine_conn, collision_groups, step, used_tokens, known_keys)

        # Update token_to_glyph with new derived tokens
        for r in results:
            token_to_glyph[r["token"]] = f"C{r['collision_id']}"

        elapsed = time.time() - t0

        # Stats
        c.execute("SELECT COUNT(*) FROM vocabulary WHERE origin = 'derived'")
        derived_vocab = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM collisions")
        total_collisions = c.fetchone()[0]

        step_stats.append({
            "step": step,
            "patterns": total_patterns,
            "new_collisions": len(results),
            "total_collisions": total_collisions,
            "derived_vocab": derived_vocab,
            "elapsed": elapsed,
        })

        # Print every step
        new_str = f"{len(results)} new" if results else "0 new"
        print(f"  Step {step:3d} | {total_patterns:5d} patterns | {new_str:8s} | {total_collisions:5d} total | {derived_vocab:5d} derived | {elapsed:.2f}s")

        # Print details for new discoveries
        if results:
            for r in results:
                print_collision_detail(r, token_to_glyph)

        # If no new collisions found, note it but keep going
        # (new patterns from this step may create collisions in future steps)
        if not results and step > 0:
            # Check if we've had many consecutive empty steps
            consecutive_empty = 0
            for s in reversed(step_stats):
                if s["new_collisions"] == 0:
                    consecutive_empty += 1
                else:
                    break
            if consecutive_empty >= 10:
                print(f"\n  [10 consecutive empty steps — engine has converged]")
                break

        engine_conn.commit()

    # Summary
    print(f"\n{'='*70}")
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
    print(f"  Collisions: {total_coll} total")
    print(f"  Engine DB: {ENGINE_DB}")

    # Growth curve
    print(f"\n=== Growth Curve ===")
    print(f"  {'Step':>5s}  {'Patterns':>8s}  {'New':>5s}  {'Total':>6s}  {'Derived':>7s}")
    for s in step_stats:
        print(f"  {s['step']:5d}  {s['patterns']:8d}  {s['new_collisions']:5d}  {s['total_collisions']:6d}  {s['derived_vocab']:7d}")

    # Collisions by step
    print(f"\n=== Collisions by Step ===")
    c.execute("SELECT step, COUNT(*), SUM(member_count) FROM collisions GROUP BY step ORDER BY step")
    for step_num, count, members in c.fetchall():
        print(f"  Step {step_num}: {count} collisions ({members} total members)")

    engine_conn.close()
    ontology_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run collision engine")
    parser.add_argument("--steps", type=int, default=100, help="Number of steps (default 100)")
    args = parser.parse_args()
    run(num_steps=args.steps)
