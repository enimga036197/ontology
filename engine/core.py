"""Collision engine: structural pattern discovery via database operations.

The database IS the model. State is save, save is state.

No VRAM, no gradients, no tokenizer. Patterns are stored as token-triples
in SQLite. Collisions — where multiple triples share structural form but
differ in specific tokens — are the engine's discoveries. Each discovery
gets a new opaque token and is fed back for the next step.

Hash collision mechanism: for each pattern, generate every possible template
by wildcarding each subset of leaf positions (up to max_wildcards deep).
Two patterns that produce the same template ARE a collision — a structural
similarity the engine discovers without being told what to look for.

All intermediate state (templates, collisions, patterns) lives in SQL.
Python holds at most one collision group at a time. No OOM regardless of scale.
"""

import json
import sqlite3
import secrets
import os
import sys
import io
from itertools import combinations

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
    """
    if isinstance(expr, str):
        return "_"
    if isinstance(expr, list):
        inner = ",".join(compute_shape(e) for e in expr)
        return f"[{inner}]"
    return "_"


def flatten_positions(expr, path=()):
    """Yield (path_tuple, token) for every leaf in the expression tree."""
    if isinstance(expr, str):
        yield (path, expr)
    elif isinstance(expr, list):
        for i, item in enumerate(expr):
            yield from flatten_positions(item, path + (i,))


def rebuild_with_path_map(expr, path_map, path=()):
    """Rebuild an expression tree, replacing leaf values per path->value map."""
    if isinstance(expr, str):
        return path_map.get(path, expr)
    if isinstance(expr, list):
        return [rebuild_with_path_map(e, path_map, path + (i,)) for i, e in enumerate(expr)]
    return expr


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

def generate_templates_for_pattern(expr, max_wildcards=3):
    """Generate wildcard templates from a token expression.

    Yields (template_json_str, wildcard_values_json_str) tuples.
    Polynomial complexity: O(N^max_wildcards) per pattern.
    """
    positions = list(flatten_positions(expr))
    n = len(positions)

    if n < 2:
        return

    max_w = min(max_wildcards, n - 1)

    for num_wild in range(1, max_w + 1):
        for wild_indices in combinations(range(n), num_wild):
            wild_set = set(wild_indices)
            path_map = {}
            wild_vals = {}
            wild_idx = 0

            for i, (path, token) in enumerate(positions):
                if i in wild_set:
                    wname = f"_{wild_idx}"
                    path_map[path] = wname
                    wild_vals[wname] = token
                    wild_idx += 1
                else:
                    path_map[path] = token

            template = rebuild_with_path_map(expr, path_map)
            template_json = json.dumps(template, ensure_ascii=False)
            yield (template_json, json.dumps(wild_vals, ensure_ascii=False))


# ---------------------------------------------------------------------------
# Translation
# ---------------------------------------------------------------------------

def build_glyph_to_token_map(ontology_conn):
    """Build glyph->token mapping from ontology.db."""
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
            weight REAL NOT NULL DEFAULT 1.0,
            indexed INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_patterns_step ON patterns(step);
        CREATE INDEX idx_patterns_indexed ON patterns(indexed);

        CREATE TABLE template_hashes (
            pattern_id INTEGER NOT NULL REFERENCES patterns(id),
            template TEXT NOT NULL,
            wildcard_values TEXT NOT NULL
        );
        CREATE INDEX idx_th_template ON template_hashes(template);

        CREATE TABLE collisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            template TEXT NOT NULL,
            variables TEXT NOT NULL,
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

        subj_tok = translate_expr(subj, glyph_map)
        op_tok = glyph_map.get(operator, operator)
        obj_tok = translate_expr(obj, glyph_map)

        triple_tok = [subj_tok, op_tok, obj_tok]
        shape = compute_shape(triple_tok)

        weight = (max_depth + 1 - depth) / (max_depth + 1)

        ec.execute(
            "INSERT INTO patterns (triple, shape, operator, step, depth, origin, weight) VALUES (?, ?, ?, 0, ?, 'seed', ?)",
            (json.dumps(triple_tok, ensure_ascii=False), shape, op_tok, depth, weight),
        )
        count += 1

    engine_conn.commit()
    return count


# ---------------------------------------------------------------------------
# Collision detection — SQL-backed, incremental, streaming
# ---------------------------------------------------------------------------

def index_new_patterns(engine_conn):
    """Generate template hashes for patterns not yet indexed.

    Templates are written directly to SQL. Python never holds the full set.
    Returns the number of new patterns indexed.
    """
    ec = engine_conn.cursor()

    ec.execute("SELECT id, triple FROM patterns WHERE indexed = 0")
    new_patterns = ec.fetchall()

    if not new_patterns:
        return 0

    batch = []
    for pid, triple_json in new_patterns:
        expr = json.loads(triple_json)
        for template_json, wild_vals_json in generate_templates_for_pattern(expr):
            batch.append((pid, template_json, wild_vals_json))

        # Flush in chunks to avoid building a huge list
        if len(batch) >= 10000:
            ec.executemany(
                "INSERT INTO template_hashes (pattern_id, template, wildcard_values) VALUES (?, ?, ?)",
                batch,
            )
            batch.clear()

    if batch:
        ec.executemany(
            "INSERT INTO template_hashes (pattern_id, template, wildcard_values) VALUES (?, ?, ?)",
            batch,
        )

    # Mark as indexed
    for pid, _ in new_patterns:
        ec.execute("UPDATE patterns SET indexed = 1 WHERE id = ?", (pid,))

    engine_conn.commit()
    return len(new_patterns)


def get_known_collisions(engine_conn):
    """Get the map of template -> max member_count seen so far."""
    ec = engine_conn.cursor()
    ec.execute("SELECT template, MAX(member_count) FROM collisions GROUP BY template")
    return dict(ec.fetchall())


def find_and_process_collisions(engine_conn, step, used_tokens, known_max):
    """Find collisions via SQL GROUP BY, process one group at a time.

    1. index_new_patterns() writes template hashes to SQL (incremental)
    2. SQL GROUP BY finds all templates with 2+ matching patterns
    3. Each group is fetched, checked, and processed individually
       — Python holds at most one group's members at a time

    Returns (new_results_for_display, confirmed_count, grew_count).
    """
    ec = engine_conn.cursor()

    # Step 1: index any new patterns since last call
    index_new_patterns(engine_conn)

    # Step 2: find candidate collision groups via SQL
    ec.execute("""
        SELECT template, COUNT(*) as cnt
        FROM template_hashes
        GROUP BY template
        HAVING cnt >= 2
    """)
    candidates = ec.fetchall()

    new_results = []
    confirmed = 0
    grew = 0

    # Step 3: stream one group at a time
    for template_json, cnt in candidates:
        # Fetch members for this single group
        ec.execute(
            "SELECT pattern_id, wildcard_values FROM template_hashes WHERE template = ?",
            (template_json,),
        )
        members = ec.fetchall()

        # Aggregate wildcard values
        all_wild_names = set()
        parsed_vals = []
        for pid, wv_json in members:
            wv = json.loads(wv_json)
            parsed_vals.append((pid, wv))
            all_wild_names.update(wv.keys())

        variables = {}
        for wname in sorted(all_wild_names):
            variables[wname] = [pv[1].get(wname, "") for pv in parsed_vals]

        # Filter: every wildcard must have 2+ distinct values
        all_vary = True
        for vals in variables.values():
            if len(set(vals)) < 2:
                all_vary = False
                break

        if not all_vary:
            continue

        member_count = len(parsed_vals)
        pattern_ids = [pv[0] for pv in parsed_vals]
        variables_json = json.dumps(variables, ensure_ascii=False)

        # Check against known collisions
        prev_max = known_max.get(template_json, 0)

        if member_count <= prev_max:
            confirmed += 1
            continue

        # GREW or NEW
        if prev_max > 0:
            grew += 1

        known_max[template_json] = member_count

        # Mint token
        new_token = mint_token(used_tokens)

        template = json.loads(template_json)
        definition = {
            "template": template,
            "variables": variables,
            "member_count": member_count,
        }
        definition_json = json.dumps(definition, ensure_ascii=False)

        ec.execute(
            "INSERT INTO collisions (template, variables, member_count, step, output_token, definition) VALUES (?, ?, ?, ?, ?, ?)",
            (template_json, variables_json, member_count, step, new_token, definition_json),
        )
        collision_id = ec.lastrowid

        for pid in pattern_ids:
            ec.execute(
                "INSERT INTO collision_members (collision_id, pattern_id) VALUES (?, ?)",
                (collision_id, pid),
            )

        ec.execute(
            "INSERT INTO vocabulary (token, name, origin, step) VALUES (?, ?, 'derived', ?)",
            (new_token, f"collision-{collision_id}", step),
        )

        # Derived pattern
        derived_weight = min(1.0, member_count / 10.0)
        derived_triple = [new_token, "\u2261", template]
        derived_shape = compute_shape(derived_triple)
        ec.execute(
            "INSERT INTO patterns (triple, shape, operator, step, depth, origin, weight) VALUES (?, ?, ?, ?, ?, 'derived', ?)",
            (json.dumps(derived_triple, ensure_ascii=False), derived_shape, "\u2261", step, step + 1, derived_weight),
        )

        new_results.append({
            "collision_id": collision_id,
            "token": new_token,
            "template": template,
            "variables": variables,
            "members": member_count,
            "grew_from": prev_max if prev_max > 0 else None,
        })

        # Free parsed_vals for this group
        del parsed_vals, members

    engine_conn.commit()
    return new_results, confirmed, grew


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_step(engine_conn, ontology_conn, glyph_map, step):
    """Check if engine discoveries correspond to ontology statements."""
    ec = engine_conn.cursor()
    oc = ontology_conn.cursor()

    ec.execute("SELECT id, template, variables, member_count FROM collisions WHERE step = ?", (step,))
    collisions = ec.fetchall()

    token_to_glyph = {v: k for k, v in glyph_map.items()}

    validations = []
    for cid, template_json, variables_json, member_count in collisions:
        template = json.loads(template_json)
        variables = json.loads(variables_json)

        def detokenize(expr):
            if isinstance(expr, str):
                if expr.startswith("_"):
                    return expr
                return token_to_glyph.get(expr, expr)
            if isinstance(expr, list):
                return [detokenize(e) for e in expr]
            return expr

        glyph_template = detokenize(template)

        constant_tokens = set()
        for pos, tok in flatten_positions(template):
            if isinstance(tok, str) and not tok.startswith("_"):
                glyph = token_to_glyph.get(tok, "")
                if glyph:
                    constant_tokens.add(glyph)

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
