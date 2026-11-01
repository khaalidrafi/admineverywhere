"""CLI renderer — emits the standalone terminal admin client as one string.

The generated artifact is a single-file, stdlib-only Python CLI. Design
rules mirror the other generators (mcp_gen, emacs_gen): everything is
derived from the OpenAPI schema at build time, so the CLI can never
drift from the API — the roster of resources, the custom actions
(transition, flag, history, reports, export...), and the sign-in path
are all baked from the schema. The order machine itself is NEVER
re-encoded here: transition steps live in the API and the CLI just
delivers what the operator asks for.

User-facing wording follows the copy law: plain store language ("sign
in", "orders", "products", "spreadsheet"), no framework jargon.
"""

from __future__ import annotations

import json

# Methods in the fixed, human order used for method selection.
_METHOD_ORDER = ("GET", "POST", "PUT", "PATCH", "DELETE")

# Path heads that never become actions: the schema document (not a
# store thing) and auth (the dedicated `login`/`whoami` commands cover
# it; raw credential endpoints must not invite token handling by hand).
_NON_ACTION_HEADS = frozenset({"schema", "auth"})


def _clean(name: str) -> str:
    """Strip a file extension from a path segment ("orders.csv" -> "orders")."""
    return name.rsplit(".", 1)[0] if "." in name else name


def _is_placeholder(segment: str) -> bool:
    return segment.startswith("{") and segment.endswith("}")


def derive_actions(paths: dict, prefix: str = "/api/",
                   reserved: set | None = None) -> list[dict]:
    """Derive custom action commands from the OpenAPI ``paths`` document.

    A path becomes an action when it is under ``prefix``, is not one of
    the reserved resource paths (the paired collection/detail paths the
    resource commands already cover), and its head is not a reserved
    head. Nested literal segments join the action name
    (``admin/reports/sales`` -> group ``admin``, action ``reports_sales``);
    ``{placeholder}`` segments become positional parameters in path
    order. Sorted by (group, action) for deterministic builds.
    """
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    if not prefix.endswith("/"):
        prefix += "/"
    reserved = reserved or set()
    actions = {}
    for path, ops in (paths or {}).items():
        if not path.startswith(prefix) or path in reserved:
            continue
        rest = path[len(prefix):].rstrip("/")
        if not rest:
            continue
        segs = rest.split("/")
        head = segs[0]
        if head in _NON_ACTION_HEADS:
            continue
        params = [s[1:-1] for s in segs if _is_placeholder(s)]
        literals = [s for s in segs if not _is_placeholder(s)]
        if len(segs) == 1:
            group, action = head, head
        else:
            if _is_placeholder(segs[-1]):
                continue                    # path ends in a param: not a call
            group = head
            action = "_".join(_clean(s) for s in literals[1:]) or head
        methods = [m for m in _METHOD_ORDER
                   if m in {k.upper() for k in (ops or {})}]
        if methods:
            actions[(group, action, path)] = {
                "group": group,
                "action": action,
                "path": path,
                "methods": methods,
                "params": params,
            }
    return [actions[k] for k in sorted(actions)]


def _bake_list(items: list) -> str:
    """Embed the roster as JSON that json.loads() re-reads at runtime, in
    the exact default-dumps form so single-item drift pins hold
    byte-for-byte."""
    return json.dumps(items, sort_keys=True)


_TEMPLATE = '''#!/usr/bin/env python3
"""__CLI_NAME__ __VERSION__ — run the store from your terminal.

Generated from the store's own API catalog, so every command here
matches what the store really offers. Regenerate any time the store
grows.

Quick start:
  __CLI_NAME__ login                     sign in once; it is remembered
  __CLI_NAME__ orders list               see the orders on the books
  __CLI_NAME__ orders transition ID --data '{"target": "PACKED"}'
                                         move an order to its next step
  __CLI_NAME__ products list             see what you sell
  __CLI_NAME__ admin reports_sales       sales report
  __CLI_NAME__ admin export_orders --out orders.csv
                                         save the orders as a spreadsheet

Every command also takes --json for the raw reply.
"""
import argparse
import getpass
import json
import os
import pathlib
import sys
import urllib.error
import urllib.parse
import urllib.request

API_HOST = "__API_HOST__"
CLI_NAME = "__CLI_NAME__"
VERSION = "__VERSION__"
TOKEN_ENV = "__TOKEN_ENV__"
AUTH_PATH = "__AUTH_PATH__"

# Baked from the API catalog at build time (regenerate, never hand-edit).
RESOURCES = json.loads(r"""_RESOURCES_JSON_""")
ACTIONS = json.loads(r"""_ACTIONS_JSON_""")

CONFIG_DIR = pathlib.Path(os.environ.get("XDG_CONFIG_HOME") or
                          pathlib.Path.home() / ".config") / CLI_NAME
TOKEN_FILE = CONFIG_DIR / "token.json"


# --------------------------------------------------------------- plumbing ---

def _token():
    tok = os.environ.get(TOKEN_ENV, "").strip()
    if tok:
        return tok
    try:
        return json.loads(TOKEN_FILE.read_text()).get("token", "").strip()
    except (OSError, ValueError):
        return ""


def _request(method, path, data=None, token="", query=None):
    url = API_HOST.rstrip("/") + path
    if query:
        url += "?" + urllib.parse.urlencode(query)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    headers = {"Accept": "application/json", "User-Agent": CLI_NAME + "/" + VERSION}
    if token:
        headers["Authorization"] = "Token " + token
    if body:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "replace")[:500]
        friendly = {400: "the store said 400 — check what you sent",
                    401: "not signed in (or the sign-in expired) — run: "
                         + CLI_NAME + " login",
                    403: "the store said 403 — your account is not allowed "
                         "to do that",
                    404: "the store said 404 — nothing lives at that address",
                    429: "the store said 429 — too many requests, wait a bit"}
        sys.stderr.write(CLI_NAME + ": " + friendly.get(
            e.code, "the store said " + str(e.code)) + "\\n")
        if detail:
            sys.stderr.write(detail + "\\n")
        raise SystemExit(1)
    except urllib.error.URLError as e:
        sys.stderr.write(CLI_NAME + ": can't reach the store at " + API_HOST
                         + " — check your connection (" + str(e.reason) + ")\\n")
        raise SystemExit(1)
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except ValueError:
        return raw


def _rows(payload):
    """Accept both a plain list and a paginated {results: [...]} reply."""
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        return payload["results"]
    if isinstance(payload, list):
        return payload
    return None


def _render_table(rows):
    if not rows:
        print("nothing to show")
        return
    keys = []
    for r in rows:
        if isinstance(r, dict):
            for k in r:
                if k not in keys:
                    keys.append(k)
    if not keys:
        for r in rows:
            print(r)
        return
    cells = [[("" if r.get(k) is None else str(r.get(k))) for k in keys]
             for r in rows if isinstance(r, dict)]
    widths = [min(max([len(k)] + [len(c[i]) for c in cells]), 60)
              for i, k in enumerate(keys)]
    print("  ".join(k.ljust(widths[i]) for i, k in enumerate(keys)))
    print("  ".join("-" * w for w in widths))
    for c in cells:
        print("  ".join(v[:widths[i]].ljust(widths[i])
                        for i, v in enumerate(c)))


def _show(payload, as_json):
    if as_json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return
    rows = _rows(payload)
    if rows is None:
        if isinstance(payload, dict):
            width = max((len(k) for k in payload), default=0)
            for k in payload:
                print(str(k).ljust(width) + "  "
                      + json.dumps(payload[k], sort_keys=True))
        else:
            print(payload)
        return
    _render_table(rows)


def _data_arg(value):
    if value is None:
        return None
    try:
        return json.loads(value)
    except ValueError:
        sys.stderr.write(CLI_NAME + ": --data must be valid JSON\\n")
        raise SystemExit(2)


def _fill(path, params, values):
    for pname, pval in zip(params, values):
        path = path.replace("{" + pname + "}", str(pval))
    return path


# ---------------------------------------------------------------- commands ---

def cmd_login(ns):
    data = {"username": ns.username or input("Store account name: ").strip()}
    data["password"] = getpass.getpass("Password: ")
    reply = _request("POST", AUTH_PATH, data=data)
    token = ""
    if isinstance(reply, dict):
        for k in ("token", "key", "access", "auth_token"):
            if reply.get(k):
                token = str(reply[k])
                break
    if not token:
        sys.stderr.write(CLI_NAME + ": sign-in failed — the store did not "
                         "return a token. Check the account name and "
                         "password.\\n")
        raise SystemExit(1)
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(
        {"api_host": API_HOST, "token": token, "username": data["username"]}))
    TOKEN_FILE.chmod(0o600)
    print("Signed in as " + data["username"] + " — saved to " + str(TOKEN_FILE))


def cmd_logout(ns):
    try:
        TOKEN_FILE.unlink()
        print("Signed out.")
    except OSError:
        print("You were not signed in.")


def cmd_whoami(ns):
    _show(_request("GET", "/api/me/", token=_token()), ns.json)


def _run_resource(ns):
    name, spec = ns._resource
    token = _token()
    if ns._op == "list":
        payload = _request("GET", spec["list_path"], token=token,
                           query={"page": ns.page} if ns.page else None)
        if ns.all:
            rows = _rows(payload) or []
            page = 2
            while rows:
                more = _request("GET", spec["list_path"], token=token,
                                query={"page": page})
                batch = _rows(more)
                if not batch:
                    break
                rows.extend(batch)
                page += 1
            _show(rows, ns.json)
        else:
            _show(payload, ns.json)
    elif ns._op == "get":
        _show(_request("GET", _fill(spec["detail_path"], ["id", "name"],
                                       [ns.id, ns.id]), token=token), ns.json)
    elif ns._op == "create":
        _show(_request("POST", spec["list_path"], data=_data_arg(ns.data),
                       token=token), ns.json)
    elif ns._op == "update":
        _show(_request("PATCH", _fill(spec["detail_path"], ["id", "name"],
                                      [ns.id, ns.id]),
                       data=_data_arg(ns.data), token=token), ns.json)
    elif ns._op == "delete":
        _request("DELETE", _fill(spec["detail_path"], ["id", "name"],
                                 [ns.id, ns.id]), token=token)
        print("Deleted.")
    else:
        sys.stderr.write(CLI_NAME + ": pick what to do — " +
                         ", ".join(["list", "get", "create", "update",
                                    "delete"]) + "\\n")
        raise SystemExit(2)


def _run_action(ns):
    data = _data_arg(getattr(ns, "data", None))
    method = getattr(ns, "_method", None) or ns._methods[0]
    if data is not None and method == "GET":
        method = next((m for m in ("POST", "PUT", "PATCH")
                       if m in ns._methods), method)
    _show(_request(method, _fill(ns._path, ns._params, ns._params_values),
                   data=data, token=_token()), ns.json)


def build_parser():
    ap = argparse.ArgumentParser(
        prog=CLI_NAME,
        description="Run the " + API_HOST + " store from your terminal.")
    ap.add_argument("--version", action="version",
                    version=CLI_NAME + " " + VERSION)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--json", action="store_true",
                        help="print the raw reply instead of a table")
    sub = ap.add_subparsers(dest="command")

    lp = sub.add_parser("login", parents=[common],
                        help="sign in once; the store remembers you")
    lp.add_argument("username", nargs="?", default=None,
                    help="your store account name (it asks if you skip this)")
    lp.set_defaults(_func=cmd_login)
    sub.add_parser("logout", parents=[common],
                   help="sign out and forget the token"
                   ).set_defaults(_func=cmd_logout)
    sub.add_parser("whoami", parents=[common],
                   help="who is signed in right now"
                   ).set_defaults(_func=cmd_whoami)

    # resources first — action groups with the same name reuse them
    resource_ops = {}
    for spec in RESOURCES:
        p = sub.add_parser(spec["name"], parents=[common],
                           help="your " + spec["name"])
        p.set_defaults(_resource=(spec["name"], spec))
        resource_ops[spec["name"]] = p.add_subparsers(dest="_op")
        l = resource_ops[spec["name"]].add_parser(
            "list", parents=[common], help="show the " + spec["name"])
        l.add_argument("--page", type=int, default=None,
                       help="page number, when there is more than one screen")
        l.add_argument("--all", action="store_true",
                       help="keep fetching until every page is shown")
        if spec.get("retrieve"):
            g = resource_ops[spec["name"]].add_parser(
                "get", parents=[common], help="show one in full")
            g.add_argument("id")
        if spec.get("create"):
            c = resource_ops[spec["name"]].add_parser(
                "create", parents=[common], help="add a new one")
            c.add_argument("--data", required=True,
                           help='the new record, e.g. \\'{"name": "…"}\\'')
        if spec.get("update"):
            u = resource_ops[spec["name"]].add_parser(
                "update", parents=[common], help="change one")
            u.add_argument("id")
            u.add_argument("--data", required=True,
                           help='the fields to change, e.g. \\'{"price": 199}\\'')
        if spec.get("destroy"):
            d = resource_ops[spec["name"]].add_parser(
                "delete", parents=[common], help="remove one")
            d.add_argument("id")

    group_ops = {}
    for act in ACTIONS:
        g = act["group"]
        if g not in resource_ops and g not in group_ops:
            gp = sub.add_parser(g, parents=[common], help="your " + g)
            group_ops[g] = gp.add_subparsers(dest="_gop")
        ops = resource_ops.get(g) or group_ops[g]
        sp = ops.add_parser(act["action"], parents=[common],
                            help=act["action"].replace("_", " "))
        for pname in act["params"]:
            sp.add_argument(pname)
        if any(m != "GET" for m in act["methods"]):
            sp.add_argument("--data", default=None,
                            help='what to send, e.g. \\'{"target": "PACKED"}\\'')
        if len(act["methods"]) > 1:
            sp.add_argument("--method", default=None, choices=act["methods"])
        sp.set_defaults(_path=act["path"], _methods=act["methods"],
                        _method=act["methods"][0], _params=act["params"],
                        _func=_run_action)
    return ap


def main(argv=None):
    ap = build_parser()
    ns = ap.parse_args(argv)
    if getattr(ns, "_func", None) is not None:
        ns._params_values = [getattr(ns, p, None) for p in ns._params]
        return ns._func(ns) or 0
    if getattr(ns, "_resource", None) is not None:
        return _run_resource(ns) or 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.stderr.write("\\n")
        sys.exit(130)
'''


def render_cli(resources: list, actions: list, api_host: str, cli_name: str,
               token_env: str, auth_path: str, version: str) -> str:
    """Render the standalone CLI for the given schema-derived roster."""
    text = _TEMPLATE
    for placeholder, value in (
            ("__CLI_NAME__", cli_name),
            ("__VERSION__", version),
            ("__API_HOST__", api_host),
            ("__TOKEN_ENV__", token_env),
            ("__AUTH_PATH__", auth_path),
            ("_RESOURCES_JSON_", _bake_list(resources)),
            ("_ACTIONS_JSON_", _bake_list(actions)),
    ):
        text = text.replace(placeholder, value)
    return text
