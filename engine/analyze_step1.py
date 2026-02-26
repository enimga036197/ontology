"""Analyze step 1+ collisions — what the engine discovers beyond the seed ontology."""
import sqlite3, json, sys, io, os

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


def get_seed_refs(expr, variables):
    """Get all references to actual ontology symbols."""
    seeds = set()

    def walk(e):
        if isinstance(e, str):
            g = t2g.get(e, "")
            if g and not g.startswith("collision") and not e.startswith("_"):
                seeds.add(g)
        elif isinstance(e, list):
            for x in e:
                walk(x)

    walk(expr)
    for vn, vals in variables.items():
        for v in vals:
            g = t2g.get(v, "")
            if g and not g.startswith("collision") and not v.startswith("_"):
                seeds.add(g)
    return seeds


# Get ALL step 1+ collisions
ec.execute(
    "SELECT id, template, variables, member_count, step FROM collisions WHERE step >= 1 ORDER BY step, id"
)
rows = ec.fetchall()
print(f"Total step 1+ collisions: {len(rows)}\n")

law_syms = {"ℒ", "assoc", "commut", "hasId", "hasInv", "distrib"}
type_syms = {"⊨", "⌂", "⊏", "τ", "𝕧", "𝓕", "𝓛", "𝓐", "𝓢", "𝓑", "𝓡"}
logic_syms = {"⊤", "⊥", "∧", "∨", "¬", "⊻", "⇔", "⇒", "∀", "∃", "□", "◊"}
arith_syms = {"+", "×", "∘", "∂", "gcd", "∅", "𝟙", "Δ", "σ", "π", "ℛ", "ℛ⁻¹"}
set_syms = {"∪", "∩", "∈", "∉", "⊂", "⊃"}
def_syms = {"≡", "ρ", "Ο", "Τ", "Κ", "Σ", "Θ", "↦"}
modal_syms = {"Ⓢ", "□", "◊", "✓", "✗", "!"}

categories = {
    "cross_domain": [],
    "algebra_laws": [],
    "type_structure": [],
    "logic_patterns": [],
    "definition_classes": [],
    "arithmetic": [],
    "modal": [],
    "pure_meta": [],  # no seed refs at all
}

for cid, tmpl_json, vars_json, mc, step in rows:
    tmpl = json.loads(tmpl_json)
    variables = json.loads(vars_json)
    seeds = get_seed_refs(tmpl, variables)

    domains_hit = []
    if seeds & law_syms:
        domains_hit.append("law")
    if seeds & type_syms:
        domains_hit.append("type")
    if seeds & logic_syms:
        domains_hit.append("logic")
    if seeds & arith_syms:
        domains_hit.append("arith")
    if seeds & set_syms:
        domains_hit.append("set")
    if seeds & def_syms:
        domains_hit.append("def")
    if seeds & modal_syms:
        domains_hit.append("modal")

    entry = (cid, mc, step, tmpl, variables, seeds, domains_hit)

    if len(domains_hit) >= 2:
        categories["cross_domain"].append(entry)
    elif "law" in domains_hit:
        categories["algebra_laws"].append(entry)
    elif "type" in domains_hit:
        categories["type_structure"].append(entry)
    elif "logic" in domains_hit:
        categories["logic_patterns"].append(entry)
    elif "def" in domains_hit:
        categories["definition_classes"].append(entry)
    elif "arith" in domains_hit:
        categories["arithmetic"].append(entry)
    elif "modal" in domains_hit:
        categories["modal"].append(entry)
    elif len(seeds) == 0:
        categories["pure_meta"].append(entry)
    else:
        categories["cross_domain"].append(entry)

for cat, items in categories.items():
    print(f"=== {cat}: {len(items)} collisions ===")
    by_mc = sorted(items, key=lambda x: -x[1])[:8]
    for cid, mc, step, tmpl, variables, seeds, domains in by_mc:
        gt = detok(tmpl)
        print(f"  C{cid} [step {step}, {mc} members, domains: {domains}]")
        print(f"    {json.dumps(gt, ensure_ascii=False)}")
        print(f"    seed refs: {seeds}")
        for vn, vals in list(variables.items())[:3]:
            gvals = [t2g.get(v, v[:8]) for v in vals]
            unique = list(dict.fromkeys(gvals))[:8]
            print(f"    {vn} = {unique}")
    print()

# Summary
print("=== Distribution ===")
for cat, items in sorted(categories.items(), key=lambda x: -len(x[1])):
    steps = set(i[2] for i in items)
    print(f"  {cat:25s}: {len(items):4d} collisions (steps {min(steps)}-{max(steps)})")
