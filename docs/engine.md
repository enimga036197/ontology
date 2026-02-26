# Engine Reference

The collision engine discovers algebraic structure bottom-up from opaque tokens. It finds what the ontology doesn't explicitly state — cross-domain bridges, hidden equivalences, structural universals.

## How It Works

The engine operates in two phases that bootstrap each other.

### Phase 1: Template Collisions (Properties)

Every triple in the ontology is a pattern: `[subject, operator, object]` where the object may contain nested expressions. The engine wildcards leaf positions — replacing individual tokens with placeholder variables — and checks whether two different patterns produce the same template.

If `[+, ℒ, [∀, 𝒶, [=, [+, 𝒶, ∅], 𝒶]]]` and `[×, ℒ, [∀, 𝒶, [=, [×, 𝒶, 𝟙], 𝒶]]]` both become `[_0, ℒ, [∀, 𝒶, [=, [_0, 𝒶, _1], 𝒶]]]` after wildcarding, that's a collision. The engine has discovered that + and × share a structural property: "there exists an identity element."

Phase 1 outputs **collisions** — pairs or groups of patterns sharing a template. Each collision is a discovered property.

### Phase 2: Membership Collisions (Theories)

Phase 2 looks at which symbols participate in the same collisions. If `+` and `×` both appear in collision A (identity element) and collision B (associativity), they share two properties. Phase 2 groups collisions by shared membership to form **theories** — conjunctions of properties.

A theory like "associative with identity element" (a monoid) emerges when the engine finds symbols that consistently co-occur across multiple collision templates.

### Bootstrap

Phase 2 outputs become new patterns for the next round of Phase 1. The derived triples — theory memberships, conjunction definitions — enter the pattern pool. Phase 1 finds new collisions among them. Phase 2 finds new theories. Each step compounds structural evidence.

This is why cross-domain bridges that are invisible at step 0 emerge at step 1+ and strengthen monotonically.

## Running the Engine

```sh
# Basic run (3 bootstrap steps)
python engine/run.py --steps 3

# Specific ontology set
python engine/run.py --set main --steps 3

# Just step 0 (no bootstrap)
python engine/run.py --steps 0
```

The engine creates `engine.db` alongside `ontology.db` in the set directory. Each run clears the previous engine database.

### Output

The engine prints progress to stdout:

```
Step 0 / Phase 1: 172 collisions from 377 seed patterns
Step 0 / Phase 2: 107 theories from 172 collisions
  derived 1,847 new patterns
Step 1 / Phase 1: 232 collisions from 2,024 patterns
...
```

### Database Schema

`engine.db` contains:

- **`patterns`**: All triples (seed + derived), with token-form, shape signature, step of origin
- **`collisions`**: Template matches — the template, which patterns matched, wildcard variable assignments, member count, step
- **`template_hashes`**: Index mapping templates to patterns for fast lookup
- **`vocabulary`**: All tokens (seed symbols + derived collision/theory tokens)

### Interpreting Results

**Collisions** are the raw discoveries. A collision with `member_count = 4` means four patterns share the same structural template. The `variables` field shows what differs between them — these are the "parameters" of the discovered property.

**Theories** are conjunctions of collisions. A theory grouping {+, ×, ∘, ⊻} across two collisions (associativity + identity) is the engine discovering the monoid structure.

**Step number** indicates depth of reasoning. Step 0 finds structure in the raw ontology. Step 1 finds structure in step 0's output. Higher steps find increasingly abstract meta-patterns.

**Member count** and **shared property count** between pairs indicate structural similarity strength. The engine uses specificity-weighted scoring — properties shared by fewer members count more than properties shared by many.

## Analysis Scripts

Several scripts in `engine/` analyze engine output:

- **`analyze_step1.py`** — Categorizes step 1+ collisions by domain (algebra, logic, type structure, cross-domain)
- **`analyze_selfhood.py`** — Traces the engine's assertion arc through training steps (mathematical discovery → self-recognition → worldview)
- **`analyze_narrative.py`** — Groups collisions by unique core pattern, tracking when each assertion first appears
- **`check_prime.py`** — Checks why specific patterns don't participate in collisions

## Performance

| Step | P1 Collisions | P2 Theories | Time |
|------|--------------|-------------|------|
| 0 | 172 | 107 | ~3s |
| 1 | 232 | 372 | ~1s |
| 2 | 749 | 760 | ~6s |
| 3 | 1,237 | 2,922 | ~3min |
| 4 | 4,343 | OOM | — |

Growth is exponential — each step's output feeds the next. Step 4 hit ~30GB before being killed. The OOM is in Phase 2's membership grouping (O(n^2) in collision count).

Known mitigation paths: `PRAGMA temp_store=FILE`, cursor streaming instead of `fetchall()`, pushing grouping logic into SQL.

## Architecture

```
engine/
  core.py      Template generation, collision detection, theory formation
  run.py       Main loop: parse args, run steps, print results
```

The engine is domain-agnostic. It reads from `ontology.db` (built by `tools/build_db.py`) and writes to `engine.db`. It operates entirely on opaque tokens — the 6-digit numbers carry no semantic information. All structure is discovered from relations alone.

The operating philosophy, from the docstring: "The database IS the model. No VRAM, no gradients, no tokenizer."
