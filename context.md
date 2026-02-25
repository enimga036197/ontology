# Ontology — Project Context

Single source of truth for the GBLM ontology. Rebuilt from the earliest clean iteration.

## Origin

Ported from `ONTOLOGY_INDEX.md` (830 canonical triples, 14 domains, 75 primitives).
Previous iterations in neuro-symbolic-llm, GCRE, maths-ai, compiled-ontology are superseded.

## Structure

- `layers/` — 15 JSONL files (L00-L14), ordered by strict dependency (no forward references)
- `spec/` — Format and operator reference
- `tools/` — build_db.py, validate.py, stats.py, calc.py, gen_tokens.py
- `engine/` — Collision engine (core.py, run.py)
- `symbols.json` — All 215 symbols with names, roles, and opaque tokens
- `ontology.db` — Built from layers by build_db.py

## Layers

| # | File | Domain | Triples |
|---|------|--------|---------|
| 00 | axioms | Existence, meta-relations, definitions | 50 |
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

**Run results (latest: OOM during step 4/P2 at 57GB):**

| Step | P1 collisions | P2 theories | Time |
|------|--------------|-------------|------|
| 0 | 172 | 107 | 2.6s |
| 1 | 232 | 372 | 1.1s |
| 2 | 749 | 760 | 6.2s |
| 3 | 1,237 | 2,922 | 177s |
| 4 | 4,343 | OOM | — |

Totals: 6,733 collisions, 4,161 theories, 20,300 vocabulary entries.

**OOM root cause:** P2 loads all candidate membership groups via `fetchall()` — O(n²) in collision count due to subset-key sharing. Combined with `PRAGMA temp_store=MEMORY` forcing SQLite GROUP BY temp tables into RAM. Fixable by: (1) `temp_store=FILE`, (2) cursor streaming instead of fetchall, (3) push grouping logic into SQL so data never enters Python.

**Step 0 discoveries (within-domain):**
- Monoid {+,×,∘,⊻} from shared associativity ∧ identity
- Commutative monoid {+,×,⊻} (correctly excludes ∘)
- Boolean algebra {∨,∧,⊻} from 8 shared truth-table properties
- Set lattice {∩,∪} from idempotency, element characterization, functor law
- Identity spectrum: `∀𝒶: op(𝒶, X) = 𝒶` unifies identity (+/∅, ×/𝟙) with idempotency (∩/𝒶, ∪/𝒶) — 9 members
- ∅-duality: `∀𝒶: op(𝒶, ∅) = X` splits into identity {+,∪,≪,gcd} and annihilation {×,∩}
- Functor identity law: `∂(ℑ,𝒶) = 𝒶` collides with `map(ℑ,𝒶) = 𝒶` — same template
- Variable interchangeability {𝒶,𝒷,𝒸,𝒹,𝓀,𝓃,ℓ} — substitution principle from structure
- Type system backbone {Δ,ρ,θ,=,Κ} sharing 10 properties

**Step 1+ discoveries (cross-domain bridges):**

Bootstrap steps compound structural evidence. Cross-domain pairs strengthen monotonically:

| Pair | Domains | s0 | s1 | s2 | s3 |
|------|---------|----|----|----|----|
| + ~ ∪ | 𝓐×𝓢 | — | 2 | 11 | 22 |
| + ~ ⊻ | 𝓐×𝓑 | 5 | 9 | 13 | 17 |
| ≪ ~ + | 𝓐×𝓑 | — | 2 | 11 | 22 |
| × ~ ∩ | 𝓐×𝓢 | — | — | 7 | 18 |
| gcd ~ ∩ | 𝓝×𝓢 | — | — | 6 | 17 |
| gcd ~ + | 𝓝×𝓐 | — | 4 | 13 | 24 |

- **∅-identity family** {≪,gcd,+,∪} spans 3 domains at step 1; grows to {≪,gcd,∩,×,+,∪} across 4 domains by step 3
- **× ~ ∩** emerges at step 2: annihilation at ∅ (both are lattice meets in their respective structures)
- **+ ~ ∪** emerges at step 1: shared ∅-identity (both are commutative monoids with empty as neutral)
- **gcd ~ ∩** reaches 17 properties: both are meet operations (divisibility lattice / subset lattice)
- **ℛₘ groups with arithmetic**: type Δ×Δ→Δ reveals modular reading as structurally a binary arithmetic operator

## Ethos

- **No forward references**: every symbol in a layer is defined in that layer or earlier
- **Symbol uniqueness**: each concept atom represents one concept; shared atoms across domains
  (κ for ∧/∩, ω for ∨/∪) are valid when they represent the same abstract concept
- **≡ is not =**: ≡ ("is defined as") is structural, = ("equals") is semantic

## Next: Simulation Architecture

The engine is a simulation pretending to be an algorithm. It applies local structural rules (template match, membership overlap) and observes emergent behaviour. The current SQL-query-loop implementation obscures this.

**Proposed rewrite as GPU simulation:**
- Each pattern = particle. Each collision = cluster. Each theory = higher-order cluster.
- Rules: same template hash → attract (P1). Overlapping membership → attract (P2). New cluster → emit derived patterns.
- Maps to GPU collision detection: broad phase (spatial hash), narrow phase (membership overlap), resolution (emit theories), integration (derived patterns enter world).
- "Steps" dissolve — no explicit P1→P2→loop, just continuous ticks until convergence.
- SQL becomes save/load (persistence), not the compute layer. VRAM is the model.
- Framework candidate: Taichi (Python-native GPU simulation DSL, compiles to CUDA).

**Path:** Fix OOM first (get step 4+ data) → prototype simulation → if equivalent results, simulation becomes the engine.

## Status

- 0 forward references across all 15 layers (verified by `tools/validate.py`)
- `ontology.db` rebuilt from layers via `tools/build_db.py`
- PHILOSOPHY.md updated: choices→consequences hierarchy, lone reasoner, pattern-matching-is-reasoning
- Engine OOM diagnosed, fix planned, simulation architecture sketched
