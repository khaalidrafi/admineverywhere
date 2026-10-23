#!/usr/bin/env python3
"""chat_feature_check.py — the chat send-back's verdict as ONE command.

WHY this exists (measured, not assumed). The board item "verify-chat-2"
(agent-team/TODOS.org) carries FOUR specced checks, and until now every one of
them lived only in prose: a seat's chat entry and a :LOGBOOK: note. Prose is
not re-runnable (DEVGUIDE *EIGHTH harness law: a GATE that lives as prose is a
check nobody can re-run), and this repo has already paid for that shape once —
the very same item's own log records that BOTH merge-blocking findings of the
chat send-back slipped past a GREEN suite:

  * "buildSchemaPrompt (chat.ts:48) ships with 5 tests and no caller, while
    the live prompt path stays ChatPanel.svelte:69 -> schemaSummary", and
  * "the same commit removed systemPrompt's legend while the panel still
    passes schemaSummary output",

because every test fed the helper a HAND-WRITTEN string instead of the prompt
the panel actually POSTs. A check that cannot fail is not a check (DEVGUIDE
*ELEVENTH harness law, applied to the harness itself), so this one grades the
four claims against the tree (plus the one-builder refusal that closes the
fifth), the way the other harnesses grade their pairs:

  GOVERNANCE  agent-team/TEAM.md carries no "MEMBER IDS" section (the
              governance reversal the send-back was about), still carries its
              DISPATCH PREAMBLE RULE and FENCE FORMAT headings, and every
              fenced-language hit is the prohibition that NAMES it. mainline's
              own "(no ```followup, no ```bash, no ```text)" line is a RULE,
              not a violation — the item's log records that false positive,
              so this harness does not repeat it.
  SWEEP       the three files the send-back touched carry ZERO hard-coded
              colors: no hex/rgb/hsl literal and no Tailwind palette utility;
              the panel resolves its colors from the brand vars.
  ONE-PANEL   exactly one ChatPanel.svelte exists under app/src, exactly one
              non-test importer, exactly one mount.
  LIVE-PATH   the panel really calls buildSchemaPrompt (not the dead
              schemaSummary), the legend the send-back restored is still in
              chat.ts INSIDE the prompt builder, and the wire-level proof (the
              mount test that asserts the captured request body) is still on
              disk — so "the prompt the panel ACTUALLY sends is the wired one"
              rests on a machine proof, not on a hand-written string.
  ONE-BUILDER exactly ONE product file in app/src builds the AI schema-prompt
              line, and it is chat.ts. LIVE-PATH alone cannot see the opposite
              failure: it greps the panel for the dead name, so a second
              legend-less builder stays invisible right up to the moment a
              future edit imports it — which is the exact defect this item was
              filed for (openapi.ts kept shipping schemaSummary, a clone of the
              builder with no legend and no caller, green behind its own unit
              test). Existence of an alternative is what makes re-wiring
              possible, so the alternative is what this leg refuses.

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness no longer understands its own input — never a
false red for a tree it has not measured).

Controls run against copies via --root, so the shipped tree is only read:
  cp -r . /tmp/x && python3 scripts/chat_feature_check.py --root /tmp/x

And the harness proves it can FAIL, against a copy, with no hand-holding:
  python3 scripts/chat_feature_check.py --selftest

It is deliberately NOT named `*_diff.py`: that glob is the landing gate's twin
roster (scripts/landing_gate.py: EXPECTED_TWINS) and this grades no PAIR of
artifacts — it stands beside the gate and is run by hand, like
scripts/chain_test_check.py and scripts/release_readiness.py.
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ------------------------------------------------------------ pinned inputs
# These are the PROMISE, not the disk: they are what the item said, and the
# tree is measured against them. A harness that derives its expectations from
# the tree it grades proves nothing.
GOVERNANCE_REL = "agent-team/TEAM.md"
PANEL_REL = "app/src/ai/ChatPanel.svelte"
CHAT_REL = "app/src/lib/chat.ts"
CHAT_TEST_REL = "app/src/lib/__tests__/chat.test.ts"
MOUNT_PROOF_REL = "app/src/lib/__tests__/chatMount.test.ts"
SHELL_REL = "app/src/components/Shell.svelte"
OPENAPI_REL = "app/src/lib/openapi.ts"
APP_SRC = "app/src"

# the three files the send-back touched, and the size of that population
SWEPT_FILES = (PANEL_REL, CHAT_REL, CHAT_TEST_REL)
EXPECTED_SWEPT_FILES = 3
EXPECTED_PANEL_FILES = 1
EXPECTED_IMPORTERS = 1
EXPECTED_MOUNTS = 1
GOVERNANCE_SECTIONS = ("DISPATCH PREAMBLE RULE", "FENCE FORMAT")
EXPECTED_GOVERNANCE_SECTIONS = 2
# the panel must resolve its colors from the brand vars AT ALL (one is enough;
# the count of brand-var uses is a fact about the file, not a promise)
EXPECTED_BRAND_VARS_IN_PANEL = 1
LEGEND = "Available models (fields in parentheses; fk = foreign key to that model):"

# The AI schema-prompt line's shape — `${f.name}(fk->${f.fkModel})` — is written
# in exactly ONE product file, and that file is the live prompt builder. A test
# file may repeat the literal (that is the wire-level assertion), so __tests__ is
# out of domain here; a second PRODUCT file carrying it is a second builder, and a
# second builder is what a future edit silently imports.
PROMPT_SHAPE = "(fk->"
EXPECTED_PROMPT_BUILDERS = 1

# A hard-coded color: a hex literal or an rgb()/hsl() call. Brand vars are
# var(--brand-*) and carry no color of their own.
COLOR_LITERAL_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\brgba?\(|\bhsla?\(")
# A Tailwind PALETTE utility (bg-emerald-500, text-red-200, ...) — the shape
# the color sweep forbids. The leading "-" is what makes it a utility and not
# an English word ending in a color name.
PALETTE_RE = re.compile(
    r"-(?:emerald|red|blue|green|indigo|gray|grey|slate|zinc|amber|yellow|sky|"
    r"violet|purple|pink|rose|orange|teal|cyan|lime|fuchsia)-[0-9]{2,3}\b")
BRAND_VAR_RE = re.compile(r"var\(--brand-")
# the panel imports the builder from ../lib/chat and sends systemPrompt(...,
# buildSchemaPrompt(...)) — the wiring the send-back was about
PANEL_IMPORT_RE = re.compile(
    r'import\s*\{[^}]*\bbuildSchemaPrompt\b[^}]*\}\s*from\s*"\.\./lib/chat"')
PANEL_CALL_RE = re.compile(r"systemPrompt\([^()]*buildSchemaPrompt\(")
# the legend must be BOUND to a const inside the prompt builder, not merely
# present somewhere in the file
LEGEND_CONST_RE = re.compile(r'const\s+legend\s*=\s*"%s"' % re.escape(LEGEND))
IMPORT_LINE_RE = re.compile(r"^\s*import\s+.*\bChatPanel\b")
MOUNT_LINE_RE = re.compile(r"<ChatPanel\b")

IGNORE_DIRS = ("node_modules", "dist", "build", "__pycache__", ".pytest_cache")


class CannotRun(Exception):
    """The harness does not understand its own input — never a false red."""


# ------------------------------------------------------------------ helpers
def read(root, rel):
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        raise CannotRun("%s is missing — this harness cannot measure a claim "
                        "about a file that is not there" % rel)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def write(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


def walk_files(root, rel):
    base = os.path.join(root, rel)
    if not os.path.isdir(base):
        raise CannotRun("%s is not a directory in this tree" % rel)
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d not in IGNORE_DIRS]
        for name in filenames:
            found.append(os.path.relpath(os.path.join(dirpath, name), root))
    return sorted(found)


def product_sources(root):
    """Product .ts/.svelte files under app/src — test dirs are out of domain."""
    found = []
    for rel in walk_files(root, APP_SRC):
        if "__tests__" in rel.split(os.sep):
            continue
        if rel.endswith((".svelte", ".ts")):
            found.append(rel)
    return found


def line_of(text, pattern):
    """1-based line number of the first line matching `pattern`, or None."""
    for number, line in enumerate(text.splitlines(), 1):
        if re.search(pattern, line):
            return number
    return None


# --------------------------------------------------------------------- legs
# Each leg returns (problems, summary). An empty problem list is the pass.
def leg_governance(root):
    text = read(root, GOVERNANCE_REL)
    problems = []
    if "MEMBER IDS" in text:
        problems.append("governance: %s reintroduces the reversed MEMBER IDS section"
                        % GOVERNANCE_REL)
    found = []
    for section in GOVERNANCE_SECTIONS:
        if re.search(r"^#{2,6}[ \t]*%s" % re.escape(section), text, re.M):
            found.append(section)
        else:
            problems.append("governance: %s lost its %s heading"
                            % (GOVERNANCE_REL, section))
    for number, line in enumerate(text.splitlines(), 1):
        if "```followup" in line and "no ```followup" not in line:
            problems.append("governance: %s:%d uses the fenced follow-up language "
                            "outside the fence rule" % (GOVERNANCE_REL, number))
    summary = "no MEMBER IDS, %d/%d sections, fence clean" % (
        len(found), EXPECTED_GOVERNANCE_SECTIONS)
    return problems, summary


def leg_sweep(root):
    problems = []
    swept = 0
    literals = 0
    palettes = 0
    for rel in SWEPT_FILES:
        text = read(root, rel)
        swept += 1
        for number, line in enumerate(text.splitlines(), 1):
            if COLOR_LITERAL_RE.search(line):
                literals += 1
                problems.append("sweep: %s:%d carries a hard-coded color literal: %s"
                                % (rel, number, line.strip()[:60]))
            if PALETTE_RE.search(line):
                palettes += 1
                problems.append("sweep: %s:%d carries a Tailwind palette utility: %s"
                                % (rel, number, line.strip()[:60]))
    panel = read(root, PANEL_REL)
    brand_vars = len(BRAND_VAR_RE.findall(panel))
    if brand_vars < EXPECTED_BRAND_VARS_IN_PANEL:
        problems.append("sweep: %s resolves no color from the brand vars"
                        % PANEL_REL)
    if swept != EXPECTED_SWEPT_FILES:
        problems.append("sweep: the harness swept %d file(s), it is pinned to %d"
                        % (swept, EXPECTED_SWEPT_FILES))
    summary = "%d/%d files swept, %d color literal(s), %d palette utility(ies), " \
              "panel resolves %d color(s) from the brand vars" % (
                  swept, EXPECTED_SWEPT_FILES, literals, palettes, brand_vars)
    return problems, summary


def leg_one_panel(root):
    problems = []
    files = walk_files(root, APP_SRC)
    panels = [f for f in files if os.path.basename(f).startswith("ChatPanel")]
    if len(panels) != EXPECTED_PANEL_FILES:
        problems.append("one-panel: %d ChatPanel file(s) under %s, the claim is "
                        "exactly one (%s)" % (len(panels), APP_SRC,
                                              ", ".join(panels) or "none"))
    importers = []
    mounts = []
    for rel in files:
        if "__tests__" in rel.split(os.sep):
            continue
        if not rel.endswith((".svelte", ".ts")):
            continue
        text = read(root, rel)
        for number, line in enumerate(text.splitlines(), 1):
            if IMPORT_LINE_RE.match(line):
                importers.append("%s:%d" % (rel, number))
            if MOUNT_LINE_RE.search(line):
                mounts.append("%s:%d" % (rel, number))
    if len(importers) != EXPECTED_IMPORTERS:
        problems.append("one-panel: %d importer(s) (%s), the claim is exactly one"
                        % (len(importers), ", ".join(importers) or "none"))
    if len(mounts) != EXPECTED_MOUNTS:
        problems.append("one-panel: %d mount(s) (%s), the claim is exactly one"
                        % (len(mounts), ", ".join(mounts) or "none"))
    summary = "%d panel file, %d importer (%s), %d mount (%s)" % (
        len(panels), len(importers), ", ".join(importers) or "none",
        len(mounts), ", ".join(mounts) or "none")
    return problems, summary


def leg_live_path(root):
    problems = []
    panel = read(root, PANEL_REL)
    chat = read(root, CHAT_REL)
    proof = read(root, MOUNT_PROOF_REL)
    if not PANEL_IMPORT_RE.search(panel):
        problems.append("live-path: %s does not import buildSchemaPrompt from "
                        "../lib/chat" % PANEL_REL)
    if not PANEL_CALL_RE.search(panel):
        problems.append("live-path: %s does not send systemPrompt(appName, "
                        "buildSchemaPrompt(schema))" % PANEL_REL)
    if "schemaSummary" in panel:
        problems.append("live-path: %s still reaches for the dead schemaSummary path"
                        % PANEL_REL)
    if "export function buildSchemaPrompt(" not in chat:
        problems.append("live-path: %s no longer defines buildSchemaPrompt" % CHAT_REL)
    if not LEGEND_CONST_RE.search(chat):
        problems.append("live-path: the legend the send-back restored is not bound "
                        "to a const in %s" % CHAT_REL)
    if LEGEND not in proof:
        problems.append("live-path: the wire-level proof (%s) does not assert the "
                        "legend" % MOUNT_PROOF_REL)
    if "buildSchemaPrompt" not in proof:
        problems.append("live-path: the wire-level proof (%s) does not assert the "
                        "wired builder" % MOUNT_PROOF_REL)
    summary = ("builder wired (%s:%d imports, :%d sends), legend at %s:%d, wire "
               "proof at %s" % (
                   PANEL_REL,
                   line_of(panel, r"import\s*\{[^}]*buildSchemaPrompt") or 0,
                   line_of(panel, r"systemPrompt\([^()]*buildSchemaPrompt\(") or 0,
                   CHAT_REL, line_of(chat, r"const\s+legend") or 0,
                   MOUNT_PROOF_REL))
    return problems, summary


def leg_one_builder(root):
    """Exactly one product file writes the prompt line, and it is chat.ts."""
    builders = []
    for rel in product_sources(root):
        if PROMPT_SHAPE in read(root, rel):
            builders.append(rel)
    problems = []
    if len(builders) != EXPECTED_PROMPT_BUILDERS:
        problems.append("one-builder: %d product file(s) build the AI schema-prompt "
                        "line (%s), the claim is exactly one" % (
                            len(builders), ", ".join(builders) or "none"))
    elif builders[0] != CHAT_REL:
        problems.append("one-builder: the only prompt builder is %s, not the live %s"
                        % (builders[0], CHAT_REL))
    summary = "%d builder(s): %s" % (len(builders), ", ".join(builders) or "none")
    return problems, summary


LEGS = (
    ("governance", leg_governance),
    ("sweep", leg_sweep),
    ("one-panel", leg_one_panel),
    ("live-path", leg_live_path),
    ("one-builder", leg_one_builder),
)


def check(root):
    """Grade every leg. Returns (rows, problems)."""
    rows = []
    problems = []
    for name, leg in LEGS:
        try:
            found, summary = leg(root)
        except CannotRun:
            raise
        except Exception as exc:
            # A leg that blows up on a weird tree must still yield a READABLE
            # verdict: an unreadable traceback with rc 1 looks like RED to the
            # caller but tells the reader nothing. The detail is kept in the
            # message so a harness bug is still visible.
            found = ["%s: the leg raised %s: %s" % (name, type(exc).__name__, exc)]
            summary = "the leg raised %s" % type(exc).__name__
        problems.extend(found)
        rows.append((name, summary, found))
    return rows, problems


# ------------------------------------------------------------------ selftest
# A check that cannot FAIL is not a check (ELEVENTH harness law, applied to
# the harness itself). Every control below mutates a COPY of the tree and
# asserts that the leg owning the mutated fact goes RED — or, for a missing
# input, CANNOT RUN. The shipped tree is never written to.
def _replace_once(root, rel, old, new):
    text = read(root, rel)
    if old not in text:
        raise CannotRun("control: %r is not in %s — the control cannot mutate what "
                        "the tree no longer holds" % (old, rel))
    write(root, rel, text.replace(old, new, 1))


def control_member_ids(root):
    _replace_once(root, GOVERNANCE_REL, "## DISPATCH PREAMBLE RULE",
                  "## MEMBER IDS\n\n## DISPATCH PREAMBLE RULE")


def control_fence_heading(root):
    _replace_once(root, GOVERNANCE_REL, "## FENCE FORMAT (2026-10-18, owner ruling)",
                  "## Fence (2026-10-18, owner ruling)")


def control_hex_literal(root):
    _replace_once(root, PANEL_REL, '<script lang="ts">',
                  '<script lang="ts">\n  // injected: #ff00aa')


def control_palette_utility(root):
    _replace_once(root, PANEL_REL, '<script lang="ts">',
                  '<script lang="ts">\n  // injected: bg-emerald-500/15')


def control_second_panel(root):
    # the copy lands BESIDE the real panel, so the panel's own directory is
    # reused rather than re-spelled (a re-spelled path would silently write
    # outside app/src and the control would prove nothing)
    panel_dir = os.path.dirname(os.path.join(root, PANEL_REL))
    shutil.copyfile(os.path.join(root, PANEL_REL),
                    os.path.join(panel_dir, "ChatPanelCopy.svelte"))


def control_rewired(root):
    _replace_once(root, PANEL_REL, "import { buildSchemaPrompt,",
                  "import {")


def control_legend_gone(root):
    _replace_once(root, CHAT_REL, 'const legend = "%s";' % LEGEND,
                  'const legend = "";')


def control_proof_gone(root):
    os.remove(os.path.join(root, MOUNT_PROOF_REL))


def control_brand_vars_gone(root):
    text = read(root, PANEL_REL)
    write(root, PANEL_REL, text.replace("var(--brand-", "var(--x-"))


def control_second_mount(root):
    _replace_once(root, SHELL_REL, "<ChatPanel />", "<ChatPanel />\n<ChatPanel />")


def control_second_importer(root):
    _replace_once(root, "app/src/components/Toaster.svelte", "<script",
                  '<script lang="ts">\n  import ChatPanel from "../ai/ChatPanel.svelte";\n</script>\n<script')


def control_second_builder(root):
    # the control that makes the one-builder leg honest: the dead clone is
    # re-added to a PRODUCT file (openapi.ts, the file that shipped it), so the
    # leg must count two builders. Written inside app/src on purpose — a copy
    # outside it would prove nothing, the hazard control_second_panel records.
    text = read(root, OPENAPI_REL)
    write(root, OPENAPI_REL, text + "\nexport function schemaSummary(schema: "
          "AdminSchema): string {\n  return schema.models.map((m) => "
          "`${m.name}(fk->${m.id})`).join(\"\\n\");\n}\n")


# (name, mutation, expected exit code, expected text in the output)
CONTROLS = (
    ("governance: MEMBER IDS restored", control_member_ids, 1, "MEMBER IDS"),
    ("governance: FENCE FORMAT heading lost", control_fence_heading, 1, "FENCE FORMAT"),
    ("sweep: a hex literal appears", control_hex_literal, 1, "color literal"),
    ("sweep: a palette utility appears", control_palette_utility, 1, "palette utility"),
    ("sweep: the panel loses its brand vars", control_brand_vars_gone, 1, "brand vars"),
    ("one-panel: a second panel file", control_second_panel, 1, "ChatPanel file"),
    ("one-panel: a second mount", control_second_mount, 1, "mount(s)"),
    ("one-panel: a second importer", control_second_importer, 1, "importer(s)"),
    ("live-path: the panel is rewired", control_rewired, 1, "does not import buildSchemaPrompt"),
    ("live-path: the legend is gone", control_legend_gone, 1, "legend"),
    ("live-path: the wire proof is gone", control_proof_gone, 2, "CANNOT RUN"),
    ("one-builder: the dead clone returns", control_second_builder, 1, "one-builder"),
)


def selftest(root):
    """Prove each leg can fire, against copies. Returns 0 or raises CannotRun."""
    script = os.path.join(root, "scripts", "chat_feature_check.py")
    failures = []
    for name, mutation, expected_rc, expected_text in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="chat-feature-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", ".git",
                                                          "__pycache__",
                                                          ".pytest_cache",
                                                          "dist", "build"))
            mutation(target)
            proc = subprocess.run([sys.executable, script, "--root", target],
                                  capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-38s -> rc %d as expected (%s)"
                      % (name, proc.returncode, expected_text))
            else:
                failures.append("%s: expected rc %d containing %r, got rc %d: %s"
                                % (name, expected_rc, expected_text,
                                   proc.returncode, out.strip()[:300]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        raise CannotRun("SELFTEST RED — %d control(s) did not fire as expected: %s"
                        % (len(failures), "; ".join(failures)))
    print("SELFTEST OK — %d control(s), every leg proved able to fail"
          % len(CONTROLS))
    return 0


def main(argv):
    parser = argparse.ArgumentParser(
        description="Grade the chat send-back's five specced checks.")
    parser.add_argument("--root", default=".",
                        help="the tree to grade (default: this repo)")
    parser.add_argument("--selftest", action="store_true",
                        help="prove every leg can fail, against copies")
    opts = parser.parse_args(argv)

    root = os.path.abspath(opts.root)
    if opts.selftest:
        return selftest(root)

    rows, problems = check(root)
    print("COOL-CHAT CHECK — %d legs" % len(rows))
    for name, summary, found in rows:
        print("  %-10s %-4s %s" % (name, "OK" if not found else "RED", summary))
    if problems:
        print("COOL-CHAT CHECK RED — %d problem(s)" % len(problems))
        for problem in problems:
            print("  - %s" % problem)
        return 1
    print("COOL-CHAT CHECK OK — %d legs, %d files swept, 1 panel / %d importer / "
          "%d mount" % (len(rows), EXPECTED_SWEPT_FILES, EXPECTED_IMPORTERS,
                        EXPECTED_MOUNTS))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except CannotRun as exc:
        print("CANNOT RUN — %s" % exc)
        sys.exit(2)
