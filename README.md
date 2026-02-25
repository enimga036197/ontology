# Ontology

370 triples encoding mathematics from axioms through algebra, stored as JSON arrays across 15 layers.

## Structure

```
layers/          15 JSONL files (L00-L14), strict dependency order
spec/            Format and operator reference
tools/           Build, validate, statistics, calculator
engine/          Collision engine (structural pattern discovery)
symbols.json     215 symbols with names, roles, opaque tokens
ontology.db      SQLite database (built from layers, not tracked)
```

## Layers

| # | File | Content | Triples |
|---|------|---------|---------|
| 00 | axioms | Meta-relations, self-grounding definitions | 50 |
| 01 | variables | Quantifiers, variable declarations | 12 |
| 02 | logic | Propositional connectives, truth tables | 18 |
| 03 | core_laws | Equality, successor, empty set | 7 |
| 04 | types | Type constructors, product, concatenation | 6 |
| 05 | arithmetic | +, -, ×, ÷, ^, %, \|, <, > | 27 |
| 06 | sets | ∈, ⊂, ∪, ∩ | 14 |
| 07 | functions | Application, composition, inverse | 14 |
| 08 | response | Assertion, query, modality | 26 |
| 09 | bitwise | XOR, shifts, bit operations | 19 |
| 10 | sequences | Length, index, map, fold, range | 47 |
| 11 | numerals | Digit-Peano bridge, positional reading | 23 |
| 12 | typing | Domain assignments, domain associations | 41 |
| 13 | number_theory | Congruence, gcd, primes, totient | 31 |
| 14 | algebra | Magma through semiring, homomorphisms | 35 |

No layer references symbols defined in a later layer. Layer 00 is self-referential by design.

## Setup

Requires Python 3 (stdlib only — sqlite3, json).

```sh
# Build the database from layer files
python tools/build_db.py

# Validate layer files
python tools/validate.py

# Print statistics
python tools/stats.py
```

## Tools

**`tools/calc.py`** — Interactive REPL that computes through the ontology's own laws. Extracts rewrite rules from ℒ (law) triples and reduces expressions by pattern matching and substitution.

```sh
python tools/calc.py
ontology> eval +(2, 3)
  +(2, 3) → σ(+(2, 2))  [+]
  ...
= 5
ontology> expand Group
Group ≡ ∧(Monoid(𝒶, 𝒷), hasInv(𝒷, 𝒶))
  Monoid ≡ ∧(Semigroup(𝒶, 𝒷), hasId(𝒷, 𝒶))
    ...
ontology> info +
ontology> check ⊻ hasInv
```

Commands: `eval`, `def`, `laws`, `type`, `expand`, `info`, `deps`, `refs`, `check`, `layer`, `layers`, `search`.

## Engine

The collision engine (`engine/core.py`, `engine/run.py`) discovers algebraic structures bottom-up from opaque tokens. It wildcards leaf positions in triples, finds pairs sharing the same template (Phase 1), then groups collisions by shared membership (Phase 2). The two phases bootstrap each other.

```sh
python engine/run.py --steps 3
```

Step 0 finds within-domain structure: monoid {+,×,∘,⊻}, Boolean algebra {∨,∧,⊻}, set lattice {∩,∪}. Steps 1–3 discover cross-domain bridges — addition and union ({+,∪}), multiplication and intersection ({×,∩}), GCD and intersection ({gcd,∩}) are connected through shared ∅-behaviour, strengthening monotonically with each bootstrap step. See `PHILOSOPHY.md` for the full analysis.

## Triple Format

Every statement is `[subject, operator, object]`, stored as JSON arrays in JSONL files. See `spec/TRIPLE_FORMAT.md` for details.

```json
["⊨", "⊨", "⊤"]
["+", "ℒ", ["∀", "𝒶", ["=", ["+", "𝒶", "∅"], "𝒶"]]]
["Group", "≡", ["∧", ["Monoid", "𝒶", "𝒷"], ["hasInv", "𝒷", "𝒶"]]]
```
