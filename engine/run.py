"""Run the collision engine for N steps.

Every step sees the FULL ontology + all previous discoveries.
Output shows three streams:
  - CONFIRMED: re-validated previous discoveries (the heartbeat)
  - GREW: existing collision groups that gained new members
  - NEW: genuinely novel collision groups

All state lives in SQLite. No OOM regardless of scale.

Usage: python engine/run.py [--steps N] [--set NAME]
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

# Pre-parse --set before importing core (which reads ONTOLOGY_SET at import time)
_pre = argparse.ArgumentParser(add_help=False)
_pre.add_argument("--set", default=os.environ.get("ONTOLOGY_SET", "main"))
_pre_args, _ = _pre.parse_known_args()
os.environ["ONTOLOGY_SET"] = _pre_args.set

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    create_engine_db,
    seed_vocabulary,
    ingest_all_triples,
    find_and_process_collisions,
    get_known_collisions,
    find_membership_collisions,
    get_known_membership_collisions,
    build_glyph_to_token_map,
    apply_pragmas,
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


def fmt_membership_collision(result, token_to_glyph):
    """Format a membership collision (theory) as a compact string."""
    grew = result.get("grew_from")
    score = result.get("collision_score", result["collision_count"])
    prefix = f"GREW {grew}\u2192{score}" if grew else f"NEW  {result['collision_count']}coll w={score}"

    coll_names = [f"C{cid}" for cid in result["collision_ids"]]
    shown = coll_names[:5]
    suffix = f"..+{len(coll_names)-5}" if len(coll_names) > 5 else ""

    subj_glyphs = [token_to_glyph.get(s, s[:6]) for s in result["subject_set"]]
    subj_shown = subj_glyphs[:8]
    subj_suffix = f"..+{len(subj_glyphs)-8}" if len(subj_glyphs) > 8 else ""

    return (f"    {result['token']} [{prefix}] "
            f"theories={{{','.join(shown)}{suffix}}} "
            f"shared={{{','.join(subj_shown)}{subj_suffix}}} ({result['subject_count']} subj)")


def run(num_steps=100):
    if not os.path.exists(ONTOLOGY_DB):
        print(f"ERROR: {ONTOLOGY_DB} not found. Run tools/build_db.py first.")
        sys.exit(1)

    ontology_conn = sqlite3.connect(ONTOLOGY_DB)
    apply_pragmas(ontology_conn)
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
    known_membership_max = get_known_membership_collisions(engine_conn)
    step_log = []

    for step in range(num_steps):
        t0 = time.time()

        c = engine_conn.cursor()
        c.execute("SELECT COUNT(*) FROM patterns")
        total_patterns = c.fetchone()[0]

        used_tokens = get_used_tokens(engine_conn)
        equiv_token = glyph_map["≡"]
        conj_token = glyph_map["∧"]
        member_of_token = glyph_map.get("∈")

        # Phase 1: Template collisions
        new_results, confirmed, grew = find_and_process_collisions(
            engine_conn, step, used_tokens, known_max, equiv_token
        )

        for r in new_results:
            token_to_glyph[r["token"]] = f"C{r['collision_id']}"

        # Phase 2: Membership collisions
        used_tokens = get_used_tokens(engine_conn)
        mc_results, mc_confirmed, mc_grew = find_membership_collisions(
            engine_conn, step, used_tokens, known_membership_max,
            equiv_token, conj_token, member_of_token,
        )

        for r in mc_results:
            token_to_glyph[r["token"]] = f"T{r['mc_id']}"

        elapsed = time.time() - t0

        c.execute("SELECT COUNT(*) FROM collisions")
        total_collisions = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM membership_collisions")
        total_theories = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM vocabulary WHERE origin = 'derived'")
        derived_vocab = c.fetchone()[0]
        c.execute("SELECT COUNT(*) FROM template_hashes")
        total_hashes = c.fetchone()[0]

        new_count = len(new_results) - grew
        mc_new_count = len(mc_results) - mc_grew
        step_log.append({
            "step": step,
            "patterns": total_patterns,
            "confirmed": confirmed,
            "grew": grew,
            "new": new_count,
            "minted": len(new_results),
            "mc_confirmed": mc_confirmed,
            "mc_grew": mc_grew,
            "mc_new": mc_new_count,
            "mc_minted": len(mc_results),
            "total_collisions": total_collisions,
            "total_theories": total_theories,
            "derived_vocab": derived_vocab,
            "hashes": total_hashes,
            "elapsed": elapsed,
        })

        # Print step summary
        p1_parts = []
        if confirmed:
            p1_parts.append(f"{confirmed} conf")
        if grew:
            p1_parts.append(f"{grew} grew")
        if new_count:
            p1_parts.append(f"{new_count} new")

        p2_parts = []
        if mc_confirmed:
            p2_parts.append(f"{mc_confirmed} conf")
        if mc_grew:
            p2_parts.append(f"{mc_grew} grew")
        if mc_new_count:
            p2_parts.append(f"{mc_new_count} new")

        p1_status = " | ".join(p1_parts) if p1_parts else "\u2014"
        p2_status = " | ".join(p2_parts) if p2_parts else "\u2014"
        print(f"Step {step:3d} | {total_patterns:5d} pat | P1: {p1_status} | P2: {p2_status} | {total_theories} theories | {derived_vocab} derived | {elapsed:.2f}s")

        # Print Phase 1 details
        for r in new_results:
            print(fmt_collision(r, token_to_glyph))

        # Print Phase 2 details
        for r in mc_results:
            print(fmt_membership_collision(r, token_to_glyph))

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
    c.execute("SELECT COUNT(*) FROM membership_collisions")
    total_theories = c.fetchone()[0]
    c.execute("SELECT COUNT(*) FROM template_hashes")
    total_hashes = c.fetchone()[0]

    print(f"  Vocabulary: {seed_count} seed + {derived_count} derived = {seed_count + derived_count}")
    print(f"  Patterns:   {seed_patterns} seed + {derived_patterns} derived = {seed_patterns + derived_patterns}")
    print(f"  Collisions: {total_coll} (P1) + {total_theories} theories (P2)")
    print(f"  Template hashes: {total_hashes} on disk")

    # Growth curve
    print(f"\n=== Growth ===")
    print(f"  {'Step':>5s} {'Pat':>6s} {'P1 new':>6s} {'P1 grew':>7s} {'P2 new':>6s} {'P2 grew':>7s} {'Theories':>8s} {'Derived':>7s} {'Time':>6s}")
    for s in step_log:
        print(f"  {s['step']:5d} {s['patterns']:6d} {s['new']:6d} {s['grew']:7d} {s['mc_new']:6d} {s['mc_grew']:7d} {s['total_theories']:8d} {s['derived_vocab']:7d} {s['elapsed']:5.1f}s")

    engine_conn.close()
    ontology_conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run collision engine")
    parser.add_argument("--steps", type=int, default=100, help="Number of steps (default 100)")
    args = parser.parse_args()
    run(num_steps=args.steps)
