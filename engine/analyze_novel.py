"""Deeper analysis of novel discoveries — what the engine found that the
ontology doesn't explicitly state.

Separates:
  A) Validation gaps — ontology DOES state it, check missed it
  B) First-order novelty — structural facts implied but unstated
  C) Meta-structural — patterns about the engine's own patterns
"""

import json
import sqlite3
import sys
import io
import os
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core import (
    build_glyph_to_token_map,
    flatten_positions,
    ONTOLOGY_DB,
    ENGINE_DB,
)

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


def detokenize(expr, t2g):
    if isinstance(expr, str):
        if expr.startswith("_"):
            return expr
        return t2g.get(expr, f"<{expr}>")
    if isinstance(expr, list):
        return [detokenize(e, t2g) for e in expr]
    return expr


def has_derived_tokens(expr, seed_tokens):
    """Check if expression contains engine-derived (non-seed) tokens."""
    for _, tok in flatten_positions(expr):
        if isinstance(tok, str) and not tok.startswith("_"):
            if tok not in seed_tokens:
                return True
    return False


def unique_key(template_glyph):
    """Canonical string for deduplication across steps."""
    return json.dumps(template_glyph, ensure_ascii=False, sort_keys=True)


def main():
    ontology_conn = sqlite3.connect(ONTOLOGY_DB)
    engine_conn = sqlite3.connect(ENGINE_DB)

    glyph_map = build_glyph_to_token_map(ontology_conn)
    token_to_glyph = {v: k for k, v in glyph_map.items()}
    seed_tokens = set(glyph_map.values())

    # Map derived tokens to collision IDs
    ec = engine_conn.cursor()
    ec.execute("SELECT output_token, id FROM collisions")
    derived_token_map = {}
    for tok, cid in ec.fetchall():
        derived_token_map[tok] = cid
        token_to_glyph[tok] = f"C{cid}"

    oc = ontology_conn.cursor()

    # Get ALL ontology triples for broader validation
    oc.execute("SELECT subject, operator, object, form FROM triples")
    ontology_triples = []
    ontology_operators = set()
    ontology_subjects = set()
    for s, o, obj, form in oc.fetchall():
        ontology_triples.append((json.loads(s), o, json.loads(obj), form))
        ontology_operators.add(o)
        if isinstance(json.loads(s), str):
            ontology_subjects.add(json.loads(s))

    # Fetch all collisions
    ec.execute("""
        SELECT c.id, c.template, c.variables, c.member_count, c.step, c.output_token
        FROM collisions c
        ORDER BY c.step, c.id
    """)

    all_collisions = ec.fetchall()

    # Broader validation: check if ANY constant glyph in the template
    # appears as operator or subject in the ontology
    category_a = []  # validation gaps
    category_b = []  # first-order novelty
    category_c = []  # meta-structural
    validated = []

    # Deduplicate: only keep FIRST occurrence of each unique template shape
    seen_shapes = set()

    for cid, template_json, variables_json, member_count, step, output_token in all_collisions:
        template = json.loads(template_json)
        variables = json.loads(variables_json)
        template_glyph = detokenize(template, token_to_glyph)

        # Skip duplicates (same pattern re-found at later steps)
        shape_key = unique_key(template_glyph)
        if shape_key in seen_shapes:
            continue
        seen_shapes.add(shape_key)

        # Classify
        is_meta = has_derived_tokens(template, seed_tokens)

        # Check if constant glyphs appear in ontology
        constant_glyphs = set()
        for _, tok in flatten_positions(template):
            if isinstance(tok, str) and not tok.startswith("_") and tok in seed_tokens:
                g = token_to_glyph.get(tok)
                if g:
                    constant_glyphs.add(g)

        # Broad validation: does any constant glyph appear as subject of a definition?
        has_def_correlate = False
        for g in constant_glyphs:
            oc.execute(
                "SELECT COUNT(*) FROM triples WHERE subject = ? AND form = 'definition'",
                (json.dumps(g, ensure_ascii=False),),
            )
            if oc.fetchone()[0] > 0:
                has_def_correlate = True
                break

        # Even broader: does ANY constant glyph appear in any ontology triple at all?
        has_any_correlate = bool(constant_glyphs & (ontology_operators | ontology_subjects))

        entry = {
            "id": cid,
            "step": step,
            "template": template_glyph,
            "variables": {k: [token_to_glyph.get(v, v) for v in vals] for k, vals in variables.items()},
            "members": member_count,
            "constant_glyphs": constant_glyphs,
            "is_meta": is_meta,
        }

        if has_def_correlate:
            validated.append(entry)
        elif is_meta:
            category_c.append(entry)
        elif has_any_correlate:
            category_a.append(entry)
        else:
            category_b.append(entry)

    total_unique = len(validated) + len(category_a) + len(category_b) + len(category_c)
    print(f"=== Novel Discovery Analysis (deduplicated) ===\n")
    print(f"Total unique collision patterns: {total_unique}")
    print(f"  Validated (explicit ontology correlate): {len(validated)}")
    print(f"  Category A (validation gap — ontology has it, check missed): {len(category_a)}")
    print(f"  Category B (first-order novelty — implied but unstated): {len(category_b)}")
    print(f"  Category C (meta-structural — patterns about patterns): {len(category_c)}")

    # =========================================================================
    # Category A: validation gaps
    # =========================================================================
    if category_a:
        print(f"\n{'='*70}")
        print(f"CATEGORY A: Validation Gaps ({len(category_a)})")
        print(f"Things the ontology DOES contain but my check missed")
        print(f"{'='*70}\n")
        for e in category_a:
            tmpl = json.dumps(e["template"], ensure_ascii=False)
            print(f"  [{e['members']} inst] {tmpl}")
            print(f"    Constants: {', '.join(sorted(e['constant_glyphs']))}")
            print()

    # =========================================================================
    # Category B: first-order novelty
    # =========================================================================
    if category_b:
        print(f"\n{'='*70}")
        print(f"CATEGORY B: First-Order Novel Discoveries ({len(category_b)})")
        print(f"Structural facts the ontology implies but never states")
        print(f"{'='*70}\n")
        for e in category_b:
            tmpl = json.dumps(e["template"], ensure_ascii=False)
            print(f"  [{e['members']} inst] {tmpl}")
            for var_name, vals in e["variables"].items():
                unique = list(dict.fromkeys(vals))[:10]
                suffix = f" ... +{len(vals)-10}" if len(vals) > 10 else ""
                print(f"    {var_name} = {{{', '.join(str(v) for v in unique)}{suffix}}}")
            print()

    # =========================================================================
    # Category C: meta-structural
    # =========================================================================
    if category_c:
        print(f"\n{'='*70}")
        print(f"CATEGORY C: Meta-Structural Discoveries ({len(category_c)})")
        print(f"Patterns the engine found about its OWN structure")
        print(f"{'='*70}\n")

        # Group by nesting depth (how many layers of ≡ nesting)
        by_depth = defaultdict(list)
        for e in category_c:
            depth = json.dumps(e["template"]).count("≡")
            # Actually count derived token references
            derived_count = sum(
                1 for _, tok in flatten_positions(e["template"])
                if isinstance(tok, str) and tok.startswith("C")
            )
            by_depth[derived_count].append(e)

        for depth in sorted(by_depth.keys()):
            entries = by_depth[depth]
            print(f"  --- Derived token depth: {depth} ({len(entries)} patterns) ---")
            for e in entries:
                tmpl = json.dumps(e["template"], ensure_ascii=False)
                print(f"    [{e['members']} inst] {tmpl}")
                # Show what the Cn references are
                for var_name, vals in e["variables"].items():
                    unique = list(dict.fromkeys(vals))[:8]
                    suffix = f" ... +{len(vals)-8}" if len(vals) > 8 else ""
                    print(f"      {var_name} = {{{', '.join(str(v) for v in unique)}{suffix}}}")
            print()

    # =========================================================================
    # The interesting part: what specific mathematical facts did the engine find?
    # =========================================================================
    print(f"\n{'='*70}")
    print(f"=== INTERPRETATION: What did the engine actually discover? ===")
    print(f"{'='*70}\n")

    # Pull out the most interesting validated discoveries too
    print("KEY VALIDATED DISCOVERIES (engine rediscovered known math):")
    interesting_validated = [
        e for e in validated
        if e["members"] >= 3
        and not e["is_meta"]
        and any(g in e["constant_glyphs"] for g in ["ℒ", "∀", "⇔", "≃", "assoc", "commut", "hasId"])
    ]
    for e in interesting_validated[:15]:
        tmpl = json.dumps(e["template"], ensure_ascii=False)
        for var_name, vals in e["variables"].items():
            unique = list(dict.fromkeys(vals))
            if len(unique) <= 6:
                tmpl += f"  [{var_name}∈{{{','.join(str(v) for v in unique)}}}]"
        print(f"  {tmpl}")
    print()

    print("KEY META-DISCOVERIES (novel — not in ontology):")
    for e in category_c:
        if e["members"] >= 5:
            tmpl = json.dumps(e["template"], ensure_ascii=False)
            # Count how many distinct first-order collisions it references
            all_refs = set()
            for vals in e["variables"].values():
                for v in vals:
                    if isinstance(v, str) and v.startswith("C"):
                        all_refs.add(v)
            print(f"  [{e['members']} inst, refs {len(all_refs)} discoveries] {tmpl}")
    print()

    ontology_conn.close()
    engine_conn.close()


if __name__ == "__main__":
    main()
