# Ontology Guide

How to read, write, and create ontology sets.

## Triple Format

Every statement is a triple: `[subject, operator, object]`, stored as a JSON array. Layer files are JSONL — one triple per line.

```json
["⊨", "⊨", "⊤"]
["σ", "↦", ["→", "Δ", "Δ"]]
["+", "ℒ", ["∀", "𝒶", ["=", ["+", "𝒶", "∅"], "𝒶"]]]
```

The **subject** is the thing being described — a symbol, an operation, a type. The **operator** (middle position) determines the statement type. The **object** can be an atom (`"⊤"`, `"∅"`) or a nested expression (`["→", "Δ", "Δ"]`, `["∀", "𝒶", ["=", "𝒶", "𝒶"]]`). Nesting is unbounded but typically 1-4 levels deep.

Files use UTF-8 throughout with mathematical Unicode symbols. One JSON array per line, no trailing commas.

## Operators

The middle position of a triple determines what kind of statement it is.

### Meta Operators

| Operator | Name | Pattern | Meaning |
|----------|------|---------|---------|
| `⊨` | Entails | `[a, ⊨, ⊤]` | a holds / is valid |
| `⌂` | Foundation | `[a, ⌂, ⊤]` | a is a foundational primitive |
| `≡` | Definition | `[a, ≡, b]` | a is defined as b |
| `↦` | Type | `[a, ↦, T]` | a has type T |
| `ℒ` | Law | `[a, ℒ, P]` | P is a law of a |
| `=` | Equality | `[a, =, b]` | a equals b (inside expressions) |
| `≠` | Inequality | `[a, ≠, b]` | a does not equal b |
| `⊏` | Domain-of | `[a, ⊏, D]` | a belongs to domain D |
| `⋔` | Compatible | `[D₁, ⋔, D₂]` | domain D₁ can express D₂ |
| `𝕧` | Variable | `[a, 𝕧, ⊤]` | a is a bound variable |
| `Ϛ` | Digit-succ | `[d₁, Ϛ, d₂]` | d₂ is the digit after d₁ |
| `ℛ` | Reading | `[d, ℛ, n]` | digit d reads as Peano number n |
| `⇒` | Implication | `[a, ⇒, b]` | a implies b (as operator) |
| `!` | Assertion | `[S, !, v]` | statement S asserts value v |
| `?` | Query | `[R, ?, v]` | result R queries value v |

### Structural Constructors

These appear inside expressions (object position), not as operators:

| Symbol | Name | Usage |
|--------|------|-------|
| `τ` | Structure | Meta-structural primitive |
| `ρ` | Relation | `["ρ", concept]` — constructs a relation |
| `Κ` | Constructor | `["Κ", name]` — constructs a value |
| `Τ` | Type | `["Τ", name]` — declares a type |
| `Ο` | Operation | `["Ο", name]` — declares an operation |
| `Σ` | Self-ref | `["Σ", a]` = a (identity/self-reference) |
| `Θ` | Origin | `["Θ", Δ]` = ∅ (zero/base) |
| `σ` | Successor | `["σ", n]` = n + 1 (Peano) |
| `θ` | Binder | `["θ", concept]` — constructs a binder |

### Symbols by Domain

**Logic** (L02): `¬` negation, `∧` conjunction, `∨` disjunction, `⇒` implication, `⇔` biconditional

**Quantifiers** (L01): `∀` universal (`["∀", var, pred]`), `∃` existential (`["∃", var, pred]`)

**Arithmetic** (L05): `+` `-` `×` `÷` `^` `%` `|` `<` `>` `≥`

**Sets** (L06): `∈` `∉` `⊂` `∪` `∩`

**Functions** (L07): `∂` application, `∘` composition, `ℑ` identity, `→` function type, `⊗` product type

**Bitwise** (L09): `⊻` XOR, `≪` left shift, `≫` right shift, `⊙` bit extract

**Domains** (L12): `𝓛` logical, `𝓐` arithmetic, `𝓢` set-theoretic, `𝓑` bitwise, `𝓡` representational, `𝓕` formal/variable

## Self-Grounding

The ontology is self-defined. Operators appear as both subjects and operators:

```json
["⊨", "⊨", "⊤"]
```

Entailment entails truth. The operator `⊨` uses itself to declare its own validity. This is the bootstrap — there is no external metalanguage. When the ontology says what `≡` means, it says:

```json
["≡", "≡", ["ρ", "ε"]]
```

Definition is defined as a relation whose concept is ε (the identity-concept). Seven concepts are irreducible — defined as themselves: `ϑ`, `τ`, `⊤`, `ℑ`, `β`, `ε`, `λ`, `φ`.

## Layers

Layers are numbered JSONL files. Each layer may only reference symbols defined in earlier layers (no forward references). Layer 00 is self-referential by necessity.

The main ontology has 15 content layers (00-14) plus companion ".5" law-pass layers:

| Layer | Domain | What it encodes |
|-------|--------|-----------------|
| 00 | Axioms | Meta-relations, self-grounding definitions |
| 01 | Variables | Quantifiers, 7 variable declarations |
| 02 | Logic | Propositional connectives, truth tables |
| 03 | Core Laws | Equality, successor, Peano axioms |
| 04 | Types | Type constructors |
| 05 | Arithmetic | +, ×, ^, constructive definitions via successor |
| 05.5 | Arithmetic Laws | Law-concept definitions (assoc, commut, hasId, distrib), compact law forms |
| 06 | Sets | ∈, ⊂, ∪, ∩ |
| 06.5 | Set Laws | closes definition, compact law forms |
| 07 | Functions | Application, composition, identity |
| 07.5 | Function Laws | Compact law forms for ∘ |
| 08 | Response | Assertion, query, modality |
| 09 | Bitwise | XOR, shifts, bit operations |
| 09.5 | Bitwise Laws | hasInv definition, compact law forms for ⊻ |
| 10 | Sequences | Length, index, map, fold, range |
| 11 | Numerals | Digit-Peano bridge, positional reading |
| 12 | Typing | Domain assignments and associations |
| 13 | Number Theory | Congruence, gcd, primes, totient |
| 13.5 | Number Theory Laws | Compact law forms for gcd, lcm |
| 14 | Algebra | Magma through semiring, homomorphisms |

### Law-Pass (.5) Layers

The ".5" layers sit between content layers. They define abstract law-concepts (like `assoc`, `commut`) at the first layer where concrete instances exist, then restate expanded laws in compact named form.

For example, L05 defines addition associativity as an expanded quantified expression:

```json
["+", "ℒ", ["∀", "𝒶", "𝒷", "𝒸", ["=", ["+", ["+", "𝒶", "𝒷"], "𝒸"], ["+", "𝒶", ["+", "𝒷", "𝒸"]]]]]
```

L05.5 defines `assoc` abstractly and restates the same law in compact form:

```json
["assoc", "≡", ["∀", "𝒸", "𝒹", "𝓀", ["=", ["𝒷", ["𝒷", "𝒸", "𝒹"], "𝓀"], ["𝒷", "𝒸", ["𝒷", "𝒹", "𝓀"]]]]]
["+", "ℒ", ["assoc", "+"]]
```

Both forms coexist. The engine can discover that the expanded and compact forms are structurally equivalent, and that `assoc` spans multiple domains: `+`, `×`, `∘`, `⊻`.

## Reading Triples

### Definitions (`≡`)

```json
["¬", "≡", ["Ο", "Ν"]]
```

Negation is an operation (Ο) whose concept atom is Ν. This classifies by structure, not by name.

### Laws (`ℒ`)

```json
["+", "ℒ", ["∀", "𝒶", ["=", ["+", "𝒶", "∅"], "𝒶"]]]
```

For all 𝒶: +(𝒶, ∅) = 𝒶. Adding zero gives you back what you started with. This is both an axiom and a rewrite rule — the calculator uses it to compute.

### Type signatures (`↦`)

```json
["+", "↦", ["→", ["⊗", "Δ", "Δ"], "Δ"]]
```

Addition takes a pair of natural numbers and returns a natural number: `(Δ × Δ) → Δ`.

### Truth tables (`ℒ` with ground terms)

```json
["∧", "ℒ", ["=", ["∧", "⊤", "⊤"], "⊤"]]
["∧", "ℒ", ["=", ["∧", "⊤", "⊥"], "⊥"]]
```

Each case is stated individually. No axiom schemas — maximally explicit.

### Compact laws (`ℒ` with named concepts)

```json
["+", "ℒ", ["assoc", "+"]]
["+", "ℒ", ["hasId", "+", "∅"]]
```

Addition is associative. Addition has identity element ∅. These reference the abstract definitions from .5 layers.

### Algebraic hierarchy

```json
["Magma", "≡", ["closes", "𝒶", "𝒷"]]
["Semigroup", "≡", ["∧", ["Magma", "𝒶", "𝒷"], ["assoc", "𝒷"]]]
["Monoid", "≡", ["∧", ["Semigroup", "𝒶", "𝒷"], ["hasId", "𝒷", "𝒶"]]]
```

Each structure is a conjunction of the previous one plus one property. The final assertion:

```json
["Δ", "ℒ", ["Semiring", "Δ", "+", "×"]]
```

The natural numbers form a semiring under addition and multiplication. The ontology recognises its own arithmetic as an instance of its own algebra.

## Creating Your Own Set

An ontology set is a directory containing:

```
your_set/
  layers/          JSONL files (numbered, dependency order)
  symbols.json     Symbol definitions with opaque tokens
```

### 1. Define Symbols

`symbols.json` maps glyphs to metadata. Each symbol has a name, role, and opaque token (random 6-digit number, digits 1-9):

```json
{
  "⊨": {"name": "entails", "role": "meta", "token": "481936"},
  "⊤": {"name": "truth", "role": "meta", "token": "273518"},
  "+": {"name": "plus", "role": "operation", "token": "619247"}
}
```

Generate tokens with `python tools/gen_tokens.py`. The tokens carry no semantic information — the engine must find structure in relations alone.

### 2. Write Layers

Create JSONL files in `layers/`, numbered to enforce dependency order:

```
00_foundation.jsonl     Bootstrap: self-grounding definitions
01_basics.jsonl         Core concepts your domain needs
02_rules.jsonl          Laws and relationships
...
```

Rules:
- No forward references: layer N may only use symbols from layers 0 through N
- Layer 00 is self-referential (it must define its own operators)
- One JSON array per line
- Use the operators from your symbols.json

### 3. Build and Validate

```sh
# Build the database
python tools/build_db.py --set your_set

# Validate (checks for format errors)
python tools/validate.py  # set ONTOLOGY_SET=your_set

# Run the engine
python engine/run.py --set your_set --steps 3
```

### 4. Design Principles

From the main ontology's experience:

- **State what's true, not what's derivable.** If a fact follows from other stated facts, don't state it again. The engine finds derivable structure.
- **Enumerate at the base, abstract at the top.** When the domain is finite (truth values), enumerate all cases. When the domain is open (algebraic structures), use quantifiers.
- **One symbol, one concept.** Don't reuse glyphs for different meanings. If two things in different domains are structurally identical (like ∧ and ∩), give them the same concept atom — but this should reflect genuine structural equivalence, not convenience.
- **Separate meta from object level.** `≡` (what something IS) belongs in the operator position. `=` (computational equality) belongs inside expressions. Don't mix them.
- **Let the engine discover.** Don't pre-classify or label things for the engine's benefit. The engine's strength is finding structure you didn't anticipate. Over-labeling blinds it.

## Tools

### build_db.py

Builds `ontology.db` from layer files and `symbols.json`. The database contains:
- `symbols` table: glyph, name, role, token, layer
- `triples` table: subject, operator, object (as tokens), layer, raw JSON

### validate.py

Checks layer files for format errors: valid JSON, triple structure, known operators.

### calc.py

Interactive REPL that computes through the ontology's own laws:

```
ontology> eval +(2, 3)
  +(2, 3) → σ(+(2, 2))  [+]
  ...
= 5
ontology> expand Group
Group ≡ ∧(Monoid(𝒶, 𝒷), hasInv(𝒷, 𝒶))
ontology> info +
ontology> check ⊻ hasInv
```

Commands: `eval`, `def`, `laws`, `type`, `expand`, `info`, `deps`, `refs`, `check`, `layer`, `layers`, `search`.

### stats.py

Prints layer-by-layer triple counts and totals.

### gen_tokens.py

Regenerates opaque tokens in `symbols.json`. Each token is a random 6-digit number (digits 1-9).
