# Operator Reference

## Meta Operators (Layer 0)

| Symbol | Name | Arity | Semantics |
|--------|------|-------|-----------|
| `⊨` | Entails | `[a, ⊨, ⊤]` | a holds / is valid |
| `⌂` | Foundation | `[a, ⌂, ⊤]` | a is a foundational primitive |
| `≡` | Definition | `[a, ≡, b]` | a is defined as b |
| `↦` | Type | `[a, ↦, T]` | a has type T |
| `ℒ` | Law | `[a, ℒ, P]` | P is a law of a |
| `=` | Equality | `[a, =, b]` | a equals b |
| `≠` | Inequality | `[a, ≠, b]` | a does not equal b |

## Structural Constructors

| Symbol | Name | Usage |
|--------|------|-------|
| `τ` | Structure | Meta-structural primitive |
| `ρ` | Relation | Constructs relations: `["ρ", concept]` |
| `Κ` | Constructor | Constructs values: `["Κ", name]` |
| `Τ` | Type | Declares types: `["Τ", name]` |
| `Ο` | Operation | Declares operations: `["Ο", name]` |
| `Σ` | Self-ref | `["Σ", a]` = a (identity/self-reference) |
| `Θ` | Origin | Constructs zero/base: `["Θ", Δ]` = ∅ |
| `σ` | Successor | `["σ", n]` = n + 1 (Peano) |
| `π` | Position | Encodes triple positions |

## Logic (Layer 1)

| Symbol | Name | Type |
|--------|------|------|
| `¬` | Negation | `𝓛 → 𝓛` |
| `∧` | Conjunction | `𝓛 × 𝓛 → 𝓛` |
| `∨` | Disjunction | `𝓛 × 𝓛 → 𝓛` |
| `⇒` | Implication | `𝓛 × 𝓛 → 𝓛` |
| `⇔` | Biconditional | `𝓛 × 𝓛 → 𝓛` |

## Arithmetic (Layer 3)

| Symbol | Name | Type |
|--------|------|------|
| `+` | Addition | `Δ × Δ → Δ` |
| `-` | Subtraction | `Δ × Δ → Δ` |
| `×` | Multiplication | `Δ × Δ → Δ` |
| `÷` | Division | `Δ × Δ → Δ` |
| `^` | Exponentiation | `Δ × Δ → Δ` |
| `%` | Modulo | `Δ × Δ → Δ` |
| `\|` | Divisibility | `Δ × Δ → 𝓛` |
| `<` | Less than | `Δ × Δ → 𝓛` |
| `>` | Greater than | `Δ × Δ → 𝓛` |
| `≤` | Less or equal | `Δ × Δ → 𝓛` |
| `≥` | Greater or equal | `Δ × Δ → 𝓛` |

## Quantifiers (Layer 5)

| Symbol | Name | Usage |
|--------|------|-------|
| `∀` | Universal | `["∀", var, predicate]` |
| `∃` | Existential | `["∃", var, predicate]` |

## Functions (Layer 6)

| Symbol | Name | Type |
|--------|------|------|
| `∂` | Application | `(a→b) × a → b` |
| `∘` | Composition | `(b→c) × (a→b) → (a→c)` |
| `ℑ` | Identity | `a → a` |
| `→` | Function type | Type constructor |
| `⊗` | Product type | Type constructor |

## Sets (Layer 4)

| Symbol | Name | Type |
|--------|------|------|
| `∈` | Element of | `a × 𝒮 → 𝓛` |
| `∉` | Not element of | `a × 𝒮 → 𝓛` |
| `⊂` | Subset | `𝒮 × 𝒮 → 𝓛` |
| `∪` | Union | `𝒮 × 𝒮 → 𝒮` |
| `∩` | Intersection | `𝒮 × 𝒮 → 𝒮` |
| `{` | Set constructor | Delimiter |

## Bitwise (Layer 9)

| Symbol | Name | Type |
|--------|------|------|
| `⊻` | XOR | `Δ × Δ → Δ` |
| `≪` | Left shift | `Δ × Δ → Δ` |
| `≫` | Right shift | `Δ × Δ → Δ` |
| `⊙` | Bit extract | `Δ × Δ → 𝔹` |

## Typing (Layer 10)

| Symbol | Name | Meaning |
|--------|------|---------|
| `⊏` | Domain-of | Symbol belongs to domain |
| `⋔` | Compatible | Domain can express another domain |

## Domains

| Symbol | Name | Contains |
|--------|------|----------|
| `𝓛` | Logical | Boolean connectives, truth values |
| `𝓐` | Arithmetic | Numbers, operators |
| `𝓢` | Set-theoretic | Membership, union, intersection |
| `𝓑` | Bitwise | XOR, shifts, extraction |
| `𝓡` | Representational | Digit-Peano bridge |
| `𝓕` | Formal/Variable | Variables, quantified terms |
