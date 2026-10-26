#!/usr/bin/env python3
"""Re-runnable preflight of the HARNESS IMAGE recipe (docker/harness/Dockerfile).

WHY this exists (measured, not assumed). The image IS the turn lane: no image ->
no turn, no reviewer, no verdict -> review-missing -> stall. Between 2026-10-26
13:51Z and 15:00Z the chain paid FIVE build attempts for two defects that a
static read of the same file answers before a single layer is built:

  * runs 40334271125 / 40335134249 / 40336007896 — turn jobs FAILED at
    'Build harness image' (the Owner R-2-77 agent-org bake).
  * run 40339371283 (job 121631387783) — the libasound2-only dep fix installed
    clean and the in-RUN verify died exit 127 on the NEXT absent library,
    `libdbus-1.so.3`: the runtime dep set had been HAND-LISTED instead of derived
    from the pinned deb's own Depends, so it covered one library of nineteen.
  * run 40342641149 (job 121643249434) — deps satisfied, apt triggers ran clean,
    and the verify STILL exited 1: `Error:
    /usr/share/emacs/30.1/etc/charsets: No such file or directory`. An `ENV`
    block placed AFTER a `RUN` does not apply inside that RUN, so the relocate
    verify ran without EMACSDATA / EMACSLOADPATH.

Both repairs are landed (Lead 10-fp: 85a1989 derives the dep set, f039fdd hoists
the ENV above the RUN) and the Dockerfile is Lead-adjacent machinery no seat
rewrites behind a running repair. What a seat keeps is the COMMAND that grades
the laws those two builds bought, read-only, before the next build is paid —
the same shape as scripts/slot_reader_probe.py ("the fix is Lead-owned
machinery, the measurement is a command any seat can re-run"). No docker here
(measured: `docker: command not found`, no /var/run/docker.sock), so every leg
is a TEXT read: it can refuse a recipe, never run one.

Six legs, one per promise the recipe owes:

  env-above-verify     every variable a relocated program needs at exec time is
                       declared ABOVE the RUN whose in-RUN verify execs it. A
                       Dockerfile ENV never reaches the RUN written before it,
                       and never reaches the RUN below it either — only above.
  dep-set-derived      the runtime deps of a relocated deb are DERIVED from that
                       deb's own Depends field, and every deb the same RUN
                       relocates is EXCLUDED from that derived list (apt would
                       otherwise pull a second, unpackaged copy beside it).
  wrapper-verify       every launcher the image WRITES BY HAND is chmod-ed
                       executable and exec'd inside the same RUN. `ln -sf` of an
                       installer-provided binary and `install -m 0755` carry
                       their own mode, so they are out of this leg's domain —
                       this leg is about the two printf-written exec wrappers.
  no-secret-baked      SECRET LAW (Owner 2026-10-21 18:27Z): an ENV/ARG whose
                       NAME is a credential carries no literal value, and no
                       credential file is COPY-ed into the image. Names travel,
                       values do not.
  body-population      every agent body the chain rotates through is still baked
                       (lane_budget_check.py grades the LANE script against the
                       provider's budgets; nothing graded the IMAGE, which is
                       where a body either exists or does not).
  install-disposition  every agent body installed from an UNPINNED source is
                       ruled: `strict` (a proven body whose failure must brick
                       the build, the 10-fm/10-di ruling) or `degrades` (a
                       dormant body that must retry and then fail into a loud
                       ABSENT marker — the 10-ba BUILD LAW, run 40117823054: one
                       flaky npm install of a dormant body killed the whole
                       chain). An unpinned install with no rule, or a rule whose
                       unpinned install has vanished, is CANNOT RUN: the roster
                       no longer describes the file, so a green would be a green
                       over coverage the harness does not have.

COVERAGE is graded, not assumed: each leg prints how many inputs it found, and
a leg that found zero is RED naming its own vacuity — the failure mode this
whole family exists for (a truncated list only makes a comparison agree over
less; DEVGUIDE *ELEVENTH harness law*).

Verdicts follow the house convention (docs/DEVGUIDE.md *EIGHTH* + *ELEVENTH*
harness laws): 0 = OK, 1 = RED (a claim is false), 2 = CANNOT RUN (the harness
no longer understands its own input — never a false red for a tree it has not
measured). The leg roster is pinned, so a leg that vanishes is a refusal too.

  python3 scripts/harness_image_check.py                    # grade this tree
  python3 scripts/harness_image_check.py --root /tmp/copy   # grade another tree
  python3 scripts/harness_image_check.py --selftest         # 11 controls

Deliberately NOT named `*_diff.py`: that glob IS the landing gate's twin roster
(`scripts/landing_gate.py` EXPECTED_TWINS cross-checks every `scripts/*_diff.py`
on disk against the harnesses its --fe legs actually run), and this grades one
recipe against its own laws, not an artifact against its twin.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

DOCKERFILE_REL = "docker/harness/Dockerfile"

# ------------------------------------------------------------ pinned inputs
# The PROMISE, not the disk. A harness that derives its expectations from the
# tree it grades proves nothing.
LEG_ROSTER = ("env-above-verify", "dep-set-derived", "wrapper-verify",
              "no-secret-baked", "body-population", "install-disposition")
EXPECTED_LEGS = 6

# The relocated program the batch lane execs, and the variables it must already
# be in the environment when an in-RUN verify runs it. Measured: run 40342641149
# died on EMACSDATA's charsets directory; 85a1989's NEEDED list died on a library.
# (name, must_be_nonempty) — EMACSNATIVELOADPATH is DELIBERATELY empty: it turns
# off native compilation, which is the only reason it is set at all.
RELOCATED_EXEC = {
    "emacs --batch": (("EMACSDATA", True),
                      ("EMACSLOADPATH", True),
                      ("EMACSNATIVELOADPATH", False),
                      ("LD_LIBRARY_PATH", True)),
}

# The bodies the chain rotates through: section marker in the recipe's own
# comments, and the launcher token that must appear in some RUN.
PINNED_BODIES = (("OpenCode", "opencode"),
                 ("Goose", "goose"),
                 ("Qoder", "qoder"),
                 ("CodeBuddy", "codebuddy"),
                 ("Cline", "cline"),
                 ("MCode", "mcode"),
                 ("agent-org", "emacs"))
EXPECTED_BODIES = 7

# How each body's install is allowed to arrive. `degrades` = retry, then a loud
# ABSENT/UNVERIFIED marker (the 10-ba BUILD LAW for a DORMANT body); `strict` =
# a failure must brick the build, the Lead's ruling for the proven bodies. A
# body absent from this table has no unpinned install (version- or sha-pinned) —
# that claim is graded, not trusted, by leg_install_disposition.
INSTALL_RULES = {"OpenCode": "strict",
                 "Goose": "strict",
                 "Qoder": "strict",
                 "CodeBuddy": "strict",
                 "Cline": "degrades"}
EXPECTED_RULES = 5

# A credential-shaped variable name. Names are legal (SECRET LAW asks for the
# NAME); a literal VALUE baked into an image layer is the violation.
SECRET_NAME = re.compile(r"(^|_)(API_?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH|KEY)(_|$)")
# A value that only forwards a name — the run-time injection the law allows.
VAR_REF = re.compile(r"^\$\{?[A-Za-z_][A-Za-z0-9_]*\}?$")
SECRET_FILE = re.compile(r"(\.pem|\.p12|\.jks|\.keystore|id_rsa|\.npmrc|\.netrc|secret|credential)", re.I)

ASSIGN = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"]*\"|'[^']*'|[^\s]*)")

LOUD_MARKER = re.compile(r"[A-Z][A-Z0-9_]*-(ABSENT|UNVERIFIED|SKIP)")


class Red(Exception):
    pass


class CannotRun(Exception):
    pass


class Step(object):
    def __init__(self, kind, args, line, comments):
        self.kind = kind
        self.args = args
        self.line = line
        self.comments = comments

    def blob(self):
        return " ".join(self.comments)


def parse(text):
    """Dockerfile -> ordered Steps, continuation lines joined, comments attached.

    Comments accumulate until the next instruction, so a body's section header is
    readable from the RUN it documents — the only place the DORMANT / proven
    rulings live.
    """
    lines = text.splitlines()
    steps = []
    comments = []
    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()
        if not stripped:
            i += 1
            continue
        if stripped.startswith("#"):
            comments.append(stripped)
            i += 1
            continue
        start = i + 1
        parts = []
        while i < n:
            cur = lines[i]
            cont = cur.rstrip().endswith("\\")
            chunk = cur.strip()
            if cont:
                chunk = chunk[:-1].strip()
            parts.append(chunk)
            i += 1
            if not cont:
                break
        body = " ".join(p for p in parts if p)
        match = re.match(r"([A-Za-z]+)\s+(.*)$", body, re.S)
        if not match:
            comments = []
            continue
        steps.append(Step(match.group(1).upper(), match.group(2), start, tuple(comments)))
        comments = []
    return steps


def assignments(args):
    return dict((m.group(1), m.group(2).strip("\"'")) for m in ASSIGN.finditer(args))


def read_dockerfile(root):
    path = os.path.join(root, DOCKERFILE_REL)
    if not os.path.isfile(path):
        raise CannotRun("%s is not on disk — the harness image recipe the chain builds "
                        "is gone, and this harness cannot grade a file that is not "
                        "there (a missing recipe is never a quieter green)" % DOCKERFILE_REL)
    text = open(path, "r").read()
    steps = parse(text)
    if len(steps) < 10:
        raise CannotRun("%s parsed to %d instruction(s); this harness reads a recipe of "
                        "24+ — the parse no longer understands its input, so every verdict "
                        "below would be arithmetic over nothing" % (DOCKERFILE_REL, len(steps)))
    return text, steps


def steps_of(steps, kind):
    return [s for s in steps if s.kind == kind]


def section_map(steps):
    """Pinned body marker -> the steps its `# --- <marker>` header documents.

    A section runs from its header until the next header of any kind, so a body
    baked across two RUNs (MCode: the private Node download, then the package
    install) is graded as ONE body, not as one RUN and an orphan.
    """
    out = {}
    current = None
    for step in steps:
        blob = step.blob()
        header = None
        for marker, _launcher in PINNED_BODIES:
            if "# --- %s" % marker in blob:
                header = marker
                break
        if header is None and "# --- " in blob:
            current = None
        if header:
            current = header
            out.setdefault(current, []).append(step)
        elif current is not None:
            out.setdefault(current, []).append(step)
    return out


def section_steps(steps, marker):
    return section_map(steps).get(marker, [])


def unpinned_installs(step):
    """Install commands in this step that arrive from an UNPINNED source.

    Pinned means: an explicit version (`@0.6.13`, `_30.1+1-6~bpo12+1`), a sha
    (`sha256sum -c`, `checkout <40-hex>`), or a tagged raw URL (`/v0.14.3/`).
    Everything else — `npm install -g <pkg>`, `curl ... | bash`, a `/stable/`
    download — is whatever the upstream publishes on the day the build runs.
    """
    args = step.args
    hits = []
    for match in re.finditer(r"npm install\b", args):
        window = args[match.start():match.start() + 200]
        if not re.search(r"@[0-9][0-9a-zA-Z.+~-]*", window):
            hits.append(("npm", window.split("&&")[0].strip()))
    for match in re.finditer(r"curl[^\n]*\|\s*(?:bash|sh)\b", args):
        hits.append(("pipe", match.group(0).strip()))
    for match in re.finditer(r"curl[^\n]*/download/stable/[^\s]+", args):
        hits.append(("stable", match.group(0).strip()))
    for match in re.finditer(r"git clone[^\n]*", args):
        window = args[match.start():match.start() + 400]
        if "checkout" not in window and not re.search(r"--branch\s+\S+", window):
            hits.append(("clone", match.group(0).strip()))
    return hits


# ------------------------------------------------------------------ the legs
def leg_env_above_verify(steps, log):
    """Every exec-time variable is declared ABOVE the RUN that execs the program."""
    reds = []
    graded = 0
    all_env = [(step.line, assignments(step.args)) for step in steps_of(steps, "ENV")]
    for step in steps:
        if step.kind != "RUN":
            continue
        for token, needed in RELOCATED_EXEC.items():
            if token not in step.args:
                continue
            graded += 1
            above = {}
            for line, pairs in all_env:
                if line < step.line:
                    above.update(pairs)
            missing = [name for name, non_empty in needed
                       if name not in above or (non_empty and not above[name].strip())]
            if not missing:
                continue
            below = sorted(set(ln for ln, pairs in all_env if ln > step.line
                               for name in missing if name in pairs))
            if below:
                why = ("declared only at :%s — BELOW this RUN. A Dockerfile ENV block "
                       "does NOT apply inside the RUN written above it: the in-RUN verify "
                       "runs without its data paths (measured: run 40342641149, "
                       "'/usr/share/emacs/30.1/etc/charsets: No such file or directory', "
                       "repaired by the Lead's hoist at f039fdd)"
                       % ", :".join(str(ln) for ln in below))
            else:
                why = "never declared anywhere in the recipe"
            reds.append("env-above-verify: the RUN at :%d execs `%s` while %s is %s — "
                        "that verify cannot start" % (step.line, token, ", ".join(missing), why))
    if graded == 0:
        reds.append("env-above-verify COVERAGE: no RUN execs any relocated program this "
                    "leg knows (%s) — the leg graded 0 of its own inputs, so its silence "
                    "is not evidence. Fix the table or delete the leg in the SAME commit."
                    % ", ".join(sorted(RELOCATED_EXEC)))
    log("env-above-verify", graded)
    return reds


def leg_dep_set_derived(steps, log):
    """Deps derived from the pinned deb's own Depends; relocated debs excluded."""
    reds = []
    graded = 0
    for step in steps_of(steps, "RUN"):
        debs = [os.path.basename(p) for p in re.findall(r"dpkg -x\s+(\S+\.deb)", step.args)]
        if not debs:
            continue
        graded += 1
        names = [d.split("_")[0] for d in debs]
        if "apt-get satisfy" not in step.args:
            reds.append("dep-set-derived: the RUN at :%d relocates %s with `dpkg -x` but "
                        "never satisfies their Depends — the image ships a binary whose "
                        "libraries are whatever the base happens to carry (measured: run "
                        "40339371283, exit 127 on `libdbus-1.so.3`)"
                        % (step.line, ", ".join(sorted(set(names)))))
            continue
        derived = re.search(r"([A-Za-z_][A-Za-z0-9_]*)=\s*\"\$\(dpkg-deb -f (\S+\.deb) Depends",
                            step.args)
        if not derived:
            reds.append("dep-set-derived: the RUN at :%d hands `apt-get satisfy` an operand "
                        "that is not derived from a deb's own Depends field — a HAND-LISTED "
                        "dep set is the exact shape that cost run 40339371283 (libasound2 "
                        "listed, 18 of 19 NEEDED libraries absent)" % step.line)
        else:
            var, src_deb = derived.group(1), os.path.basename(derived.group(2))
            tail = step.args[step.args.index("apt-get satisfy"):][:240]
            if '"$%s"' % var not in tail and "$" + var not in tail:
                reds.append("dep-set-derived: the RUN at :%d derives `%s` from %s but feeds "
                            "`apt-get satisfy` something else — the derived list is dead "
                            "code and the operand is what actually installs"
                            % (step.line, var, src_deb))
            if src_deb not in debs:
                reds.append("dep-set-derived: the RUN at :%d derives its dep list from %s, "
                            "a deb it does not relocate (%s) — the list belongs to a "
                            "different payload than the one that ships"
                            % (step.line, src_deb, ", ".join(sorted(set(debs)))))
        excl = re.search(r"grep -v -E '([^']+)'", step.args)
        if not excl:
            reds.append("dep-set-derived: the RUN at :%d derives its dep list but excludes "
                        "nothing — every relocated deb must leave the apt list, or apt "
                        "installs a second, unpackaged copy beside it" % step.line)
        else:
            members = [m for m in excl.group(1).lstrip("^(").rstrip(")").split("|") if m]
            unruled = [name for name in names
                       if not any(name == m or name.startswith(m) for m in members)]
            if unruled:
                reds.append("dep-set-derived: the RUN at :%d relocates %s into the image but "
                            "its exclusion list (%s) does not name them — apt would resolve "
                            "those names from the index and install a copy that shadows the "
                            "pinned, byte-readelf-measured deb"
                            % (step.line, ", ".join(sorted(set(unruled))),
                               ", ".join(members)))
    if graded == 0:
        reds.append("dep-set-derived COVERAGE: no RUN relocates a .deb with `dpkg -x` — the "
                    "leg graded 0 of its own inputs. A dep law nobody reads is not a green, "
                    "it is a vanished leg")
    log("dep-set-derived", graded)
    return reds


def leg_wrapper_verify(steps, log):
    """Every hand-written launcher is chmod-ed and exec'd inside its own RUN."""
    reds = []
    graded = 0
    for step in steps_of(steps, "RUN"):
        written = re.findall(r">\s*/usr/local/bin/([\w.\-]+)", step.args)
        for name in written:
            graded += 1
            path = "/usr/local/bin/%s" % name
            idx = step.args.find("> " + path)
            if idx < 0:
                idx = step.args.find(path)
            tail = step.args[idx:]
            if not re.search(r"chmod[^\n]*%s" % re.escape(path), tail):
                reds.append("wrapper-verify: the RUN at :%d writes %s but never chmods it "
                            "executable in the same step — the wrapper lands non-executable "
                            "and the first paid segment discovers that, not the build"
                            % (step.line, path))
            if not re.search(r"(?:^|[\s;&])%s\s+--" % re.escape(name), tail):
                reds.append("wrapper-verify: the RUN at :%d writes %s but never execs it in "
                            "the same step — a relocated launcher that is never run at build "
                            "time ships unverified (the emacs wrapper is exactly the one that "
                            "caught the charsets failure, because the recipe DOES run it)"
                            % (step.line, path))
    if graded == 0:
        reds.append("wrapper-verify COVERAGE: no hand-written `/usr/local/bin/<name>` wrapper "
                    "in the recipe — the leg graded 0 of its own inputs (symlinks and "
                    "`install -m` carry their own mode and were never in this leg's domain, "
                    "so their absence does not make this a pass)")
    log("wrapper-verify", graded)
    return reds


def leg_no_secret_baked(steps, log):
    """SECRET LAW: credential-shaped NAMES are legal, baked VALUES are not."""
    reds = []
    graded = 0
    for step in steps:
        if step.kind in ("ENV", "ARG"):
            pairs = assignments(step.args) if step.kind == "ENV" else \
                dict(ASSIGN.findall(step.args))
            for name, value in sorted(pairs.items()):
                graded += 1
                if not SECRET_NAME.search(name):
                    continue
                if not value.strip():
                    continue          # an empty default: the name travels, nothing else
                if VAR_REF.match(value):
                    continue          # forwards a run-time injection, bakes no value
                reds.append("no-secret-baked: %s at :%d assigns a literal value to %s — "
                            "SECRET LAW (Owner 2026-10-21 18:27Z) says credentials travel "
                            "as ENV VAR NAMES only. A value written here is a layer, and a "
                            "layer is permanent" % (step.kind, step.line, name))
        elif step.kind == "COPY":
            sources = step.args.split()[:-1]
            for src in sources:
                graded += 1
                if SECRET_FILE.search(os.path.basename(src)):
                    reds.append("no-secret-baked: the COPY at :%d pulls %s into the image — "
                                "a credential file in a layer is readable by every container "
                                "this image ever runs" % (step.line, src))
    if graded == 0:
        reds.append("no-secret-baked COVERAGE: no ENV/ARG assignment and no COPY source was "
                    "read — the leg graded 0 of its own inputs")
    log("no-secret-baked", graded)
    return reds


def leg_body_population(steps, log):
    """Every rotated-through body is still baked, by section header AND launcher."""
    reds = []
    found = []
    for marker, launcher in PINNED_BODIES:
        section = section_steps(steps, marker)
        if not section:
            reds.append("body-population: no instruction in the recipe is documented by the "
                        "`# --- %s` body header — a body that leaves the image leaves every "
                        "lane that names it unanswerable, and lane_budget_check.py would "
                        "still print a budget for it" % marker)
            continue
        joined = " ".join(step.args for step in section)
        if not re.search(r"\b%s\b" % re.escape(launcher), joined):
            reds.append("body-population: the `%s` section is present but none of its steps "
                        "name its launcher `%s` — the header is prose, the launcher is the "
                        "bake" % (marker, launcher))
            continue
        found.append(marker)
    if len(found) != EXPECTED_BODIES and not reds:
        reds.append("body-population: %d of %d pinned bodies located — the roster and the "
                    "recipe no longer describe the same image"
                    % (len(found), EXPECTED_BODIES))
    log("body-population", len(PINNED_BODIES))
    return reds


def leg_install_disposition(steps, log):
    """An unpinned body install is either ruled strict or must degrade loudly."""
    reds = []
    graded = 0
    ruled = set()
    absent = set()
    for marker, launcher in PINNED_BODIES:
        section = section_steps(steps, marker)
        if not section:
            absent.add(marker)
            continue                       # body-population already names it
        hits = []
        for step in section:
            hits.extend(unpinned_installs(step))
        if not hits:
            continue
        graded += len(hits)
        rule = INSTALL_RULES.get(marker)
        if rule is None:
            reds.append("install-disposition: the `%s` body is installed from an unpinned "
                        "source (%s) and no rule in this harness names it — strict or "
                        "degrades is a RULING, not a detail, and an unruled install lets the "
                        "build decide by accident" % (marker, "; ".join(h[1][:60] for h in hits)))
            continue
        ruled.add(marker)
        if rule != "degrades":
            continue
        joined = " ".join(step.args for step in section)
        if "||" not in joined or not LOUD_MARKER.search(joined):
            reds.append("install-disposition: the `%s` body is ruled `degrades` (a DORMANT "
                        "body must never brick the image — the 10-ba BUILD LAW, run "
                        "40117823054) but its section starting at :%d carries no `||` "
                        "fallback with a loud marker: one flaky install from upstream and "
                        "there is no image, no turn, no review"
                        % (marker, section[0].line))
    stale = sorted(set(INSTALL_RULES) - ruled - absent)
    if stale:
        raise CannotRun("install-disposition: this harness rules %s, but each of those is "
                        "baked and NO LONGER installed from an unpinned source — the roster "
                        "no longer describes the file it grades, so a green here would be "
                        "arithmetic over coverage that is gone. Pin the new state in the "
                        "SAME commit" % ", ".join(stale))
    if len(INSTALL_RULES) != EXPECTED_RULES:
        raise CannotRun("install-disposition: the rule table holds %d entries, this harness "
                        "pins %d — its own roster is no longer its own expectation"
                        % (len(INSTALL_RULES), EXPECTED_RULES))
    log("install-disposition", graded)
    return reds


LEGS = (leg_env_above_verify, leg_dep_set_derived, leg_wrapper_verify,
        leg_no_secret_baked, leg_body_population, leg_install_disposition)


def grade(root):
    text, steps = read_dockerfile(root)
    counts = {}

    def log(leg, n):
        counts[leg] = n

    reds = []
    for leg in LEGS:
        reds.extend(leg(steps, log))
    names = tuple(c for c in counts)
    if len(names) != EXPECTED_LEGS or set(names) != set(LEG_ROSTER):
        raise CannotRun("this harness ran %d leg(s) — %s — but its roster pins %d: %s. "
                        "A leg that no longer runs is not a smaller green, it is a harness "
                        "that stopped describing the thing it claims to check"
                        % (len(names), ", ".join(names), EXPECTED_LEGS, ", ".join(LEG_ROSTER)))
    print("  recipe     %s (%d instruction(s), %d line(s))"
          % (DOCKERFILE_REL, len(steps), text.count("\n") + 1))
    for leg in LEG_ROSTER:
        print("  %-20s %d input(s) graded" % (leg, counts[leg]))
    if reds:
        print("\nHARNESS IMAGE RED — %d finding(s) that a build would have paid for:"
              % len(reds))
        for line in reds:
            print("  %s" % line)
        print("  Read-only over the recipe; it issues no verdict and builds nothing — "
              "docker is not even present where this runs.")
        return 1
    print("HARNESS IMAGE OK — %d leg(s) green over %s: the ENV reaches the RUN that "
          "verifies, the dep set is derived from the pinned deb, every hand-written "
          "launcher is chmod-ed and exec'd, nothing credential-shaped carries a value, "
          "all %d bodies are baked and every unpinned install is ruled"
          % (EXPECTED_LEGS, DOCKERFILE_REL, EXPECTED_BODIES))
    return 0


# ------------------------------------------------------------------ controls
def _mutate(root, find, replace, label):
    path = os.path.join(root, DOCKERFILE_REL)
    text = open(path, "r").read()
    if find not in text:
        raise AssertionError("control %s: its anchor is not in the recipe — the control "
                             "rotted, not the tree" % label)
    open(path, "w").write(text.replace(find, replace, 1))


def control_no_change(root):
    pass


def control_env_below_run(root):
    path = os.path.join(root, DOCKERFILE_REL)
    text = open(path, "r").read()
    start = text.index("ENV LD_LIBRARY_PATH=")
    end = text.index("RUN mkdir -p /opt/emacs30")
    env_block = text[start:end]
    anchor = 'agent-org batch lane baked (pin ${AGENT_ORG_PIN})"\n'
    if anchor not in text:
        raise AssertionError("control ENV hoist reverted: the emacs RUN's last line is gone")
    rest = text[:start] + text[end:]
    out = rest.replace(anchor, anchor + env_block, 1)
    open(path, "w").write(out)


def control_drop_emacsdata(root):
    _mutate(root, "    EMACSDATA=/opt/emacs30/usr/share/emacs/30.1/etc \\\n", "", "EMACSDATA deleted")


def control_hand_listed_deps(root):
    _mutate(root, 'apt-get satisfy -y -qq --no-install-recommends "$LIBDEPS"',
            'apt-get satisfy -y -qq --no-install-recommends "libasound2,libgmp10"',
            "satisfy hand-listed")


def control_unexcluded_deb(root):
    _mutate(root, "^(emacs-|emacsen-|install-info|libtree-sitter0)",
            "^(emacs-|emacsen-|install-info)", "relocated deb not excluded")


def control_strip_verify(root):
    _mutate(root, " && emacs --batch --eval '(message \"emacs %s relocated ok\" emacs-version)'",
            "", "emacs verify stripped (1/2)")
    _mutate(root, " && emacs --batch -L /opt/agent-org --eval '(require (quote agent-org-batch))'",
            "", "emacs verify stripped (2/2)")


def control_strip_chmod(root):
    _mutate(root, " && chmod 0755 /usr/local/bin/emacs", "", "wrapper chmod stripped")


def control_bake_secret(root):
    path = os.path.join(root, DOCKERFILE_REL)
    text = open(path, "r").read()
    open(path, "w").write(text.replace("STOPSIGNAL SIGTERM",
                                       "ENV QODER_API_KEY=sk-literally-not-a-real-secret\n"
                                       "STOPSIGNAL SIGTERM", 1))


def control_delete_body(root):
    path = os.path.join(root, DOCKERFILE_REL)
    text = open(path, "r").read()
    start = text.index("# --- Goose body")
    end = text.index("# --- Qoder body")
    open(path, "w").write(text[:start] + text[end:])


def control_remove_fallback(root):
    path = os.path.join(root, DOCKERFILE_REL)
    text = open(path, "r").read()
    start = text.index("RUN (npm install -g cline")
    end = text.index("# --- MCode body")
    replacement = ("RUN npm install -g cline \\\n && timeout 120 cline --version\n\n"
                   "# --- MCode body")
    open(path, "w").write(text[:start] + replacement + text[end:])


def control_missing_recipe(root):
    os.remove(os.path.join(root, DOCKERFILE_REL))


CONTROLS = (
    ("shipped recipe is green", control_no_change, 0, "HARNESS IMAGE OK", True),
    ("ENV hoist reverted", control_env_below_run, 1, "env-above-verify", True),
    ("EMACSDATA deleted", control_drop_emacsdata, 1, "env-above-verify", True),
    ("satisfy hand-listed", control_hand_listed_deps, 1, "dep-set-derived", True),
    ("relocated deb not excluded", control_unexcluded_deb, 1, "dep-set-derived", True),
    ("emacs verify stripped", control_strip_verify, 1, "wrapper-verify", True),
    ("wrapper chmod stripped", control_strip_chmod, 1, "wrapper-verify", True),
    ("a credential value baked", control_bake_secret, 1, "no-secret-baked", True),
    ("goose body block deleted", control_delete_body, 1, "body-population", True),
    ("cline fallback removed", control_remove_fallback, 1, "install-disposition", True),
    ("recipe file missing", control_missing_recipe, 2, "CANNOT RUN", True),
)
EXPECTED_CONTROLS = 11


def selftest(root):
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d control(s) but this harness pins %d — "
                        "its population is no longer its own expectation"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    script = os.path.join(root, "scripts", "harness_image_check.py")
    if not os.path.isfile(script):
        raise CannotRun("cannot find scripts/harness_image_check.py to run the controls "
                        "against — grade a real checkout")
    failures = []
    for name, mutation, expected_rc, expected_text, _green in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="harness-image-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                          ".pytest_cache", ".git", "dist",
                                                          "build", "target"))
            mutation(target)
            proc = subprocess.run([sys.executable, script, "--root", target],
                                  capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-28s -> rc %d as expected (%s)"
                      % (name, proc.returncode, expected_text))
            else:
                failures.append("%-28s wanted rc %d / %r, got rc %d:\n%s"
                                % (name, expected_rc, expected_text, proc.returncode, out))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        print("\nSELFTEST RED — %d control(s) did not fail the way the law they grade "
              "requires:" % len(failures))
        for line in failures:
            print("  %s" % line)
        return 1
    print("SELFTEST OK — %d control(s), every leg proved able to fail" % EXPECTED_CONTROLS)
    return 0


def main(argv):
    ap = argparse.ArgumentParser(description="Preflight the harness image recipe, read-only")
    ap.add_argument("--root", help="tree to grade (default: this checkout)")
    ap.add_argument("--selftest", action="store_true", help="run the controls")
    ns = ap.parse_args(argv[1:])
    root = os.path.abspath(ns.root or os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        if ns.selftest:
            return selftest(root)
        return grade(root)
    except CannotRun as exc:
        print("CANNOT RUN: %s" % exc)
        return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
