"""Collision engine: structural pattern discovery via database operations.

The database IS the model. Ingestion is training. Structural collision is
inference. Compounding tokenization is learning.

No VRAM, no gradients, no tokenizer. Patterns are stored as token-triples
in SQLite. Collisions — where multiple triples share structural form but
differ in specific tokens — are the engine's discoveries. Each discovery
gets a new opaque token and is fed back for the next step.
"""

import json
import sqlite3
import secrets
import os
import sys
import io

if not isinstance(sys.stdout, io.TextIOWrapper) or sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ONTOLOGY_DB = os.path.join(ROOT, "ontology.db")
ENGINE_DB = os.path.join(ROOT, "engine", "engine.db")


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------

def mint_token(used):
    """Cryptographically random 6-digit token, digits 1-9, no zeros."""
    while True:
        token = "".join(str(secrets.randbelow(9) + 1) for _ in range(6))
        if token not in used:
            used.add(token)
            return token


# ---------------------------------------------------------------------------
# Structural hashing
# ---------------------------------------------------------------------------

def compute_shape(expr):
    """Compute the structural shape of a token expression.

    Replaces every leaf token with '_', preserving tree structure.
    Returns a canonical string for grouping.

    Examples:
        "618371"                    → "_"
        ["618371", "417247"]        → "[_,_]"
        ["618371", ["417247", "X"]] → "[_,[_,_]]"
    """
    if isinstance(expr, str):
        return "_"
    if isinstance(expr, list):
        inner = ",".join(compute_shape(e) for e in expr)
        return f"[{inner}]"
    return "_"


def flatten_positions(expr, path=()):
    """Yield (path_tuple, token) for every leaf in the expression tree.

    Path encodes position: (0,) is first element, (2, 1) is second element
    inside the third element, etc.
    """
    if isinstance(expr, str):
        yield (path, expr)
    elif isinstance(expr, list):
        for i, item in enumerate(expr):
            yield from flatten_positions(item, path + (i,))


def rebuild_from_positions(shape_expr, position_map):
    """Rebuild an expression from a shape template and position→value map."""
    if isinstance(shape_expr, str):
        return shape_expr
    if isinstance(shape_expr, list):
        return [rebuild_from_positions(e, position_map) for e in shape_expr]


# ---------------------------------------------------------------------------
# Template extraction
# ---------------------------------------------------------------------------

def extract_template(triples_token_exprs):
    """Given a list of token-space triples that share structure, extract
    the shared template with co-varying wildcard positions.

    Returns (template, variables) where:
        template: the expression with _N wildcards
        variables: {wildcard: [values across instances]}
        bindings: {wildcard: set of positions it appears in}
    """
    if not triples_token_exprs:
        return None, None, None

    # Get all position→token maps
    all_positions = []
    for expr in triples_token_exprs:
        pos_map = dict(flatten_positions(expr))
        all_positions.append(pos_map)

    # Get the union of all positions (should be identical since same shape)
    positions = sorted(all_positions[0].keys())

    # For each position, collect the set of values across all triples
    pos_values = {}
    for pos in positions:
        vals = tuple(pm.get(pos, "") for pm in all_positions)
        pos_values[pos] = vals

    # Classify each position: CONSTANT (same value everywhere) or VARYING
    constants = {}  # pos → token
    varying = {}    # pos → tuple of values

    for pos, vals in pos_values.items():
        if len(set(vals)) == 1:
            constants[pos] = vals[0]
        else:
            varying[pos] = vals

    # Detect co-varying positions: positions that always have the same token
    # as each other across all instances
    covar_groups = []
    varying_positions = list(varying.keys())
    assigned = set()

    for i, pos_a in enumerate(varying_positions):
        if pos_a in assigned:
            continue
        group = [pos_a]
        assigned.add(pos_a)
        for pos_b in varying_positions[i + 1:]:
            if pos_b in assigned:
                continue
            if varying[pos_a] == varying[pos_b]:
                group.append(pos_b)
                assigned.add(pos_b)
        covar_groups.append(group)

    # Assign wildcard names
    wildcard_map = {}  # pos → wildcard name
    variables = {}     # wildcard name → list of values
    bindings = {}      # wildcard name → set of positions

    for idx, group in enumerate(covar_groups):
        name = f"_{idx}"
        for pos in group:
            wildcard_map[pos] = name
        variables[name] = list(varying[group[0]])
        bindings[name] = set(group)

    # Build the template expression
    def build_template(expr, path=()):
        if isinstance(expr, str):
            if path in constants:
                return constants[path]
            elif path in wildcard_map:
                return wildcard_map[path]
            else:
                return expr
        elif isinstance(expr, list):
            return [build_template(e, path + (i,)) for i, e in enumerate(expr)]
        return expr

    # Use the first triple as the structural scaffold
    template = build_template(triples_token_exprs[0])

    return template, variables, bindings


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def build_glyph_to_token_map(ontology_conn):
    """Build glyph→token mapping from ontology.db."""
    c = ontology_conn.cursor()
    c.execute("SELECT glyph, token FROM symbols")
    return dict(c.fetchall())


def translate_expr(expr, glyph_map):
    """Recursively translate a glyph expression to token expression."""
    if isinstance(expr, str):
        return glyph_map.get(expr, expr)
    if isinstance(expr, list):
        return [translate_expr(e, glyph_map) for e in expr]
    return expr


# ---------------------------------------------------------------------------
# Engine database
# ---------------------------------------------------------------------------

def create_engine_db():
    """Create fresh engine database."""
    if os.path.exists(ENGINE_DB):
        os.remove(ENGINE_DB)

    conn = sqlite3.connect(ENGINE_DB)
    c = conn.cursor()
    c.executescript("""
        CREATE TABLE vocabulary (
            token TEXT PRIMARY KEY,
            name TEXT,
            origin TEXT NOT NULL,
            step INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE patterns (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            triple TEXT NOT NULL,
            shape TEXT NOT NULL,
            operator TEXT NOT NULL,
            step INTEGER NOT NULL,
            depth INTEGER NOT NULL,
            origin TEXT NOT NULL,
            weight REAL NOT NULL DEFAULT 1.0
        );
        CREATE INDEX idx_patterns_step ON patterns(step);
        CREATE INDEX idx_patterns_op_shape ON patterns(operator, shape);

        CREATE TABLE collisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template TEXT NOT NULL,
            variables TEXT NOT NULL,
            bindings TEXT NOT NULL,
            member_count INTEGER NOT NULL,
            step INTEGER NOT NULL,
            output_token TEXT UNIQUE,
            definition TEXT NOT NULL
        );

        CREATE TABLE collision_members (
            collision_id INTEGER NOT NULL REFERENCES collisions(id),
            pattern_id INTEGER NOT NULL REFERENCES patterns(id)
        );
        CREATE INDEX idx_cm_collision ON collision_members(collision_id);
        CREATE INDEX idx_cm_pattern ON collision_members(pattern_id);
    """)
    conn.commit()
    return conn


def seed_vocabulary(engine_conn, ontology_conn):
    """Import all ontology tokens into engine vocabulary."""
    oc = ontology_conn.cursor()
    ec = engine_conn.cursor()

    oc.execute("SELECT token, name FROM symbols")
    for token, name in oc.fetchall():
        ec.execute(
            "INSERT OR IGNORE INTO vocabulary (token, name, origin, step) VALUES (?, ?, 'seed', 0)",
            (token, name),
        )
    engine_conn.commit()


def get_max_ontology_depth(ontology_conn):
    """Get the maximum depth value in the ontology."""
    c = ontology_conn.cursor()
    c.execute("SELECT MAX(depth) FROM triples")
    return c.fetchone()[0] or 0


def ingest_all_triples(engine_conn, ontology_conn, glyph_map):
    """Translate and ingest ALL ontology triples at step 0.

    Every triple gets a weight inversely proportional to its depth:
        weight = (max_depth + 1 - depth) / (max_depth + 1)
    So depth-0 (foundation) has weight 1.0, deepest has lowest weight.
    """
    oc = ontology_conn.cursor()
    ec = engine_conn.cursor()

    max_depth = get_max_ontology_depth(ontology_conn)

    oc.execute("SELECT subject, operator, object, depth FROM triples")
    count = 0
    for subj_json, operator, obj_json, depth in oc.fetchall():
        subj = json.loads(subj_json)
        obj = json.loads(obj_json)

        # Translate to token space
        subj_tok = translate_expr(subj, glyph_map)
        op_tok = glyph_map.get(operator, operator)
        obj_tok = translate_expr(obj, glyph_map)

        triple_tok = [subj_tok, op_tok, obj_tok]
        shape = compute_shape(triple_tok)

        # Weight: foundation triples weigh most
        weight = (max_depth + 1 - depth) / (max_depth + 1)

        ec.execute(
            "INSERT INTO patterns (triple, shape, operator, step, depth, origin, weight) VALUES (?, ?, ?, 0, ?, 'seed', ?)",
            (json.dumps(triple_tok, ensure_ascii=False), shape, op_tok, depth, weight),
        )
        count += 1

    engine_conn.commit()
    return count


# ---------------------------------------------------------------------------
# Collision detection
# ---------------------------------------------------------------------------

def find_collisions(engine_conn):
    """Find structural collisions across ALL patterns in the database.

    Groups patterns by (operator, shape) and extracts templates from
    groups with 2+ members.
    """
    ec = engine_conn.cursor()

    # Find groups with same operator and shape — across everything
    ec.execute("""
        SELECT operator, shape, GROUP_CONCAT(id) as ids, COUNT(*) as cnt
        FROM patterns
        GROUP BY operator, shape
        HAVING cnt >= 2
    """)

    collision_groups = []
    for op, shape, ids_str, cnt in ec.fetchall():
        pattern_ids = [int(x) for x in ids_str.split(",")]

        # Fetch the actual triples
        triples = []
        for pid in pattern_ids:
            ec.execute("SELECT triple FROM patterns WHERE id = ?", (pid,))
            row = ec.fetchone()
            if row:
                triples.append((pid, json.loads(row[0])))

        if len(triples) >= 2:
            collision_groups.append({
                "operator": op,
                "shape": shape,
                "patterns": triples,  # [(id, triple_expr), ...]
            })

    return collision_groups


def get_known_collision_keys(engine_conn):
    """Get the set of template+member_count keys for already-discovered collisions."""
    ec = engine_conn.cursor()
    ec.execute("SELECT template, member_count FROM collisions")
    return {(row[0], row[1]) for row in ec.fetchall()}


def process_collisions(engine_conn, collision_groups, step, used_tokens, known_keys):
    """Extract templates from collision groups and mint new tokens.

    Skips collision groups that exactly match a previously discovered
    collision (same template, same member count). Only NEW or GROWN
    collision groups produce new tokens.
    """
    ec = engine_conn.cursor()
    results = []

    for group in collision_groups:
        triple_exprs = [t[1] for t in group["patterns"]]
        pattern_ids = [t[0] for t in group["patterns"]]

        template, variables, bindings = extract_template(triple_exprs)
        if template is None or not variables:
            continue  # no varying positions — exact duplicates, not collisions

        # Serialize for storage
        template_json = json.dumps(template, ensure_ascii=False)
        variables_json = json.dumps(variables, ensure_ascii=False)
        bindings_json = json.dumps(
            {k: [list(p) for p in v] for k, v in bindings.items()},
            ensure_ascii=False,
        )

        # Deduplication: skip if we already found this exact collision
        collision_key = (template_json, len(triple_exprs))
        if collision_key in known_keys:
            continue
        known_keys.add(collision_key)

        # Mint a new token for this discovery
        new_token = mint_token(used_tokens)

        # Build definition
        definition = {
            "template": template,
            "variables": variables,
            "member_count": len(triple_exprs),
        }
        definition_json = json.dumps(definition, ensure_ascii=False)

        # Store collision
        ec.execute(
            "INSERT INTO collisions (template, variables, bindings, member_count, step, output_token, definition) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (template_json, variables_json, bindings_json, len(triple_exprs), step, new_token, definition_json),
        )
        collision_id = ec.lastrowid

        # Store member links
        for pid in pattern_ids:
            ec.execute(
                "INSERT INTO collision_members (collision_id, pattern_id) VALUES (?, ?)",
                (collision_id, pid),
            )

        # Add to vocabulary
        ec.execute(
            "INSERT INTO vocabulary (token, name, origin, step) VALUES (?, ?, 'derived', ?)",
            (new_token, f"collision-{collision_id}", step),
        )

        # Create derived pattern with weight based on member count
        # More instances = higher confidence = higher weight
        derived_weight = min(1.0, len(triple_exprs) / 10.0)
        derived_triple = [new_token, "≡", template]
        derived_shape = compute_shape(derived_triple)
        ec.execute(
            "INSERT INTO patterns (triple, shape, operator, step, depth, origin, weight) VALUES (?, ?, ?, ?, ?, 'derived', ?)",
            (json.dumps(derived_triple, ensure_ascii=False), derived_shape, "≡", step, step + 1, derived_weight),
        )

        results.append({
            "collision_id": collision_id,
            "token": new_token,
            "template": template,
            "variables": variables,
            "members": len(triple_exprs),
        })

    engine_conn.commit()
    return results


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_step(engine_conn, ontology_conn, glyph_map, step):
    """Check if engine discoveries correspond to ontology statements.

    For each collision template, check if the ontology contains an explicit
    universal (∀) or definition (≡) that captures the same pattern.
    """
    ec = engine_conn.cursor()
    oc = ontology_conn.cursor()

    # Get this step's collisions
    ec.execute("SELECT id, template, variables, member_count FROM collisions WHERE step = ?", (step,))
    collisions = ec.fetchall()

    # Get ontology definitions and laws for comparison
    # Reverse the glyph map for token→glyph lookup
    token_to_glyph = {v: k for k, v in glyph_map.items()}

    validations = []
    for cid, template_json, variables_json, member_count in collisions:
        template = json.loads(template_json)
        variables = json.loads(variables_json)

        # Translate template back to glyph space for comparison
        def detokenize(expr):
            if isinstance(expr, str):
                if expr.startswith("_"):
                    return expr  # keep wildcards
                return token_to_glyph.get(expr, expr)
            if isinstance(expr, list):
                return [detokenize(e) for e in expr]
            return expr

        glyph_template = detokenize(template)

        # Check if any constant token in the template has an explicit ≡ definition
        # in the ontology (meaning the ontology formalizes what the engine discovered)
        constant_tokens = set()
        for pos, tok in flatten_positions(template):
            if isinstance(tok, str) and not tok.startswith("_"):
                glyph = token_to_glyph.get(tok, "")
                if glyph:
                    constant_tokens.add(glyph)

        # Look for ontology definitions of the constant symbols
        matches = []
        for glyph in constant_tokens:
            oc.execute(
                "SELECT subject, operator, object FROM triples WHERE subject = ? AND form = 'definition'",
                (json.dumps(glyph, ensure_ascii=False),),
            )
            for row in oc.fetchall():
                matches.append(row)

        validations.append({
            "collision_id": cid,
            "glyph_template": glyph_template,
            "member_count": member_count,
            "variable_count": len(variables),
            "ontology_matches": len(matches),
        })

    return validations
