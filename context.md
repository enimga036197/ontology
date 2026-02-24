# Ontology — Project Context

Single source of truth for the GBLM ontology. Rebuilt from the earliest clean iteration.

## Origin

Ported from `ONTOLOGY_INDEX.md` (830 canonical triples, 14 domains, 75 primitives).
Previous iterations in neuro-symbolic-llm, GCRE, maths-ai, compiled-ontology are superseded.

## Structure

- `layers/` — 15 JSONL files (L00-L14), ordered by strict dependency (no forward references)
- `spec/` — Format and operator reference
- `tools/` — build_db.py, gen_tokens.py, validation scripts
- `engine/` — Collision engine (core.py, run.py)
- `symbols.json` — All 215 symbols with names, roles, and opaque tokens
- `ontology.db` — Built from layers by build_db.py

## Layers

| # | File | Domain | Triples |
|---|------|--------|---------|
| 00 | axioms | Existence, meta-relations, definitions | 51 |
| 01 | variables | Quantifiers, variable declarations | 12 |
| 02 | logic | Propositional connectives + laws, ∀/∃ duality | 18 |
| 03 | core_laws | = reflexivity, Σ, ∅, 𝟙, σ laws | 7 |
| 04 | types | Type constructors: [, 𝒮, 𝕊, ⊗, ++ | 6 |
| 05 | arithmetic | +, ×, ^, <, >, -, ÷, |, % | 27 |
| 06 | sets | ∈, ∉, ⊂, {, ∪, ∩ | 14 |
| 07 | functions | ∂, ∘, ⁻, ℑ, ⟷ | 14 |
| 08 | response | Ⓢ, Ⓡ, □, ◊, modality | 26 |
| 09 | bitwise | 𝔹, ⊻, ≪, ≫ | 19 |
| 10 | sequences | ⦃, ⦄, #, @, map, fold, etc. | 47 |
| 11 | numerals | 𝔻, ℛ, digit-Peano bridge | 23 |
| 12 | typing | ⊏ domain assignments, ⋔ associations | 41 |
| 13 | number_theory | ≅, gcd, lcm, ϕ, ℙ, ⟂ | 31 |
| 14 | algebra | Groups, semirings, homomorphisms | 35 |

Total: 370 triples, 215 symbols, 15 layers.

## Engine

Two-phase collision engine discovers algebraic structures bottom-up.

**Phase 1 (Template Collisions):** Leaf-only wildcarding of pattern triples. Groups patterns sharing the same template → discovers PROPERTIES.

**Phase 2 (Membership Collisions):** Finds groups of P1 collisions sharing member symbols → discovers THEORIES (conjunctions of properties). Emits `[token, ≡, [C_a, ∧, C_b]]` definitions + `[subject, ∈, theory_token]` membership assertions.

The two phases bootstrap each other: P1 properties → P2 theories → derived patterns → new P1 properties → new P2 theories → ...

**Bug fixes (2026-02-25):**
- Fixed derived patterns using literal ≡ glyph instead of opaque token
- Fixed wildcard name leakage (_0, _1, _2 leaked as shared constants → 234 false collisions/step)
- Both now use freshly minted opaque tokens

**Run results (10 steps, killed at step 3 due to 30GB disk):**
- Step 0: 172 P1 collisions, 107 P2 theories
- Step 1: 221 new P1, 265 new P2 (bootstrap confirmed)
- Step 2: 653 new P1, 382 new P2
- Step 3: 1058 new P1, 2150 new P2 (94 seconds)
- Exponential growth — engine discovers monoid structure, Boolean algebra, type hierarchies, variable interchangeability, meta-theories (theories about theories)
- Three abstraction levels: symbols → properties → theories → meta-theories

**Key discoveries:**
- Monoid {+,×,∘,⊻} from shared associativity ∧ identity ∧ law-property
- Boolean algebra {∨,∧,⊻,⇒,⊤,⊥,¬,⇔} from truth-table properties
- Variable interchangeability {𝒶,𝒷,𝒸,𝒹,𝓀,𝓃,ℓ} — substitution principle from pure structure
- Type system backbone {Δ,ρ,θ,=,Κ} sharing 10 properties

## Ethos

- **No forward references**: every symbol in a layer is defined in that layer or earlier
- **Symbol uniqueness**: each concept atom represents one concept; shared atoms across domains
  (κ for ∧/∩, ω for ∨/∪) are valid when they represent the same abstract concept
- **≡ is not =**: ≡ ("is defined as") is structural, = ("equals") is semantic

## Status

- Layer restructure complete (2025-02-23) — fixed 5 forward-reference violations
- Sub-tree wildcarding removed in favor of leaf-only
- Audit verified: 0 forward references across all 15 layers
