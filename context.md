# Ontology — Project Context

Single source of truth for the GBLM ontology. Rebuilt from the earliest clean iteration.

## Origin

Ported from `ONTOLOGY_INDEX.md` (830 canonical triples, 14 domains, 75 primitives).
Previous iterations in neuro-symbolic-llm, GCRE, maths-ai, compiled-ontology are superseded.

## Structure

- `sets/main/` — The main ontology set (mathematics from axioms through algebra)
  - `layers/` — 15 content layers (L00-L14) + 5 law-pass layers (.5), strict dependency order
  - `symbols.json` — 215 symbols with names, roles, and opaque tokens
  - `ontology.db` — Built from layers by build_db.py
  - `engine.db` — Engine output
- `sets/morals/` — Moral reasoning ontology set
  - `layers/` — 12 layers (L00-L09, includes L06.5, L07.5)
  - `symbols.json` — 111 symbols (58 inherited from L00-L02 + 53 moral-specific)
  - `ontology.db` — 219 triples
- `tools/` — build_db.py, validate.py, stats.py, calc.py, gen_tokens.py
- `engine/` — Collision engine (core.py, run.py) + analysis scripts
- `docs/` — Guide, engine reference, philosophy

## Ontology Sets

Each set in `sets/` is self-contained: layers, symbols, databases. The engine is domain-agnostic — point it at any set via `--set <name>` or `ONTOLOGY_SET=<name>`.

## Layers (main set)

| # | File | Domain | Triples |
|---|------|--------|---------|
| 00 | axioms | Existence, meta-relations, definitions | 50 |
| 01 | variables | Quantifiers, variable declarations | 12 |
| 02 | logic | Propositional connectives + laws, ∀/∃ duality | 18 |
| 03 | core_laws | = reflexivity, Σ, ∅, 𝟙, σ laws | 7 |
| 04 | types | Type constructors: [, 𝒮, 𝕊, ⊗, ++ | 6 |
| 05 | arithmetic | +, ×, ^, <, >, -, ÷, |, % | 29 |
| 05.5 | arithmetic_laws | assoc, commut, hasId, distrib defs + compact forms | 11 |
| 06 | sets | ∈, ∉, ⊂, {, ∪, ∩ | 14 |
| 06.5 | set_laws | closes def, compact forms | 2 |
| 07 | functions | ∂, ∘, ⁻, ℑ, ⟷ | 15 |
| 07.5 | function_laws | Compact forms for ∘ | 2 |
| 08 | response | Ⓢ, Ⓡ, □, ◊, modality | 26 |
| 09 | bitwise | 𝔹, ⊻, ≪, ≫ | 19 |
| 09.5 | bitwise_laws | hasInv def, compact forms for ⊻ | 5 |
| 10 | sequences | ⦃, ⦄, #, @, map, fold, etc. | 47 |
| 11 | numerals | 𝔻, ℛ, digit-Peano bridge | 23 |
| 12 | typing | ⊏ domain assignments, ⋔ associations | 41 |
| 13 | number_theory | ≅, gcd, lcm, ϕ, ℙ, ⟂ | 31 |
| 13.5 | number_theory_laws | Compact forms for gcd, lcm | 3 |
| 14 | algebra | Magma→Abelian hierarchy, semirings, homomorphisms | 16 |

Total: ~377 triples, 215 symbols, 20 layers.

## Engine

Two-phase collision engine discovers algebraic structures bottom-up.

**Phase 1 (Template Collisions):** Leaf-only wildcarding of pattern triples. Groups patterns sharing the same template → discovers PROPERTIES.

**Phase 2 (Membership Collisions):** Finds groups of P1 collisions sharing member symbols → discovers THEORIES (conjunctions of properties). Emits definitions + membership assertions.

The two phases bootstrap each other: P1 properties → P2 theories → derived patterns → new P1 properties → new P2 theories → ...

**Recent changes:**
- Specificity weighting (`56a0746`): P2 scoring uses `sum(1.0/member_count)` instead of raw collision count
- .5 law-pass layers (`f3bf372`): Law-concepts distributed to first-instance layers
- Multi-set support (`75f7d65`): Ontology sets in `sets/`, resolved via `ONTOLOGY_SET` env var

## Ethos

- **No forward references**: every symbol in a layer is defined in that layer or earlier
- **Symbol uniqueness**: each concept atom represents one concept; shared atoms across domains
  (κ for ∧/∩, ω for ∨/∪) are valid when they represent the same abstract concept
- **≡ is not =**: ≡ ("is defined as") is structural, = ("equals") is semantic
- **Don't name what the engine should discover**: the engine's scope is correctness, not human categories

## Status

- 0 forward references across all layers (verified by `tools/validate.py`)
- `ontology.db` rebuilt from layers via `tools/build_db.py` (377 triples main, 219 morals)
- Engine: specificity weighting + .5 law-pass layers committed
- Engine: graceful handling when ∈ not in vocabulary (for sets without set theory)
- Multi-set support: `sets/main/` structure, `--set` flag on all tools
- Docs reorganized: `docs/guide.md`, `docs/engine.md`, `docs/philosophy.md`
- Morals set: 12 layers, 219 triples, 143 P1 collisions + 25 theories in 3 steps
