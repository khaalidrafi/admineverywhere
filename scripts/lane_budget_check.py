#!/usr/bin/env python3
"""Do the chain's REVIEWER and TURN lanes fit the provider they are wired to?

WHY this exists (measured 2026-10-25, inside the lane that died). `finalize`
wrote `stall=1 ... (codebuddy+qoder-ds+zai+laguna lanes all failed — check the
harness)`, and the review arm left the workspace holding a `.turn-review.txt`
whose only content was:

    error: Context length exceeded: Request too large for model
    `qwen/qwen3.8-27b` ... on input tokens per minute (ITPM): Limit 7000,
    Requested 44003 ... Please try again or create a new session

No seat and no harness could see WHY, because the size that kills the lane lives
OUTSIDE the brief: goose carries the repo's own `AGENTS.md` in every request,
and the Owner-rotated duty reviewer lands on a free tier whose input budget is
a fraction of that. Probed in this container — goose 1.56.0, the exact env
recipe the lane ships (`OPENAI_HOST=https://api.groq.com`,
`GOOSE_MODEL=qwen/qwen3.8-27b`), a 30-byte prompt:

    /tmp         (no AGENTS.md)          ANSWERED, rc 0, request under the cap
    /tmp/ctx-ab  (AGENTS.md, 68878 B)    rejected, Requested 22895  req_01m5the92kehhahwngsv266z53
    /workspace   (the real lane)         rejected, Requested 22892  req_01m5thd10ream8chgszete560c

The carrier is `AGENTS.md` alone: 68878 bytes for 22895 tokens = 3.0084
bytes/token, and the same request in the real workspace lands within ~200
tokens of it. Groq's free tier caps input at 7000 and output at 1000 (the
second rejection in the shipped review file is goose's own compaction asking
1932 output tokens against OTPM 1000). A goose lane on that host therefore
cannot answer its FIRST request in this repo — not intermittently, not under
load: never. The zero-artifact `review-missing` streaks the Lead has triaged by
hand are the cost, and a branch that cannot be reviewed cannot land.

Three promises, graded read-only against the Lead-owned lane script and the
tree — never by re-matching prose about it:

  lanes-parsed        every lane command names the CLI it runs, the model it
                      asks for, the host it sends it to and the ENV VAR NAME of
                      its key. A lane with no `OPENAI_HOST` inherits a provider
                      this harness cannot budget, and the goose POPULATION is
                      pinned by host: a groq lane deleted while the roster still
                      counted five would make the impossible lane vanish from
                      the check that exists to catch it (DEVGUIDE *ELEVENTH
                      law*: a comparison cannot see its own coverage). Zero
                      lanes, an ungradeable lane or roster drift is CANNOT RUN.
  primary-fits        the lane an arm TRUSTS FIRST must fit its provider. The
                      estimate is DERIVED from the tree — carrier bytes over
                      the calibrated bytes-per-token, plus that arm's own brief
                      — so trimming the carrier or growing it moves the verdict;
                      it is never a frozen number. A trusted-first lane on a
                      host whose pinned input budget is below the estimate is
                      RED naming the arm, the member it credits, the factor and
                      the receipt. A provider with no measured budget is
                      reported ungraded, never guessed into green — and a lane
                      that is merely LAST in a fallback chain is reported, not
                      refused, because an authoring arm self-heals off it while
                      a review arm cannot.
  rejection-guarded   a provider rejection is not a missing verdict. goose
                      exits non-zero when the FIRST request is refused (measured
                      rc 1 here) but the shipped review file shows a session that
                      died mid-flight leaving its own text as the whole answer —
                      and the chain reads that file for a `VERDICT:` token. So
                      the markers the provider prints must be grepped out of the
                      review file before its verdict is trusted, RED when
                      nothing reads it. `review_verdict_check.py` refuses a
                      substituted CLI brain; this refuses the provider-shaped
                      death that produced review-missing here.

Verdicts follow house law: 0 = every trusted lane fits and every rejection is
read; 1 = RED, a lane that can never answer or a rejection nothing greps;
2 = CANNOT RUN, the harness no longer understands the lane script.

  python3 scripts/lane_budget_check.py             # grade this tree
  python3 scripts/lane_budget_check.py --root DIR  # grade a copy (controls)
  python3 scripts/lane_budget_check.py --probe     # re-measure the receipts:
                                                   # ONE live request per pinned
                                                   # host; the request is refused
                                                   # before it runs, so nothing
                                                   # is billed
  python3 scripts/lane_budget_check.py --selftest  # 6 controls: every leg
                                                   # proved able to fail
"""

import argparse
import math
import os
import re
import subprocess
import sys
import tempfile

SEGMENT_REL = ".github/scripts/turn_segment.sh"
CARRIER_REL = "AGENTS.md"
REVIEW_FILE = ".turn-review.txt"

# The lane script's two halves: the REVIEW dispatch runs before the author
# segment's `case "$SEAT" in`, so that line is the seam between the arms.
ARM_SEAM = 'case "$SEAT" in'

# Calibration, from the receipts above: the request size of a goose session
# whose only injected context is AGENTS.md.
RECEIPT = {"carrier_bytes": 68878, "requested_tokens": 22895,
           "receipt_id": "req_01m5the92kehhahwngsv266z53"}
BYTES_PER_TOKEN = RECEIPT["carrier_bytes"] / float(RECEIPT["requested_tokens"])

# Pinned provider budgets — one row per host this chain wires, measured from
# the provider's OWN rejection text. A host NOT in this table is ungraded.
PROVIDER_BUDGETS = {
    "https://api.groq.com": {
        "input_tokens": 7000,    # ITPM
        "output_tokens": 1000,   # OTPM (goose's compaction asked 1932)
        "receipt": "Requested %d over %d B of %s (%s)" % (
            RECEIPT["requested_tokens"], RECEIPT["carrier_bytes"],
            CARRIER_REL, RECEIPT["receipt_id"]),
    },
}

# What a provider rejection looks like in the lane's own output.
REJECTION_MARKERS = ("Context length exceeded", "Rate limit exceeded",
                     "too large for model")

# The block the handover patch adds, spelled ONCE so the controls can add it and
# take it away again without a second copy drifting from the first.
GUARD_BLOCK = ('  if grep -qE \'Context length exceeded|Rate limit exceeded|too large '
               'for model\' /workspace/%s 2>/dev/null; then\n'
               '    echo "REVIEW: provider rejected the review lane — the verdict '
               'file is a dead session, not a review"\n'
               '  fi\n' % REVIEW_FILE)

# 10-ed APPLY (Lead): the handover hunks are IN the shipped carrier now, so the
# controls that proved the founding defect able to fail anchor on the REPAIR ITSELF
# — the applied QA-arm sub-blocks, spelled once and reverted on copies. The shipped
# tree answers 0; a copy with the repair reverted must answer red, or the check has
# stopped measuring what it exists to measure.
QODER_PRIMARY = (
    '      if timeout 900 env HOME=/usr/local/lib/qoder-home \\\n'
    '           qoder -p "$REVIEW_BRIEF" --output-format json --model deepseek-v4.1-flash \\\n'
    '           --permission-mode bypassPermissions --max-turns 60 \\\n'
    '           > /workspace/.turn-review.txt 2>&1; then\n'
    '        echo "REVIEW: qoder run OK (review lane: deepseek-v4.1-flash@qoder — lane-budget demotion 2026-10-25)"\n'
    '      else\n'
    '        echo "REVIEW: qoder lane failed — falling back to groq/qwen3.8-27b@goose"\n'
    '        env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \\\n'
    '           OPENAI_API_KEY="$GROQ_API_KEY" \\\n'
    '           OPENAI_HOST="https://api.groq.com" \\\n'
    '           OPENAI_BASE_PATH="/openai/v1/chat/completions" \\\n'
    '           timeout 900 goose run -t "$REVIEW_BRIEF" \\\n'
    '           > /workspace/.turn-review.txt 2>&1 || true\n'
    '      fi\n')
GROQ_PRIMARY = (
    '      if env GOOSE_PROVIDER=openai GOOSE_MODEL=qwen/qwen3.8-27b \\\n'
    '           OPENAI_API_KEY="$GROQ_API_KEY" \\\n'
    '           OPENAI_HOST="https://api.groq.com" \\\n'
    '           OPENAI_BASE_PATH="/openai/v1/chat/completions" \\\n'
    '           timeout 900 goose run -t "$REVIEW_BRIEF" \\\n'
    '           > /workspace/.turn-review.txt 2>&1; then\n'
    '        echo "REVIEW: goose run OK (review lane: groq/qwen3.8-27b@goose — Owner rotation 2026-10-25)"\n'
    '      else\n'
    '        echo "REVIEW: groq lane failed — falling back to qoder deepseek (demoted primary)"\n'
    '        timeout 900 env HOME=/usr/local/lib/qoder-home \\\n'
    '          qoder -p "$REVIEW_BRIEF" --output-format json --model deepseek-v4.1-flash \\\n'
    '          --permission-mode bypassPermissions --max-turns 60 \\\n'
    '          > /workspace/.turn-review.txt 2>&1 || true\n'
    '      fi\n')
GUARD_APPLIED = (
    '      # A provider rejection is NOT a missing verdict. The extractor greps this\n'
    '      # file for a VERDICT token; when the session died on the provider\'s own\n'
    '      # limit there is no verdict to find, and the branch is parked for a beat\n'
    '      # that was never spent. Read the markers the provider prints and say so.\n'
    '      if grep -qE \'Context length exceeded|Rate limit exceeded|too large '
    'for model\' /workspace/.turn-review.txt 2>/dev/null; then\n'
    '        echo "REVIEW: provider rejected the review lane — the verdict file is a '
    'dead session, not a review"\n')
ARM_CLOSE = '      fi ;;\n'

# The goose population this harness claims to understand, measured on the
# shipped lane script: 12 lanes — 5 groq, 4 zai, 3 openrouter.
EXPECTED_GOOSE_LANES = 12
EXPECTED_LANES_BY_HOST = {"https://api.groq.com": 5,
                          "https://api.z.ai": 4,
                          "https://openrouter.ai": 3}

LEG_ROSTER = ("lanes-parsed", "primary-fits", "rejection-guarded")
EXPECTED_LEGS = 3
EXPECTED_CONTROLS = 6

# A real invocation carries its flags; the RESULT lines (`echo "TURN_RESULT=goose
# run OK ...`) name the same CLI and would otherwise be parsed as lanes.
# 2156 union (Lead, measured): the lane dialect moved — the session-loop fix (10-ds)
# stripped `--no-session` from every goose call, so the shipped lanes now read
# `goose run -t "$BRIEF"` / `goose run -t "$REVIEW_BRIEF"` (12 of them, same host
# table). The authored anchor matched the dead dialect and the harness answered
# CANNOT RUN (rc 2) on main — re-pointed to the live shape; `goose run OK` prose
# and the `--probe` one-shot stay outside the match.
LANE_RE = re.compile(r"\b(goose run -t |qoder -p |codebuddy -p )")
HOST_RE = re.compile(r'OPENAI_HOST="([^"]+)"')
MODEL_RE = re.compile(r"GOOSE_MODEL=(\S+)|--model (\S+)")
KEY_RE = re.compile(r'OPENAI_API_KEY="\$([A-Z0-9_]+)"')
CASE_RE = re.compile(r"^\s+([a-z-]+|\*)\)\s*(?:#.*)?$")


class CannotRun(Exception):
    pass


class Red(Exception):
    pass


def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CannotRun("cannot read %s: %s" % (rel, exc))


def carrier_bytes(root):
    try:
        return os.path.getsize(os.path.join(root, CARRIER_REL))
    except OSError as exc:
        raise CannotRun("the context carrier %s is unreadable: %s" % (CARRIER_REL, exc))


def estimate_tokens(root, brief_len):
    """Tokens a lane request carries in this tree: the injected carrier plus the
    arm's own brief. Derived from current bytes, so the verdict moves with the
    tree instead of quoting the measurement that founded it."""
    size = carrier_bytes(root)
    base = RECEIPT["requested_tokens"] if size == RECEIPT["carrier_bytes"] \
        else math.ceil(size / BYTES_PER_TOKEN)
    return base + math.ceil(brief_len / BYTES_PER_TOKEN)


def lanes(text, offset=0):
    """Every lane command, with the env prefix that feeds it, in dispatch order.

    Lanes are written as a multi-line `env A=1 B=2 ... \\` chain ending in the
    call, so the host, model and key sit on the lines ABOVE it — reading only
    the command line would find no provider at all. `offset` keeps the reported
    line numbers absolute when a section of the script is graded alone.
    """
    lines = text.splitlines()
    out = []
    for position, line in enumerate(lines):
        match = LANE_RE.search(line)
        if not match:
            continue
        blob = [line]
        walk = position - 1
        while walk >= 0 and lines[walk].rstrip().endswith("\\"):
            blob.insert(0, lines[walk])
            walk -= 1
        joined = "\n".join(blob)
        cli = match.group(1).split()[0]
        model = MODEL_RE.search(joined)
        host = HOST_RE.search(joined)
        key = KEY_RE.search(joined)
        out.append({"line": position + 1 + offset, "cli": cli,
                    "host": host.group(1) if host else None,
                    "model": (model.group(1) or model.group(2)) if model else None,
                    "key": key.group(1) if key else None})
    return out


def arms(text, offset=0):
    """{arm label: [lane, ...]} in dispatch order — review arms and turn arms
    alike. The lane an arm trusts is the FIRST one in its list."""
    by_line = {lane["line"]: lane for lane in lanes(text, offset)}
    out, current = {}, None
    for index, line in enumerate(text.splitlines(), start=1 + offset):
        match = CASE_RE.match(line)
        if match:
            current = match.group(1)
        elif index in by_line and current:
            out.setdefault(current, []).append(by_line[index])
    return out


REVIEW_BRIEF_MARK = 'REVIEW_BRIEF="REVIEW DUTY'
TURN_BRIEF_MARK = 'BRIEF="You are the on-turn member'


def brief_len(text, marker):
    """Length of the brief an arm is handed, read from its own assignment.

    The closing quote is not on a line of its own (the reviewer brief ends on
    its verdict-token line), so the end is the first line after the assignment
    that ENDS in a quote.
    """
    start = text.find(marker)
    if start < 0:
        raise CannotRun("no lane brief starting %s in %s — this harness no "
                        "longer understands the lane script"
                        % (marker, SEGMENT_REL))
    open_at = text.find('"', start)
    tail = text[open_at + 1:].splitlines()
    for offset, line in enumerate(tail):
        if line.rstrip().endswith('"'):
            return len("\n".join(tail[:offset] + [line.rstrip()[:-1]]).encode())
    raise CannotRun("%s never closes in %s" % (marker, SEGMENT_REL))


def leg_lanes_parsed(all_lanes):
    if not all_lanes:
        raise CannotRun("no lane command parsed out of %s — this harness grades "
                        "a lane script it can no longer read" % SEGMENT_REL)
    goose = [lane for lane in all_lanes if lane["cli"] == "goose"]
    blind = [lane for lane in goose if not (lane["host"] and lane["model"] and lane["key"])]
    if blind:
        raise CannotRun("%d goose lane(s) at line(s) %s carry no host, model or key "
                        "env NAME — a lane whose provider is unknown has no budget "
                        "to compare, and guessing the nearest one would invent a "
                        "verdict" % (len(blind), ", ".join(str(l["line"]) for l in blind)))
    if len(goose) != EXPECTED_GOOSE_LANES:
        raise CannotRun("the lane script holds %d goose lane(s), the pin says %d — a "
                        "lane was added or deleted without this roster, so what is "
                        "compared below is not the population that ships"
                        % (len(goose), EXPECTED_GOOSE_LANES))
    counts = {}
    for lane in goose:
        counts[lane["host"]] = counts.get(lane["host"], 0) + 1
    if counts != EXPECTED_LANES_BY_HOST:
        raise CannotRun("goose lanes by host are %s, the pin says %s — coverage "
                        "moved underneath the roster this check claims to grade"
                        % (counts, EXPECTED_LANES_BY_HOST))
    return "%d lane(s), %d of them goose over %s, every goose lane naming host, " \
           "model and key NAME" % (
               len(all_lanes), len(goose),
               ", ".join("%s x%d" % (h, n) for h, n in sorted(counts.items())))


def leg_primary_fits(review_text, turn_text, text, root):
    review_estimate = estimate_tokens(root, brief_len(text, REVIEW_BRIEF_MARK))
    turn_estimate = estimate_tokens(root, brief_len(text, TURN_BRIEF_MARK))
    problems, notes = [], []
    turn_offset = len(text.split(ARM_SEAM, 1)[0].splitlines())
    for arm_label, section, offset, estimate in (
            ("REVIEW", review_text, 0, review_estimate),
            ("TURN", turn_text, turn_offset, turn_estimate)):
        for name, arm_lanes in sorted(arms(section, offset).items()):
            for position, lane in enumerate(arm_lanes):
                trusted_first = position == 0
                where = "%s/%s %s lane %s@%s (line %d)" % (
                    arm_label, name, "trusted-first" if trusted_first else "fallback",
                    lane["model"] or lane["cli"], lane["host"] or "-", lane["line"])
                if lane["cli"] != "goose":
                    if trusted_first:
                        notes.append("%s is a %s call: no pinned budget for that CLI, "
                                     "not graded" % (where, lane["cli"]))
                    continue
                budget = PROVIDER_BUDGETS.get(lane["host"])
                if budget is None:
                    if trusted_first:
                        notes.append("%s: host has no measured budget, not graded" % where)
                    continue
                if estimate <= budget["input_tokens"]:
                    continue
                if not trusted_first:
                    notes.append("%s is equally impossible — dead weight that only "
                                 "self-heals while goose exits non-zero on the refusal"
                                 % where)
                    continue
                problems.append(
                    "%s: this tree produces ~%d token(s) over %d B of %s plus the "
                    "arm's own brief, %.1fx that host's pinned input budget %d "
                    "(receipt: %s). A trusted-first lane that can never answer emits "
                    "no verdict and no work while the record still credits the member "
                    "the lane names. FIX (Lead-owned): put a lane that can answer "
                    "first, or stop carrying %s into every request of this provider."
                    % (where, estimate, carrier_bytes(root), CARRIER_REL,
                       estimate / float(budget["input_tokens"]),
                       budget["input_tokens"], budget["receipt"], CARRIER_REL))
    if problems:
        raise Red("; ".join(problems) + (" || " + " | ".join(notes) if notes else ""))
    return "review ~%d token(s), turn ~%d over %d pinned budget(s); %s" % (
        review_estimate, turn_estimate, len(PROVIDER_BUDGETS),
        " | ".join(notes) if notes else "every trusted-first lane graded and fitting")


def leg_rejection_guarded(review_text):
    hits = []
    for line in review_text.splitlines():
        if REVIEW_FILE in line and "grep" in line \
                and any(marker in line for marker in REJECTION_MARKERS):
            hits.append(line.strip()[:70])
    if not hits:
        raise Red("nothing greps a provider rejection out of %s before its verdict "
                  "is trusted. Measured in this container: a first-request refusal "
                  "exits 1 and the fallback overwrites the file, but a session that "
                  "dies MID-flight leaves its own error text as the whole answer, "
                  "the extractor's `VERDICT:` grep finds nothing, and the merger "
                  "writes review-missing against a reviewer that never reviewed. "
                  "FIX (Lead-owned): after the review dispatch, grep %s for %s and "
                  "record the arm as a dead lane when one is present."
                  % (REVIEW_FILE, REVIEW_FILE, " / ".join(REJECTION_MARKERS)))
    return "provider rejection read out of %s %d time(s): %s" % (
        REVIEW_FILE, len(hits), " | ".join(hits))


def grade(root):
    text = read(root, SEGMENT_REL)
    if ARM_SEAM not in text:
        raise CannotRun("%s no longer carries `%s` — the review arm and the turn "
                        "arms cannot be told apart" % (SEGMENT_REL, ARM_SEAM))
    review_text, turn_text = text.split(ARM_SEAM, 1)
    all_lanes = lanes(text)
    return {
        "lanes-parsed": leg_lanes_parsed(all_lanes),
        "primary-fits": leg_primary_fits(review_text, turn_text, text, root),
        "rejection-guarded": leg_rejection_guarded(review_text),
    }


# ------------------------------------------------------------------- fixtures
def write(root, rel, text):
    path = os.path.join(root, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def copy_tree(base):
    dest = tempfile.mkdtemp(prefix="lane-budget-")
    write(dest, SEGMENT_REL, read(base, SEGMENT_REL))
    write(dest, CARRIER_REL, read(base, CARRIER_REL))
    return dest


def add_guard(text):
    """The Lead-side half of the handover: read the rejection markers out of the
    review file before its verdict is trusted."""
    anchor = '  echo "REVIEW: duty reviewer ${REVIEWER_SEAT:-none}'
    if anchor not in text:
        raise AssertionError("the review dispatch anchor moved: %s" % anchor[:48])
    return text.replace(anchor, GUARD_BLOCK + anchor, 1)


def small_carrier(root):
    # The other half of the handover: stop carrying AGENTS.md into every
    # request (a trimmed working dir fits the same lane under the same pinned
    # budget). This control exists to prove the estimate is read from bytes.
    write(root, CARRIER_REL, "# trimmed working copy\n" * 200)


def guarded_copy(root, guard=True, carrier_trimmed=True):
    _edit_segment(root, add_guard)
    if carrier_trimmed:
        small_carrier(root)
    if not guard:
        _edit_segment(root, lambda text: text.replace(GUARD_BLOCK, "", 1))


# ------------------------------------------------------------------- controls
CONTROLS = [
    ("the repair reverted on a copy — groq trusted-first again, guard gone: "
     "the founding defect must still answer red",
     lambda root: _revert_repair(root), 1),
    ("groq restored trusted-first on a guarded copy — the budget leg grades "
     "apart from the rejection leg, never by one shared condition",
     lambda root: _restore_groq_primary(root), 1),
    ("the carrier trimmed on the guarded copy — the estimate moves with the "
     "bytes and the whole harness answers 0",
     lambda root: guarded_copy(root), 0),
    ("the guard taken back out of the shipped arm — the rejection leg proved "
     "able to fail",
     lambda root: _drop_guard(root), 1),
    ("a deleted goose lane shrinks the population under its pin — CANNOT RUN, "
     "never a quieter green",
     lambda root: _drop_lane(root), 2),
    ("a lane stripped of its OPENAI_HOST has no provider, so no budget — "
     "refused rather than guessed",
     lambda root: _strip_host(root), 2),
]


def _edit_segment(root, transform):
    write(root, SEGMENT_REL, transform(read(root, SEGMENT_REL)))


def _drop_lane(root):
    def transform(text):
        lines = text.splitlines(True)
        for index, line in enumerate(lines):
            if "goose run" in line:
                return "".join(lines[:index] + lines[index + 1:])
        raise AssertionError("no goose lane to drop")
    _edit_segment(root, transform)


def _strip_host(root):
    _edit_segment(root, lambda text: text.replace(
        'OPENAI_HOST="https://api.groq.com"', 'OPENAI_HOST="$LANE_HOST"', 1))


def _revert_repair(root):
    """The 10-ed inverse: restore groq trusted-first AND take the guard out —
    the exact pre-APPLY state the founding measurement was taken in."""
    def transform(text):
        for probe in (QODER_PRIMARY,):
            if probe not in text:
                raise AssertionError("the applied QA-arm repair moved — retarget "
                                     "the fixture, never delete the control")
        return text.replace(QODER_PRIMARY + GUARD_APPLIED + ARM_CLOSE,
                            GROQ_PRIMARY.replace('      fi\n', '      fi ;;\n'), 1)
    _edit_segment(root, transform)


def _restore_groq_primary(root):
    """Half-inverse: groq back trusted-first, the guard kept — the budget leg
    must grade apart from the rejection leg, never through one shared condition."""
    def transform(text):
        if QODER_PRIMARY not in text:
            raise AssertionError("the applied QA-arm repair moved — retarget "
                                 "the fixture, never delete the control")
        return text.replace(QODER_PRIMARY, GROQ_PRIMARY, 1)
    _edit_segment(root, transform)


def _drop_guard(root):
    """The rejection half of the repair taken back out of the shipped arm."""
    def transform(text):
        needle = QODER_PRIMARY + GUARD_APPLIED + ARM_CLOSE
        if needle not in text:
            raise AssertionError("the applied QA-arm guard moved — retarget "
                                 "the fixture, never delete the control")
        return text.replace(needle,
                            QODER_PRIMARY.replace('      fi\n', '      fi ;;\n'), 1)
    _edit_segment(root, transform)


def selftest(base):
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("CONTROLS holds %d but EXPECTED_CONTROLS says %d — a control "
                        "left the roster without its pin (DEVGUIDE *ELEVENTH law*)"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    if len(LEG_ROSTER) != EXPECTED_LEGS:
        raise CannotRun("LEG_ROSTER holds %d but EXPECTED_LEGS says %d"
                        % (len(LEG_ROSTER), EXPECTED_LEGS))
    failures = 0
    for title, mutate, want in CONTROLS:
        root = copy_tree(base)
        try:
            mutate(root)
        except AssertionError as exc:
            print("  %-64s BROKEN CONTROL: %s" % (title[:64], exc))
            failures += 1
            continue
        try:
            grade(root)
            got = 0
        except Red:
            got = 1
        except CannotRun:
            got = 2
        print("  %-64s want=%d got=%d %s" % (title[:64], want, got,
                                             "ok" if got == want else "FAIL"))
        if got != want:
            failures += 1
    print("SELFTEST %s: %d control(s) over %d leg(s)" % (
        "OK" if not failures else "FAILED", len(CONTROLS), len(LEG_ROSTER)))
    return 1 if failures else 0


def probe(root):
    """One live request per pinned host, so the receipts re-measure themselves."""
    lines = []
    for host, budget in sorted(PROVIDER_BUDGETS.items()):
        env = dict(os.environ)
        env.update({"GOOSE_PROVIDER": "openai", "GOOSE_MODEL": "qwen/qwen3.8-27b",
                    "OPENAI_HOST": host,
                    "OPENAI_BASE_PATH": "/openai/v1/chat/completions"})
        try:
            proc = subprocess.run(["goose", "run", "--no-session", "-t",
                                   "Reply with exactly one word: OK"],
                                  cwd=root, env=env, capture_output=True,
                                  text=True, timeout=300)
            requested = re.findall(r"Requested (\d+)", proc.stdout + proc.stderr)
            lines.append("%s rc=%d requested=%s pinned_input_budget=%d -> %s" % (
                host, proc.returncode,
                ",".join(requested) or "answered", budget["input_tokens"],
                "receipt holds" if requested else "lane answered"))
        except Exception as exc:
            raise CannotRun("probe of %s could not run: %s" % (host, exc))
    return "\n".join(lines)


def main(argv):
    # 2156 union (Lead, measured): the flags are declared through argparse —
    # harness_roster_check's INVOKE leg reads add_argument literals, and the
    # hand-rolled loop left --selftest/--probe invisible to it (INVOKE RED on
    # both mirrors at the union).
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    parser.add_argument("--selftest", action="store_true")
    parser.add_argument("--probe", action="store_true")
    ns = parser.parse_args(argv[1:])
    root = ns.root
    mode = "selftest" if ns.selftest else ("probe" if ns.probe else "grade")
    try:
        if mode == "selftest":
            return selftest(root)
        if mode == "probe":
            print(probe(root))
            return 0
        legs = grade(root)
    except CannotRun as exc:
        print("CANNOT RUN: %s" % exc)
        return 2
    except Red as exc:
        print("RED: %s" % exc)
        return 1
    for name in LEG_ROSTER:
        print("%-18s %s" % (name, legs[name]))
    print("LANE BUDGET OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
