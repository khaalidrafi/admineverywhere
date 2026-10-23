/** openapi.ts normalizer — drf-spectacular OpenAPI 3 -> internal AdminSchema.

Written against the REAL fixture captured from the demo backend
(src/lib/__tests__/fixtures/openapi.json).
Verified deviations: none (FKs, decimals, enums, COMPONENT_SPLIT_REQUEST all correct).
Heuristics, deliberately MVP:
- models = paths with GET+POST and a trailing slash, no '{id}'
- FK = integer/number/string property whose name matches another model's
  singular/id (drf-spectacular emits FKs as bare `type: integer`)
- enum = property $ref to a component carrying `enum: [...]`; a blank/nullable
  choices field arrives as a oneOf union with BlankEnum/NullEnum and is read
  through — the sentinel is never a choice, and only NullEnum sets `nullable`
- forms are driven by <Model>Request components; response <Model> adds
  readOnly fields (id, created_at)
*/
import type { AdminSchema, FieldSpec, FieldType, ModelSpec } from "./types";

export function singularize(seg: string): string {
  // "categories" -> "category"; keep "status"/"bus" (u before final s)
  return seg.replace(/ies$/, "y").replace(/([^u])s$/, "$1");
}

export function titleCase(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1);
}

/** "#/components/schemas/X" -> ["X", resolved schema object] */
function deref(doc: any, node: any): [string, any] {
  if (node && typeof node === "object" && node.$ref) {
    const name = node.$ref.split("/").pop();
    return [name, doc.components?.schemas?.[name] ?? {}];
  }
  return [null as any, node ?? {}];
}

/** drf-spectacular splits a `blank=True` / `null=True` choices field into a
 * oneOf/anyOf/allOf union of its enum component with `BlankEnum` / `NullEnum`
 * (either a `$ref` to that component or its literal `{enum: [""]}` /
 * `{enum: [null]}` shape). The sentinel carries no type information and never
 * becomes a choice: every enum select and FK dropdown already ships an "—"
 * option, and a blank field is absent from `required`.
 *
 * The two sentinels are NOT interchangeable, and the difference is a wire fact:
 * `null=True` means the server accepts JSON null, so `nullable` is true and
 * buildPayload sends an explicit null to clear the value. `blank=True` alone
 * means it accepts the EMPTY STRING — such a field is usually still
 * non-nullable, so a null there earns a DRF 400 and buildPayload must omit the
 * empty value instead (AGENTS.md: "never send null in a non-nullable field"). */
function sentinelKinds(name: string | null, schema: any): ("blank" | "null")[] {
  if (name === "BlankEnum") return ["blank"];
  if (name === "NullEnum") return ["null"];
  const values = schema?.enum;
  if (!Array.isArray(values) || values.length === 0) return [];
  if (values.every((v: any) => v === null)) return ["null"];
  if (values.every((v: any) => v === "" || v === null)) return ["blank", "null"];
  return [];
}

function isBlankNullSentinel(name: string | null, schema: any): boolean {
  return sentinelKinds(name, schema).length > 0;
}

/** The property's union members, each with its own `$ref` followed — or null
 * when the property is not a union at all. */
function unionMembers(doc: any, prop: any): { name: string | null; schema: any }[] | null {
  for (const key of ["oneOf", "anyOf", "allOf"] as const) {
    const members = prop?.[key];
    if (Array.isArray(members) && members.length > 0) {
      return members.map((m: any) => {
        const [name, schema] = deref(doc, m);
        return { name, schema };
      });
    }
  }
  return null;
}

/** The property as the form should see it: top-level `$ref` followed, then the
 * first union member that is not a blank/null sentinel. Reading through the
 * union is what keeps such a field an enum instead of falling to the
 * schemaless `"text"` default. */
function effectiveSchema(doc: any, prop: any): any {
  const [, resolved] = deref(doc, prop);
  const members = unionMembers(doc, resolved);
  if (!members) return resolved;
  return members.find((m) => !isBlankNullSentinel(m.name, m.schema))?.schema ?? resolved;
}

function fieldTypeOf(doc: any, propName: string, rawProp: any,
                     names: Map<string, string>): FieldSpec["type"] {
  const prop = effectiveSchema(doc, rawProp);
  const [refName, resolved] = deref(doc, prop);

  // enum via $ref (drf-spectacular hoists TextChoices into components)
  if (Array.isArray((prop as any).enum)) return "enum";
  if (refName && Array.isArray(resolved?.enum)) return "enum";

  // FK: property name (minus optional _id) matches another model's
  // singular or path id — drf-spectacular emits FKs as bare integers
  const name = propName.toLowerCase().replace(/_id$/, "");
  if (
    (prop.type === "integer" || prop.type === "number" || prop.type === "string")
    && names.has(name)
  ) {
    return "fk";
  }

  switch (prop.type) {
    case "boolean":
      return "boolean";
    case "integer":
    case "number":
      return "number";
    case "string":
      if (prop.format === "date") return "date";
      if (prop.format === "date-time") return "datetime";
      // DRF DecimalField serializes as type:string + format:decimal
      if (prop.format === "decimal" || prop.format === "float"
          || prop.format === "double") {
        return "number";
      }
      return "text";
    case "array":
    case "object":
      return "json";
    default:
      // OpenAPI allows schemaless props; default to text so forms degrade
      return "text";
  }
}

function propToField(doc: any, propName: string, rawProp: any, requiredSet: Set<string>,
                     names: Map<string, string>, readOnly: boolean): FieldSpec {
  const prop = effectiveSchema(doc, rawProp);
  const [, resolved] = deref(doc, prop);
  const type = fieldTypeOf(doc, propName, rawProp, names);
  let choices: string[] | undefined;
  let optional = Boolean(rawProp?.nullable ?? prop?.nullable);
  const members = unionMembers(doc, deref(doc, rawProp)[1]);
  if (members) {
    const real = members.filter((m) => !isBlankNullSentinel(m.name, m.schema));
    // only a NULL sentinel makes the field nullable — a blank one is the empty
    // string, and an omitted value is what a non-nullable server expects
    if (real.length < members.length
        && members.some((m) => sentinelKinds(m.name, m.schema).includes("null"))) {
      optional = true;
    }
    if (type === "enum") {
      choices = real.flatMap((m) => (Array.isArray(m.schema?.enum) ? m.schema.enum : []))
        .map(String);
      if (!choices.length) choices = (resolved?.enum ?? []).map(String);
    }
  } else if (type === "enum") {
    choices = ((prop as any).enum ?? resolved?.enum ?? []).map(String);
  }
  const field: FieldSpec = {
    name: propName,
    type,
    required: !readOnly && requiredSet.has(propName),
    readOnly,
    nullable: optional,
    format: prop.format,
  };
  if (choices) field.choices = choices;
  if (type === "fk") {
    const name = propName.toLowerCase().replace(/_id$/, "");
    field.fkModel = names.get(name);
  }
  return field;
}

function requestSchemaFor(doc: any, pathItem: any): any {
  const ref = pathItem?.post?.requestBody?.content?.["application/json"]?.schema;
  const [, resolved] = deref(doc, ref);
  return resolved && resolved.properties ? resolved : null;
}

function responseSchemaFor(doc: any, pathItem: any): any {
  const ref = pathItem?.get?.responses?.["200"]?.content?.["application/json"]?.schema;
  const [refName, resolved] = deref(doc, ref);
  // Paginated<X>List -> unwrap .results.items
  if (refName?.startsWith("Paginated") && resolved?.properties?.results?.items) {
    const [, inner] = deref(doc, resolved.properties.results.items);
    return inner && inner.properties ? inner : null;
  }
  return resolved && resolved.properties ? resolved : null;
}

const LABEL_CANDIDATES = ["name", "title", "label", "username", "email", "slug", "code"];

export function normalizeOpenAPI(doc: any): AdminSchema {
  const paths: Record<string, any> = doc?.paths ?? {};
  const models: ModelSpec[] = [];

  // Pass 1: discover list endpoints (GET + POST, trailing slash, no params)
  const discovered: { id: string; path: string; pathItem: any }[] = [];
  for (const [path, pathItem] of Object.entries(paths)) {
    if (!path.endsWith("/") || path.includes("{")) continue;
    if (!pathItem?.get || !pathItem?.post) continue;
    const seg = path.replace(/\/+$/, "").split("/").pop();
    if (!seg) continue;
    discovered.push({ id: seg, path, pathItem });
  }
  const modelIds = discovered.map((d) => d.id);
  // FK name resolution: singular + id forms -> model id (path segment)
  const names = new Map<string, string>();
  for (const d of discovered) {
    names.set(singularize(d.id), d.id);
    names.set(d.id, d.id);
  }

  // Pass 2: build field specs per model
  for (const { id, path, pathItem } of discovered) {
    const singular = singularize(id);
    const req = requestSchemaFor(doc, pathItem) ?? {};
    const res = responseSchemaFor(doc, pathItem) ?? {};
    const requiredSet = new Set<string>((req.required ?? []).map(String));

    const fields: FieldSpec[] = [];
    const seen = new Set<string>();

    // 'id' first (from response) so tables always lead with the pk
    if (res.properties?.id) {
      fields.push(propToField(doc, "id", res.properties.id, requiredSet, names, true));
      seen.add("id");
    }
    // writable fields in Request order
    for (const [name, prop] of Object.entries<any>(req.properties ?? {})) {
      if (seen.has(name)) continue;
      fields.push(propToField(doc, name, prop, requiredSet, names, false));
      seen.add(name);
    }
    // response-only read-only fields (created_at, ...)
    for (const [name, prop] of Object.entries<any>(res.properties ?? {})) {
      if (seen.has(name) || !prop?.readOnly) continue;
      fields.push(propToField(doc, name, prop, requiredSet, names, true));
      seen.add(name);
    }

    const detailPath = `${path}{id}/`;
    const labelField = fields.find((f) => LABEL_CANDIDATES.includes(f.name))?.name ?? "id";

    // FR-R005 layer 2: a server-side line-level export is bound ONLY when the
    // document carries GET <listPath>export/. Require get && !post — a path
    // with both is a model list, not an action, and guessing here is how a
    // bare `apiUrl + "export"` concatenation once broke the R-001 calls.
    const exportPathItem = paths[`${path}export/`];
    const serverExport = exportPathItem?.get && !exportPathItem?.post ? `${path}export/` : undefined;

    // FR-R001 lifecycle: the governed endpoints are bound ONLY when the document
    // carries them. transition is a POST-only detail action; history is GET-only
    // with no POST (an action that also accepts POST is a collection, not a
    // trail). A model whose machine is declared client-side but not documented
    // server-side gets no buttons — see statusTransitions.lifecycleProblem().
    const transitionPathItem = paths[`${detailPath}transition/`];
    const serverTransition = transitionPathItem?.post ? `${detailPath}transition/` : undefined;
    const historyPathItem = paths[`${detailPath}history/`];
    const serverHistory = historyPathItem?.get && !historyPathItem?.post ? `${detailPath}history/` : undefined;

    models.push({
      id,
      name: titleCase(singular),
      singular,
      listPath: path,
      detailPath,
      fields,
      byName: Object.fromEntries(fields.map((f) => [f.name, f])),
      labelField,
      ...(serverExport ? { exportPath: serverExport } : {}),
      ...(serverTransition ? { transitionPath: serverTransition } : {}),
      ...(serverHistory ? { historyPath: serverHistory } : {}),
    });
  }

  models.sort((a, b) => a.name.localeCompare(b.name));

  // FR-R007 role-claims source: bound ONLY when the document carries a
  // GET …/me/ with no POST — the same evidence law as exportPath. A plain
  // DRF backend without it yields no mePath, and the client filters nothing.
  let mePath: string | undefined;
  for (const [p, item] of Object.entries<any>(paths)) {
    if (p.endsWith("/me/") && item?.get && !item?.post) {
      mePath = p;
      break;
    }
  }

  return { models, byId: Object.fromEntries(models.map((m) => [m.id, m])), ...(mePath ? { mePath } : {}) };
}
