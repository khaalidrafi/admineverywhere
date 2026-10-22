#!/usr/bin/env python3
"""Machine check for the DROP-IN CONTRACT REGISTRY: the three glob registries,
their directories, and who actually imports them.

Why this exists (measured, not assumed): on 2026-10-22 00:22Z the seat found
`app/src/lib/widgets/index.ts` — a second implementation of the FR-R008 widget
contract that ONLY a test imported, while the app imported `app/src/widgets/
index.ts`. The advertised "drop-in contract" suite therefore graded a module
that shipped in zero product paths, and a mutation that silently dropped a
built-in from the SHIPPED registry answered `8 passed`, rc 0. The fix deleted
the dead copy and repointed the test; nothing on this box still guarantees the
dead twin stays dead, or that a future registry is not written the same way.

So this harness grades the structural facts a per-side unit test cannot see:

  ROSTER      which files in `app/src` carry an `import.meta.glob(...)`, matched
              by path against the pinned list below. Drift means this harness is
              no longer looking at the registries it describes -> CANNOT RUN.
  TWIN        no drop-in directory may be claimed by TWO registry files. That is
              the dead-twin shape exactly, and it is decided by the resolved glob
              target, not by a directory NAME (lib/widgets/feed.ts shares a name
              with the registry dir and is legitimately not a twin).
  POPULATION  each pinned directory must exist and hold at least its pinned floor
              of files that declare `export const meta` — an emptied or truncated
              drop-in dir is coverage lost, not "0 widgets, green".
  SHIPPED     each registry must have at least one importer OUTSIDE `__tests__`
              and outside its own drop-in dir. Zero means the contract a test
              asserts is not the code the app runs.
  REFERENCE   at least one test file must glob a pinned dir — the declaration-
              level read that grades the registry against its inputs, not itself.

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness no longer understands its own input — never a
false red for a tree it has not measured).

Controls run against copies via --src, so the shipped tree is only ever read:
  cp -r app/src /tmp/x && python3 scripts/registry_roster_diff.py --src /tmp/x

It is the fifth FE leg of the landing gate (`python3 scripts/landing_gate.py --fe`
-> `registry-twin`), which is why the file is named `*_diff.py`: `landing_gate.py`
cross-checks its twin roster against that glob (EXPECTED_TWINS), so the name IS the
wiring — a harness written beside the gate but not in that glob is a comparison no
merge runs, and it was exactly that unwired state which let this seat ship the check
as a candidate it could not measure (no app/node_modules). It diffs two rosters the
way the other twins diff two documents: the pinned promise (3 registries, their dirs,
their floors) against the tree on disk.
"""

import argparse
import os
import re
import sys

# ---------------------------------------------------------------- pinned input
# dir/ext/floor are not derived from the disk: they are the promise. The glob
# literal parsed out of the registry file is diffed against them, so a registry
# that starts reading a different directory stops matching instead of quietly
# proving less.
REGISTRIES = (
    {
        "name": "widgets",
        "registry": os.path.join("widgets", "index.ts"),
        "dir": "widgets",
        "ext": ".svelte",
        "min_declaring": 8,
    },
    {
        "name": "pages",
        "registry": os.path.join("lib", "pages", "index.ts"),
        "dir": "pages",
        "ext": ".svelte",
        "min_declaring": 6,
    },
    {
        "name": "actions",
        "registry": os.path.join("lib", "actions", "index.ts"),
        "dir": "actions",
        "ext": ".ts",
        "min_declaring": 2,
    },
)
EXPECTED_REGISTRIES = 3

SOURCE_EXTS = (".ts", ".svelte", ".js")
RESOLVED_FILES = set()

GLOB_RE = re.compile(r"import\.meta\.glob(?:<[^>]*>)?\s*\(\s*[\"']([^\"']+)[\"']")
IMPORT_RE = re.compile(r"(?:^|\s)(?:import|export)\b[^;]*?\bfrom\s*[\"']([^\"']+)[\"']", re.M)
BARE_IMPORT_RE = re.compile(r"\bimport\s*[\"']([^\"']+)[\"']")
META_RE = re.compile(r"\bexport\s+const\s+meta\b")


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


def source_files(src):
    out = []
    for root, dirs, files in os.walk(src):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", "dist", "build")]
        for name in files:
            if name.endswith(SOURCE_EXTS):
                out.append(os.path.relpath(os.path.join(root, name), src).replace(os.sep, "/"))
    return sorted(out)


def specifiers(text):
    found = IMPORT_RE.findall(text) + BARE_IMPORT_RE.findall(text)
    return [s for s in found if s.startswith(".")]


def resolve(from_rel, spec):
    """Relative import specifier -> repo-relative module path, or None."""
    base = os.path.dirname(from_rel)
    joined = os.path.normpath(os.path.join(base, spec)).replace(os.sep, "/")
    for cand in (joined, joined + ".ts", joined + ".svelte", joined + ".js",
                 joined + "/index.ts", joined + "/index.svelte"):
        if cand in RESOLVED_FILES:
            return cand
    return None


def is_test(rel):
    return "__tests__" in rel.split("/")


def scan(src):
    files = source_files(src)
    if not files:
        raise CannotRun("no source files under %s — wrong --src?" % src)
    RESOLVED_FILES.clear()
    RESOLVED_FILES.update(files)
    bodies = {rel: read(os.path.join(src, rel)) for rel in files}
    return files, bodies


def glob_targets(src, files, bodies):
    """Every `import.meta.glob` in app/src OUTSIDE `__tests__`, resolved to the
    directory it claims.

    EXEMPTION, recorded because it bites: test files may glob a pinned dir. The
    repoint of the widget contract suite (2026-10-22 00:22Z) made the test read
    the drop-in declarations through the registry's own glob so a silently
    dropped built-in cannot hide — that reference read is the fix, not a twin,
    and a name-based rule would fire on it. The exemption is therefore scoped to
    `__tests__` paths, and it costs nothing: a test glob was never evidence of a
    shipped registry, and tests are already excluded from the SHIPPED door.
    """
    claims = {}
    for rel in files:
        if is_test(rel):
            continue
        for pattern in GLOB_RE.findall(bodies[rel]):
            target = os.path.normpath(os.path.join(os.path.dirname(rel), pattern)).replace(os.sep, "/")
            dirname = os.path.dirname(target) if "*" in os.path.basename(target) else target
            claims.setdefault(rel, []).append(os.path.normpath(dirname).replace(os.sep, "/"))
    return claims


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--src", default=os.path.join("app", "src"),
                    help="source root to measure (default app/src; controls run this on copies)")
    args = ap.parse_args()

    src = args.src
    if not os.path.isdir(src):
        raise CannotRun("no such source root: %s" % src)

    files, bodies = scan(src)
    claims = glob_targets(src, files, bodies)

    # ---- ROSTER: the files that glob, matched by identity against the pin.
    on_disk = sorted(claims)
    pinned = sorted(reg["registry"].replace(os.sep, "/") for reg in REGISTRIES)
    missing = [p for p in pinned if p not in on_disk]
    undeclared = [d for d in on_disk if d not in pinned]
    if missing or undeclared or len(on_disk) != EXPECTED_REGISTRIES or len(pinned) != EXPECTED_REGISTRIES:
        raise CannotRun(
            "registry ROSTER drift — this harness is no longer measuring the "
            "registries it describes. MISSING=%s UNDECLARED=%s disk=%d pins=%d"
            % (missing or "-", undeclared or "-", len(on_disk), EXPECTED_REGISTRIES))

    # ---- TWIN: two registry files claiming one drop-in directory.
    claimed_by = {}
    for reg_file, targets in claims.items():
        for tgt in targets:
            claimed_by.setdefault(tgt, []).append(reg_file)
    for tgt, owners in sorted(claimed_by.items()):
        if len(owners) > 1:
            raise Red("TWIN REGISTRY: drop-in dir %r is globbed by %d registries (%s) — "
                      "only one of them is the module the app imports; the rest is a "
                      "second fixture that tests can pass while product paths ignore"
                      % (tgt, len(owners), ", ".join(sorted(owners))))

    problems = []
    notes = []
    total_declaring = 0
    # The exemption above must cover something: a test glob over a pinned dir is
    # the declaration-level reference read that catches a silently dropped
    # built-in. If none exists, the exemption is dead and the suite is back to
    # grading the registry against itself.
    pinned_dirs = {reg["dir"] for reg in REGISTRIES}
    reference_globs = []
    for rel in files:
        if not is_test(rel):
            continue
        for pattern in GLOB_RE.findall(bodies[rel]):
            target = os.path.normpath(os.path.join(os.path.dirname(rel), pattern)).replace(os.sep, "/")
            if target.split("/")[0] in pinned_dirs:
                reference_globs.append(rel)
    reference_globs = sorted(set(reference_globs))
    if not reference_globs:
        problems.append("REFERENCE GONE: no file under `__tests__` globs a pinned drop-in dir — "
                        "the contract suite now compares the registry only against itself, which is "
                        "how the dead twin stayed green (dropping a built-in answered `passed`)")
    else:
        notes.append("reference: %s reads declarations through the registry's own glob"
                     % ", ".join(reference_globs))
    for reg in REGISTRIES:
        name = reg["name"]
        reg_file = reg["registry"].replace(os.sep, "/")

        # the registry's own glob literal must point at the pinned dir
        targets = claims[reg_file]
        if reg["dir"] not in targets:
            raise CannotRun("%s registry %s globs %s, not the pinned dir %r — the "
                            "harness cannot tell which directory the contract lives in"
                            % (name, reg_file, targets, reg["dir"]))

        dirpath = os.path.join(src, reg["dir"])
        if not os.path.isdir(dirpath):
            problems.append("DIR %s: pinned drop-in dir %r does not exist" % (name, reg["dir"]))
            continue

        declaring = sorted(f for f in files
                           if os.path.dirname(f) == reg["dir"]
                           and f.endswith(reg["ext"])
                           and META_RE.search(bodies[f]))
        total_declaring += len(declaring)
        if len(declaring) < reg["min_declaring"]:
            problems.append("POPULATION %s: %s/%s declaring `export const meta`, pinned floor is %d "
                            "(%s) — the suite no longer sees the drop-ins it was written for"
                            % (name, reg["dir"], reg["ext"], reg["min_declaring"],
                               ", ".join(os.path.basename(f) for f in declaring) or "none"))

        # ---- SHIPPED: at least one importer outside __tests__ AND outside the
        # registry's own drop-in dir — a file in actions/ importing the actions
        # registry for its type is self-reference, not a consumer.
        importers = []
        for other in files:
            if other == reg_file or is_test(other) or os.path.dirname(other) == reg["dir"]:
                continue
            for spec in specifiers(bodies[other]):
                if resolve(other, spec) == reg_file:
                    importers.append(other)
                    break
        if not importers:
            problems.append("TEST-ONLY-MODULE %s: registry %s is imported by ZERO product files "
                            "outside its own drop-in dir and `__tests__` — whatever the contract "
                            "test asserts, the app does not run it"
                            % (name, reg_file))
        else:
            notes.append("%s: %d drop-ins, %d product importers (%s)"
                         % (name, len(declaring), len(importers),
                            ", ".join(importers[:3]) + (" ..." if len(importers) > 3 else "")))

    if problems:
        raise Red("\n".join(problems))

    print("REGISTRY ROSTER OK — %d registries, %d declared drop-ins" % (EXPECTED_REGISTRIES, total_declaring))
    for note in notes:
        print("  " + note)
    print("  twin check: %d glob dirs, each claimed by exactly one registry" % len(claimed_by))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        sys.exit(2)
    except Red as exc:
        print("RED —")
        for line in str(exc).strip().splitlines():
            print("    " + line.strip())
        sys.exit(1)
