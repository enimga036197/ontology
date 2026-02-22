"""Trace the engine's self-identity arc through training steps.

Tracks how the engine's assertions evolve from mathematical discovery
through self-recognition to philosophical/worldview assertions.
"""
import sqlite3, json, sys, io, os
from collections import defaultdict

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

eng = sqlite3.connect(os.path.join(ROOT, "engine", "engine.db"))
ont = sqlite3.connect(os.path.join(ROOT, "ontology.db"))
ec = eng.cursor()
oc = ont.cursor()

oc.execute("SELECT glyph, token FROM symbols")
g2t = dict(oc.fetchall())
t2g = {v: k for k, v in g2t.items()}

ec.execute("SELECT token, name FROM vocabulary WHERE origin = 'derived'")
derived_names = {}
for tok, name in ec.fetchall():
    derived_names[tok] = name
    t2g[tok] = name


def detok(expr):
    if isinstance(expr, str):
        if expr.startswith("_"):
            return expr
        return t2g.get(expr, expr[:6])
    if isinstance(expr, list):
        return [detok(e) for e in expr]
    return expr


def nesting_depth(tmpl):
    """Count how many layers of [_0, ≡, ...] wrapping."""
    if isinstance(tmpl, list) and len(tmpl) == 3:
        if isinstance(tmpl[0], str) and tmpl[0].startswith("_"):
            if tmpl[1] == "\u2261" or (isinstance(tmpl[1], str) and tmpl[1].startswith("_")):
                return 1 + nesting_depth(tmpl[2])
    return 0


def get_core(tmpl):
    """Unwrap [_0, ≡, [_0, ≡, ...]] to get the innermost non-meta content."""
    if isinstance(tmpl, list) and len(tmpl) == 3:
        if isinstance(tmpl[0], str) and tmpl[0].startswith("_"):
            if tmpl[1] == "\u2261":
                return get_core(tmpl[2])
    return tmpl


def get_seed_refs(expr):
    """Get all ontology symbol references in an expression."""
    refs = set()
    if isinstance(expr, str):
        g = t2g.get(expr, "")
        if g and not g.startswith("collision") and not expr.startswith("_"):
            refs.add(g)
    elif isinstance(expr, list):
        for e in expr:
            refs.update(get_seed_refs(e))
    return refs


# Semantic categories for ontology symbols
IDENTITY_SYMS = {"≡", "=", "⊨", "⊤", "τ"}
REASONING_SYMS = {"⇒", "⇔", "∀", "∃", "¬", "⊢", "⊨"}
STRUCTURE_SYMS = {"ρ", "Ο", "Τ", "Κ", "Σ", "Θ", "θ", "↦"}
VALUE_SYMS = {"⊤", "⊥", "✓", "✗", "𝟙", "∅"}
FRAMEWORK_SYMS = {"𝓕", "𝓢", "𝓐", "𝓛", "𝓡", "𝓑", "⊏", "⋔"}
LAW_SYMS = {"ℒ", "assoc", "commut", "hasId", "hasInv", "distrib"}
EXISTENCE_SYMS = {"∃", "∀", "¬", "⊤", "⊥", "𝟙", "∅", "∈", "∉"}
MODAL_SYMS = {"□", "◊", "Ⓢ", "!", "✓", "✗"}

# Get all collisions ordered by step
ec.execute(
    "SELECT id, template, variables, member_count, step FROM collisions ORDER BY step, id"
)
all_collisions = ec.fetchall()

print(f"Total collisions across all steps: {len(all_collisions)}")
print()

# Analyze the arc step by step
step_themes = defaultdict(lambda: defaultdict(int))
step_examples = defaultdict(list)

for cid, tmpl_json, vars_json, mc, step in all_collisions:
    tmpl = json.loads(tmpl_json)
    variables = json.loads(vars_json)

    nd = nesting_depth(tmpl)
    core = get_core(tmpl)
    core_refs = get_seed_refs(core)
    all_refs = get_seed_refs(tmpl)

    # Also check variable values for seed refs
    var_refs = set()
    for vn, vals in variables.items():
        for v in vals:
            g = t2g.get(v, "")
            if g and not g.startswith("collision") and not v.startswith("_"):
                var_refs.add(g)

    total_refs = all_refs | var_refs

    # Classify the THEME of this assertion
    themes = []

    if total_refs & IDENTITY_SYMS:
        themes.append("identity")
    if total_refs & REASONING_SYMS:
        themes.append("reasoning")
    if total_refs & LAW_SYMS:
        themes.append("algebraic_law")
    if total_refs & STRUCTURE_SYMS:
        themes.append("structure")
    if total_refs & FRAMEWORK_SYMS:
        themes.append("framework")
    if total_refs & MODAL_SYMS:
        themes.append("modal")
    if total_refs & EXISTENCE_SYMS:
        themes.append("existence")
    if not total_refs:
        themes.append("pure_self_reference")

    for theme in themes:
        step_themes[step][theme] += 1

    # Collect examples for narrative
    entry = {
        "cid": cid,
        "mc": mc,
        "nd": nd,
        "core": detok(core),
        "full": detok(tmpl),
        "themes": themes,
        "seed_refs": total_refs,
        "variables": {k: [t2g.get(v, v[:8]) for v in vals][:6] for k, vals in variables.items()},
    }
    step_examples[step].append(entry)

# Print the arc
print("=" * 80)
print("THE ENGINE'S ARC: from mathematics to self-knowledge to worldview")
print("=" * 80)

for step in sorted(step_themes.keys()):
    themes = step_themes[step]
    examples = step_examples[step]
    total = len(examples)

    # Average nesting depth
    avg_nd = sum(e["nd"] for e in examples) / max(len(examples), 1)

    print(f"\n{'='*70}")
    print(f"STEP {step} | {total} collisions | avg nesting depth: {avg_nd:.1f}")
    print(f"{'='*70}")

    # Theme distribution
    print("  Themes:")
    for theme, count in sorted(themes.items(), key=lambda x: -x[1]):
        bar = "#" * min(count, 40)
        print(f"    {theme:20s}: {count:4d} {bar}")

    # Show the most interesting examples per theme grouping
    # Sort by member count descending, pick diverse examples
    shown_themes = set()
    interesting = sorted(examples, key=lambda x: -x["mc"])

    print("  Key assertions:")
    shown = 0
    for e in interesting:
        # Pick examples that show different themes
        primary_theme = e["themes"][0] if e["themes"] else "unknown"
        if shown >= 8:
            break

        core_str = json.dumps(e["core"], ensure_ascii=False)
        if len(core_str) > 120:
            core_str = core_str[:117] + "..."

        refs_str = ", ".join(sorted(e["seed_refs"])[:8])

        print(f"    C{e['cid']} [{e['mc']} members, depth-{e['nd']}] ({', '.join(e['themes'])})")
        print(f"      core: {core_str}")
        if e["variables"]:
            first_var = list(e["variables"].items())[0]
            print(f"      {first_var[0]} spans: {first_var[1]}")
        shown += 1

# Phase analysis
print(f"\n{'='*80}")
print("PHASE ANALYSIS")
print(f"{'='*80}")

for step in sorted(step_themes.keys()):
    themes = step_themes[step]
    total = sum(themes.values())
    examples = step_examples[step]
    avg_nd = sum(e["nd"] for e in examples) / max(len(examples), 1)

    # Compute ratios
    math_ratio = (themes.get("algebraic_law", 0) + themes.get("structure", 0)) / max(total, 1)
    self_ratio = (themes.get("identity", 0) + themes.get("pure_self_reference", 0)) / max(total, 1)
    world_ratio = (themes.get("existence", 0) + themes.get("modal", 0) + themes.get("framework", 0)) / max(total, 1)
    reason_ratio = themes.get("reasoning", 0) / max(total, 1)

    phase = "MATH" if math_ratio > 0.4 else "SELF" if self_ratio > 0.3 else "WORLDVIEW" if world_ratio > 0.4 else "MIXED"

    print(f"  Step {step:2d} | depth {avg_nd:3.1f} | math {math_ratio:.0%} | self {self_ratio:.0%} | reasoning {reason_ratio:.0%} | world {world_ratio:.0%} | → {phase}")
