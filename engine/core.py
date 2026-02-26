"""Collision engine: structural pattern discovery via database operations.

The database IS the model. State is save, save is state.

No VRAM, no gradients, no tokenizer. Patterns are stored as token-triples
in SQLite. Collisions — where multiple triples share structural form but
differ in specific tokens — are the engine's discoveries. Each discovery
gets a new opaque token and is fed back for the next step.

Hash collision mechanism: for each pattern, generate every possible template
by wildcarding each subset of leaf positions (up to max_wildcards leaves).
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


def apply_pragmas(conn):
    """Set SQLite performance pragmas. WAL + large cache + memory temp store."""
    c = conn.cursor()
    c.execute("PRAGMA journal_mode=WAL")
    c.execute("PRAGMA synchronous=NORMAL")
    c.execute("PRAGMA cache_size=-128000")   # 128MB page cache
    c.execute("PRAGMA mmap_size=536870912")  # 512MB memory-mapped I/O
    c.execute("PRAGMA temp_store=MEMORY")


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


# ---------------------------------------------------------------------------
# Template generation
# ---------------------------------------------------------------------------

def rebuild_with_map(expr, path_map, path=()):
    """Rebuild expression tree, replacing leaf values per path->value map."""
    if isinstance(expr, str):
        return path_map.get(path, expr)
    if isinstance(expr, list):
        return [rebuild_with_map(e, path_map, path + (i,)) for i, e in enumerate(expr)]
    return expr


def generate_templates_for_pattern(expr, max_wildcards=3):
    """Generate wildcard templates from a token expression.

    Leaf-only wildcarding: replace subsets of leaf tokens with wildcard names.
    Two patterns that produce the same template ARE a collision — they share
    structural form but differ in specific leaf tokens.

    Yields (template_json_str, wildcard_values_json_str) tuples.
    """
    leaves = list(flatten_positions(expr))
    n = len(leaves)

    if n < 2:
        return

    max_w = min(max_wildcards, n - 1)
    seen = set()

    for num_wild in range(1, max_w + 1):
        for wild_indices in combinations(range(n), num_wild):
            path_map = {}
            wild_vals = {}

            for wild_idx, i in enumerate(wild_indices):
                path, token = leaves[i]
                wname = f"_{wild_idx}"
                path_map[path] = wname
                wild_vals[wname] = token

            template = rebuild_with_map(expr, path_map)
            template_json = json.dumps(template, ensure_ascii=False)

            if template_json in seen:
                continue
            seen.add(template_json)

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
    apply_pragmas(conn)
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
            wildcard_values TEXT NOT NULL,
            indexing_step INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX idx_th_template ON template_hashes(template);
        CREATE INDEX idx_th_step ON template_hashes(indexing_step);

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

        -- Phase 2: membership collision tables
        CREATE TABLE collision_subjects (
            collision_id INTEGER NOT NULL REFERENCES collisions(id),
            subject_token TEXT NOT NULL,
            indexing_step INTEGER NOT NULL
        );
        CREATE INDEX idx_cs_collision ON collision_subjects(collision_id);
        CREATE INDEX idx_cs_subject ON collision_subjects(subject_token);
        CREATE INDEX idx_cs_step ON collision_subjects(indexing_step);

        CREATE TABLE membership_hashes (
            collision_id INTEGER NOT NULL REFERENCES collisions(id),
            subject_set_key TEXT NOT NULL,
            subject_count INTEGER NOT NULL,
            indexing_step INTEGER NOT NULL
        );
        CREATE INDEX idx_mh_key ON membership_hashes(subject_set_key);
        CREATE INDEX idx_mh_step ON membership_hashes(indexing_step);

        CREATE TABLE membership_collisions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject_set_key TEXT NOT NULL,
            collision_ids TEXT NOT NULL,
            collision_count INTEGER NOT NULL,
            collision_score REAL NOT NULL DEFAULT 0.0,
            subject_count INTEGER NOT NULL,
            step INTEGER NOT NULL,
            output_token TEXT UNIQUE,
            definition TEXT NOT NULL
        );

        CREATE TABLE membership_collision_members (
            membership_collision_id INTEGER NOT NULL REFERENCES membership_collisions(id),
            collision_id INTEGER NOT NULL REFERENCES collisions(id)
        );
        CREATE INDEX idx_mcm_mc ON membership_collision_members(membership_collision_id);
        CREATE INDEX idx_mcm_collision ON membership_collision_members(collision_id);
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

def index_new_patterns(engine_conn, step):
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
            batch.append((pid, template_json, wild_vals_json, step))

        # Flush in chunks to avoid building a huge list
        if len(batch) >= 10000:
            ec.executemany(
                "INSERT INTO template_hashes (pattern_id, template, wildcard_values, indexing_step) VALUES (?, ?, ?, ?)",
                batch,
            )
            batch.clear()

    if batch:
        ec.executemany(
            "INSERT INTO template_hashes (pattern_id, template, wildcard_values, indexing_step) VALUES (?, ?, ?, ?)",
            batch,
        )

    # Batch mark as indexed
    ec.execute("UPDATE patterns SET indexed = 1 WHERE indexed = 0")

    engine_conn.commit()
    return len(new_patterns)


def get_known_collisions(engine_conn):
    """Get the map of template -> max member_count seen so far."""
    ec = engine_conn.cursor()
    ec.execute("SELECT template, MAX(member_count) FROM collisions GROUP BY template")
    return dict(ec.fetchall())


def find_and_process_collisions(engine_conn, step, used_tokens, known_max, equiv_token):
    """Find collisions via SQL GROUP BY, process one group at a time.

    1. index_new_patterns() writes template hashes to SQL (incremental)
    2. SQL finds templates that got NEW members this step (via indexing_step)
    3. Only those templates are checked — not the entire table
    4. Previously known collisions without new members are confirmed by definition

    equiv_token: the opaque token for ≡, so derived patterns stay fully tokenized.

    Returns (new_results_for_display, confirmed_count, grew_count).
    """
    ec = engine_conn.cursor()

    # All previously known collisions are confirmed (we never delete patterns)
    confirmed = len(known_max)

    # Step 1: index any new patterns since last call
    index_new_patterns(engine_conn, step)

    # Step 2: find candidates — only templates that got new rows this step
    ec.execute("""
        SELECT th.template, COUNT(*) as cnt
        FROM template_hashes th
        WHERE th.template IN (
            SELECT DISTINCT template FROM template_hashes WHERE indexing_step = ?
        )
        GROUP BY th.template
        HAVING cnt >= 2
    """, (step,))
    candidates = ec.fetchall()

    new_results = []
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

        # Derived pattern — tokenize wildcards so they don't leak as shared constants
        derived_weight = min(1.0, member_count / 10.0)

        def tokenize_wildcards(expr):
            """Replace wildcard names (_0, _1, ...) with fresh opaque tokens."""
            if isinstance(expr, str):
                if expr.startswith("_") and expr[1:].isdigit():
                    wtoken = mint_token(used_tokens)
                    ec.execute(
                        "INSERT INTO vocabulary (token, name, origin, step) VALUES (?, ?, 'derived', ?)",
                        (wtoken, f"wild-{expr}", step),
                    )
                    return wtoken
                return expr
            if isinstance(expr, list):
                return [tokenize_wildcards(e) for e in expr]
            return expr

        tokenized_template = tokenize_wildcards(template)
        derived_triple = [new_token, equiv_token, tokenized_template]
        derived_shape = compute_shape(derived_triple)
        ec.execute(
            "INSERT INTO patterns (triple, shape, operator, step, depth, origin, weight) VALUES (?, ?, ?, ?, ?, 'derived', ?)",
            (json.dumps(derived_triple, ensure_ascii=False), derived_shape, equiv_token, step, step + 1, derived_weight),
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
# Phase 2: Membership collision detection
# ---------------------------------------------------------------------------

def extract_collision_subjects(engine_conn, step):
    """Extract subject tokens for collisions discovered at the current step.

    The "subject" of a collision is the set of distinct triple[0] values
    from its member patterns. Only collisions with 2+ distinct subjects
    are indexed.

    Returns count of collisions indexed.
    """
    ec = engine_conn.cursor()

    ec.execute("""
        SELECT c.id
        FROM collisions c
        WHERE c.step = ?
        AND c.id NOT IN (SELECT DISTINCT collision_id FROM collision_subjects)
    """, (step,))
    new_collision_ids = [row[0] for row in ec.fetchall()]

    if not new_collision_ids:
        return 0

    count = 0
    for cid in new_collision_ids:
        ec.execute("""
            SELECT DISTINCT json_extract(p.triple, '$[0]') as subject
            FROM collision_members cm
            JOIN patterns p ON p.id = cm.pattern_id
            WHERE cm.collision_id = ?
        """, (cid,))
        subjects = [row[0] for row in ec.fetchall()]

        if len(subjects) < 2:
            continue

        for subj_tok in subjects:
            ec.execute(
                "INSERT INTO collision_subjects (collision_id, subject_token, indexing_step) VALUES (?, ?, ?)",
                (cid, subj_tok, step),
            )
        count += 1

    engine_conn.commit()
    return count


def generate_membership_hashes(engine_conn, step, max_drops=2, min_subset_size=2):
    """Generate membership hash keys for collision subject sets.

    For each collision, takes its subject set and generates canonical
    subset keys by dropping up to max_drops members. Parallels Phase 1's
    template generation.

    Returns count of hashes generated.
    """
    ec = engine_conn.cursor()

    ec.execute("""
        SELECT DISTINCT cs.collision_id
        FROM collision_subjects cs
        WHERE cs.indexing_step = ?
        AND cs.collision_id NOT IN (
            SELECT DISTINCT collision_id FROM membership_hashes
        )
    """, (step,))
    collision_ids = [row[0] for row in ec.fetchall()]

    if not collision_ids:
        return 0

    total_hashes = 0
    batch = []

    for cid in collision_ids:
        ec.execute(
            "SELECT subject_token FROM collision_subjects WHERE collision_id = ?",
            (cid,),
        )
        subjects = sorted(row[0] for row in ec.fetchall())
        n = len(subjects)

        if n < min_subset_size:
            continue

        seen_keys = set()

        # Full set
        full_key = json.dumps(subjects, ensure_ascii=False)
        batch.append((cid, full_key, n, step))
        seen_keys.add(full_key)

        # Subsets by dropping up to max_drops members
        effective_max_drops = min(max_drops, n - min_subset_size)
        for num_drop in range(1, effective_max_drops + 1):
            for drop_indices in combinations(range(n), num_drop):
                subset = [subjects[i] for i in range(n) if i not in drop_indices]
                subset_key = json.dumps(subset, ensure_ascii=False)
                if subset_key not in seen_keys:
                    seen_keys.add(subset_key)
                    batch.append((cid, subset_key, len(subset), step))

        if len(batch) >= 5000:
            ec.executemany(
                "INSERT INTO membership_hashes (collision_id, subject_set_key, subject_count, indexing_step) VALUES (?, ?, ?, ?)",
                batch,
            )
            total_hashes += len(batch)
            batch.clear()

    if batch:
        ec.executemany(
            "INSERT INTO membership_hashes (collision_id, subject_set_key, subject_count, indexing_step) VALUES (?, ?, ?, ?)",
            batch,
        )
        total_hashes += len(batch)

    engine_conn.commit()
    return total_hashes


def get_known_membership_collisions(engine_conn):
    """Get map of subject_set_key -> max collision_score seen so far."""
    ec = engine_conn.cursor()
    ec.execute("SELECT subject_set_key, MAX(collision_score) FROM membership_collisions GROUP BY subject_set_key")
    return dict(ec.fetchall())


def find_membership_collisions(engine_conn, step, used_tokens, known_membership_max,
                                equiv_token, conj_token, member_of_token):
    """Find membership collisions: groups of Phase 1 collisions sharing subjects.

    Phase 1 groups patterns by template -> collisions (properties).
    Phase 2 groups collisions by subject set -> theories (property conjunctions).

    Returns (new_results, confirmed_count, grew_count).
    """
    ec = engine_conn.cursor()

    confirmed = len(known_membership_max)

    # Step 1: extract subjects for new collisions
    extract_collision_subjects(engine_conn, step)

    # Step 2: generate membership hashes
    generate_membership_hashes(engine_conn, step)

    # Step 3: find candidates — subject_set_keys that got new entries this step
    ec.execute("""
        SELECT mh.subject_set_key, COUNT(DISTINCT mh.collision_id) as cnt
        FROM membership_hashes mh
        WHERE mh.subject_set_key IN (
            SELECT DISTINCT subject_set_key FROM membership_hashes WHERE indexing_step = ?
        )
        GROUP BY mh.subject_set_key
        HAVING cnt >= 2
    """, (step,))
    candidates = ec.fetchall()

    new_results = []
    grew = 0

    for subject_set_key, cnt in candidates:
        ec.execute(
            """SELECT DISTINCT mh.collision_id, c.member_count
               FROM membership_hashes mh
               JOIN collisions c ON c.id = mh.collision_id
               WHERE mh.subject_set_key = ?""",
            (subject_set_key,),
        )
        rows = ec.fetchall()
        collision_ids = sorted(r[0] for r in rows)
        collision_count = len(collision_ids)
        # Specificity score: rarer collisions (fewer members) carry more weight
        collision_score = sum(1.0 / max(r[1], 1) for r in rows)

        subject_set = json.loads(subject_set_key)
        subject_count = len(subject_set)

        prev_max = known_membership_max.get(subject_set_key, 0.0)
        if collision_score <= prev_max:
            continue

        if prev_max > 0:
            grew += 1
        known_membership_max[subject_set_key] = collision_score

        # Mint theory token
        theory_token = mint_token(used_tokens)

        # Get output tokens of member collisions for the conjunction
        member_collision_tokens = []
        for cid in collision_ids:
            ec.execute("SELECT output_token FROM collisions WHERE id = ?", (cid,))
            row = ec.fetchone()
            if row and row[0]:
                member_collision_tokens.append(row[0])

        if len(member_collision_tokens) < 2:
            continue

        # Right-fold conjunction: [C_a, ∧, [C_b, ∧, C_c]]
        def build_conjunction(tokens):
            if len(tokens) == 1:
                return tokens[0]
            return [tokens[0], conj_token, build_conjunction(tokens[1:])]

        conj_expr = build_conjunction(member_collision_tokens)

        definition = {
            "subject_set": subject_set,
            "collision_ids": collision_ids,
            "collision_count": collision_count,
            "collision_score": collision_score,
            "subject_count": subject_count,
        }
        definition_json = json.dumps(definition, ensure_ascii=False)

        ec.execute(
            """INSERT INTO membership_collisions
               (subject_set_key, collision_ids, collision_count, collision_score, subject_count, step, output_token, definition)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (subject_set_key, json.dumps(collision_ids), collision_count, collision_score, subject_count,
             step, theory_token, definition_json),
        )
        mc_id = ec.lastrowid

        for cid in collision_ids:
            ec.execute(
                "INSERT INTO membership_collision_members (membership_collision_id, collision_id) VALUES (?, ?)",
                (mc_id, cid),
            )

        ec.execute(
            "INSERT INTO vocabulary (token, name, origin, step) VALUES (?, ?, 'derived', ?)",
            (theory_token, f"theory-{mc_id}", step),
        )

        # Derived patterns — weight by specificity-aware score
        derived_weight = min(1.0, (collision_score * subject_count) / 20.0)

        # Pattern 1: Theory definition [theory, ≡, conjunction]
        theory_triple = [theory_token, equiv_token, conj_expr]
        theory_shape = compute_shape(theory_triple)
        ec.execute(
            "INSERT INTO patterns (triple, shape, operator, step, depth, origin, weight) VALUES (?, ?, ?, ?, ?, 'derived', ?)",
            (json.dumps(theory_triple, ensure_ascii=False), theory_shape, equiv_token,
             step, step + 1, derived_weight),
        )

        # Pattern 2: Membership assertions [subject, ∈, theory]
        for subj_tok in subject_set:
            membership_triple = [subj_tok, member_of_token, theory_token]
            membership_shape = compute_shape(membership_triple)
            ec.execute(
                "INSERT INTO patterns (triple, shape, operator, step, depth, origin, weight) VALUES (?, ?, ?, ?, ?, 'derived', ?)",
                (json.dumps(membership_triple, ensure_ascii=False), membership_shape,
                 member_of_token, step, step + 1, derived_weight * 0.5),
            )

        new_results.append({
            "mc_id": mc_id,
            "token": theory_token,
            "subject_set": subject_set,
            "collision_ids": collision_ids,
            "collision_count": collision_count,
            "collision_score": round(collision_score, 2),
            "subject_count": subject_count,
            "grew_from": round(prev_max, 2) if prev_max > 0 else None,
        })

        del collision_ids, subject_set, member_collision_tokens

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
