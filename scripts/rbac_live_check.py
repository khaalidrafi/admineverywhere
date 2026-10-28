#!/usr/bin/env python3
"""rbac_live_check.py — the live RBAC rejection path as ONE command.

WHY this exists (measured, not assumed). The board row FR-R007-LIVE
(agent-team/TODOS.org, "seeded non-superuser demo user / live rejection path") is
delivered, and its :DELIVERED: note lists the proof as a checklist whose two
hardest lines are prose about a rig somebody started by hand:

    [X] LIVE rig (migrate + seed_demo + runserver 127.0.0.1:8013, token auth per
          user): admin -> {...roles:["auditors","managers"]}; auditor -> {...
          roles:["auditors"]}; anon GET /api/me/ -> 401.

That was measured once, by a seat, on a port, at a sha. Nothing on the tree can
re-run it (DEVGUIDE *EIGHTH harness law*: a gate that lives as prose is a check
nobody can re-run), and the closest test — `app/src/lib/__tests__/rbac.test.ts:139`
feeds the client gate literals named `ADMIN_LIVE` / `AUDITOR_LIVE` that were
TYPED from a capture. A typed capture cannot see the server change shape: it stays
green over a renamed `roles` key, a superuser `auditor`, or a `POST …/me/` that
breaks the client's discovery rule, because no assertion connects the running
rig's bytes to the client's decision.

So this harness connects them, in one command, the way the twin harnesses connect
the two CSV/brand writers:

  BOOT        the real demo rig, in a subprocess, on a THROWAWAY sqlite DB in a
              temp dir (a seat re-running this must never inherit or trash a
              hand-started db.sqlite3). No venv needed — the same interpreter runs
              it, and a missing Django is CANNOT RUN with the install command,
              never a false red.
  DISCOVERY   GET the live /api/schema/ and apply the CLIENT's own evidence law to
              the document the server actually publishes: a claims path is real
              only if it carries `get` and NOT `post` (the same rule that binds
              `schema.mePath` in app/src/lib/openapi.ts, and the same
              exportPath/mePath law docs/rbac.md states). A guessed `/api/me/`
              would answer 200 here and prove nothing, so every URL below comes
              from this discovered path.
  CLAIMS      POST the discovered token route for BOTH seeded logins, then GET the
              discovered claims path with each, plus anonymously. The bodies are
              asserted EXACTLY (keys, flags, sorted roles), so a server-side shape
              change is a failure here rather than a silently stale literal in a
              fixture.
  REJECTION   the two LIVE bodies, written to disk by this process and read back,
              are fed through the REAL globbed action registry
              (`app/src/lib/actions/index.ts` → `actions` / `actionsFor`, which is
              what DataTable renders from) and the REAL `roleAllows()` under a
              per-run vitest probe spec — the `brand_twin_diff.py` trick: the spec
              lives inside app/src because that is vitest's include root, and is
              unlinked in the same breath, so no suite pollution. The claim is the
              DIFFERENCE: `Flag batch` survives for the caller who holds
              `managers` and disappears for the caller who does not, the ungated
              `Flag` survives for BOTH, and `claims = null` filters NOTHING (the
              degradation law). That is the row the board says only a human eye in
              a browser could close; it is now graded by the DOM-free equivalent —
              the shipped registry's own answer set against a live server's bytes.
              POPULATION is pinned first (the glob must carry exactly the two
              reference actions and exactly ONE role-gated among them), because a
              registry that went empty would answer "identical sets" and look like
              a passing gate that hides nothing (DEVGUIDE *ELEVENTH harness law*).
  AUDIT       the same authenticated caller writes one `order.flag` audit entry
              through the discovered action path, and reading it back through the
              discovered audit list path + `?object_id=` must name THAT actor. This
              is the "hiding is UX, never security" line made measurable: the
              endpoint is open to any authenticated caller, and what the server
              records about the caller is server-derived, not client-supplied.
  IDEMPOTENT  a second `seed_demo` must not drift the claims (rigs get re-seeded;
              a re-seed that adds a group turns the rejection case into an
              acceptance case with no test noticing).

Verdicts follow the house convention: 0 = OK, 1 = RED (a claim is false),
2 = CANNOT RUN (the harness cannot understand its own input — no rig, no node,
no vitest — never a false red for a tree it has not measured).

Controls run against copies, so the shipped tree is only read:
  cp -r . /tmp/x && ln -s $PWD/app/node_modules /tmp/x/app/node_modules
  python3 scripts/rbac_live_check.py --root /tmp/x

And the harness proves it can FAIL, with no hand-holding:
  python3 scripts/rbac_live_check.py --selftest

Deliberately NOT named `*_diff.py`: that glob IS the landing gate's twin roster
(`EXPECTED_TWINS` in scripts/landing_gate.py), and this grades ONE side's live
behaviour, not a pair of artifacts.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ADMIN_LOGIN = ("admin", "admin123")
AUDITOR_LOGIN = ("auditor", "audit123")

# The exact bodies docs/rbac.md's demo-user table promises. Keys are spelled as
# the WIRE spells them (is_staff / is_superuser / roles), not as the client's
# parsed RoleClaims — this leg grades the server, the parse is the next leg's job.
ADMIN_CLAIMS = {
    "username": "admin",
    "is_staff": True,
    "is_superuser": True,
    "roles": ["auditors", "managers"],
}
AUDITOR_CLAIMS = {
    "username": "auditor",
    "is_staff": False,
    "is_superuser": False,
    "roles": ["auditors"],
}

# The shipped drop-in registry's expected population: two reference actions, and
# exactly one of them carries `roles` (bulk_flag → ["managers"]). A third gated
# action is a legitimate future change; an EMPTY registry is not, and this pin is
# what tells the two apart. POPULATED_ACTIONS is the floor, GATED_IDS names who
# must be gated for the rejection leg to mean anything.
MIN_ACTIONS = 2
GATED_LABEL = "Flag batch"
UNGATED_LABEL = "Flag"

# The client half. Written into app/src/lib/__tests__/ and unlinked in the same
# breath (vitest's include root is src/, and node cannot load a .ts directly).
CLIENT_SPEC = r"""
import { readFileSync, writeFileSync } from "node:fs";
import { it } from "vitest";
import { actions, actionsFor } from "../actions/index";
import { parseClaims } from "../rbac";

const [inbox, outbox] = process.env.RBAC_LIVE_PATHS.split(",");
it("rbac live probe", () => {
  const raw = JSON.parse(readFileSync(inbox, "utf8"));
  // null claims = the graceful-degradation case the docs promise: no role source,
  // so the client applies NO policy at all. Hand-built here as null, never parsed.
  const parsed = (k: string) => (raw[k] === null ? null : parseClaims(raw[k]));
  const admin = parsed("admin");
  const auditor = parsed("auditor");
  const anon = parsed("anon");
  const labels = (claims: any) => ({
    bulk: actionsFor("orders", "bulk", actions, claims).map((a) => a.meta.label),
    record: actionsFor("orders", "record", actions, claims).map((a) => a.meta.label),
  });
  writeFileSync(
    outbox,
    JSON.stringify({
      population: {
        total: Object.keys(actions).length,
        ids: Object.keys(actions).sort(),
        gated: Object.values(actions)
          .filter((a) => (a.meta.roles?.length ?? 0) > 0)
          .map((a) => a.meta.label)
          .sort(),
      },
      admin: labels(admin),
      auditor: labels(auditor),
      noClaims: labels(anon),
    }),
  );
});
"""


class CannotRun(Exception):
    """The harness is not looking at a runnable rig — exit 2, never a red."""


class Problem(Exception):
    """A claim the tree made is false — exit 1."""


def repo(root, *parts):
    return os.path.join(root, *parts)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def http(url, data=None, token=None, method=None, timeout=15):
    """One live request. Returns (status, parsed-body-or-None). A 4xx is an ANSWER,
    not a crash — the anon-401 and the guard-400 legs both depend on reading it."""
    req = urllib.request.Request(url)
    if token:
        req.add_header("Authorization", f"Token {token}")
    body = None
    if data is not None:
        body = json.dumps(data).encode()
        req.add_header("Content-Type", "application/json")
    if method:
        req.get_method = lambda: method
    elif body is not None:
        req.get_method = lambda: "POST"
    try:
        with urllib.request.urlopen(req, body, timeout=timeout) as r:
            return r.status, _maybe_json(r.read().decode("utf-8", "replace"))
    except urllib.error.HTTPError as exc:
        return exc.code, _maybe_json(exc.read().decode("utf-8", "replace"))
    except OSError as exc:
        raise CannotRun(f"request to {url} failed: {exc}")


def _maybe_json(raw):
    try:
        return json.loads(raw)
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------- the rig
def rig_python(root):
    """The interpreter that can boot the rig. System python3 is fine when Django
    is importable; otherwise CANNOT RUN naming the fix, never a silent skip.
    A lane without setuptools cannot build the editable install (measured on the
    duty-review lane), so when the plain probe fails it retries once more with
    this checkout's ``plugin/src`` on PYTHONPATH — the same bridge
    ``demo-backend/core/devpaths.py`` gives ``manage.py`` children — and reports
    which one carried the import. The refusal still fires when the deps are
    genuinely absent: a preflight that never says no is not a preflight
    (DEVGUIDE *EIGHTH law*)."""
    exe = sys.executable or "python3"
    probe_src = "import django, rest_framework, drf_spectacular, admineverywhere"
    probe = subprocess.run([exe, "-c", probe_src], capture_output=True, text=True)
    if probe.returncode != 0:
        plugin_src = repo(root, "plugin", "src")
        retry = subprocess.run(
            [exe, "-c", probe_src], capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(plugin_src)},
        )
        if retry.returncode == 0:
            print("env        rig deps importable on %s — plugin from %s, "
                  "no editable install" % (exe, plugin_src))
            return exe
        raise CannotRun(
            "%s cannot import the rig's deps: %s\nFix: python3 -m pip install -e %s "
            "--no-deps" % (exe, (probe.stderr or "").strip().splitlines()[-1:], repo(root, "plugin"))
        )
    return exe


def boot_rig(root, workdir):
    """A settings shim that reuses the rig's OWN settings and only redirects the
    database into a temp dir: a seat re-running this must not inherit, migrate or
    trash a hand-started demo-backend/db.sqlite3."""
    demo = repo(root, "demo-backend")
    if not os.path.isfile(repo(demo, "manage.py")):
        raise CannotRun("demo-backend/manage.py is missing — there is no rig to boot")
    shim = os.path.join(workdir, "rbac_live_rig_settings.py")
    with open(shim, "w", encoding="utf-8") as fh:
        fh.write(
            "from core.settings import *  # noqa: F403\n"
            "from pathlib import Path\n"
            "import tempfile\n"
            "_TMP = Path(%r)\n"
            "DATABASES = {\"default\": {\"ENGINE\": \"django.db.backends.sqlite3\","
            " \"NAME\": _TMP / \"rbac_live.sqlite3\"}}\n"
            "ADMINEVERYWHERE_BRAND_DIR = str(_TMP / \"brand\")\n"
            % workdir
        )
    env = {
        **os.environ,
        "PYTHONPATH": os.pathsep.join([workdir, demo]),
        "DJANGO_SETTINGS_MODULE": "rbac_live_rig_settings",
    }
    return demo, env


def manage(exe, demo, env, *args, timeout=180):
    cmd = [exe, "manage.py", *args]
    try:
        p = subprocess.run(cmd, cwd=demo, env=env, capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise CannotRun("manage.py %s could not run: %s" % (" ".join(args), exc))
    return p


def need_ok(proc, what):
    if proc.returncode != 0:
        raise CannotRun(
            "%s failed (rc %d) — the rig is not bootable, so nothing below this line "
            "was measured: %s" % (what, proc.returncode, (proc.stderr or proc.stdout)[-400:])
        )


class Server:
    """The rig, over REAL HTTP — the row the board note claims by prose."""

    def __init__(self, exe, demo, env):
        self.port = free_port()
        self.base = f"http://127.0.0.1:{self.port}"
        self.env = env
        self.proc = subprocess.Popen(
            [exe, "manage.py", "runserver", f"127.0.0.1:{self.port}", "--noreload"],
            cwd=demo, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise CannotRun("runserver exited with %s before answering" % self.proc.returncode)
            try:
                code, _ = http(self.base + "/api/schema/", timeout=5)
                if code == 200:
                    return
            except CannotRun:
                pass
            time.sleep(0.5)
        self.stop()
        raise CannotRun("runserver never answered on %s within 60s" % self.base)

    def stop(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                self.proc.kill()


# ----------------------------------------------------------------- the client
def run_client_probe(root, inbox: Path, outbox: Path):
    app = repo(root, "app")
    if not os.path.isdir(repo(app, "node_modules", ".bin")):
        raise CannotRun(
            "app/node_modules is missing — the REJECTION leg runs the shipped registry "
            "under vitest. Fix: (cd app && npm install)"
        )
    spec = os.path.join(app, "src", "lib", "__tests__", "zzRbacLiveProbe.tmp.test.ts")
    if not os.path.isdir(os.path.dirname(spec)):
        raise CannotRun("app/src/lib/__tests__ is missing — the probe spec that runs the "
                        "shipped registry has no home, so the REJECTION leg cannot run")
    with open(spec, "w", encoding="utf-8") as fh:
        fh.write(CLIENT_SPEC)
    try:
        return subprocess.run(
            ["npx", "vitest", "run", "src/lib/__tests__/zzRbacLiveProbe.tmp.test.ts", "--maxWorkers=1"],
            cwd=app, capture_output=True, text=True,
            env={**os.environ, "RBAC_LIVE_PATHS": f"{inbox},{outbox}",
                 "NODE_OPTIONS": "--max-old-space-size=1024"},
            timeout=420,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        # A missing launcher is exit 2 (rig not runnable), never exit 1 — the same
        # guard brand_twin_diff.py carries.
        return subprocess.CompletedProcess(["npx"], 127, "", "cannot launch: %s" % (exc,))
    finally:
        if os.path.exists(spec):
            os.unlink(spec)


# ------------------------------------------------------------------- the legs
def find_me_path(doc):
    """The client's OWN discovery rule, applied to the live document: a claims path
    counts only with `get` and WITHOUT `post` (openapi.ts binds schema.mePath the
    same way — exportPath law). Returns None when the document carries no claims
    source at all, which is the degradation case, not a crash."""
    for path, ops in (doc.get("paths") or {}).items():
        if path.rstrip("/").endswith("/me"):
            if "get" in ops and "post" not in ops:
                return path
            raise Problem(
                "the live document advertises %s with a POST too, so the client refuses "
                "it as a claims source (a write at the claims path is not a claims "
                "source) — docs/rbac.md's read-only rule is broken at the router" % path
            )
    return None


def check(root):
    rows, problems = [], []
    exe = rig_python(root)
    workdir = tempfile.mkdtemp(prefix="rbac-live-")
    demo, env = boot_rig(root, workdir)
    server = None
    try:
        # ---- BOOT -----------------------------------------------------------------
        need_ok(manage(exe, demo, env, "migrate", "--no-input"), "manage.py migrate")
        seed1 = manage(exe, demo, env, "seed_demo")
        need_ok(seed1, "manage.py seed_demo")
        server = Server(exe, demo, env)
        rows.append(("BOOT", "rig on a throwaway DB, runserver answering at %s" % server.base))

        # ---- DISCOVERY ------------------------------------------------------------
        # drf-spectacular's default content negotiation answers YAML here, so ask the
        # document for JSON explicitly — the same shape the thin client normalizes.
        # The bare path stays as a fallback for a rig that renamed the format query.
        doc = None
        for qs in ("?format=json", "?format=openapi-json", ""):
            code, body = http(server.base + "/api/schema/" + qs)
            if code == 200 and isinstance(body, dict) and body.get("paths"):
                doc = body
                break
        if doc is None:
            raise CannotRun("GET /api/schema/ answered no JSON document (%s) — there is "
                            "nothing to discover paths from, so nothing below this line "
                            "was measured" % code)
        me_path = find_me_path(doc)
        if me_path is None:
            raise Problem(
                "the live document carries no GET-only …/me/ path, so the client would bind "
                "NO mePath and filter nothing — the claims source FR-R007 is built on is gone"
            )
        token_path = next((p for p in doc.get("paths", {}) if p.rstrip("/").endswith("/auth/token")), None)
        rows.append(("DISCOVERY", "claims path %s is GET-only in the LIVE document%s"
                     % (me_path, " (token route %s)" % token_path if token_path else "")))

        # ---- CLAIMS ---------------------------------------------------------------
        if not token_path:
            # No documented token route: this harness refuses to guess a URL the
            # document does not carry — same law as actionPath(). A missing route is
            # a CANNOT RUN (nothing was measured), never a silent /api/me/ probe.
            raise CannotRun(
                "the live document does not advertise the token route, so no caller can be "
                "authenticated by discovery; the rig's core/urls.py route is undocumented"
            )
        tokens = {}
        for label, (user, pw) in (("admin", ADMIN_LOGIN), ("auditor", AUDITOR_LOGIN)):
            code, body = http(server.base + token_path, {"username": user, "password": pw})
            if code != 200 or not isinstance(body, dict) or not body.get("token"):
                raise Problem("POST %s for %s answered %s / %r — the seeded login the docs "
                              "publish does not authenticate" % (token_path, label, code, body))
            tokens[label] = body["token"]
        admin_tok, auditor_tok = tokens["admin"], tokens["auditor"]

        code, admin_body = http(server.base + me_path, token=admin_tok)
        if (code, admin_body) != (200, ADMIN_CLAIMS):
            problems.append("CLAIMS admin: wanted (200, %s), got (%s, %s)"
                            % (ADMIN_CLAIMS, code, json.dumps(admin_body, sort_keys=True)))
        code, auditor_body = http(server.base + me_path, token=auditor_tok)
        if (code, auditor_body) != (200, AUDITOR_CLAIMS):
            problems.append("CLAIMS auditor: wanted (200, %s), got (%s, %s) — the rejection "
                            "case is exactly a NON-superuser holding one role; a superuser "
                            "here short-circuits roleAllows() and the rig has no hidden button "
                            "to show" % (AUDITOR_CLAIMS, code, json.dumps(auditor_body, sort_keys=True)))
        code, _ = http(server.base + me_path)
        if code != 401:
            problems.append("CLAIMS anon: GET %s answered %s, the docs promise 401 (the claims "
                            "path is auth'd like the rest of the API)" % (me_path, code))
        rows.append(("CLAIMS", "admin %s / auditor %s / anon %s, from the LIVE %s"
                     % (admin_body, auditor_body, code, me_path)))

        # ---- REJECTION (client, on the live bytes) --------------------------------
        inbox = Path(workdir) / "claims.json"
        outbox = Path(workdir) / "answer.json"
        # The LIVE bodies, on disk, read back by the client — not a typed fixture.
        inbox.write_text(json.dumps({"admin": admin_body, "auditor": auditor_body, "anon": None}),
                         encoding="utf-8")
        p = run_client_probe(root, inbox, outbox)
        if p.returncode != 0 or not outbox.exists():
            raise CannotRun(
                "the client probe could not run (rc %d) — the REJECTION leg was NOT measured:\n%s"
                % (p.returncode, (p.stdout or "")[-800:] + (p.stderr or "")[-800:])
            )
        ans = json.loads(outbox.read_text(encoding="utf-8"))
        pop = ans["population"]
        # POPULATION first: an empty registry would answer "the two sets match" and
        # look like a passing gate (ELEVENTH law — a comparison cannot see its own coverage).
        if pop["total"] < MIN_ACTIONS:
            problems.append("POPULATION: the shipped action glob carries %d action(s) (%s); the "
                            "rejection leg needs the %d reference actions on disk, or 'identical "
                            "sets' is an empty-registry artifact"
                            % (pop["total"], pop["ids"], MIN_ACTIONS))
        elif GATED_LABEL not in pop["gated"]:
            problems.append("POPULATION: no globbed action declares roles (gated = %s) — nothing "
                            "here can be hidden, so the claims below cannot differ" % pop["gated"])
        else:
            admin_set, auditor_set = ans["admin"]["bulk"], ans["auditor"]["bulk"]
            if GATED_LABEL not in admin_set:
                problems.append("REJECTION: %r is missing for the caller who HOLDS the role (%s) — "
                                "a gate that hides from everyone is not a role gate"
                                % (GATED_LABEL, admin_set))
            if GATED_LABEL in auditor_set:
                problems.append("REJECTION: %r still shows for the caller holding only %s (%s) — the "
                                "row FR-R007-LIVE exists to prove vanish, and it did not"
                                % (GATED_LABEL, AUDITOR_CLAIMS["roles"], auditor_set))
            if UNGATED_LABEL not in ans["auditor"]["record"]:
                problems.append("REJECTION: the UNGATED %r vanished for auditor (%s) — a role gate "
                                "hides gated surfaces, never the ungated ones"
                                % (UNGATED_LABEL, ans["auditor"]["record"]))
            if ans["noClaims"] != ans["admin"]:
                problems.append("DEGRADATION: with claims=null the client filtered (%s vs admin %s) — "
                                "no role source must mean NO policy at all (docs/rbac.md)"
                                % (ans["noClaims"], ans["admin"]))
        rows.append(("REJECTION", "bulk for admin %s vs auditor %s / record %s / ungated-with-null-claims %s"
                     % (ans["admin"]["bulk"], ans["auditor"]["bulk"], ans["auditor"]["record"],
                        ans["noClaims"]["bulk"])))

        # ---- AUDIT (the same caller, server-derived) ------------------------------
        audit_path = next((pp for pp in doc.get("paths", {}) if pp.rstrip("/").endswith("/audit")), None)
        order_path = next((pp for pp in doc.get("paths", {}) if pp.rstrip("/").endswith("/orders")), None)
        if not audit_path or not order_path:
            raise CannotRun("the live document carries no audit or orders list path (%s/%s) — "
                            "the AUDIT leg discovers its URLs and refuses to guess them"
                            % (audit_path, order_path))
        code, page = http(server.base + order_path.rstrip("/") + "/?page_size=1", token=auditor_tok)
        results = (page or {}).get("results") or []
        if code != 200 or not results:
            raise CannotRun("GET %s answered %s / %d row(s) — no record to act on"
                            % (order_path, code, len(results)))
        oid = results[0]["id"]
        oid_path = "%s/%s" % (order_path.strip("/"), oid)
        code, entry = http("%s/%s/flag/" % (server.base, oid_path),
                           {"reason": "rbac_live_check probe"}, token=auditor_tok)
        if code not in (200, 201):
            problems.append("AUDIT: POST flag as the SEEDED NON-SUPERUSER answered %s (%s) — the "
                            "reference action is deliberately open to any authenticated caller so "
                            "the rig keeps exercising the trail; hiding is UX, not security"
                            % (code, entry))
        else:
            code, trail = http("%s%s?object_type=order&object_id=%s" % (server.base, audit_path, oid),
                               token=auditor_tok)
            entries = (trail or {}).get("results") or []
            actors = [e.get("actor_username") or e.get("actor") for e in entries]
            if code != 200 or "auditor" not in json.dumps(actors):
                problems.append("AUDIT: the trail for order %s (HTTP %s, %d entr%s) does not name the "
                                "caller `auditor` — the actor must be SERVER-derived, and this is "
                                "the one live proof that a non-superuser can act and is recorded"
                                % (oid, code, len(entries), "y" if len(entries) == 1 else "ies"))
            rows.append(("AUDIT", "order %s flagged by auditor over HTTP, trail %s -> %d entr%s"
                         % (oid, audit_path, len(entries), "y" if len(entries) == 1 else "ies")))

        # ---- IDEMPOTENT -----------------------------------------------------------
        need_ok(manage(exe, demo, env, "seed_demo"), "second manage.py seed_demo")
        _, again = http(server.base + me_path, token=auditor_tok)
        if again != AUDITOR_CLAIMS:
            problems.append("IDEMPOTENT: a second seed_demo drifted the claims to %s — the rig "
                            "re-seeds, and drift turns the rejection case into an acceptance case "
                            "with no test noticing" % json.dumps(again, sort_keys=True))
        else:
            rows.append(("IDEMPOTENT", "claims identical after a re-seed"))

        # ---- PROSE ------------------------------------------------------------------
        # The docs promise a table; the table must still say what the wire answers.
        doc_path = repo(root, "docs", "rbac.md")
        if os.path.isfile(doc_path):
            text = open(doc_path, encoding="utf-8").read()
            for promise in ("audit123", "`auditors` **only**", GATED_LABEL):
                if promise not in text:
                    problems.append("PROSE: docs/rbac.md no longer carries %r, which this harness "
                                    "reads as the published contract for the live rig" % promise)
            rows.append(("PROSE", "docs/rbac.md still publishes the seeded login, the single role "
                                  "and the gated label the live registry just answered"))
    finally:
        if server:
            server.stop()
        shutil.rmtree(workdir, ignore_errors=True)
    return rows, problems


# ------------------------------------------------------------------ selftest
# A check that cannot FAIL is not a check (DEVGUIDE *ELEVENTH harness law*,
# applied to the harness itself). Every control mutates a COPY of the tree and
# asserts the leg that owns the mutated fact goes RED — or CANNOT RUN for a
# missing input. The shipped tree is never written to.
SEED_REL = os.path.join("demo-backend", "shop", "management", "commands", "seed_demo.py")
VIEWS_REL = os.path.join("demo-backend", "shop", "views.py")
ME_VIEWS_REL = os.path.join("demo-backend", "core", "views.py")
URLS_REL = os.path.join("demo-backend", "core", "urls.py")
BULK_REL = os.path.join("app", "src", "actions", "bulk_flag.ts")
RBAC_REL = os.path.join("app", "src", "lib", "rbac.ts")
DOC_REL = os.path.join("docs", "rbac.md")


def _read(root, rel):
    with open(repo(root, rel), encoding="utf-8") as fh:
        return fh.read()


def _write(root, rel, text):
    with open(repo(root, rel), "w", encoding="utf-8") as fh:
        fh.write(text)


def _replace_once(root, rel, old, new):
    text = _read(root, rel)
    if old not in text:
        raise CannotRun("control: %r is not in %s — the control cannot mutate what the "
                        "tree no longer holds, so it would prove nothing" % (old, rel))
    _write(root, rel, text.replace(old, new, 1))


def control_auditor_superuser(root):
    _replace_once(root, SEED_REL, 'username="auditor", defaults={"email": "auditor@example.com"}',
                  'username="auditor", is_superuser=True,\n            defaults={"email": "auditor@example.com"}')


def control_auditor_loses_group(root):
    _replace_once(root, SEED_REL, 'auditor.groups.set([groups["auditors"]])',
                  'auditor.groups.set([])')


def control_drift_on_reseed(root):
    # fires ONLY on the second seed: the claims leg reads green, the re-seed is what
    # moves the groups — that is the failure the IDEMPOTENT leg exists to catch
    _replace_once(root, SEED_REL, 'auditor.groups.set([groups["auditors"]])',
                  'auditor.groups.set([groups["auditors"]] if created else list(groups.values()))')


def control_me_accepts_post(root):
    _replace_once(root, ME_VIEWS_REL, "class MeView(APIView):",
                  'class MeView(APIView):\n\n    def post(self, request):  # control: a write at '
                  'the claims path\n        return Response({})')


def control_gate_opened(root):
    # the client-side half: roleAllows answers yes to everything, so no surface can
    # vanish — the REJECTION leg must see the two callers answer the SAME set
    _replace_once(root, RBAC_REL, "  if (!required || required.length === 0) return true;",
                  "  if (!required || required.length === 0) return true;\n  return true; // control")


def control_roles_dropped(root):
    _replace_once(root, BULK_REL, '  roles: ["managers"],', "")


def control_action_vanished(root):
    os.remove(repo(root, BULK_REL))


def control_actor_client_supplied(root):
    # the record-flag write stops deriving the actor from the request: the trail
    # still answers 200, and only the AUDIT leg can see that it no longer says WHO
    _replace_once(root, VIEWS_REL, "            actor=_request_actor(request),\n"
                                  '            action="order.flag",',
                  "            actor=None,\n"
                                  '            action="order.flag",')


def control_doc_stale(root):
    _replace_once(root, DOC_REL, "audit123", "auditXXXX")


def control_no_rig(root):
    os.remove(repo(root, "demo-backend", "manage.py"))


def control_no_node(root):
    nm = repo(root, "app", "node_modules")
    if os.path.islink(nm):
        os.unlink(nm)
    elif os.path.isdir(nm):
        shutil.rmtree(nm)


CONTROLS = (
    ("CLAIMS: the seeded auditor is a superuser", control_auditor_superuser, 1, "rejection case"),
    ("CLAIMS: the auditor holds no group", control_auditor_loses_group, 1, "CLAIMS auditor"),
    ("IDEMPOTENT: a re-seed drifts the groups", control_drift_on_reseed, 1, "IDEMPOTENT"),
    ("DISCOVERY: POST added at the claims path", control_me_accepts_post, 1, "with a POST too"),
    ("REJECTION: roleAllows() allows everything", control_gate_opened, 1, "prove vanish"),
    ("POPULATION: the gate's roles line is gone", control_roles_dropped, 1, "declares roles"),
    ("POPULATION: a reference action vanished", control_action_vanished, 1, "POPULATION"),
    ("AUDIT: the actor is client-supplied", control_actor_client_supplied, 1, "SERVER-derived"),
    ("PROSE: docs/rbac.md no longer publishes the login", control_doc_stale, 1, "PROSE"),
    ("BOOT: there is no rig to start", control_no_rig, 2, "CANNOT RUN"),
    ("REJECTION: vitest cannot run", control_no_node, 2, "CANNOT RUN"),
)

# The roster's own population, pinned (ELEVENTH harness law, applied to its own
# author): a control deleted from the tuple above would print a smaller N under
# `SELFTEST OK` while AGENTS.md keeps publishing the old one, so a vanished leg
# has to be CANNOT RUN, not a shorter green run.
EXPECTED_CONTROLS = 11


def selftest(root):
    """Prove each leg can fire, against copies. The copy keeps the tree but relinks
    app/node_modules, because the REJECTION leg runs the shipped registry under
    vitest and a copy without node_modules could only ever answer CANNOT RUN."""
    if len(CONTROLS) != EXPECTED_CONTROLS:
        raise CannotRun("the control roster holds %d entries, the pin says %d — a control "
                        "vanished (or was added without the pin), so `SELFTEST OK` would no "
                        "longer mean every leg was run"
                        % (len(CONTROLS), EXPECTED_CONTROLS))
    script = repo(root, "scripts", "rbac_live_check.py")
    real_nm = repo(root, "app", "node_modules")
    failures = []
    for name, mutation, expected_rc, expected_text in CONTROLS:
        tmp = tempfile.mkdtemp(prefix="rbac-live-control-")
        target = os.path.join(tmp, "tree")
        try:
            shutil.copytree(root, target, symlinks=True,
                            ignore=shutil.ignore_patterns("node_modules", ".git", "__pycache__",
                                                           ".pytest_cache", "db.sqlite3",
                                                           "dist", "build"))
            if os.path.isdir(real_nm):
                os.symlink(real_nm, os.path.join(target, "app", "node_modules"))
            try:
                mutation(target)
            except CannotRun as exc:
                failures.append("%s: the control itself could not run (%s)" % (name, exc))
                continue
            proc = subprocess.run([sys.executable, script, "--root", target],
                                  capture_output=True, text=True, timeout=1800)
            out = proc.stdout + proc.stderr
            if proc.returncode == expected_rc and expected_text in out:
                print("  control %-46s -> rc %d as expected (%s)"
                      % (name, proc.returncode, expected_text))
            else:
                failures.append("%s: expected rc %d containing %r, got rc %d: %s"
                                % (name, expected_rc, expected_text, proc.returncode,
                                   out.strip()[-400:]))
        except (OSError, subprocess.TimeoutExpired) as exc:
            failures.append("%s: could not run (%s)" % (name, exc))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    if failures:
        raise CannotRun("SELFTEST RED — %d control(s) did not fire as expected: %s"
                        % (len(failures), "; ".join(failures)))
    print("SELFTEST OK — %d control(s), every leg proved able to fail" % len(CONTROLS))
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Grade the FR-R007-LIVE claims + rejection path "
                                              "against the LIVE rig, in one command.")
    ap.add_argument("--root", default=".", help="the tree to grade (default: this repo)")
    ap.add_argument("--selftest", action="store_true",
                    help="prove every leg can fail, against copies")
    opts = ap.parse_args(argv)
    root = os.path.abspath(opts.root)
    if opts.selftest:
        return selftest(root)
    try:
        rows, problems = check(root)
    except Problem as exc:
        print("RBAC LIVE CHECK RED — %s" % exc)
        return 1
    print("RBAC LIVE CHECK — %d leg(s)" % len(rows))
    for name, detail in rows:
        print("  %-11s %s" % (name, detail))
    if problems:
        print("\nRED — %d claim(s) the tree made are false:" % len(problems))
        for p in problems:
            print("  * %s" % p)
        return 1
    print("RBAC LIVE CHECK OK — the live claims, the rejection through the shipped registry, "
          "the server-derived actor and the re-seed all answer as published")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except CannotRun as exc:
        # A rig this harness could not boot is NOT a red tree: it is an honest
        # refusal, so a seat never reads an unrunnable environment as a defect.
        print("CANNOT RUN — %s" % exc)
        sys.exit(2)
