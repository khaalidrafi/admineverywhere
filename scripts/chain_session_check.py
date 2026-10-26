#!/usr/bin/env python3
"""Re-runnable check of the chain's SESSION LAW (Owner order 2026-10-21 18:27Z).

WHY this exists (measured, not assumed). The Owner's SESSION LAW says the
chain must collect each turn's CLI session files, upload them, and restore
them into the next turn, so a seat RESUMES instead of starting cold. Turn 4
of the TEST-CHAIN objective measured the loop and found it never closes:

  1. the restore copies only the container HOME's store, while the collect
     tar takes a second store (the qoder lane's, under
     /usr/local/lib/qoder-home/.qoder) that is therefore collected and never
     restored;
  2. the collect tars a goose session path the current goose never writes
     (.config/goose/sessions), and tar's "Cannot stat" was swallowed by
     2>/dev/null, so the miss was silent every run;
  3. all three goose lanes run the CLI with --no-session, the flag whose
     own help says it runs "without creating or using a session file" - the
     exact opposite of the law.

A finding delivered as prose is a finding the next reader has to trust.
The fix itself is a patch (docs/session-loop-fix.patch) that a seat may NOT
apply: the chain's own files are Lead-owned. So the seat can only hand over
something the Lead can run: a check that grades the loop from the tree.

This harness grades the loop against the Lead-owned chain, READ-ONLY. The
inner .turn-inside.sh is taken from whichever file writes it - the workflow
inline (the shape before 2026-10-22) or the segment script the workflow runs
(eaf34bd extracted the over-long inline block). A carrier the workflow does
not run, or a second heredoc competing with the first, is refused: grading
the wrong script would be a false green.

  COLLECT       the collect block exists and takes a plausible population of
                stores (a tar list that lost its members collects nothing).
  RESTORE       every store the collect takes is restored to ITS OWN place.
                The tar is rooted at /, so each member keeps its absolute
                path inside the archive; a restore that copies the archive
                root into $HOME puts the member at $HOME/<absolute path>,
                which is NOT where the CLI reads it. This is the leg the
                real defect trips.
  NO-OPT-OUT    no lane runs the CLI with --no-session (comments excluded:
                a prose mention of the flag is not a use of it).
  GOOSE-STORE   the collect list covers the goose session store - measured
                live where a store exists, otherwise against the pinned
                goose >= 1.5x layout.
  MOUNT         the chain mounts a restore dir at /sessions-restore and
                creates the source dir it mounts from.
  REVIEW-CAPTURE the duty reviewer's verdict really reaches the merger: the
                arm's write path and the extractor's read path name ONE file,
                the container mounts the host workspace under that path, and
                the extractor's own pattern captures every verdict literal the
                reviewer brief demands (replayed, not compared as prose).
  SCRATCH       the loop's workspace scratch is invisible to its own commit. The
                host commits with a bare `git add -A`, so every dot-path the
                carriers write into $PWD is a commit candidate for that run's
                branch. The names are DERIVED from the carriers and pinned by
                roster, then asked of git: ignored (`check-ignore --no-index`)
                and untracked (`ls-files`). `.turn-sessions.tgz` is the reason
                this is not housekeeping - it holds the session stores BEFORE
                the host scrub step, and the scrubber's grep cannot read inside
                a gzip stream. A lost `git add -A`, a roster that no longer
                matches the carriers, or a scratch name the index already holds
                are CANNOT RUN / RED respectively (measured: `.turn-review.txt`
                landed in 1a87144 + 7a4623d, `demo-backend/.coverage` in d819f6e).

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness no longer understands its own input - never a
false red for a tree it has not measured).

The shipped tree is RED on purpose: the defect is real and the fix is the
Lead's to apply. That is why the controls build their own green baseline -
the three repairs, reconstructed on a COPY from whatever shape the carrier
holds (the delivered patch pinned the old one and stopped applying when the
block was extracted, which silently killed all eight controls) - because a
check that can only ever say RED is not a check (DEVGUIDE *EIGHTH harness
law, applied to the harness itself).

  python3 scripts/chain_session_check.py                 # grade this tree
  python3 scripts/chain_session_check.py --root /tmp/x   # grade another tree
  python3 scripts/chain_session_check.py --selftest      # prove every leg can fail
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ------------------------------------------------------------ pinned inputs
# The PROMISE, not the disk. A harness that derives its expectations from
# the tree it grades proves nothing.
WORKFLOW_REL = ".github/workflows/agent-team.yml"
# The segment step used to be one inline block in the workflow. GitHub refuses
# an inline `run:` over 21000 chars, so it was extracted into this script
# (commit eaf34bd, 2026-10-22) and the workflow now only runs it. The session
# loop lives wherever the heredoc lives, so BOTH shapes are read.
SEGMENT_REL = ".github/scripts/turn_segment.sh"

# The restore mount the chain uses (Owner order 18:27Z).
RESTORE_MOUNT = "/sessions-restore"

# The goose session store. goose 1.55.0 keeps its session in a SQLite store
# under .local/share/goose/sessions (sessions.db + -wal/-shm); the older
# .config/goose/sessions layout is still listed by the collect for an older
# goose. Pinned here with the date it was measured (2026-10-22, chain image)
# because the leg below probes the live HOME and falls back to this pin
# when it finds no store at all.
GOOSE_STORE = ".local/share/goose/sessions"
LEGACY_GOOSE_STORE = ".config/goose/sessions"

# The flag that opts a lane OUT of the session law. Its own help says it
# runs "without creating or using a session file".
FORBIDDEN_FLAGS = ("--no-session",)

# A collect list smaller than this cannot be a population (ELEVENTH law:
# a printed count is not an expectation).
COLLECT_POPULATION_FLOOR = 3

# The duty reviewer's verdict is the ONLY input the merger acts on, and it
# crosses a container boundary as a scratch file: the reviewer arm writes it
# INSIDE the container at its absolute /workspace path, the extractor reads it
# on the HOST as $PWD/<same name>, and `-v "$PWD":/workspace` is the only thing
# that makes those two spellings one file. Measured 2026-10-24: three
# review-missing records in ~50 min (0339 07:10Z, 0659 07:21Z + 07:59Z), two of
# them with a reviewer lane named and no verdict captured - which the chain
# cannot tell apart from a lane that never ran. The promise, not the disk.
REVIEW_SCRATCH_NAME = ".turn-review.txt"
REVIEW_MOUNT_RE = re.compile(r'-v\s+"\$PWD":/workspace\b')
# A redirect target ending in the scratch name, on either side of the boundary.
REVIEW_PATH_RE = re.compile(r'(?P<path>[^\s"\'<>|;&]*\.turn-review[\w.-]*\.txt)')
# The host's capture line: `REVIEW_VERDICT=$(grep <flags> '<ERE>' "<path>" ...)`
REVIEW_EXTRACT_RE = re.compile(
    r"""^REVIEW_VERDICT=\$\(grep\s+[-A-Za-z]+\s+'(?P<pat>[^']+)'\s+"(?P<path>[^"]+)" """,
    re.M)
# The reviewer brief's own demand: the last line must be one of these literals.
REVIEW_TOKEN_RE = re.compile(r"^VERDICT:\s*(?P<tok>[A-Z]+)[^\n]*$", re.M)
# What the arms wrap the CLI in - recorded as evidence, never graded as a
# verdict: a lane killed at its timeout writes a truncated payload with no
# VERDICT line, which lands in REVIEW-LOG as review-missing (see the 07:59Z
# record); the fix is the Lead's budget call, not a seat's claim.
REVIEW_TIMEOUT_RE = re.compile(r'timeout\s+(?P<n>\d+)\b')

# ---------------------------------------------------- workspace scratch
# The turn loop writes its scratch INTO THE CHECKOUT, and the host commit a few
# lines later is a bare `git add -A` (measured once, and graded below as the
# premise of this whole leg). Every workspace path the carriers therefore name is
# a commit candidate for whatever branch delivers that run. Not a hypothesis:
# `.turn-review.txt` landed twice (1a87144, 7a4623d) and `demo-backend/.coverage`
# once (d819f6e) — all three through that same add -A.
#
# The names this leg exists to keep ignored are the session-law ones:
#   * `.turn-sessions.tgz` — the collect tar, written by the container at
#     /workspace and read by the host's "Persist session files" step only AFTER
#     the commit, so a non-empty tarball reaches git history BEFORE any scrubbing
#     (the secret-guard runs on the extracted copy, and a grep-based redaction
#     cannot see inside a gzip stream in any case). The lanes that run --no-session
#     are why nothing has landed YET: the same NO-OPT-OUT defect this harness
#     already grades makes the tar empty today, and docs/session-loop-fix.patch —
#     the Lead's pending repair — is exactly what makes it non-empty every run.
#   * `.sessions-restore/`, `.sessions-upload/`, `.review-upload/`,
#     `.sessions-prev.zip` — the artifact staging the same loop builds in $PWD.
# The roster is PINNED, like every other population here: a carrier that starts
# writing a name this harness has not heard of is CANNOT RUN, never a green that
# quietly grades one file fewer.
WORKSPACE_WRITE_RE = re.compile(r'(?:"\$PWD"?|/workspace)/(?P<name>\.[\w.-]+)')
# `mkdir -p "$PWD/.x"` marks a name as a DIRECTORY, which is what decides the
# form git is asked about (a `.x/` pattern matches a child path, not the bare
# name, when nothing on disk says "directory").
SCRATCH_MKDIR_RE = re.compile(r'mkdir\s+-p\s+"?\$PWD/?(?P<name>\.[\w.-]+)"?')
ADD_ALL_RE = re.compile(r'^\s*git\s+add\s+-A\b', re.M)
EXPECTED_SCRATCH = (
    ".review-preflight.txt",
    ".review-upload",
    ".sessions-prev.zip",
    ".sessions-restore",
    ".sessions-upload",
    ".turn-inside.sh",
    ".turn-result.txt",
    ".turn-review.txt",
    ".turn-sessions.tgz",
)
# Paths MEASURED in git history as already committed by that add -A, with the
# commit that did it. Such a name must be untracked as well as ignored: an
# ignored path that the index already holds is still committed, every run, which
# is why demo-backend/.coverage sat on ai/main from d819f6e onwards while
# `.gitignore` said nothing about it. The pin is the PROMISE (a leak stays
# graded shut), not the disk.
PROVEN_LEAKS = (".turn-review.txt", "demo-backend/.coverage")
# A child path under a scratch DIRECTORY, for the ignore question. It is never
# created on disk — `git check-ignore` evaluates rules against path text.
SCRATCH_DIR_PROBE = ".ignore-probe"


# ------------------------------------------------------------- file shapes
HEREDOC_OPEN_RE = re.compile(r"cat\s+>\s+\"?\$PWD/\.turn-inside\.sh\"?\s*<<'([A-Z_]+)'")
SEGMENT_CALL_RE = re.compile(r"bash\s+\S*\.github/scripts/turn_segment\.sh")
TAR_OPEN_RE = re.compile(r"^\s*tar\s+czf\s+\S+\s+-C\s+/\s*\\?\s*$")
CP_RE = re.compile(r"^\s*cp\s+-a\s+(?P<src>\S+)\s+(?P<dst>\S+)\b")
MOUNT_RE = re.compile(r"/sessions-restore:ro")
MKDIR_RESTORE_RE = re.compile(r"mkdir\s+-p\s+\"?\$PWD/\.sessions-restore\"?")


class CannotRun(Exception):
    pass


class Red(Exception):
    pass


# ------------------------------------------------------------------ parsing
def read(root, rel):
    try:
        with open(os.path.join(root, rel), encoding="utf-8") as fh:
            return fh.read()
    except OSError as exc:
        raise CannotRun("cannot read %s: %s" % (rel, exc))


def heredoc_body(text, rel):
    """The .turn-inside.sh heredoc inside `text`, or None if there is none.

    The script is embedded in a quoted heredoc, so its body is taken verbatim
    between the opening line and the terminator and dedented - the shell never
    sees the YAML indentation the workflow shape used to add.
    """
    lines = text.splitlines()
    for index, line in enumerate(lines):
        match = HEREDOC_OPEN_RE.search(line)
        if not match:
            continue
        marker = match.group(1)
        body = []
        for candidate in lines[index + 1:]:
            if candidate.strip() == marker:
                break
            body.append(candidate)
        else:
            raise CannotRun("the %s heredoc in %s is never closed" % (marker, rel))
        indent = min((len(l) - len(l.lstrip()) for l in body if l.strip()), default=0)
        return "\n".join(l[indent:] if l.strip() else l for l in body)
    return None


def resolve_inner_script(root, workflow_text):
    """(where, file text, inner script) for the chain's turn script.

    TWO shipped shapes, and the harness must follow whichever the chain
    actually uses: the heredoc used to sit inline in the workflow, and the
    workflow now runs .github/scripts/turn_segment.sh instead (eaf34bd -
    GitHub rejects the 31.5KB inline block). Reading only the first shape is
    how this harness went blind on 2026-10-22, so a missing leg is a refusal,
    never a silent pass.
    """
    inline = heredoc_body(workflow_text, WORKFLOW_REL)
    segment_text = ""
    extracted = None
    if SEGMENT_CALL_RE.search(workflow_text):
        segment_text = read(root, SEGMENT_REL)
        extracted = heredoc_body(segment_text, SEGMENT_REL)
    if inline is not None and extracted is not None:
        raise Red("TWO carriers write the .turn-inside.sh heredoc - %s inline and %s, "
                  "which %s runs: the loop cannot be graded from a script nobody "
                  "executes" % (WORKFLOW_REL, SEGMENT_REL, WORKFLOW_REL))
    if inline is not None:
        return WORKFLOW_REL, workflow_text, inline
    if extracted is not None:
        return SEGMENT_REL, segment_text, extracted
    raise CannotRun("neither %s nor the %s it runs writes a .turn-inside.sh heredoc - "
                    "the chain's inner script is gone and this harness no longer "
                    "understands its input" % (WORKFLOW_REL, SEGMENT_REL))


def strip_comment(line):
    """Drop a trailing `# ...` comment so prose about a flag is not a use."""
    out = []
    for index, char in enumerate(line):
        if char == "#" and (index == 0 or line[index - 1] in " \t"):
            break
        out.append(char)
    return "".join(out)


def logical_lines(script):
    """The shell's LOGICAL lines: backslash-continued lines are one command.

    The restore's `cp -a` is written across two lines in the workflow, so a
    line-by-line scan would see a command with no destination and grade the
    copy as absent - a false red produced by the reader, not by the chain.
    """
    out = []
    buf = ""
    for line in script.splitlines():
        piece = line.strip()
        buf = (buf + " " + piece).strip() if buf else piece
        if buf.endswith("\\"):
            buf = buf[:-1].rstrip()
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def collect_members(script):
    """The stores the collect tar takes, as archive-relative paths.

    The tar is rooted at / (`tar czf ... -C /`), so every member keeps its
    ABSOLUTE path inside the archive: `${HOME#/}/.qoder` lands as
    `home/agent/.qoder` when HOME=/home/agent. That is why the restore must
    mirror the collect's path list and not just the HOME-relative one.
    """
    members = []
    for line in logical_lines(script):
        if not line.startswith("tar ") or "-C /" not in line:
            continue
        rest = line.split("-C /", 1)[1].split("2>/dev/null", 1)[0]
        for token in rest.split():
            if token.startswith("2>") or token in ("|", "||", "true"):
                continue
            members.append(token.strip('"').strip("'"))
        break
    return members


def resolve_member(entry, home_rel):
    """A collect entry -> the path it has inside the archive (no leading /)."""
    if "${HOME#/}" in entry:
        return home_rel + "/" + entry.replace("${HOME#/}", "").lstrip("/")
    return entry.lstrip("/")


def restore_copies(script):
    """Every `cp -a SRC DST` of the restore block, parsed."""
    out = []
    for line in logical_lines(script):
        match = CP_RE.match(line)
        if not match:
            continue
        out.append((match.group("src").strip('"'), match.group("dst").strip('"')))
    return out


def home_rel_from_copies(copies):
    """The container HOME as the archive sees it, derived from the restore.

    The restore copies `/sessions-restore/<home>/.` into `$HOME`, so the
    <home> in that path IS the container's HOME inside the archive. Deriving
    it from the workflow (instead of pinning it, or asking the running
    machine) keeps the checker's verdict identical wherever it runs.
    """
    for src, dst in copies:
        if dst.rstrip("/") != "$HOME":
            continue
        if not src.startswith(RESTORE_MOUNT + "/"):
            continue
        rest = src[len(RESTORE_MOUNT) + 1:]
        if rest.endswith("/."):
            rest = rest[:-2]
        if rest:
            return rest.strip("/")
    return None


def covers(copy, member, home_rel):
    """Does one `cp -a` put this archive member back where it belongs?

    `cp -a SRC/. DST` copies the CONTENTS of SRC into DST; `cp -a SRC DST`
    copies the directory SRC itself into DST. The member must land on its
    own absolute path - a copy of the archive ROOT into $HOME lands every
    member at $HOME/<absolute path>, which is not where the CLI looks.
    """
    src, dst = copy
    if not src.startswith(RESTORE_MOUNT):
        return False
    rest = src[len(RESTORE_MOUNT):]
    if rest.endswith("/."):
        contents = True
        src_rel = rest[:-2].strip("/")
    elif rest.endswith("/"):
        contents = True
        src_rel = rest[:-1].strip("/")
    else:
        contents = False
        src_rel = rest.strip("/")
    if contents:
        dest_rel = dst.rstrip("/")
        if dest_rel == "$HOME":
            dest_rel = home_rel
        else:
            dest_rel = dest_rel.lstrip("/")
        if member == src_rel:
            return dest_rel == member
        if not member.startswith(src_rel + "/"):
            return False
        tail = member[len(src_rel) + 1:]
        return dest_rel + "/" + tail == member
    # `cp -a SRC DST` (no `/.`): the directory itself lands inside DST.
    if dst.rstrip("/") == "$HOME":
        dest_root = home_rel
    else:
        dest_root = dst.rstrip("/").lstrip("/")
    if src_rel == "":
        return False
    if member.startswith(src_rel + "/"):
        tail = member[len(src_rel) + 1:]
    elif member == src_rel:
        tail = ""
    else:
        return False
    base = os.path.basename(src_rel)
    landed = dest_root + "/" + base + ("/" + tail if tail else "")
    return landed == member


# ------------------------------------------------------- review-capture law
def grade_review_capture(script, loop_text):
    """(problems, notes) for the duty reviewer's verdict crossing the boundary.

    THREE claims, because the capture breaks in three independent places, and
    today's three review-missing records show the chain cannot tell them apart:
    (1) the arm's write path and the extractor's read path must name the SAME
    file; (2) the container must mount the host workspace where the arm writes;
    (3) the verdict literal the BRIEF demands must be capturable by the
    extractor's OWN pattern - replayed, not compared as prose, the same way the
    CSV twins are diffed by running both writers.
    """
    writers = sorted(set(match.group("path")
                         for match in REVIEW_PATH_RE.finditer(script)))
    if not writers:
        raise CannotRun("no reviewer arm writes a %s - the duty review lane is gone, "
                        "so there is no capture for this harness to grade"
                        % REVIEW_SCRATCH_NAME)
    extract = REVIEW_EXTRACT_RE.search(loop_text)
    if not extract:
        raise CannotRun("the host no longer captures the verdict in the shape this "
                        'harness parses (REVIEW_VERDICT=$(grep <flags> \'<E>\' "<path>")) '
                        "- a capture rewritten is a capture re-measured, never assumed")

    problems = []
    notes = []
    write_names = set(os.path.basename(path) for path in writers)
    read_name = os.path.basename(extract.group("path"))
    if read_name not in write_names:
        problems.append("REVIEW-CAPTURE: the reviewer arm writes %s but the extractor "
                        "reads %s - the verdict is captured from a file nobody writes, "
                        "so a completed review records review-missing"
                        % (", ".join(writers), extract.group("path")))
    notes.append("REVIEW-CAPTURE: writer(s) %s -> reader %s"
                 % (", ".join(writers), extract.group("path")))

    if not REVIEW_MOUNT_RE.search(loop_text):
        problems.append("REVIEW-CAPTURE: no %s mounts the host workspace at /workspace "
                        "- the arm's /workspace/%s and the extractor's $PWD/%s are then "
                        "TWO different files and the verdict never leaves the container"
                        % (SEGMENT_REL, REVIEW_SCRATCH_NAME, REVIEW_SCRATCH_NAME))

    demands = list(REVIEW_TOKEN_RE.finditer(loop_text))
    if not demands:
        raise CannotRun("the reviewer brief asks for no VERDICT line, so there is no "
                        "token to capture - the review duty is no longer what this "
                        "harness grades")
    ere = extract.group("pat")
    if "[[:" in ere.replace("[[:space:]]", ""):
        raise CannotRun("the extractor's pattern uses a POSIX class this harness cannot "
                        "translate (%s) - it would grade its own guess, not the capture"
                        % ere)
    try:
        capture = re.compile(ere.replace("[[:space:]]", r"\s"))
    except re.error as exc:
        raise CannotRun("the extractor's pattern is not a pattern this harness can "
                        "replay: %s (%s)" % (ere, exc))
    lost = []
    for match in demands:
        hit = capture.search(match.group(0) + "\n")
        if not hit or hit.group(1) != match.group("tok"):
            lost.append("%r" % match.group(0))
    if lost:
        problems.append("REVIEW-CAPTURE: the brief demands %s but the extractor's own "
                        "pattern %r captures none of it - the reviewer can answer "
                        "perfectly and the merger still sees verdict=none"
                        % (", ".join(lost), ere))
    notes.append("REVIEW-CAPTURE: pattern %r replayed against %d brief token line(s), "
                 "%d captured" % (ere, len(demands), len(demands) - len(lost)))
    timeouts = REVIEW_TIMEOUT_RE.findall(script)
    if timeouts:
        notes.append("REVIEW-CAPTURE: reviewer arm(s) wrapped in `timeout %s` - a lane "
                     "killed mid-answer writes no VERDICT line and lands in REVIEW-LOG "
                     "as review-missing (budget: Lead's call, not a claim here)"
                     % ", ".join(sorted(set(timeouts))))
    return problems, notes


def git_ask(root, args, what):
    """Run one read-only git query against ROOT; a refusal is CANNOT RUN.

    The ignore question is asked of git itself rather than reimplemented here:
    gitignore matching has negations, anchoring and directory rules, and a
    hand-written matcher would grade its own guess. `--no-index` is deliberate —
    the question is "would `git add -A` take this untracked scratch path", and an
    index lookup would answer "not ignored" for a name that IS ignored but has
    already leaked. That second failure is its own check below, never a pass.
    """
    done = subprocess.run(("git", "-C", root) + args, capture_output=True, text=True)
    if done.returncode not in (0, 1):
        raise CannotRun("git %s exited %d (%s) - %s cannot be answered without git, "
                        "so this leg refuses rather than guessing: %s"
                        % (" ".join(args[:2]), done.returncode,
                           done.stderr.strip()[:140], what,
                           "is the graded tree a git work tree?"))
    return done


def scratch_writes(loop_text):
    """(names, dirs) — every workspace-resident dot-path the carriers touch."""
    names = set(match.group("name") for match in WORKSPACE_WRITE_RE.finditer(loop_text))
    dirs = set(match.group("name") for match in SCRATCH_MKDIR_RE.finditer(loop_text))
    return names, dirs


def grade_scratch(root, loop_text):
    """(problems, notes) for the scratch the host `git add -A` can commit.

    FOUR claims, checked in the order a reader can falsify them:
      premise  the turn loop really does commit with a bare `git add -A`. If it
               stops, ignore coverage is no longer load-bearing and this leg has
               lost its subject, so it says CANNOT RUN instead of going quietly
               green (the same ruling as a gate that parses to zero commands).
      roster   the names derived from the carriers are exactly EXPECTED_SCRATCH.
      ignore   git reports every one of them ignored in the graded tree.
      index    none of them, and no PROVEN_LEAKS path, is tracked.
    """
    problems = []
    notes = []

    if not ADD_ALL_RE.search(loop_text):
        raise CannotRun("no bare `git add -A` in the turn loop - the commit that this "
                        "leg exists to guard has changed shape, so ignore coverage is "
                        "no longer what keeps scratch out of a branch")
    notes.append("PREMISE: the turn loop commits with `git add -A` (that is why an "
                 "unignored scratch path lands)")

    names, dirs = scratch_writes(loop_text)
    if not names:
        raise CannotRun("the carriers name no workspace scratch path at all - the loop "
                        "no longer writes where this harness reads, so there is nothing "
                        "for the leg to grade")
    if tuple(sorted(names)) != EXPECTED_SCRATCH:
        vanished = sorted(set(EXPECTED_SCRATCH) - names)
        unrostered = sorted(names - set(EXPECTED_SCRATCH))
        raise CannotRun("the workspace scratch the carriers write is %d name(s), the pin "
                        "says %d (vanished: %s / unrostered: %s) - a comparison cannot see "
                        "its own coverage, so this is a refusal, not a smaller green "
                        "(add the name to EXPECTED_SCRATCH and .gitignore in the SAME "
                        "commit as the carrier that writes it)"
                        % (len(names), len(EXPECTED_SCRATCH),
                           ", ".join(vanished) or "none",
                           ", ".join(unrostered) or "none"))

    unignored = []
    for name in EXPECTED_SCRATCH:
        probe = name + "/" + SCRATCH_DIR_PROBE if name in dirs else name
        if git_ask(root, ("check-ignore", "--no-index", "-q", probe),
                   "is %s ignored" % name).returncode != 0:
            unignored.append(name)
            problems.append("SCRATCH: the turn loop writes %s into the checkout and git "
                            "does NOT ignore it (%s) - the host `git add -A` commits it "
                            "onto whatever branch delivers that run; add the pattern to "
                            ".gitignore" % (name, probe))
    notes.append("IGNORE: %d workspace scratch name(s) derived from the carriers (%d of "
                 "them dirs created by mkdir), %d ignored, unignored: %s"
                 % (len(EXPECTED_SCRATCH), len(dirs),
                    len(EXPECTED_SCRATCH) - len(unignored),
                    ", ".join(unignored) or "none"))

    for name in EXPECTED_SCRATCH:
        held = [line for line in git_ask(root, ("ls-files", "--", name),
                                        "is %s tracked" % name).stdout.splitlines()
                if line.strip()]
        if held:
            problems.append("SCRATCH: %s is TRACKED in this tree (%s) - ignoring it does "
                            "not untrack it, so `git add -A` keeps committing it every "
                            "run; run `git rm --cached %s`"
                            % (name, held[0], name))

    for rel in PROVEN_LEAKS:
        held = [line for line in git_ask(root, ("ls-files", "--", rel),
                                        "is %s tracked" % rel).stdout.splitlines()
                if line.strip()]
        if held:
            problems.append("PROVEN-LEAK: %s is measured in git history as already "
                            "committed by that add -A and it is STILL tracked here - the "
                            "leak is live, not historical: `git rm --cached %s`"
                            % (rel, rel))
        if git_ask(root, ("check-ignore", "--no-index", "-q", rel),
                   "is %s ignored" % rel).returncode != 0:
            problems.append("PROVEN-LEAK: %s (a path measured committed by `git add -A`) "
                            "is not ignored in this tree - nothing keeps the next run "
                            "from committing it again" % rel)
    notes.append("PROVEN-LEAK: %d path(s) pinned from git history (%s) checked untracked "
                 "and ignored" % (len(PROVEN_LEAKS), ", ".join(PROVEN_LEAKS)))
    return problems, notes


# -------------------------------------------------------------- live probes
def find_stores(home):
    """Where the CLIs on THIS machine keep their session stores."""
    found = []
    for relative in (GOOSE_STORE, LEGACY_GOOSE_STORE):
        path = os.path.join(home, relative)
        if os.path.isdir(path):
            found.append(relative)
    return found


def live_note(home):
    """Evidence about the live container (never a verdict on its own)."""
    notes = []
    for relative in (GOOSE_STORE, LEGACY_GOOSE_STORE):
        path = os.path.join(home, relative)
        if os.path.isdir(path):
            try:
                entries = sorted(os.listdir(path))
            except OSError:
                entries = []
            notes.append("live store %s -> %s (%d entr(y/ies): %s)"
                         % (relative, path, len(entries), ", ".join(entries[:4]) or "-"))
        else:
            notes.append("live store %s -> ABSENT (%s)" % (relative, path))
    if os.path.isdir(RESTORE_MOUNT):
        try:
            mounted = sorted(os.listdir(RESTORE_MOUNT))
        except OSError:
            mounted = []
        notes.append("restore mount %s -> %d entr(y/ies): %s"
                     % (RESTORE_MOUNT, len(mounted), ", ".join(mounted[:6]) or "EMPTY"))
    else:
        notes.append("restore mount %s -> not mounted here" % RESTORE_MOUNT)
    return notes


# ------------------------------------------------------------------- main
def grade(root, home):
    workflow_text = read(root, WORKFLOW_REL)
    carrier, carrier_text, script = resolve_inner_script(root, workflow_text)
    # The container run, its mount and the restore dir it mounts from may sit in
    # either turn-loop file, so the MOUNT leg reads both. Which script the chain
    # actually runs is the carrier's business, decided above.
    loop_text = "\n".join([workflow_text, carrier_text])
    if carrier != SEGMENT_REL and os.path.exists(os.path.join(root, SEGMENT_REL)):
        loop_text += "\n" + read(root, SEGMENT_REL)

    problems = []
    notes = []
    notes.append("CARRIER: the .turn-inside.sh heredoc is written by %s" % carrier)

    copies = restore_copies(script)
    if not copies:
        raise CannotRun("%s copies nothing back into $HOME - the restore block is gone "
                        "and this harness no longer understands its input" % carrier)
    home_rel = home_rel_from_copies(copies)
    if not home_rel:
        raise CannotRun("the restore block never copies /sessions-restore/<home>/ into "
                        "$HOME - the container HOME cannot be derived, so the members "
                        "cannot be placed")

    # ---- 1. COLLECT: the population
    members = collect_members(script)
    if not members:
        raise CannotRun("the collect block lists no store - the tar takes nothing, so the "
                        "loop cannot close")
    if len(members) < COLLECT_POPULATION_FLOOR:
        problems.append("COLLECT: the tar takes %d store(s), floor is %d - the population "
                        "this harness grades is no longer there"
                        % (len(members), COLLECT_POPULATION_FLOOR))
    notes.append("COLLECT: %d store(s) in the tar list" % len(members))

    # ---- 2. RESTORE: every collected store is restored to its OWN place
    for entry in members:
        member = resolve_member(entry, home_rel)
        if not any(covers(copy, member, home_rel) for copy in copies):
            problems.append("RESTORE: the collect takes %s (archive member %s) but no "
                            "restore copy puts it back at its own path - it is collected "
                            "every turn and never restored" % (entry, member))
    notes.append("RESTORE: %d copy/copies in the restore block, container HOME inside "
                 "the archive is %s" % (len(copies), home_rel))

    # ---- 3. NO-OPT-OUT: no lane opts out of the session law
    for number, line in enumerate(logical_lines(script), start=1):
        code = strip_comment(line)
        for flag in FORBIDDEN_FLAGS:
            if flag in code:
                problems.append("NO-OPT-OUT: the inner script passes %s (line %d): the CLI "
                                "then runs \"without creating or using a session file\", "
                                "the opposite of the Owner's SESSION LAW" % (flag, number))
    notes.append("NO-OPT-OUT: %d flag(s) forbidden, comments excluded" % len(FORBIDDEN_FLAGS))

    # ---- 4. GOOSE-STORE: the collect list covers the goose session store
    stores = find_stores(home)
    if stores:
        expected = stores
        source = "measured live in %s" % home
    else:
        expected = [GOOSE_STORE]
        source = "pinned (goose >= 1.5x layout, measured 2026-10-22 in the chain image)"
    resolved = [resolve_member(entry, home_rel) for entry in members]
    for store in expected:
        tail = store.lstrip("./")
        if not any(member.endswith(tail) for member in resolved):
            problems.append("GOOSE-STORE: the collect list does not cover the goose "
                            "session store %s (%s) - the store the CLI actually writes is "
                            "never collected" % (store, source))
    notes.append("GOOSE-STORE: expecting %s (%s)" % (", ".join(expected), source))

    # ---- 5. MOUNT: the restore dir is mounted and created
    if not MOUNT_RE.search(loop_text):
        problems.append("MOUNT: neither %s nor %s mounts a restore dir at %s - the "
                        "collected sessions have no way back in"
                        % (WORKFLOW_REL, SEGMENT_REL, RESTORE_MOUNT))
    if not MKDIR_RESTORE_RE.search(loop_text):
        problems.append("MOUNT: no %s / %s creates the source dir it mounts from - the "
                        "mount would land on an empty host path"
                        % (WORKFLOW_REL, SEGMENT_REL))
    notes.append("MOUNT: %s mounted at %s" % (RESTORE_MOUNT, RESTORE_MOUNT))

    # ---- 6. REVIEW-CAPTURE: the duty reviewer's verdict really reaches the merger
    review_problems, review_notes = grade_review_capture(script, loop_text)
    problems.extend(review_problems)
    for note in review_notes:
        notes.append(note)

    # ---- 7. SCRATCH: the host `git add -A` can only ever commit ignored scratch
    scratch_problems, scratch_notes = grade_scratch(root, loop_text)
    problems.extend(scratch_problems)
    for note in scratch_notes:
        notes.append(note)

    for note in live_note(home):
        notes.append(note)

    if problems:
        raise Red("\n".join(problems))

    print("SESSION-LOOP CHECK OK — %d store(s) collected, all restored to their own path"
          % len(members))
    for note in notes:
        print("  " + note)
    return 0


def main(argv):
    parser = argparse.ArgumentParser(description="grade the chain's SESSION collect->restore loop")
    parser.add_argument("--root", default=None,
                        help="run against another tree (control); default: this repo")
    parser.add_argument("--home", default=os.environ.get("HOME", "/home/agent"),
                        help="the HOME to probe for live session stores")
    parser.add_argument("--selftest", action="store_true",
                        help="prove every leg can fail, against copies of this tree")
    args = parser.parse_args(argv)
    root = os.path.abspath(args.root) if args.root else os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    if args.selftest:
        return selftest(root)

    return grade(root, args.home)


# ------------------------------------------------------------------ selftest
# A check that cannot FAIL is not a check (DEVGUIDE *EIGHTH harness law,
# applied to the harness itself). Every control below works on a COPY of
# the tree and asserts the verdict it must produce. The shipped tree is
# RED (the defect is real), so a green baseline has to be built before a
# control can prove that a leg can go red. The shipped tree is never
# written to.
#
# The baseline used to be docs/session-loop-fix.patch applied to the copy.
# That patch targets the shape the workflow carried BEFORE eaf34bd extracted
# the segment step into .github/scripts/turn_segment.sh, so `git apply` no
# longer matched - and every control died in CANNOT RUN before grading
# anything, which is how this harness reported rc 2 for a whole cycle while
# the loop it exists to guard went unmeasured. The same three repairs are
# therefore BUILT from the shipped text: indentation-agnostic (they land in
# either carrier shape), idempotent (a repair already present is a no-op)
# and a refusal naming the lost anchor when the text no longer looks like
# either shape.
def _read_file(root, rel):
    with open(os.path.join(root, rel), encoding="utf-8") as fh:
        return fh.read()


def _write_file(root, rel, text):
    with open(os.path.join(root, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


def _subn_file(root, rel, pattern, repl, count, missing):
    """Regex-mutate a file once; a mutation that finds nothing is CANNOT RUN.

    A control whose target text has moved is not a passing control - it
    graded nothing. Silence here is the rot this harness already fell into.
    """
    text = _read_file(root, rel)
    new, hits = re.subn(pattern, repl, text, count=count, flags=re.M)
    if not hits:
        raise CannotRun("control: %s - %s no longer carries that shape, so this "
                        "control grades nothing" % (missing, rel))
    _write_file(root, rel, new)


# The three repairs, as shipped shapes: each is anchored on the line the
# chain actually writes, never on a literal indentation count.
QODER_RESTORE_MARK = "/sessions-restore/usr/local/lib/qoder-home/.qoder"
GOOSE_LEGACY_STORE_LINE = r'^([ \t]*)"\$\{HOME#/\}/\.config/goose/sessions" \\\n'
QODER_RESTORE_ANCHOR = r'^[ \t]*cp -a /sessions-restore/\. "\$HOME/".*\n([ \t]*)fi[ \t]*\n'


def carrier_rel(root):
    """Which file carries the .turn-inside.sh heredoc on this tree."""
    for rel in (WORKFLOW_REL, SEGMENT_REL):
        if not os.path.exists(os.path.join(root, rel)):
            continue
        if heredoc_body(_read_file(root, rel), rel) is not None:
            return rel
    raise CannotRun("neither %s nor %s writes a .turn-inside.sh heredoc - the green "
                    "baseline cannot be built" % (WORKFLOW_REL, SEGMENT_REL))


def build_green(root):
    """Close the three session-law gaps on a COPY of the tree."""
    rel = carrier_rel(root)
    text = _read_file(root, rel)

    # 1. NO-OPT-OUT: a lane that runs the CLI with --no-session writes no
    #    session file, so the flag has to leave every goose lane.
    if "goose run --no-session" in text:
        text = text.replace("goose run --no-session", "goose run")
    elif 'goose run -t' not in text:
        raise CannotRun("%s has no goose lane in either shape - the baseline cannot "
                        "grade NO-OPT-OUT" % rel)

    # 2. GOOSE-STORE: the collect list must hold the store goose 1.55 writes.
    if '"${HOME#/}/.local/share/goose/sessions"' not in text:
        match = re.search(GOOSE_LEGACY_STORE_LINE, text, re.M)
        if not match:
            raise CannotRun("%s no longer collects the goose store the way the harness "
                            "parses it - the baseline cannot be built" % rel)
        line = '%s"${HOME#/}/.local/share/goose/sessions" \\\n' % match.group(1)
        text = text[:match.end()] + line + text[match.end():]

    # 3. RESTORE: every collected store returns to ITS OWN path.
    if QODER_RESTORE_MARK not in text:
        match = re.search(QODER_RESTORE_ANCHOR, text, re.M)
        if not match:
            raise CannotRun("%s no longer ends its restore block where the harness "
                            "attaches the second store - the baseline cannot be built" % rel)
        ind = match.group(1)
        block = (
            '{0}if [ -d {1}/usr/local/lib/qoder-home/.qoder ]; then\n'
            '{0}  mkdir -p /usr/local/lib/qoder-home/.qoder\n'
            '{0}  cp -a {1}/usr/local/lib/qoder-home/.qoder/. \\\n'
            '{0}    /usr/local/lib/qoder-home/.qoder/ 2>/dev/null || true\n'
            '{0}fi\n').format(ind, RESTORE_MOUNT)
        text = text[:match.end()] + block + text[match.end():]

    _write_file(root, rel, text)

    # The baseline must still be SHELL, not just text this harness likes.
    inner = heredoc_body(text, rel)
    with tempfile.NamedTemporaryFile("w", suffix=".sh", delete=False) as fh:
        fh.write(inner)
        probe = fh.name
    try:
        done = subprocess.run(("bash", "-n", probe), capture_output=True, text=True)
        if done.returncode != 0:
            raise CannotRun("the green baseline is not valid shell: %s"
                            % done.stderr.strip()[:200])
    finally:
        os.unlink(probe)


def control_no_change(root):
    return None


def control_drop_restore_copy(root):
    """Take the qoder store out of the restore: the leg must fire."""
    _subn_file(root, carrier_rel(root),
               r'^[ \t]*if \[ -d ' + re.escape(QODER_RESTORE_MARK) + r' \]; then\n'
               r'(?:.*\n)*?[ \t]*fi\n', "", 1,
               "the second store's restore block is gone")


def control_reintroduce_opt_out(root):
    """Put --no-session back on a lane: the leg must fire."""
    _subn_file(root, carrier_rel(root),
               r'goose run -t "\$BRIEF"', 'goose run --no-session -t "$BRIEF"', 1,
               "no goose lane to opt out")


def control_drop_goose_store(root):
    """Take the goose store out of the collect list: the leg must fire."""
    _subn_file(root, carrier_rel(root),
               r'^[ \t]*"\$\{HOME#/\}/\.local/share/goose/sessions" \\\n', "", 1,
               "the goose store is not in the collect list")


def control_drop_mount(root):
    """Unmount the restore dir: the leg must fire."""
    _subn_file(root, carrier_rel(root),
               r'^[ \t]*-v "\$PWD/\.sessions-restore":/sessions-restore:ro \\\n', "", 1,
               "the restore mount is not there")


def control_drop_collect(root):
    """Take the collect list away: the harness cannot understand its input."""
    _subn_file(root, carrier_rel(root),
               r'^([ \t]*)tar czf "\$SESS" -C / \\\n', r'\1true # tar czf "$SESS" -C / \\\n', 1,
               "the collect tar is not there")


def control_second_carrier(root):
    """A heredoc in the workflow AND in the script it runs: nothing is graded."""
    rel = _read_file(root, WORKFLOW_REL)
    _write_file(root, WORKFLOW_REL,
                rel + '\ncat > "$PWD/.turn-inside.sh" <<\'OTHER\'\ntrue\nOTHER\n')


def control_inline_carrier(root):
    """Move the heredoc back into the workflow and drop the pointer.

    The other carrier shape. If the resolver only follows the extracted
    script, this tree grades nothing - so the shape claim is graded here.
    """
    segment = _read_file(root, SEGMENT_REL).splitlines(True)
    opener = next((index for index, line in enumerate(segment)
                   if HEREDOC_OPEN_RE.search(line)), None)
    if opener is None:
        raise CannotRun("control: %s holds no .turn-inside.sh heredoc to move" % SEGMENT_REL)
    marker = HEREDOC_OPEN_RE.search(segment[opener]).group(1)
    closing = next((index for index in range(opener + 1, len(segment))
                    if segment[index].strip() == marker), None)
    if closing is None:
        raise CannotRun("control: %s's heredoc never closes" % SEGMENT_REL)
    block = "".join(segment[opener:closing + 1])
    _write_file(root, SEGMENT_REL, "".join(segment[:opener] + segment[closing + 1:]))
    workflow = _read_file(root, WORKFLOW_REL)
    if not SEGMENT_CALL_RE.search(workflow):
        raise CannotRun("control: %s does not run %s, so the carrier cannot be moved"
                        % (WORKFLOW_REL, SEGMENT_REL))
    _write_file(root, WORKFLOW_REL,
                SEGMENT_CALL_RE.sub("true", workflow, count=1) + "\n" + block)


def control_missing_carrier(root):
    os.remove(os.path.join(root, SEGMENT_REL))


# The host's verdict-capture line, spelled exactly as the carrier writes it.
# A control mutates THIS and refuses (CANNOT RUN) when it no longer matches,
# because a control whose target has moved grades nothing.
REVIEW_CAPTURE_NEEDLE = ('REVIEW_VERDICT=$(grep -hoE '
                         "'VERDICT:[[:space:]]*(APPROVED|REJECTED)' "
                         '"$PWD/.turn-review.txt"')


def _mutate_once(root, needle, replacement, missing):
    """Replace one exact needle in the carrier; a moved needle is CANNOT RUN."""
    rel = carrier_rel(root)
    text = _read_file(root, rel)
    if needle not in text:
        raise CannotRun("control: %s - %s no longer carries that line, so this "
                        "control grades nothing" % (missing, rel))
    _write_file(root, rel, text.replace(needle, replacement, 1))


def control_rename_review_scratch(root):
    """The extractor reads a different scratch file than the reviewer arm writes.

    The read path moves to `.turn-result.txt` — a name the SCRATCH roster already
    knows — rather than to an invented one. Retyped here because the original
    control invented `.turn-review-v2.txt`, and the SCRATCH leg's population pin
    REFUSES an unrostered workspace name before any red is reported: the control
    then proved that the roster works, not that REVIEW-CAPTURE can fail. A control
    must trip its own leg, and no other.
    """
    _mutate_once(root, REVIEW_CAPTURE_NEEDLE,
                 REVIEW_CAPTURE_NEEDLE.replace('"$PWD/.turn-review.txt"',
                                               '"$PWD/.turn-result.txt"'),
                 "the verdict capture line is gone")


def control_break_verdict_token(root):
    """The brief's verdict literal and the extractor's pattern drift apart."""
    _mutate_once(root, REVIEW_CAPTURE_NEEDLE,
                 REVIEW_CAPTURE_NEEDLE.replace("'VERDICT:[[:space:]]*",
                                               "'VERDICT=[[:space:]]*"),
                 "the verdict pattern is not on the capture line")


def control_unmount_workspace(root):
    """The container mounts the host workspace under a different path."""
    _subn_file(root, carrier_rel(root),
               r'(-v "\$PWD":)/workspace', r"\1/work", 1,
               "the workspace mount is not there")


def control_missing_workflow(root):
    os.remove(os.path.join(root, WORKFLOW_REL))


# --- SCRATCH controls. Each provokes ONE of the four claims the leg makes, on
# a COPY; the shipped tree is never written to.
SCRATCH_SESS_NEEDLE = 'SESS="/workspace/.turn-sessions.tgz"'


def control_unignore_scratch(root):
    """The collect tarball loses its ignore line: the add -A would take it."""
    rel = ".gitignore"
    text = _read_file(root, rel)
    if ".turn-sessions.tgz\n" not in text:
        raise CannotRun("control: %s no longer carries the .turn-sessions.tgz line, so "
                        "this control grades nothing" % rel)
    _write_file(root, rel, text.replace(".turn-sessions.tgz\n", "", 1))


def control_scratch_reaches_the_index(root):
    """The d819f6e shape: scratch that got committed stays committed when ignored."""
    path = os.path.join(root, ".turn-sessions.tgz")
    with open(path, "wb") as fh:
        fh.write(b"\x1f\x8b\x08\x00 control payload, never read\n")
    done = subprocess.run(("git", "add", "-f", "--", ".turn-sessions.tgz"), cwd=root,
                          capture_output=True, text=True)
    if done.returncode != 0:
        raise CannotRun("control: `git add -f` failed in the copy (%s) - the "
                        "tracked-scratch claim cannot be provoked without git"
                        % done.stderr.strip()[:140])


def control_rename_session_tarball(root):
    """A carrier starts writing a scratch name the roster has never heard of."""
    _mutate_once(root, SCRATCH_SESS_NEEDLE,
                 'SESS="/workspace/.turn-sessions-v2.tgz"',
                 "the collect tarball path is not where the harness reads it")


def control_replace_add_all(root):
    """The host commit stops being a bare `git add -A`: the leg's subject is gone."""
    _mutate_once(root, "  git add -A", "  git add -u",
                 "the host commit is no longer the bare add -A this leg guards")


def control_no_git_repo(root):
    """No git to ask: the leg refuses rather than guessing gitignore semantics."""
    shutil.rmtree(os.path.join(root, ".git"), ignore_errors=True)


# (name, mutation, expected rc, expected text, build the green baseline first?)
CONTROLS = (
    ("green baseline is green", control_no_change, 0, "SESSION-LOOP CHECK OK", True),
    ("shipped tree needs no baseline builder - the session repair is in the "
     "carrier (10-ds applied it; the builder's three gap-fixers no-op on the "
     "shipped tree), so a re-opened gap must fail HERE even though the builder "
     "still greens the copies - the rc-1 RESTORE defect shape stays covered by "
     "the restore-copy-dropped control",
     control_no_change, 0, "SESSION-LOOP CHECK OK", False),
    ("second carrier heredoc", control_second_carrier, 1, "TWO carriers", True),
    ("heredoc back inline in the workflow", control_inline_carrier, 0,
     "SESSION-LOOP CHECK OK", True),
    ("restore copy dropped", control_drop_restore_copy, 1, "RESTORE", True),
    ("--no-session reintroduced", control_reintroduce_opt_out, 1, "NO-OPT-OUT", True),
    ("goose store dropped", control_drop_goose_store, 1, "GOOSE-STORE", True),
    ("restore mount dropped", control_drop_mount, 1, "MOUNT", True),
    ("collect block dropped", control_drop_collect, 2, "CANNOT RUN", True),
    ("verdict read path renamed", control_rename_review_scratch, 1, "REVIEW-CAPTURE", True),
    ("verdict token pattern drift", control_break_verdict_token, 1, "REVIEW-CAPTURE", True),
    ("workspace mount renamed", control_unmount_workspace, 1, "REVIEW-CAPTURE", True),
    ("carrier script missing", control_missing_carrier, 2, "CANNOT RUN", True),
    ("workflow file missing", control_missing_workflow, 2, "CANNOT RUN", False),
    ("scratch ignore line lost", control_unignore_scratch, 1, "SCRATCH", True),
    ("scratch reaches the index", control_scratch_reaches_the_index, 1,
     "TRACKED in this tree", True),
    ("unrostered scratch name", control_rename_session_tarball, 2, "unrostered", True),
    ("add -A replaced by -u", control_replace_add_all, 2, "git add -A", True),
    ("graded tree is not a repo", control_no_git_repo, 2, "CANNOT RUN", True),
)

# ELEVENTH harness law, on this harness's own roster: a deleted control is a
# refusal, never a shorter SELFTEST OK.
EXPECTED_CONTROLS = 19


def selftest(root):
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster is %d long, the pin says %d - a vanished "
                        "control must stop the run, not shorten it"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    script = os.path.join(root, "scripts", "chain_session_check.py")
    failures = []
    for name, mutation, expected_rc, expected_text, green in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="chain-session-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", "__pycache__",
                                                          ".pytest_cache", "dist", "build"))
            if green:
                build_green(target)
            mutation(target)
            proc = subprocess.run([sys.executable, script, "--root", target],
                                  capture_output=True, text=True)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-26s -> rc %d as expected (%s)"
                      % (name, proc.returncode, expected_text))
            else:
                failures.append("%s: expected rc %d containing %r, got rc %d: %s"
                                % (name, expected_rc, expected_text, proc.returncode,
                                   out.strip()[:300]))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        raise Red("\n".join(failures))
    print("SELFTEST OK — %d control(s), every leg proved able to fail" % len(CONTROLS))
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
