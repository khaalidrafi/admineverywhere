/** Shared types for the schema-driven admin. */

export type FieldType =
  | "text"
  | "number"
  | "boolean"
  | "date"
  | "datetime"
  | "enum"
  | "fk"
  | "json";

export interface FieldSpec {
  name: string;
  type: FieldType;
  required: boolean;
  readOnly: boolean;
  /** enum choices */
  choices?: string[];
  /** target model id (list path segment) for FK fields */
  fkModel?: string;
  nullable?: boolean;
  maxLength?: number;
  /** OpenAPI format hint (decimal, date, date-time, email, ...) */
  format?: string;
}

export interface ModelSpec {
  /** url segment, e.g. "products" */
  id: string;
  /** display name, e.g. "Product" */
  name: string;
  singular: string;
  listPath: string;
  detailPath: string;
  fields: FieldSpec[];
  /** fields indexed by name */
  byName: Record<string, FieldSpec>;
  /** best guess for a human label field (FK dropdowns) */
  labelField: string;
}

export interface AdminSchema {
  models: ModelSpec[];
  byId: Record<string, ModelSpec>;
}

export interface Brand {
  appName: string;
  tagline?: string;
  logo?: string;
  favicon?: string;
  colors: Record<string, string>;
  radius: string;
  font: string;
}

export interface AppConfig {
  apiUrl: string;
  authPath: string;
  schemaPath: string;
}

/** One append-only audit entry (FR-R003). Loose targeting: object_type is the
 *  model's singular name, object_id the record pk as a string. */
export interface AuditEntry {
  id: number;
  action: string;
  object_type: string;
  object_id: string;
  actor: string | null;
  summary: string;
  data?: Record<string, any>;
  created_at: string;
}

export type RecordRow = Record<string, any> & { id?: number | string };

export interface Page<T> {
  count: number;
  results: T[];
  next: string | null;
  previous: string | null;
}
