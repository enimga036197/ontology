# Ontology — Project Context

Single source of truth for the GBLM ontology. Rebuilt from the earliest clean iteration.

## Origin

Ported from `ONTOLOGY_INDEX.md` (830 canonical triples, 14 domains, 75 primitives).
Previous iterations in neuro-symbolic-llm, GCRE, maths-ai, compiled-ontology are superseded.

## Structure

- `layers/` — 14 JSONL files, one per domain, ordered by dependency
- `spec/` — Format and operator reference
- `tools/` — Validation and stats scripts

## Layers

| # | File | Domain | Triples |
|---|------|--------|---------|
| 00 | foundation | Meta-logical primitives, self-grounding | 46 |
| 01 | logic | Propositional connectives | 17 |
| 02 | types | Type system | 11 |
| 03 | arithmetic | Peano arithmetic | 28 |
| 04 | sets | Set theory | 14 |
| 05 | quantifiers | ∀/∃ quantification | 13 |
| 06 | functions | Lambda calculus, composition | 16 |
| 07 | response | Query-response, modality | 26 |
| 08 | numerals | Digit-Peano bridge | 51 |
| 09 | bitwise | XOR, shifts, bit ops | 21 |
| 10 | typing | Domain assignments | 50 |
| 11 | modular | GCD, LCM, Euler, primes | 25 |
| 12 | sequences | Lists, map/fold | 47 |
| 13 | algebra | Groups, homomorphisms | 38 |

## Status

- Initial port complete (403 triples ported of 830 canonical)
- Remaining triples need careful verification against ONTOLOGY_INDEX.md
- Source: `D:\enigma\Desktop\test\ONTOLOGY_INDEX.md`
