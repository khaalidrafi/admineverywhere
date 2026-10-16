/** openapi.ts normalizer — drf-spectacular OpenAPI 3 -> internal AdminSchema.

Written against the REAL fixture captured from the demo backend
(src/lib/__tests__/fixtures/openapi.json).
Verified deviations: none (FKs, decimals, enums, COMPONENT_SPLIT_REQUEST all correct).
Heuristics, deliberately MVP:
- models = paths with GET+POST and a trailing slash, no '{id}'
- FK = integer/number/string property whose name matches another model's
  singular/id (drf-spectacular emits FKs as bare `type: integer`)
- enum = property $ref to a component carrying `enum: [...]`
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

function fieldTypeOf(doc: any, propName: string, prop: any,
                     names: Map<string, string>): FieldSpec["type"] {
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

function propToField(doc: any, propName: string, prop: any, requiredSet: Set<string>,
                     names: Map<string, string>, readOnly: boolean): FieldSpec {
  const [refName, resolved] = deref(doc, prop);
  let type = fieldTypeOf(doc, propName, prop, names);
  let choices: string[] | undefined;
  if (type === "enum") {
    choices = ((prop as any).enum ?? resolved?.enum ?? []).map(String);
  }
  const field: FieldSpec = {
    name: propName,
    type,
    required: !readOnly && requiredSet.has(propName),
    readOnly,
    nullable: Boolean(prop.nullable),
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

    models.push({
      id,
      name: titleCase(singular),
      singular,
      listPath: path,
      detailPath,
      fields,
      byName: Object.fromEntries(fields.map((f) => [f.name, f])),
      labelField,
    });
  }

  models.sort((a, b) => a.name.localeCompare(b.name));
  return { models, byId: Object.fromEntries(models.map((m) => [m.id, m])) };
}

/** Short schema summary for the AI system prompt ("data-aware" answers). */
export function schemaSummary(schema: AdminSchema): string {
  return schema.models
    .map((m) => {
      const fields = m.fields
        .map((f) => (f.type === "fk" ? `${f.name}(fk->${f.fkModel})` : `${f.name}(${f.type})`))
        .join(", ");
      return `- ${m.name} [${m.listPath}]: ${fields}`;
    })
    .join("\n");
}
