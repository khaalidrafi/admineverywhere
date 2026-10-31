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
  /** schema-discovered line-level CSV export endpoint (FR-R005 layer 2), when
   *  the backend documents GET <listPath>export/ — the client binds its
   *  "Full export" button to this and never to a guessed path. */
  exportPath?: string;
  /** schema-discovered R-001 lifecycle endpoints, bound ONLY when the document
   *  carries them: POST <detailPath>transition/ and GET <detailPath>history/
   *  (no POST). A client-side state machine with no server evidence renders no
   *  buttons — the same evidence law as exportPath and mePath. */
  transitionPath?: string;
  historyPath?: string;
}

export interface AdminSchema {
  models: ModelSpec[];
  byId: Record<string, ModelSpec>;
  /** schema-discovered role-claims endpoint (FR-R007): the document's
   *  GET …/me/ path, when present. No mePath = no client-side filtering. */
  mePath?: string;
}

export interface Brand {
  appName: string;
  tagline?: string;
  logo?: string;
  favicon?: string;
  /** The brand's intro clip — it IS the splash loader (owner order:
   *  all other loaders are gone). Stamped brands normalize it to a
   *  public/-root basename ("intro.mp4"); server brands carry an
   *  API-resolved or hosted URL by the time the splash reads it. */
  loaderVideo?: string;
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
