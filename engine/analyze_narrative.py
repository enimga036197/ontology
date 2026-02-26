"""Trace the engine's narrative arc by looking at UNIQUE core patterns.

Strip all [_0, ≡, ...] nesting to find what the engine actually asserts,
then track when each assertion first appears and how it evolves.
"""
import sqlite3, json, sys, io, os
from collections import defaultdict, Counter

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SET_DIR = os.path.join(ROOT, "sets", os.environ.get("ONTOLOGY_SET", "main"))

eng = sqlite3.connect(os.path.join(SET_DIR, "engine.db"))
ont = sqlite3.connect(os.path.join(SET_DIR, "ontology.db"))
ec = eng.cursor()
oc = ont.cursor()

oc.execute("SELECT glyph, token FROM symbols")
g2t = dict(oc.fetchall())
t2g = {v: k for k, v in g2t.items()}

ec.execute("SELECT token, name FROM vocabulary WHERE origin = 'derived'")
for tok, name in ec.fetchall():
    t2g[tok] = name


def detok(expr):
    if isinstance(expr, str):
        if expr.startswith("_"):
            return expr
        return t2g.get(expr, expr[:6])
    if isinstance(expr, list):
        return [detok(e) for e in expr]
    return expr


def get_core(tmpl):
    """Unwrap [_0, ≡, ...] layers to get the innermost assertion."""
    if isinstance(tmpl, list) and len(tmpl) == 3:
        if isinstance(tmpl[0], str) and tmpl[0].startswith("_"):
            if tmpl[1] == "\u2261":
                return get_core(tmpl[2])
    return tmpl


def nesting_depth(tmpl):
    if isinstance(tmpl, list) and len(tmpl) == 3:
        if isinstance(tmpl[0], str) and tmpl[0].startswith("_"):
            if tmpl[1] == "\u2261":
                return 1 + nesting_depth(tmpl[2])
    return 0


def normalize_core(core):
    """Create a canonical form of the core for grouping.
    Replace specific tokens with their glyph, keep wildcards."""
    if isinstance(core, str):
        if core.startswith("_"):
            return core
        g = t2g.get(core, core)
        if g.startswith("collision"):
            return "_C"  # any derived token
        return g
    if isinstance(core, list):
        return [normalize_core(e) for e in core]
    return core


# Get ALL collisions
ec.execute(
    "SELECT id, template, variables, member_count, step FROM collisions ORDER BY step, id"
)
all_collisions = ec.fetchall()

# Group by normalized core pattern
core_families = defaultdict(list)
for cid, tmpl_json, vars_json, mc, step in all_collisions:
    tmpl = json.loads(tmpl_json)
    variables = json.loads(vars_json)
    nd = nesting_depth(tmpl)
    core = get_core(tmpl)
    norm = json.dumps(normalize_core(core), ensure_ascii=False)
    glyph_core = detok(core)

    # Get all seed symbol references from variables
    var_seeds = set()
    for vn, vals in variables.items():
        for v in vals:
            g = t2g.get(v, "")
            if g and not g.startswith("collision") and not v.startswith("_"):
                var_seeds.add(g)

    core_families[norm].append({
        "cid": cid,
        "step": step,
        "nd": nd,
        "mc": mc,
        "glyph_core": glyph_core,
        "var_seeds": var_seeds,
        "variables": variables,
    })

# Sort families by the step they first appear
families_by_first = sorted(core_families.items(), key=lambda x: x[1][0]["step"])

print(f"Total unique core patterns: {len(core_families)}")
print()

# Now trace the narrative
print("=" * 80)
print("THE ENGINE'S ASSERTIONS — what it claims, in order of discovery")
print("=" * 80)

current_step = -1
for norm, entries in families_by_first:
    first = entries[0]
    step = first["step"]

    if step != current_step:
        current_step = step
        # Count unique cores at this step
        cores_this_step = [n for n, e in families_by_first if e[0]["step"] == step]
        print(f"\n{'='*70}")
        print(f"STEP {step}: {len(cores_this_step)} new assertion types emerge")
        print(f"{'='*70}")

    # How does this family evolve?
    steps_present = sorted(set(e["step"] for e in entries))
    total_members = sum(e["mc"] for e in entries)
    max_depth = max(e["nd"] for e in entries)
    all_var_seeds = set()
    for e in entries:
        all_var_seeds |= e["var_seeds"]

    # Show the glyph core
    core_str = json.dumps(first["glyph_core"], ensure_ascii=False)
    if len(core_str) > 100:
        core_str = core_str[:97] + "..."

    repeats = f"repeats steps {steps_present[0]}-{steps_present[-1]}" if len(steps_present) > 1 else "this step only"

    print(f"\n  [{first['mc']} members] {core_str}")
    print(f"  {repeats} | deepens to depth {max_depth}")

    if all_var_seeds:
        seeds_str = ", ".join(sorted(all_var_seeds)[:15])
        if len(all_var_seeds) > 15:
            seeds_str += f" ...+{len(all_var_seeds)-15}"
        print(f"  references: {seeds_str}")

    # Show what the variables span at first occurrence
    for vn, vals in list(first["variables"].items())[:2]:
        gvals = [t2g.get(v, v[:8]) for v in vals]
        unique = list(dict.fromkeys(gvals))[:8]
        print(f"  {vn} spans: {unique}")

# Phase summary
print(f"\n{'='*80}")
print("NARRATIVE ARC SUMMARY")
print(f"{'='*80}")

for step in range(10):
    cores_this_step = [(n, e) for n, e in families_by_first if e[0]["step"] == step]

    # What KIND of cores emerge at this step?
    pure_math = 0
    self_referential = 0
    meta_reasoning = 0
    framework_philosophical = 0

    for norm, entries in cores_this_step:
        core = json.loads(norm)
        seeds = entries[0]["var_seeds"]

        # Check if core itself contains self-reference patterns
        norm_str = norm

        has_law = "ℒ" in norm_str or "assoc" in norm_str or "commut" in norm_str
        has_def = "≡" in norm_str and "_C" not in norm_str
        has_meta_def = "_C" in norm_str  # references derived tokens
        has_identity = "⊤" in norm_str or "⊨" in norm_str or "=" in norm_str
        has_framework = "⊏" in norm_str or "𝓕" in norm_str or "⋔" in norm_str
        has_modal = "□" in norm_str or "◊" in norm_str or "Ⓢ" in norm_str

        # Classify
        if has_law and not has_meta_def:
            pure_math += 1
        elif has_meta_def or (has_identity and "_C" in str(seeds)):
            meta_reasoning += 1
        elif has_framework or has_modal:
            framework_philosophical += 1
        else:
            self_referential += 1

    if cores_this_step:
        total = len(cores_this_step)
        print(f"  Step {step}: {total} new cores → math:{pure_math} self:{self_referential} meta:{meta_reasoning} worldview:{framework_philosophical}")
