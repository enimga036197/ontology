"""Run the collision engine for N steps.

Every step sees the FULL ontology + all previous discoveries.
Output shows three streams:
  - CONFIRMED: re-validated previous discoveries (the heartbeat)
  - GREW: existing collision groups that gained new members
  - NEW: genuinely novel collision groups

All state lives in SQLite. No OOM regardless of scale.

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
    find_and_process_collisions,
    get_known_collisions,
    build_glyph_to_token_map,
    ONTOLOGY_DB,
    ENGINE_DB,
)


def get_used_tokens(engine_conn):
    c = engine_conn.cursor()
    c.execute("SELECT token FROM vocabulary")
    return {row[0] for row in c.fetchall()}


def fmt_collision(result, token_to_glyph):
    """Format a single collision as a compact string."""
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
    grew = result.get("grew_from")
    prefix = f"GREW {grew}\u2192{result['members']}" if grew else f"NEW  {result['members']} inst"

    var_parts = []
    for var_name, values in result["variables"].items():
        glyph_vals = [token_to_glyph.get(v, v[:6]) for v in values]
        unique = list(dict.fromkeys(glyph_vals))
        shown = unique[:5]
        suffix = f"..+{len(unique)-5}" if len(unique) > 5 else ""
        var_parts.append(f"{var_name}\u2208{{{','.join(shown)}{suffix}}}")

    tmpl_str = json.dumps(glyph_tmpl, ensure_ascii=False)
    return f"    {result['token']} [{prefix}] {tmpl_str}  {' ; '.join(var_parts)}"


def run(num_steps=100):
    if not os.path.exists(ONTOLOGY_DB):
        print(f"ERROR: {ONTOLOGY_DB} not found. Run tools/build_db.py first.")
        sys.exit(1)

    ontology_conn = sqlite3.connect(ONTOLOGY_DB)
    glyph_map = build_glyph_to_token_map(ontology_conn)
    token_to_glyph = {v: k for k, v in glyph_map.items()}

    print(f"=== Collision Engine ===")
    print(f"Steps: {num_steps} | Seed: {len(glyph_map)} tokens")
    print()

    # Fresh engine
    engine_conn = create_engine_db()
    seed_vocabulary(engine_conn, ontology_conn)

    # Step 0 seed: ALL ontology triples
    ingested = ingest_all_triples(engine_conn, ontology_conn, glyph_map)
    print(f"Seed: {ingested} ontology triples loaded\n")

    known_max = get_known_collisions(engine_conn)
    step_log = []

    for step in range(num_steps):
        t0 = time.time()

        c = engine_conn.cursor()
        c.execute("SELECT COUNT(*) FROM patterns")
        total_patterns = c.fetchone()[0]

        used_tokens = get_used_tokens(engine_conn)
        new_results, confirmed, grew = find_and_process_collisions(
            engine_conn, step, used_tokens, known_max
        )

        # Update reverse map for display
        for r in new_results:
            token_to_glyph[r["token"]] = f"C{r['collision_id']}"

        elapsed = time.time() - t0

        c.execute("SELECT COUNT(*) FROM collisions")
        total_collisions = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM vocabulary WHERE origin = 'derived'")
        derived_vocab = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM template_hashes")
        total_hashes = c.fetchone()[0]

        new_count = len(new_results) - grew
        step_log.append({
            "step": step,
            "patterns": total_patterns,
            "confirmed": confirmed,
            "grew": grew,
            "new": new_count,
            "minted": len(new_results),
            "total_collisions": total_collisions,
            "derived_vocab": derived_vocab,
            "hashes": total_hashes,
            "elapsed": elapsed,
        })

        # Print step summary
        parts = []
        if confirmed:
            parts.append(f"{confirmed} confirmed")
        if grew:
            parts.append(f"{grew} grew")
        if new_count:
            parts.append(f"{new_count} new")

        status = " | ".join(parts) if parts else "\u2014"
        print(f"Step {step:3d} | {total_patterns:5d} pat | {total_hashes:7d} hashes | {status} | {derived_vocab} derived | {elapsed:.2f}s")

        # Print details for grew/new
        for r in new_results:
            print(fmt_collision(r, token_to_glyph))

        engine_conn.commit()

    # Summary
    print(f"\n{'='*70}")
    print(f"=== Summary after {num_steps} steps ===")
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
    c.execute("SELECT COUNT(*) FROM template_hashes")
    total_hashes = c.fetchone()[0]

    print(f"  Vocabulary: {seed_count} seed + {derived_count} derived = {seed_count + derived_count}")
    print(f"  Patterns:   {seed_patterns} seed + {derived_patterns} derived = {seed_patterns + derived_patterns}")
    print(f"  Collisions: {total_coll} total minted")
    print(f"  Template hashes: {total_hashes} on disk")

    # Growth curve
    print(f"\n=== Growth ===")
    print(f"  {'Step':>5s} {'Patterns':>8s} {'Hashes':>8s} {'Confirmed':>9s} {'Grew':>5s} {'New':>4s} {'Minted':>6s} {'Derived':>7s} {'Time':>6s}")
    for s in step_log:
        print(f"  {s['step']:5d} {s['patterns']:8d} {s['hashes']:8d} {s['confirmed']:9d} {s['grew']:5d} {s['new']:4d} {s['minted']:6d} {s['derived_vocab']:7d} {s['elapsed']:5.1f}s")

    engine_conn.close()
    ontology_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run collision engine")
    parser.add_argument("--steps", type=int, default=100, help="Number of steps (default 100)")
    args = parser.parse_args()
    run(num_steps=args.steps)
