"""Pure OpenAPI -> resource derivation, shared by the MCP and Emacs builders.

No Django imports in this module: everything here is a pure function over
an OpenAPI ``paths`` document, so the generators (and their tests) run
without a project or a live server.

Shape produced by drf-spectacular for a DRF router::

    "/api/products/":      {"get": ..., "post": ...},          # collection
    "/api/products/{id}/": {"get": ..., "patch": ..., ...},    # detail

``derive_resources`` pairs those two paths into one resource spec; the
MCP builder turns the spec into JSON-Schema tool definitions, the Emacs
builder turns it into interactive Org commands.
"""

from __future__ import annotations

import re

# Path parameter written by DRF's default lookup_field ("id" here); any
# single-segment "{...}" is accepted so custom lookup fields still pair.
_DETAIL_PARAM_RE = re.compile(r"^\{[^/]+\}$")

# The OpenAPI document endpoint describes the API, it is not a resource —
# exposing "schema_list" as an admin tool would be noise.
_NON_RESOURCE_SEGMENTS = frozenset({"schema"})


def derive_resources(paths: dict, prefix: str = "/api/") -> list[dict]:
    """Pair OpenAPI collection/detail paths into resource specs.

    Returns a list sorted by resource name; every spec has the fixed keys
    (name, list_path, detail_path, list, create, retrieve, update, destroy)
    so both generators can rely on one shape.
    """
    if not prefix.startswith("/"):
        prefix = "/" + prefix
    if not prefix.endswith("/"):
        prefix += "/"
    collections: dict[str, dict] = {}
    details: dict[str, str] = {}
    for path, ops in paths.items():
        if not path.startswith(prefix) or not path.endswith("/"):
            continue
        rest = path[len(prefix):-1]              # "products" | "products/{id}"
        segments = rest.split("/")
        if len(segments) == 1 and segments[0] and segments[0] not in _NON_RESOURCE_SEGMENTS:
            collections[segments[0]] = ops or {}
        elif len(segments) == 2 and _DETAIL_PARAM_RE.match(segments[1]):
            details[segments[0]] = path
    resources = []
    for name in sorted(collections):
        col_ops = collections[name]
        detail_path = details.get(name)          # None -> collection-only viewset
        det_ops = paths.get(detail_path, {}) if detail_path else {}
        resources.append({
            "name": name,
            "list_path": prefix + name + "/",
            "detail_path": detail_path,
            "list": "get" in col_ops,
            "create": "post" in col_ops,
            "retrieve": "get" in det_ops,
            # PUT or PATCH both mean "edit this record" to an admin agent.
            "update": "put" in det_ops or "patch" in det_ops,
            "destroy": "delete" in det_ops,
        })
    return resources


def _tool(name: str, description: str, properties: dict, required: list) -> dict:
    """One MCP tool definition (JSON-Schema input)."""
    return {
        "name": name,
        "description": description,
        "inputSchema": {"type": "object", "properties": properties,
                        "required": required},
    }


def build_tools(resources: list[dict]) -> list[dict]:
    """Turn resource specs into MCP tool definitions.

    Tool-per-action (not one mega-tool) keeps each agent call small and
    lets a client allow/deny actions individually. Page/page_size on list
    tools keep large collections manageable; create/update take one
    ``data`` object — field validation stays server-side in DRF, where it
    already exists, instead of being half-copied into the schema here.
    """
    tools: list[dict] = []
    for r in resources:
        n = r["name"]
        if r["list"]:
            tools.append(_tool(
                f"{n}_list", f"List {n} (paginated).",
                {"page": {"type": "integer"}, "page_size": {"type": "integer"}}, []))
        if r["retrieve"]:
            tools.append(_tool(
                f"{n}_retrieve", f"Fetch one {n} record by id.",
                {"id": {"type": "string"}}, ["id"]))
        if r["create"]:
            tools.append(_tool(
                f"{n}_create", f"Create a {n} record.",
                {"data": {"type": "object"}}, ["data"]))
        if r["update"]:
            tools.append(_tool(
                f"{n}_update", f"Edit a {n} record (partial body is fine).",
                {"id": {"type": "string"}, "data": {"type": "object"}},
                ["id", "data"]))
        if r["destroy"]:
            tools.append(_tool(
                f"{n}_destroy", f"Delete a {n} record by id.",
                {"id": {"type": "string"}}, ["id"]))
    # Static tools: the resource roster (so an agent can discover what it
    # may touch) and the runtime branding API mounted by the plugin.
    tools.append(_tool(
        "api_overview", "List the resources this server exposes.",
        {}, []))
    tools.append(_tool(
        "branding_get", "Read the live admin branding (name, colors, logo).",
        {}, []))
    tools.append(_tool(
        "branding_set", "Update the live admin branding (applied without rebuild).",
        {"data": {"type": "object"}}, ["data"]))
    return tools
