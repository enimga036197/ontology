# Ontology

A self-grounding mathematical ontology encoded as triples, with a collision engine that discovers algebraic structure bottom-up from opaque tokens.

## Quick Start

```sh
# Build the database from layer files
python tools/build_db.py

# Validate layer files
python tools/validate.py

# Run the collision engine (3 bootstrap steps)
python engine/run.py --steps 3

# Interactive calculator
python tools/calc.py
```

Requires Python 3 (stdlib only — sqlite3, json). No dependencies.

## Structure

```
sets/                Ontology sets (each self-contained)
  main/              The main ontology (mathematics from axioms through algebra)
    layers/          15+ JSONL files, strict dependency order
    symbols.json     215 symbols with names, roles, opaque tokens
    ontology.db      Built from layers (not tracked)
    engine.db        Engine output (not tracked)
tools/               Build, validate, statistics, calculator
engine/              Collision engine (structural pattern discovery)
docs/                Guides and reference
```

## Ontology Sets

Each set in `sets/` is a complete, self-contained ontology: layers, symbols, and databases. The engine is domain-agnostic — point it at any set.

```sh
# Build and run a specific set
python tools/build_db.py --set main
python engine/run.py --set main --steps 3

# Or via environment variable
ONTOLOGY_SET=main python engine/run.py --steps 3
```

The `main` set encodes mathematics from axioms through semirings across 15 layers (~377 triples). Other sets can encode different domains (morals, traffic, flight paths) using the same triple format and engine.

## Documentation

- **[Ontology Guide](docs/guide.md)** — How triples work, operator reference, how to read and write ontology layers, how to create your own set
- **[Engine Reference](docs/engine.md)** — How the collision engine works, what it discovers, how to run and interpret results
- **[Philosophy](docs/philosophy.md)** — Why the ontology is structured the way it is, what's chosen vs forced, what the engine's discoveries mean
