#!/usr/bin/env python3
"""Machine check for the DROP-IN CONTRACT FIELD LISTS: what the two mirror docs
promise a `meta` export must carry, against what the three registries read.

Why this exists (measured, not assumed): the three drop-in registries are ONE
contract with THREE glob dirs, and `registry_roster_diff.py` proves WHICH files
glob a dir — it says nothing about the FIELD NAMES the contract carries. Those
names live twice: in code (`PageMeta`, `ActionMeta`, and the `mod.meta.*` reads
the widget registry performs) and in prose (`meta{...}` lists in AGENTS.md and
docs/DEVGUIDE.md, which mirror each other line for line). Measured pre-fix on
the delivered tree, both suites green: `roles` was a real field of `PageMeta`
and `ActionMeta` — RBAC gating reads it — and appeared in NO contract list
anywhere in either doc, so a seat that copied the doc's `meta{...}` verbatim
got a silently un-gated page; symmetrically, renaming a field in code leaves
eight sentences promising the old shape and nothing on this box fires.

So this harness grades four claims a per-side test cannot see:

  DOC-NAMED     every field a doc list NAMES must exist in that registry's code
                set. A doc that promises `meta{width}` while the registry reads
                `size` is a contract the app does not implement.
  COVERAGE      every field the code set declares must appear in at least one
                in-domain doc list. This is the `roles` hole exactly: a new
                interface field is invisible to every reader of the docs.
  OPTIONAL      where a doc marks a field `x?`, the interface must mark it
                optional too — graded in that direction only, because a doc
                list without any `?` is a shorthand, not a claim of
                requiredness (measured: the other direction fired on four
                correct pages fields).
  MIRROR        the distinct list strings per registry must be equal between
                AGENTS.md and docs/DEVGUIDE.md. The two files are one document
                delivered twice; a one-sided contract edit leaves one reader
                with a stale shape, and neither file can see it from inside.

The code side is PARSED from source, never restated here, and pinned twice: the
widget contract comes from the registry's own `mod.meta.X` reads and must agree
with the shipped `Widget` interface minus the two keys the registry injects
(`file`, `component`). Two independent derivations of one contract; the pinned
field tuples then decide whether this harness still understands its input —
a moved set is RED naming the fields and every doc line that still promises
them, because the docs and the pin are one deliberate change.

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness no longer understands its own input — an interface
that does not parse, a list that cannot be attributed to a registry, or a doc
region whose list count moved). Never a false red for a tree it has not read.

Domain: the two mirror docs, cut at their dated `## State as of` sections —
counts and lists below that heading are historical records, out of domain by the
same ruling `release_readiness.py` applies to suite counts.

Controls run against copies via --root, so the shipped tree is only ever read:
  mkdir -p /tmp/r && cp --parents AGENTS.md docs/DEVGUIDE.md \
    app/src/lib/pages/index.ts app/src/lib/actions/index.ts app/src/widgets/index.ts /tmp/r
  python3 scripts/doc_field_roster_diff.py --root /tmp/r

It is the sixth FE leg of the landing gate (`python3 scripts/landing_gate.py --fe`
-> `doc-twin`), and the file is named `*_diff.py` for that reason: `landing_gate.py`
cross-checks its twin roster against that glob (EXPECTED_TWINS), so the name IS the
wiring — a harness written beside the gate but absent from that glob is a comparison
no merge ever runs.
"""
import argparse
import os
import re
import sys

# ------------------------------------------------------------------ pinned input
# "fields" is the promise for the code set; "lists" the promise for how many
# contract lists each doc must carry per registry. Both are checked before a
# single door runs, because a comparison cannot see its own coverage.
REGISTRIES = (
    {
        "name": "pages",
        "dir_token": "app/src/pages/",
        "src": os.path.join("app", "src", "lib", "pages", "index.ts"),
        "iface": "PageMeta",
        "fields": ("icon", "nav", "order", "path", "roles", "standalone", "title"),
        "lists": {"AGENTS.md": 3, "docs/DEVGUIDE.md": 3},
    },
    {
        "name": "actions",
        "dir_token": "app/src/actions/",
        "src": os.path.join("app", "src", "lib", "actions", "index.ts"),
        "iface": "ActionMeta",
        "fields": ("confirm", "handler", "input", "label", "model", "roles", "scope"),
        "lists": {"AGENTS.md": 2, "docs/DEVGUIDE.md": 2},
    },
    {
        "name": "widgets",
        "dir_token": "app/src/widgets/",
        "src": os.path.join("app", "src", "widgets", "index.ts"),
        # The widget registry declares no meta interface: the contract IS the
        # set of `mod.meta.X` reads it performs. `iface` is the cross-check.
        "iface": "Widget",
        "injected": ("component", "file"),
        "fields": ("data", "size", "title"),
        "lists": {"AGENTS.md": 1, "docs/DEVGUIDE.md": 1},
    },
)
EXPECTED_REGISTRIES = 3
EXPECTED_LISTS = 12
DOCS = ("AGENTS.md", "docs/DEVGUIDE.md")
STATE_HEADING = "## State as of"

LIST_RES = (re.compile(r"\bmeta\{([^{}]*)\}"),
            re.compile(r"\bmeta\s*=\s*\{\s*([^{}]*)\}"))
IFACE_RE = r"export interface %s \{(.*?)\n\}"
DECL_RE = re.compile(r"^\s*([A-Za-z_]\w*)(\?)?\s*:")
READ_RE = re.compile(r"\bmod\??\.meta\??\.([A-Za-z_]\w*)")


class CannotRun(Exception):
    pass


class Red(Exception):
    pass


def read(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CannotRun("cannot read %s: %s" % (path, exc))


# ------------------------------------------------------------------ code side
def interface_body(src_text, path, name):
    m = re.search(IFACE_RE % re.escape(name), src_text, re.S)
    if not m:
        raise CannotRun("%s: no `export interface %s { ... }` block found — the "
                        "contract this harness grades is declared there, and a "
                        "renamed or inlined interface means it is no longer reading "
                        "the registry it describes" % (path, name))
    return m.group(1)


def interface_fields(body):
    """name -> optional flag, from the top level of one interface body."""
    out = {}
    depth = 0
    for line in body.splitlines():
        stripped = line.strip()
        if depth and not stripped:
            continue
        depth += line.count("{") - line.count("}")
        if depth < 0:
            depth = 0
        if depth or stripped.startswith(("/*", "*", "//")):
            continue
        m = DECL_RE.match(stripped)
        if m:
            out[m.group(1)] = bool(m.group(2))
    if not out:
        raise CannotRun("the interface body parsed to zero fields: %r" % body[:80])
    return out


def code_contract(reg, root):
    """The declared meta fields of one registry, derived from source.

    Pages/actions: the interface IS the declared shape. Widgets: the `mod.meta.X`
    reads are the declaration, cross-checked against the shipped `Widget`
    interface minus the keys the registry injects — two independent derivations.
    """
    path = os.path.join(root, reg["src"])
    text = read(path)
    iface = interface_fields(interface_body(text, reg["src"], reg["iface"]))
    if reg.get("injected"):
        declared = sorted(set(READ_RE.findall(text)))
        from_iface = sorted(k for k in iface if k not in set(reg["injected"]))
        if declared != from_iface:
            raise CannotRun("%s: the widget contract has two sources and they "
                            "disagree — `mod.meta` reads give (%s) but `%s` minus "
                            "the injected keys (%s) gives (%s). One of them moved; "
                            "this harness cannot pick which side a doc should follow"
                            % (reg["src"], ", ".join(declared), reg["iface"],
                               ", ".join(sorted(reg["injected"])), ", ".join(from_iface)))
        names = declared
    else:
        names = sorted(iface)
    got = tuple(names)
    if got != reg["fields"]:
        raise Red("%s: the CODE contract moved off its pin — added (%s), removed (%s). "
                  "The pin in this file and the docs are one deliberate change: update "
                  "every doc list that still names a removed field, then bump `fields` "
                  "in the SAME commit."
                  % (reg["name"], ", ".join(n for n in got if n not in reg["fields"]) or "-",
                     ", ".join(n for n in reg["fields"] if n not in got) or "-"))
    return dict((n, iface.get(n, True)) for n in got)


# ------------------------------------------------------------------ doc side
def doc_body(root, rel):
    """The doc's text up to its dated state log — later lines are records, not instructions."""
    lines = read(os.path.join(root, rel)).splitlines()
    cut = len(lines)
    for i, line in enumerate(lines):
        if line.startswith(STATE_HEADING):
            cut = i
            break
    return lines[:cut]


UNIT_START = re.compile(r"^\s*(?:[-*+]\s|\d+\.\s|#|\||>|```)")


def paragraph(lines, index):
    """One claim: the matched line plus the wrapped lines that belong to it.

    Adjacent bullets and table rows carry no blank line between them, so the run
    is cut at any line that STARTS a unit — without that, one widget list reads
    as naming every registry in the following sentence. A match sitting on a
    continuation line reaches back to the unit it continues, because that is the
    line carrying the registry's directory.
    """
    start = index
    if not UNIT_START.match(lines[index]):
        while start > 0 and lines[start - 1].strip():
            start -= 1
            if UNIT_START.match(lines[start]):
                break
    end = index
    while end + 1 < len(lines) and lines[end + 1].strip() \
            and not UNIT_START.match(lines[end + 1]):
        end += 1
    return "\n".join(lines[start:end + 1])


def parse_fields(inner, where):
    # `meta{...}` in prose is an ellipsis, not a field list — and a list of nothing
    # but separators carries no claim to grade. Anything else that will not parse is
    # CANNOT RUN, because scoring prose as a field name invents a contract.
    if not re.sub(r"[.\s,\u2026-]", "", inner):
        return []
    out = []
    for piece in inner.split(","):
        piece = piece.strip()
        if not piece:
            continue
        head = piece.split(":", 1)[0].strip()
        m = re.match(r"^([A-Za-z_]\w*)(\?)?$", head)
        if not m:
            raise CannotRun("%s: a contract list piece this harness cannot parse (%r) — "
                            "grading it anyway would score prose as a field name"
                            % (where, piece))
        out.append((m.group(1), bool(m.group(2))))
    return out


def attribute(lines, index, reg_by_token, rel):
    where = "%s:%d" % (rel, index + 1)
    para = paragraph(lines, index)
    hits = [reg_by_token[t] for t in reg_by_token if t in para]
    hits = sorted(set(hits))
    if len(hits) == 1:
        return hits[0]
    if len(hits) > 1:
        raise CannotRun("%s: a contract list whose paragraph names %d registries (%s) — "
                        "ambiguity here would grade one doc sentence twice"
                        % (where, len(hits), ", ".join(hits)))
    return None


def collect_lists(root):
    reg_by_token = dict((r["dir_token"], r["name"]) for r in REGISTRIES)
    lists = []
    for rel in DOCS:
        lines = doc_body(root, rel)
        for i, line in enumerate(lines):
            for res in LIST_RES:
                for m in res.finditer(line):
                    inner = m.group(1)
                    fields = parse_fields(inner, "%s:%d" % (rel, i + 1))
                    if not fields:
                        continue
                    name = attribute(lines, i, reg_by_token, rel)
                    lists.append({"doc": rel, "line": i + 1, "registry": name,
                                  "inner": inner.strip(), "fields": fields})
    unknown = [l for l in lists if l["registry"] is None]
    if unknown:
        raise CannotRun("%d contract list(s) name no registry dir in their paragraph "
                        "(%s) — an unattributable list is graded against nothing"
                        % (len(unknown),
                           ", ".join("%s:%d" % (l["doc"], l["line"]) for l in unknown)))
    if len(lists) != EXPECTED_LISTS:
        raise CannotRun("the docs carry %d contract list(s), EXPECTED_LISTS pins %d — "
                        "a list that vanished silently shrinks every door below to the "
                        "fields that are left. Bump the literal in the SAME commit as a "
                        "deliberate change." % (len(lists), EXPECTED_LISTS))
    for reg in REGISTRIES:
        for doc in DOCS:
            got = len([l for l in lists if l["registry"] == reg["name"] and l["doc"] == doc])
            want = reg["lists"][doc]
            if got != want:
                raise CannotRun("%s in %s: %d contract list(s), this harness owes %d — "
                                "the doc region it describes moved"
                                % (reg["name"], doc, got, want))
    return lists


# ------------------------------------------------------------------ the doors
def grade(regs, lists):
    problems = []
    notes = []
    contracts = dict((r["name"], r["contract"]) for r in regs)

    def claim(where, message):
        return "%s: %s" % (where, message)

    for reg in regs:
        name = reg["name"]
        contract = contracts[name]
        own = [l for l in lists if l["registry"] == name]

        # DOC-NAMED
        for l in own:
            where = claim("%s:%d" % (l["doc"], l["line"]), name)
            unknown = [f for f, _o in l["fields"] if f not in contract]
            if unknown:
                problems.append("%s promises field(s) %s that the registry does not "
                                "declare — the doc list is a contract the code does not "
                                "implement (renamed, or never existed)"
                                % (where, ", ".join(unknown)))
            # OPTIONAL — one direction only: a doc that MARKS a field optional must not
            # promise what the interface requires. A list with no `?` is shorthand.
            for f, optional in l["fields"]:
                if optional and f in contract and contract[f] is False:
                    problems.append("%s marks `%s?` optional while `%s` requires it — a "
                                    "drop-in written from this doc is refused by the "
                                    "registry" % (where, f, reg["iface"]))

        # COVERAGE
        documented = set()
        for l in own:
            documented |= set(f for f, _o in l["fields"])
        missing = sorted(n for n in contract if n not in documented)
        if missing:
            problems.append(claim("registry %s" % name,
                                  "declares %s in code and NO in-domain doc list mentions "
                                  "it — a reader copying the contract silently drops it "
                                  "(every doc list of this registry: %s)"
                                  % (", ".join(missing),
                                     ", ".join(sorted(set(l["inner"] for l in own))))))

        # MIRROR
        per_doc = dict((d, sorted(set(l["inner"] for l in own if l["doc"] == d))) for d in DOCS)
        if per_doc[DOCS[0]] != per_doc[DOCS[1]]:
            problems.append(claim("%s vs %s [registry %s]" % (DOCS[0], DOCS[1], name),
                                  "the two mirror docs state DIFFERENT shapes for one "
                                  "contract: %s says %s, %s says %s — they are one document "
                                  "delivered twice, so one reader is being handed a stale "
                                  "list" % (DOCS[0], per_doc[DOCS[0]],
                                            DOCS[1], per_doc[DOCS[1]])))
        notes.append("%s: %d fields, %d doc list(s), %d field claim(s)"
                     % (name, len(contract), len(own), sum(len(l["fields"]) for l in own)))

    if problems:
        raise Red("\n".join(problems))
    return notes


def main(argv):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        help="repo root to grade (controls run on copies)")
    opts = parser.parse_args(argv)
    root = opts.root

    if len(REGISTRIES) != EXPECTED_REGISTRIES:
        raise CannotRun("REGISTRIES lists %d, EXPECTED_REGISTRIES pins %d"
                        % (len(REGISTRIES), EXPECTED_REGISTRIES))

    regs = []
    for reg in REGISTRIES:
        reg = dict(reg)
        reg["contract"] = code_contract(reg, root)
        regs.append(reg)
    lists = collect_lists(root)
    notes = grade(regs, lists)

    total_fields = sum(len(r["contract"]) for r in regs)
    total_claims = sum(len(l["fields"]) for l in lists)
    print("DOC FIELD ROSTER OK — %d registries, %d contract fields, %d doc lists, "
          "%d field claims graded" % (EXPECTED_REGISTRIES, total_fields,
                                      EXPECTED_LISTS, total_claims))
    for note in notes:
        print("  " + note)
    print("  domain: %s, cut at %r; optional-marker door is one-directional by design"
          % (", ".join(DOCS), STATE_HEADING))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        sys.exit(2)
    except Red as exc:
        print("RED —")
        for line in str(exc).strip().splitlines():
            print("    " + line.strip())
        sys.exit(1)
