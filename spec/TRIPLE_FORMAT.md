# Triple Format

## Core Format

Every statement is a triple: `[subject, operator, object]`

Stored as JSON arrays, one per line in `.jsonl` files.

```json
["⊨", "⊨", "⊤"]
["σ", "↦", ["→", "Δ", "Δ"]]
["+", "ℒ", ["∀", "𝒶", ["=", ["+", "𝒶", "∅"], "𝒶"]]]
```

## Self-Grounding

The ontology is self-defined. Operators appear as both subjects and operators:
- `["⊨", "⊨", "⊤"]` — entailment holds (bootstraps itself)
- `["=", "≡", ["ρ", "ℑ"]]` — equality is defined as a relation

## Object Nesting

Objects can be:
- **Atoms**: `"⊤"`, `"∅"`, `"𝒶"`
- **Nested triples**: `["→", "Δ", "Δ"]`, `["∀", "𝒶", ["=", "𝒶", "𝒶"]]`

Nesting depth is unbounded but typically 1-4 levels.

## Operator Positions

The middle position determines the statement type:

| Operator | Meaning | Example |
|----------|---------|---------|
| `⊨` | Holds/valid | `["⊨", "⊨", "⊤"]` |
| `⌂` | Is foundational | `["τ", "⌂", "⊤"]` |
| `≡` | Defined as | `["⊥", "≡", ["¬", "⊤"]]` |
| `↦` | Has type | `["+", "↦", ["→", ["⊗", "Δ", "Δ"], "Δ"]]` |
| `ℒ` | Has law | `["+", "ℒ", ["∀", "𝒶", ["=", ["+", "𝒶", "∅"], "𝒶"]]]` |
| `⊏` | Domain-of | `["¬", "⊏", "𝓛"]` |
| `⋔` | Domain-compatible | `["𝓕", "⋔", "𝓛"]` |
| `≠` | Not equal | `["⊥", "≠", "⊤"]` |
| `!` | Assertion | `["Ⓢ", "!", "⊤"]` |
| `?` | Query | `["Ⓡ", "?", "⊤"]` |
| `𝕧` | Variable-marker | `["𝒶", "𝕧", "⊤"]` |
| `Ϛ` | Digit-successor | `["0", "Ϛ", "1"]` |
| `ℛ` | Reading | `["0", "ℛ", "∅"]` |
| `⇒` | Implication | `["?", "⇒", "!"]` |

## Layer Ordering

Files are numbered `00`-`14` (15 layers). Each layer may reference symbols defined in earlier layers.
Layer 00 (foundation) is self-referential by design.

## Encoding

- UTF-8 throughout
- Mathematical Unicode symbols (no ASCII fallbacks)
- One JSON array per line, no trailing commas
