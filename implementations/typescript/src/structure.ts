/**
 * Spec sections 8 ("Defined fields") and 13: which keys each standardized document may contain.
 *
 * Each table follows the JSON Schema of the same document under ../../schemas/. A closed object
 * accepts only its listed fields, plus an `extensions` block where the schema allows one; an open
 * container (`OPEN`) is not checked inside; `ANY` is a leaf value that is not descended into.
 */
import { isObj } from "./util.js";

export const EXTENSION_NAME_RE = /^[a-z][a-z0-9-]{0,62}$/;
export const EXTENSION_KIND_RE = /^([a-z][a-z0-9-]{0,62}):([A-Z][A-Za-z0-9]*)$/;
export const RESERVED_EXTENSION_NAMES = new Set(["owp", "openworld"]);

export type Shape =
  | { t: "any" }
  | { t: "open" }
  | { t: "list"; items: Shape }
  | { t: "closed"; fields: Record<string, Shape>; extensions: boolean };

export const ANY: Shape = { t: "any" };
export const OPEN: Shape = { t: "open" };
export const list = (items: Shape): Shape => ({ t: "list", items });
/** Closed object; `extensions` is allowed unless `ext` is false (document roots). */
export const closed = (fields: Record<string, Shape>, ext = true): Shape => ({ t: "closed", fields, extensions: ext });
export const leaves = (...names: string[]): Record<string, Shape> => Object.fromEntries(names.map((n) => [n, ANY]));

/** schemas/owp-manifest.schema.json $defs/externalRef (spec 5.1). */
export const EXTERNAL_REF: Shape = closed(leaves("provider", "uri", "revision", "digest", "mediaType", "size", "status", "repository"));

/** schemas/owp-manifest.schema.json spec.ontology (spec 3.1); `prefixes` is an open map. */
export const ONTOLOGY: Shape = closed({
  ...leaves("description", "iri", "termIndex"),
  prefixes: OPEN,
  entrypoints: list(closed(leaves("path", "format", "role"))),
  externalImports: list(closed({ iri: ANY, ref: EXTERNAL_REF })),
});

/** schemas/owp-manifest.schema.json */
export const MANIFEST: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    metadata: closed(leaves("namespace", "name", "version", "title", "description", "license")),
    spec: closed({
      dependencies: list(closed(leaves("ref", "source", "as", "mustUnderstand"))),
      assets: list(closed({ ...leaves("kind", "path"), ref: EXTERNAL_REF })),
      conformance: closed(leaves("profile")),
      world: closed({
        ...leaves("definition", "description", "defaultView", "defaultStateCompiler"),
        boundary: closed(leaves("included", "excluded")),
      }),
      worldModel: closed({
        ...leaves("description", "roles", "outputs"),
        semanticGrounding: closed(leaves("worldRef", "compatibleWorldViews", "compatibleStateCompilers")),
        representation: closed(leaves("adapterRef", "input", "internal", "mode")),
        inputs: closed(leaves("contract")),
        modalities: closed(leaves("inputs", "outputs")),
        temporal: OPEN,
        validity: OPEN,
      }),
      ontology: ONTOLOGY,
      extensionDefinition: closed(leaves("description", "kinds", "schemas")),
      domains: ANY,
      capabilities: ANY,
      validity: OPEN,
    }),
  },
  false,
);

/** `metadata` of a local asset document (schemas/compatibility-evidence.schema.json, schemas/experimental/). */
export const ASSET_METADATA: Shape = closed(leaves("name", "version", "title", "description"));

/** schemas/semantic-profile.schema.json (spec 3.1 owp-yaml entrypoints). */
export const SEMANTIC_PROFILE: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    metadata: ASSET_METADATA,
    spec: closed({
      types: list(
        closed({
          ...leaves("id", "description", "subClassOf", "enum"),
          label: OPEN,
          properties: list(closed({ ...leaves("id", "description", "range", "cardinality"), label: OPEN })),
        }),
      ),
      relations: list(closed({ ...leaves("id", "description", "domain", "range"), label: OPEN })),
    }),
  },
  false,
);

/** schemas/ontology-term-index.schema.json */
export const TERM_INDEX: Shape = closed(
  { ...leaves("apiVersion", "kind"), metadata: ASSET_METADATA, spec: closed({ terms: list(closed(leaves("iri", "type", "label"))) }) },
  false,
);

/** schemas/compatibility-evidence.schema.json */
export const COMPATIBILITY_EVIDENCE: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    metadata: ASSET_METADATA,
    spec: closed({
      ...leaves("subject", "evaluationProfile", "verifier", "goldenSet", "dataset"),
      scope: closed(leaves("worldRef", "worldView", "stateCompiler", "environment", "task")),
      result: OPEN,
    }),
  },
  false,
);

/** schemas/observation-set.schema.json */
export const OBSERVATION_SET: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    spec: closed({ observations: list(closed({ ...leaves("id", "type", "observedAt", "subject"), values: OPEN })) }),
  },
  false,
);

/** schemas/effective-world-state.schema.json */
export const EFFECTIVE_WORLD_STATE: Shape = closed(
  {
    ...leaves("apiVersion", "kind"),
    spec: closed({
      ...leaves("worldRef", "worldView", "stateCompiler", "missing"),
      context: closed(leaves("asOf")),
      state: OPEN,
      unresolved: OPEN,
      provenance: OPEN,
    }),
  },
  false,
);

/** Asset kinds whose documents have a JSON Schema; other kinds are checked only for top-level extension blocks. */
export const ASSET_STRUCTURES: Record<string, Shape> = {
  CompatibilityEvidence: COMPATIBILITY_EVIDENCE,
  SemanticProfile: SEMANTIC_PROFILE,
  OntologyTermIndex: TERM_INDEX,
};

export interface Problem {
  rule: string;
  msg: string;
}

/**
 * Unknown keys and malformed `extensions` blocks in `doc`.
 * `declared` is the set of extension names the package declares, or null for runtime documents
 * (ObservationSet, EWS), whose extension names are not checked (spec 12).
 */
export function structureProblems(doc: unknown, shape: Shape, declared: Set<string> | null): Problem[] {
  const out: Problem[] = [];
  walk(doc, shape, "", declared, out);
  return out;
}

function walk(v: unknown, shape: Shape, at: string, declared: Set<string> | null, out: Problem[]): void {
  if (shape.t === "list") {
    if (Array.isArray(v)) v.forEach((item, i) => walk(item, shape.items, `${at}[${i}]`, declared, out));
    return;
  }
  if (shape.t !== "closed" || !isObj(v)) return; // type errors are reported by the rules that use the value
  for (const [k, sub] of Object.entries(v)) {
    const child = at ? `${at}.${k}` : k;
    if (k === "extensions" && shape.extensions) out.push(...extensionBlockProblems(sub, child, declared));
    else if (Object.prototype.hasOwnProperty.call(shape.fields, k)) walk(sub, shape.fields[k], child, declared, out);
    else out.push({ rule: "schema.unknown-field", msg: `${child} is not a defined field (extension data belongs in an extensions block)` });
  }
}

/** Spec 13.3: an `extensions` block maps declared extension names to mappings. */
export function extensionBlockProblems(block: unknown, at: string, declared: Set<string> | null): Problem[] {
  if (!isObj(block) || !Object.values(block).every(isObj)) {
    return [{ rule: "extension.block", msg: `${at} must map extension names to mappings` }];
  }
  const out: Problem[] = [];
  for (const name of Object.keys(block)) {
    if (!EXTENSION_NAME_RE.test(name)) out.push({ rule: "extension.block", msg: `${at} key ${JSON.stringify(name)} is not an extension name` });
    else if (declared && !declared.has(name)) {
      out.push({ rule: "extension.undeclared", msg: `${at} uses extension ${JSON.stringify(name)}, which spec.dependencies does not declare with "as"` });
    }
  }
  return out;
}
