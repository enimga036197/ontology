#!/usr/bin/env python3
"""Ontological Calculator — computes through the ontology's own axioms."""

import sys, os, json, sqlite3

# ── 1. Loader ────────────────────────────────────────────────────────────────

_ROOT = os.path.join(os.path.dirname(__file__), '..')
_SET = os.environ.get("ONTOLOGY_SET", "main")
_SET_DIR = os.path.join(_ROOT, 'sets', _SET)
DB_PATH = os.path.join(_SET_DIR, 'ontology.db')
SYM_PATH = os.path.join(_SET_DIR, 'symbols.json')

VARIABLES = set('𝒶𝒷𝒸𝒹𝓀𝓃ℓ')

# Meta-constructors: definitions using these just classify a symbol, not define it algebraically
META_OPS = {'Ο', 'ρ', 'Κ', 'τ', 'Σ', 'θ', 'Θ', 'β', 'Τ', 'π'}

def load():
    with open(SYM_PATH, 'r', encoding='utf-8') as f:
        sym_json = json.load(f)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    symbols = {}
    c.execute('SELECT glyph, name, role, layer, depth FROM symbols')
    for glyph, name, role, layer, depth in c.fetchall():
        symbols[glyph] = {'name': name, 'role': role, 'layer': layer, 'depth': depth}
    for glyph, info in sym_json.items():
        if glyph in symbols:
            symbols[glyph]['token'] = info.get('token', '')
        else:
            symbols[glyph] = {'name': info['name'], 'role': info['role'],
                              'layer': -1, 'depth': 0, 'token': info.get('token', '')}

    definitions = {}
    laws = {}
    type_sigs = {}
    domains = {}
    all_triples = []

    c.execute('SELECT subject, operator, object, layer, form, depth, line FROM triples')
    for subj_raw, op, obj_raw, layer, form, depth, line in c.fetchall():
        subj = json.loads(subj_raw)
        obj = json.loads(obj_raw)
        triple = {'subject': subj, 'operator': op, 'object': obj,
                  'layer': layer, 'form': form, 'depth': depth, 'line': line}
        all_triples.append(triple)

        if op == '≡':
            definitions.setdefault(subj, []).append(obj)
        elif op == 'ℒ':
            laws.setdefault(subj, []).append(obj)
        elif op == '↦':
            type_sigs.setdefault(subj, []).append(obj)
        elif op == '⊏':
            domains.setdefault(subj, []).append(obj)

    conn.close()
    return symbols, definitions, laws, type_sigs, domains, all_triples


# ── 2. Expression Parser ─────────────────────────────────────────────────────

def parse(text, symbols):
    text = text.strip()
    tokens = tokenize(text, symbols)
    expr, pos = parse_expr(tokens, 0)
    return expr

def tokenize(text, symbols):
    tokens = []
    i = 0
    glyphs = sorted(symbols.keys(), key=len, reverse=True)
    while i < len(text):
        if text[i] in ' \t':
            i += 1
            continue
        if text[i] in '(),':
            tokens.append(text[i])
            i += 1
            continue
        if text[i].isdigit():
            j = i
            while j < len(text) and text[j].isdigit():
                j += 1
            tokens.append(('NUM', int(text[i:j])))
            i = j
            continue
        matched = False
        for g in glyphs:
            if text[i:i+len(g)] == g:
                tokens.append(g)
                i += len(g)
                matched = True
                break
        if not matched:
            j = i
            while j < len(text) and text[j] not in ' \t(),':
                j += 1
            tok = text[i:j]
            if tok:
                tokens.append(tok)
                i = j
            else:
                i += 1
    return tokens

def parse_expr(tokens, pos):
    if pos >= len(tokens):
        return None, pos
    atom, pos = parse_atom(tokens, pos)
    if pos < len(tokens) and tokens[pos] == '(':
        pos += 1
        args = []
        if pos < len(tokens) and tokens[pos] != ')':
            arg, pos = parse_expr(tokens, pos)
            args.append(arg)
            while pos < len(tokens) and tokens[pos] == ',':
                pos += 1
                arg, pos = parse_expr(tokens, pos)
                args.append(arg)
        if pos < len(tokens) and tokens[pos] == ')':
            pos += 1
        return [atom] + args, pos
    return atom, pos

def parse_atom(tokens, pos):
    if pos >= len(tokens):
        return None, pos
    tok = tokens[pos]
    if isinstance(tok, tuple) and tok[0] == 'NUM':
        return int_to_peano(tok[1]), pos + 1
    return tok, pos + 1

def int_to_peano(n):
    if n == 0:
        return '∅'
    result = '∅'
    for _ in range(n):
        result = ['σ', result]
    return result


# ── 3. Pretty Printer ────────────────────────────────────────────────────────

def is_peano(expr):
    if expr == '∅':
        return True
    if isinstance(expr, list) and len(expr) == 2 and expr[0] == 'σ':
        return is_peano(expr[1])
    return False

def peano_to_int(expr):
    n = 0
    while isinstance(expr, list) and len(expr) == 2 and expr[0] == 'σ':
        n += 1
        expr = expr[1]
    if expr == '∅':
        return n
    return None

def fmt(expr):
    if expr is None:
        return '?'
    if isinstance(expr, str):
        return expr
    if is_peano(expr):
        n = peano_to_int(expr)
        if n is not None:
            return str(n)
    if isinstance(expr, list):
        if len(expr) == 0:
            return '[]'
        op = expr[0]
        args = expr[1:]
        if not args:
            return fmt(op)
        # Special formatting for quantifiers
        if op in ('∀', '∃') and len(args) >= 2:
            vars_list = args[:-1]
            body = args[-1]
            return f"{op}{','.join(fmt(v) for v in vars_list)}: {fmt(body)}"
        return f"{fmt(op)}({', '.join(fmt(a) for a in args)})"
    return str(expr)


# ── 4. Evaluator — Term Rewriting Engine ─────────────────────────────────────

def is_variable(s):
    return isinstance(s, str) and s in VARIABLES

def specificity(expr):
    """Count non-variable nodes. Higher = more specific pattern."""
    if is_variable(expr):
        return 0
    if isinstance(expr, str):
        return 1
    if isinstance(expr, list):
        return sum(specificity(e) for e in expr)
    return 0

def has_variables(expr):
    if is_variable(expr):
        return True
    if isinstance(expr, list):
        return any(has_variables(e) for e in expr)
    return False

def extract_rules(laws):
    """Extract rewrite rules from law triples, filtered and sorted."""
    rules = []
    for subj, law_exprs in laws.items():
        for expr in law_exprs:
            for lhs, rhs, desc in extract_from_law(subj, expr):
                # Skip: LHS is a single variable (matches everything, useless)
                if is_variable(lhs):
                    continue
                # Skip: naming rules — RHS is the subject, LHS is ground
                # (e.g., σ(∅) → 𝟙 would destroy Peano structure)
                if isinstance(rhs, str) and rhs == subj and not has_variables(lhs):
                    continue
                rules.append((lhs, rhs, desc))
    # Sort by specificity descending: most specific patterns first
    rules.sort(key=lambda r: specificity(r[0]), reverse=True)
    return rules

def extract_from_law(subj, expr):
    """Extract rewrite rules from a single law expression."""
    if not isinstance(expr, list):
        return []
    # Direct equality: ["=", lhs, rhs]
    if expr[0] == '=' and len(expr) == 3:
        return [(expr[1], expr[2], subj)]
    # Quantified: ["∀", v1, ..., body]
    if expr[0] == '∀':
        return extract_from_law(subj, expr[-1])
    return []

def match(pattern, expr, bindings=None):
    if bindings is None:
        bindings = {}
    if is_variable(pattern):
        if pattern in bindings:
            return deep_equal(bindings[pattern], expr)
        bindings[pattern] = expr
        return True
    if isinstance(pattern, str):
        return pattern == expr
    if isinstance(pattern, list) and isinstance(expr, list):
        if len(pattern) != len(expr):
            return False
        return all(match(p, e, bindings) for p, e in zip(pattern, expr))
    return False

def deep_equal(a, b):
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(deep_equal(x, y) for x, y in zip(a, b))
    return a == b

def substitute(expr, bindings):
    if isinstance(expr, str):
        return bindings.get(expr, expr)
    if isinstance(expr, list):
        return [substitute(e, bindings) for e in expr]
    return expr

def deep_copy(expr):
    if isinstance(expr, list):
        return [deep_copy(e) for e in expr]
    return expr

def expr_key(expr):
    """Hashable key for cycle detection."""
    if isinstance(expr, str):
        return expr
    if isinstance(expr, list):
        return tuple(expr_key(e) for e in expr)
    return expr

def evaluate(expr, rules, trace, max_steps=1000):
    """Fully reduce an expression: children first, then apply rules at top."""
    seen = set()
    for _ in range(max_steps):
        key = expr_key(expr)
        if key in seen:
            break
        seen.add(key)

        # Fully reduce all children first
        if isinstance(expr, list):
            expr = [evaluate(e, rules, trace, max_steps) for e in expr]

        # Try one rule at the top level
        fired = False
        for lhs, rhs, desc in rules:
            bindings = {}
            if match(lhs, expr, bindings):
                result = substitute(rhs, bindings)
                if not deep_equal(result, expr):
                    trace.append((deep_copy(expr), deep_copy(result), desc))
                    expr = result
                    fired = True
                    break
        if not fired:
            break
    return expr


# ── 5. Definition Expander ───────────────────────────────────────────────────

def is_algebraic_def(defn):
    """Is this an algebraic/logical definition (vs a meta-classification)?"""
    if isinstance(defn, str):
        return False
    if isinstance(defn, list) and len(defn) >= 1:
        if isinstance(defn[0], str) and defn[0] in META_OPS:
            return False
        return True
    return False

def expand(symbol, definitions, symbols, indent=0, visited=None):
    """Recursively expand ≡ definitions with indented tree output."""
    if visited is None:
        visited = set()
    lines = []
    prefix = '  ' * indent

    if symbol not in definitions:
        return lines

    for defn in definitions[symbol]:
        lines.append(f"{prefix}{symbol} ≡ {fmt(defn)}")

        if symbol in visited:
            lines.append(f"{prefix}  ...")
            continue
        visited.add(symbol)

        # Only expand sub-symbols that have algebraic definitions
        sub_syms = find_expandable_symbols(defn, definitions, visited)
        for s in sub_syms:
            lines.extend(expand(s, definitions, symbols, indent + 1, set(visited)))

    return lines

def find_expandable_symbols(expr, definitions, visited):
    """Find symbols in expr that have algebraic definitions worth expanding."""
    found = []
    if isinstance(expr, str):
        if expr in definitions and expr not in visited:
            if any(is_algebraic_def(d) for d in definitions[expr]):
                found.append(expr)
    elif isinstance(expr, list):
        for e in expr:
            found.extend(find_expandable_symbols(e, definitions, visited))
    seen = set()
    result = []
    for s in found:
        if s not in seen:
            seen.add(s)
            result.append(s)
    return result


# ── 6. REPL Commands ─────────────────────────────────────────────────────────

def cmd_def(args, definitions, symbols):
    sym = args.strip()
    if sym not in definitions:
        print(f"  No definition found for '{sym}'")
        return
    for defn in definitions[sym]:
        print(f"  {sym} ≡ {fmt(defn)}")

def cmd_laws(args, laws, symbols):
    sym = args.strip()
    if sym not in laws:
        print(f"  No laws found for '{sym}'")
        return
    for law in laws[sym]:
        print(f"  {sym} ℒ {fmt(law)}")

def cmd_type(args, type_sigs, symbols):
    sym = args.strip()
    if sym not in type_sigs:
        print(f"  No type signature for '{sym}'")
        return
    for ts in type_sigs[sym]:
        print(f"  {sym} ↦ {fmt(ts)}")

def cmd_expand(args, definitions, symbols):
    sym = args.strip()
    lines = expand(sym, definitions, symbols)
    if not lines:
        print(f"  No definition to expand for '{sym}'")
        return
    for line in lines:
        print(line)

def cmd_eval(args, rules, symbols_map):
    expr = parse(args, symbols_map)
    trace = []
    result = evaluate(expr, rules, trace)
    for before, after, desc in trace:
        print(f"  {fmt(before)} \u2192 {fmt(after)}  [{desc}]")
    print(f"= {fmt(result)}")

def cmd_info(args, symbols, definitions, laws, type_sigs, domains, all_triples):
    sym = args.strip()
    if sym in symbols:
        s = symbols[sym]
        print(f"  {sym} ({s['name']})")
        print(f"  Layer: {s['layer']}  Depth: {s['depth']}  Role: {s['role']}")
    else:
        print(f"  {sym} (unknown symbol)")

    if sym in definitions:
        for defn in definitions[sym]:
            print(f"  Definition: {sym} \u2261 {fmt(defn)}")
    if sym in type_sigs:
        for ts in type_sigs[sym]:
            print(f"  Type: {sym} \u21a6 {fmt(ts)}")
    if sym in domains:
        for d in domains[sym]:
            dname = symbols.get(d, {}).get('name', d)
            print(f"  Domain: {sym} \u228f {d} ({dname})")
    if sym in laws:
        print(f"  Laws ({len(laws[sym])}):")
        for law in laws[sym]:
            print(f"    {sym} \u2112 {fmt(law)}")

def cmd_deps(args, definitions, symbols):
    sym = args.strip()
    if sym not in definitions:
        print(f"  No definition for '{sym}'")
        return
    deps = set()
    for defn in definitions[sym]:
        collect_symbols(defn, deps)
    deps.discard(sym)
    deps -= VARIABLES
    if deps:
        for d in sorted(deps):
            name = symbols.get(d, {}).get('name', '')
            label = f" ({name})" if name else ''
            print(f"  {d}{label}")
    else:
        print(f"  No dependencies")

def collect_symbols(expr, acc):
    if isinstance(expr, str):
        acc.add(expr)
    elif isinstance(expr, list):
        for e in expr:
            collect_symbols(e, acc)

def cmd_refs(args, all_triples, symbols):
    sym = args.strip()
    count = 0
    for t in all_triples:
        if mentions(t['subject'], sym) or mentions(t['object'], sym):
            print(f"  [{t['form']} L{t['layer']:02d}] {t['subject']} {t['operator']} {fmt(t['object'])}")
            count += 1
    if count == 0:
        print(f"  No triples reference '{sym}'")

def mentions(expr, sym):
    if isinstance(expr, str):
        return expr == sym
    if isinstance(expr, list):
        return any(mentions(e, sym) for e in expr)
    return False

def cmd_check(args, laws, all_triples):
    parts = args.strip().split(None, 1)
    if len(parts) < 2:
        print("  Usage: check SYMBOL PROPERTY")
        return
    sym, prop = parts
    if sym in laws:
        for law in laws[sym]:
            if mentions(law, prop):
                print(f"  \u2713 {sym} \u2112 {fmt(law)}")
                return
    for t in all_triples:
        if t['operator'] == 'ℒ' and t['subject'] == sym and mentions(t['object'], prop):
            print(f"  \u2713 {sym} \u2112 {fmt(t['object'])}")
            return
    print(f"  \u2717 No law found: {sym} \u2112 {prop}({sym}, ...)")

def cmd_layer(args, all_triples, symbols):
    try:
        n = int(args.strip())
    except ValueError:
        print("  Usage: layer N")
        return
    count = 0
    for t in all_triples:
        if t['layer'] == n:
            print(f"  [{t['form']}] {t['subject']} {t['operator']} {fmt(t['object'])}")
            count += 1
    if count == 0:
        print(f"  No triples in layer {n}")
    else:
        print(f"  ({count} triples)")

def cmd_layers(all_triples):
    layer_counts = {}
    for t in all_triples:
        key = t['layer']
        if key not in layer_counts:
            layer_counts[key] = {}
        form = t['form']
        layer_counts[key][form] = layer_counts[key].get(form, 0) + 1
    for layer in sorted(layer_counts):
        forms = layer_counts[layer]
        total = sum(forms.values())
        detail = ', '.join(f"{f}:{c}" for f, c in sorted(forms.items()))
        print(f"  L{layer:02d}: {total:3d} triples  ({detail})")

def cmd_search(args, all_triples, symbols):
    term = args.strip()
    count = 0
    for t in all_triples:
        if mentions(t['subject'], term) or mentions(t['object'], term) or t['operator'] == term:
            print(f"  [{t['form']} L{t['layer']:02d}] {t['subject']} {t['operator']} {fmt(t['object'])}")
            count += 1
    if count == 0:
        for glyph, info in symbols.items():
            if term.lower() in info.get('name', '').lower():
                print(f"  {glyph} \u2014 {info['name']} ({info['role']}, L{info['layer']})")
                count += 1
    if count == 0:
        print(f"  Nothing found for '{term}'")

def cmd_help():
    print("""  Commands:
    eval EXPR       Reduce expression using ontology laws
    def X           Show \u2261 definitions of X
    laws X          Show \u2112 laws of X
    type X          Show \u21a6 type signatures of X
    expand X        Recursively expand definition tree
    info X          Show everything about X
    deps X          What symbols does X's definition depend on?
    refs X          What triples reference X?
    check X PROP    Check if X has property (e.g., check + assoc)
    layer N         Show triples in layer N
    layers          Show layer summary
    search TERM     Find triples containing symbol or name
    help            This message
    quit / exit     Leave""")


# ── 7. REPL ──────────────────────────────────────────────────────────────────

def main():
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stdin.reconfigure(encoding='utf-8')

    print("Loading ontology...", end=' ', flush=True)
    symbols, definitions, laws, type_sigs, domains, all_triples = load()
    rules = extract_rules(laws)
    print(f"{len(all_triples)} triples, {len(rules)} rewrite rules.")
    print("Type 'help' for commands.\n")

    while True:
        try:
            line = input('ontology> ').strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not line:
            continue
        if line in ('quit', 'exit', 'q'):
            break

        parts = line.split(None, 1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ''

        try:
            if cmd == 'eval':
                cmd_eval(args, rules, symbols)
            elif cmd == 'def':
                cmd_def(args, definitions, symbols)
            elif cmd == 'laws':
                cmd_laws(args, laws, symbols)
            elif cmd == 'type':
                cmd_type(args, type_sigs, symbols)
            elif cmd == 'expand':
                cmd_expand(args, definitions, symbols)
            elif cmd == 'info':
                cmd_info(args, symbols, definitions, laws, type_sigs, domains, all_triples)
            elif cmd == 'deps':
                cmd_deps(args, definitions, symbols)
            elif cmd == 'refs':
                cmd_refs(args, all_triples, symbols)
            elif cmd == 'check':
                cmd_check(args, laws, all_triples)
            elif cmd == 'layer':
                cmd_layer(args, all_triples, symbols)
            elif cmd == 'layers':
                cmd_layers(all_triples)
            elif cmd == 'search':
                cmd_search(args, all_triples, symbols)
            elif cmd == 'help':
                cmd_help()
            else:
                cmd_eval(line, rules, symbols)
        except Exception as e:
            print(f"  Error: {e}")

if __name__ == '__main__':
    main()
