"""Build ontology.db from JSONL layer files + symbols.json.

Generates a SQLite database with:
  - symbols: glyph → English name, role, layer, depth
  - triples: every triple with form classification and depth
  - refs: dependency graph (which symbols appear in which triples)
"""

import json
import sqlite3
import glob
import os
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAYERS_DIR = os.path.join(ROOT, "layers")
SYMBOLS_FILE = os.path.join(ROOT, "symbols.json")
DB_FILE = os.path.join(ROOT, "ontology.db")

# --- Form classification by operator ---
FORM_MAP = {
    "⊨": "axiom",
    "⌂": "inhabitation",
    "≡": "definition",
    "↦": "type_sig",
    "ℒ": "law",
    "⊏": "domain",
    "⋔": "association",
    "𝕧": "variable",
    "!": "assertion",
    "?": "query",
    "≠": "axiom",
    "⇒": "law",
}
CONVENTION_OPS = {"Ϛ", "ℛ"}


def extract_atoms(expr):
    """Recursively extract all string atoms from a JSON expression."""
    if isinstance(expr, str):
        return {expr}
    if isinstance(expr, list):
        result = set()
        for item in expr:
            result |= extract_atoms(item)
        return result
    return set()


def classify_form(operator):
    """Determine the form of a triple from its operator."""
    if operator in FORM_MAP:
        return FORM_MAP[operator]
    if operator in CONVENTION_OPS:
        return "convention"
    return "law"


def load_layers():
    """Load all triples from JSONL layer files."""
    triples = []
    for path in sorted(glob.glob(os.path.join(LAYERS_DIR, "*.jsonl"))):
        layer = int(os.path.basename(path).split("_")[0])
        with open(path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                triple = json.loads(line)
                triples.append({
                    "raw": triple,
                    "subject": triple[0],
                    "operator": triple[1],
                    "object": triple[2],
                    "layer": layer,
                    "line": line_num,
                    "form": classify_form(triple[1]),
                })
    return triples


def discover_symbols(triples, label_data):
    """Build symbol catalog: every atom that appears, with metadata."""
    seen = {}
    for t in triples:
        atoms = extract_atoms(t["raw"])
        for atom in atoms:
            if atom not in seen:
                seen[atom] = t["layer"]

    symbols = {}
    for glyph, layer in seen.items():
        info = label_data.get(glyph, {"name": glyph, "role": "unknown"})
        symbols[glyph] = {
            "name": info["name"],
            "role": info["role"],
            "layer": layer,
            "depth": -1,
        }
    return symbols


def compute_depths(symbols, triples):
    """BFS depth computation from foundation axioms."""
    # Collect ≡ definitions: subject -> set of referenced symbols
    definitions = {}
    for t in triples:
        if t["form"] == "definition" and isinstance(t["subject"], str):
            refs = extract_atoms(t["object"])
            refs.discard(t["subject"])  # exclude self-references
            definitions[t["subject"]] = refs

    # Depth 0: foundation markers
    foundation = set()
    for t in triples:
        if t["operator"] == "⊨" and t["object"] == "⊤":
            subj = t["subject"] if isinstance(t["subject"], str) else None
            if subj:
                foundation.add(subj)

    # Depth 0: self-grounding (X ≡ X)
    self_grounding = set()
    for t in triples:
        if t["form"] == "definition" and isinstance(t["subject"], str):
            if t["object"] == t["subject"]:
                self_grounding.add(t["subject"])

    # Depth 0: everything without an ≡ definition (primitives, variables, digits, concept atoms)
    has_definition = set(definitions.keys())
    primitives = set(symbols.keys()) - has_definition

    # Initialize depth 0
    for g in foundation | self_grounding | primitives:
        if g in symbols:
            symbols[g]["depth"] = 0

    # BFS: resolve definitions iteratively
    changed = True
    passes = 0
    while changed:
        changed = False
        passes += 1
        for subj, refs in definitions.items():
            if subj not in symbols or symbols[subj]["depth"] != -1:
                continue
            # Check if all referenced symbols have resolved depths
            ref_depths = []
            all_resolved = True
            for r in refs:
                if r in symbols:
                    d = symbols[r]["depth"]
                    if d == -1:
                        all_resolved = False
                        break
                    ref_depths.append(d)
                else:
                    ref_depths.append(0)
            if all_resolved:
                symbols[subj]["depth"] = (max(ref_depths) + 1) if ref_depths else 1
                changed = True

    # Handle any remaining unresolved (circular definitions beyond self-grounding)
    for g, s in symbols.items():
        if s["depth"] == -1:
            s["depth"] = 0

    # Compute triple depths: max depth of all referenced symbols
    for t in triples:
        atoms = extract_atoms(t["raw"])
        depths = [symbols[a]["depth"] for a in atoms if a in symbols]
        t["depth"] = max(depths) if depths else 0

    return passes


def build_database(symbols, triples):
    """Create and populate the SQLite database."""
    if os.path.exists(DB_FILE):
        os.remove(DB_FILE)

    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()

    c.executescript("""
        CREATE TABLE symbols (
            glyph TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            role TEXT NOT NULL,
            layer INTEGER NOT NULL,
            depth INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE triples (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL,
            operator TEXT NOT NULL,
            object TEXT NOT NULL,
            layer INTEGER NOT NULL,
            line INTEGER NOT NULL,
            form TEXT NOT NULL,
            depth INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE refs (
            triple_id INTEGER NOT NULL REFERENCES triples(id),
            glyph TEXT NOT NULL,
            position TEXT NOT NULL
        );
        CREATE INDEX idx_refs_triple ON refs(triple_id);
        CREATE INDEX idx_refs_glyph ON refs(glyph);
    """)

    # Insert symbols
    for glyph, info in symbols.items():
        c.execute(
            "INSERT INTO symbols (glyph, name, role, layer, depth) VALUES (?, ?, ?, ?, ?)",
            (glyph, info["name"], info["role"], info["layer"], info["depth"]),
        )

    # Insert triples and refs
    for t in triples:
        subj_json = json.dumps(t["subject"], ensure_ascii=False)
        obj_json = json.dumps(t["object"], ensure_ascii=False)
        c.execute(
            "INSERT INTO triples (subject, operator, object, layer, line, form, depth) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (subj_json, t["operator"], obj_json, t["layer"], t["line"], t["form"], t["depth"]),
        )
        triple_id = c.lastrowid

        # Subject refs
        for atom in extract_atoms(t["subject"]):
            c.execute("INSERT INTO refs (triple_id, glyph, position) VALUES (?, ?, 'subject')", (triple_id, atom))
        # Operator ref
        c.execute("INSERT INTO refs (triple_id, glyph, position) VALUES (?, ?, 'operator')", (triple_id, t["operator"]))
        # Object refs
        for atom in extract_atoms(t["object"]):
            c.execute("INSERT INTO refs (triple_id, glyph, position) VALUES (?, ?, 'object')", (triple_id, atom))

    conn.commit()
    return conn


def print_stats(conn, symbols, triples, passes):
    """Print summary statistics."""
    c = conn.cursor()

    print("=== Ontology Database Built ===\n")
    print(f"Symbols: {len(symbols)}")
    print(f"Triples: {len(triples)}")
    print(f"Depth passes: {passes}")

    # Depth distribution
    c.execute("SELECT depth, COUNT(*) FROM symbols GROUP BY depth ORDER BY depth")
    print("\n=== Symbol Depth Distribution ===")
    for depth, count in c.fetchall():
        print(f"  depth {depth}: {count} symbols")

    # Unresolved check
    c.execute("SELECT COUNT(*) FROM symbols WHERE depth = -1")
    unresolved = c.fetchone()[0]
    if unresolved:
        print(f"\n  WARNING: {unresolved} unresolved symbols!")
        c.execute("SELECT glyph, name FROM symbols WHERE depth = -1")
        for g, n in c.fetchall():
            print(f"    {g} ({n})")

    # Deepest symbols
    c.execute("SELECT glyph, name, depth FROM symbols ORDER BY depth DESC LIMIT 10")
    print("\n=== Deepest Symbols ===")
    for g, n, d in c.fetchall():
        print(f"  {g} ({n}): depth {d}")

    # Form distribution
    c.execute("SELECT form, COUNT(*) FROM triples GROUP BY form ORDER BY COUNT(*) DESC")
    print("\n=== Triple Forms ===")
    for form, count in c.fetchall():
        print(f"  {form}: {count}")

    # Unknown labels
    c.execute("SELECT glyph FROM symbols WHERE name = glyph")
    unknowns = c.fetchall()
    if unknowns:
        print(f"\n=== Unlabeled Symbols ({len(unknowns)}) ===")
        for (g,) in unknowns:
            print(f"  {g}")

    print(f"\nDatabase: {DB_FILE}")


def main():
    # Load label data
    with open(SYMBOLS_FILE, "r", encoding="utf-8") as f:
        label_data = json.load(f)

    # Load triples
    triples = load_layers()

    # Discover symbols
    symbols = discover_symbols(triples, label_data)

    # Compute depths
    passes = compute_depths(symbols, triples)

    # Build database
    conn = build_database(symbols, triples)

    # Print stats
    print_stats(conn, symbols, triples, passes)

    conn.close()


if __name__ == "__main__":
    main()
