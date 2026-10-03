/**
 * Spec section 3.1: the OntologyPackage contract (spec.ontology) and ontology conformance profiles.
 * Verdicts depend only on the manifest, OWP YAML documents (SemanticProfile, OntologyTermIndex),
 * and file existence; RDF, LinkML, and SSSOM content is not parsed.
 */
import * as path from "node:path";
import { Context, error, warn } from "../context.js";
import { SEMANTIC_PROFILE, structureProblems, TERM_INDEX } from "../structure.js";
import { get, isObj, loadYamlFile, normalizeRelPath, Obj, packageFile as packageFileAt } from "../util.js";
import { externalRefProblems } from "./externalref.js";

export const ONTOLOGY_PROFILES = ["vocabulary", "schema", "constrained", "mapped"] as const;
export type OntologyProfile = (typeof ONTOLOGY_PROFILES)[number];

const FORMATS = ["owp-yaml", "turtle", "jsonld", "rdf-xml", "owl-xml", "ntriples", "linkml", "sssom-tsv"];
const ROLES = ["schema", "shapes", "mappings", "labels"];
const TERM_TYPES = ["class", "property", "individual", "datatype", "concept"];
const PREFIX_RE = /^[A-Za-z][A-Za-z0-9_-]*$/;
const IRI_RE = /^[A-Za-z][A-Za-z0-9+.-]*:\S+$/;
const CURIE_RE = /^([A-Za-z][A-Za-z0-9_-]*):([^\s/]\S*)$/;

const isIri = (v: unknown): v is string => typeof v === "string" && IRI_RE.test(v);

/** Expand a CURIE with declared prefixes; a full IRI (`://` or `urn:`) is returned unchanged; null if the prefix is undeclared. */
export function expandCurie(curie: string, prefixes: Record<string, unknown>): string | null {
  const m = CURIE_RE.exec(curie);
  if (m && Object.prototype.hasOwnProperty.call(prefixes, m[1])) return `${String(prefixes[m[1]])}${m[2]}`;
  return curie.includes("://") || curie.startsWith("urn:") ? curie : null;
}

/** [where, value, defines] for every identifier a SemanticProfile defines (types, properties, relations) or uses. */
function profileIdentifiers(doc: Obj): Array<[string, unknown, boolean]> {
  const out: Array<[string, unknown, boolean]> = [];
  const spec = isObj(doc.spec) ? doc.spec : {};
  const types = Array.isArray(spec.types) ? spec.types : [];
  types.forEach((t, i) => {
    if (!isObj(t)) return;
    out.push([`spec.types[${i}].id`, t.id, true]);
    const parents = Array.isArray(t.subClassOf) ? t.subClassOf : t.subClassOf ? [t.subClassOf] : [];
    for (const p of parents) out.push([`spec.types[${i}].subClassOf`, p, false]);
    (Array.isArray(t.properties) ? t.properties : []).forEach((p, j) => {
      if (!isObj(p)) return;
      out.push([`spec.types[${i}].properties[${j}].id`, p.id, true]);
      // A range without ':' is a datatype name such as `string`, not an identifier.
      if (typeof p.range === "string" && p.range.includes(":")) out.push([`spec.types[${i}].properties[${j}].range`, p.range, false]);
    });
  });
  (Array.isArray(spec.relations) ? spec.relations : []).forEach((r, i) => {
    if (!isObj(r)) return;
    out.push([`spec.relations[${i}].id`, r.id, true]);
    for (const k of ["domain", "range"]) if (typeof r[k] === "string") out.push([`spec.relations[${i}].${k}`, r[k], false]);
  });
  return out;
}

/** An existing package-relative file (not starting with ./), as an absolute path; null otherwise. */
function packageFile(ctx: Context, p: unknown): string | null {
  return packageFileAt(ctx.root, p);
}

function loadDoc(abs: string): Obj | undefined {
  const l = loadYamlFile(abs);
  return l.ok && isObj(l.value) ? l.value : undefined;
}

/**
 * Spec 3.1: the prefixes an OntologyPackage declares and the terms it defines — the expanded
 * identifiers its owp-yaml schema entrypoints define (types, their properties, relations) plus
 * the terms of its termIndex. Used by the cross-package binding rules (spec 14).
 */
export function ontologyTerms(dir: string, manifest: Obj): { prefixes: Record<string, string>; terms: Set<string> } {
  const ontology = get(manifest, "spec", "ontology");
  const o = isObj(ontology) ? ontology : {};
  const prefixes: Record<string, string> = {};
  if (isObj(o.prefixes)) for (const [k, v] of Object.entries(o.prefixes)) if (typeof v === "string") prefixes[k] = v;
  const terms = new Set<string>();
  const load = (p: unknown): Obj | undefined => {
    if (typeof p !== "string") return undefined;
    const norm = normalizeRelPath(p);
    return norm === null ? undefined : loadDoc(path.join(dir, norm));
  };
  for (const e of Array.isArray(o.entrypoints) ? o.entrypoints : []) {
    if (!isObj(e) || e.format !== "owp-yaml" || e.role !== "schema") continue;
    const doc = load(e.path);
    if (!doc) continue;
    for (const [, value, defines] of profileIdentifiers(doc)) {
      const iri = defines && typeof value === "string" ? expandCurie(value, prefixes) : null;
      if (iri !== null) terms.add(iri);
    }
  }
  const index = load(o.termIndex);
  const list = get(index, "spec", "terms");
  for (const t of Array.isArray(list) ? list : []) if (isObj(t) && typeof t.iri === "string") terms.add(t.iri);
  return { prefixes, terms };
}

/** Every identifier the owp-yaml schema entrypoints use (not define), expanded with the package's prefixes. */
export function ontologyUses(dir: string, manifest: Obj): Array<{ file: string; where: string; value: string; iri: string }> {
  const o = get(manifest, "spec", "ontology");
  const ontology = isObj(o) ? o : {};
  const prefixes = isObj(ontology.prefixes) ? ontology.prefixes : {};
  const out: Array<{ file: string; where: string; value: string; iri: string }> = [];
  for (const e of Array.isArray(ontology.entrypoints) ? ontology.entrypoints : []) {
    if (!isObj(e) || e.format !== "owp-yaml" || e.role !== "schema" || typeof e.path !== "string") continue;
    const norm = normalizeRelPath(e.path);
    const doc = norm === null ? undefined : loadDoc(path.join(dir, norm));
    for (const [where, value, defines] of doc ? profileIdentifiers(doc) : []) {
      const iri = !defines && typeof value === "string" ? expandCurie(value, prefixes) : null;
      if (iri !== null) out.push({ file: e.path, where, value: value as string, iri });
    }
  }
  return out;
}

/** Single-package checks of spec.ontology (always applied, independent of the declared profile). */
function checkOntologyContract(ctx: Context, ontology: Obj): void {
  const err = (rule: string, msg: string, file = "owp.yaml") => error(ctx, rule, msg, file);

  if (ontology.iri !== undefined && ontology.iri !== null && !isIri(ontology.iri)) {
    err("ontology.iri", `spec.ontology.iri ${JSON.stringify(ontology.iri)} must be an absolute IRI`);
  }

  let prefixes: Record<string, unknown> = {};
  if (ontology.prefixes !== undefined && ontology.prefixes !== null) {
    if (!isObj(ontology.prefixes)) err("ontology.prefix", "spec.ontology.prefixes must map prefix names to IRIs");
    else {
      prefixes = ontology.prefixes;
      for (const [name, value] of Object.entries(prefixes)) {
        if (!PREFIX_RE.test(name) || !isIri(value)) {
          err("ontology.prefix", `spec.ontology.prefixes ${JSON.stringify(name)} -> ${JSON.stringify(value)} must be a name [A-Za-z][A-Za-z0-9_-]* and an absolute IRI`);
        }
      }
    }
  }

  let entrypoints: unknown[] = [];
  if (ontology.entrypoints !== undefined && ontology.entrypoints !== null) {
    if (!Array.isArray(ontology.entrypoints)) err("ontology.entrypoint", "spec.ontology.entrypoints must be a list");
    else entrypoints = ontology.entrypoints;
  }
  entrypoints.forEach((e, i) => {
    const at = `spec.ontology.entrypoints[${i}]`;
    if (!isObj(e)) return err("ontology.entrypoint", `${at} must be a mapping with path, format, and role`);
    const abs = packageFile(ctx, e.path);
    if (abs === null) return err("ontology.entrypoint", `${at}.path ${JSON.stringify(e.path)} must be an existing package-relative file`);
    if (typeof e.format !== "string" || !FORMATS.includes(e.format)) err("ontology.format", `${at}.format ${JSON.stringify(e.format)} must be one of ${FORMATS.join(", ")}`);
    if (typeof e.role !== "string" || !ROLES.includes(e.role)) err("ontology.entrypoint", `${at}.role ${JSON.stringify(e.role)} must be one of ${ROLES.join(", ")}`);
    if (e.format !== "owp-yaml") return;
    const file = e.path as string;
    const doc = loadDoc(abs);
    if (!doc || doc.kind !== "SemanticProfile") return err("ontology.parse", `${file} (format owp-yaml) must be a SemanticProfile document`, file);
    for (const p of structureProblems(doc, SEMANTIC_PROFILE, ctx.extensionNames)) err(p.rule, `${file}: ${p.msg}`, file);
    for (const [where, value] of profileIdentifiers(doc)) {
      if (typeof value !== "string" || expandCurie(value, prefixes) === null) {
        err("ontology.prefix-undeclared", `${file}: ${where} ${JSON.stringify(value)} uses a prefix that spec.ontology.prefixes does not declare`, file);
      }
    }
  });

  const ti = ontology.termIndex;
  if (ti !== undefined && ti !== null) {
    const abs = packageFile(ctx, ti);
    const doc = abs === null ? undefined : loadDoc(abs);
    if (!doc || doc.kind !== "OntologyTermIndex") {
      err("ontology.term-index", `spec.ontology.termIndex ${JSON.stringify(ti)} must be an existing OntologyTermIndex document`);
    } else {
      const file = ti as string;
      for (const p of structureProblems(doc, TERM_INDEX, ctx.extensionNames)) err(p.rule, `${file}: ${p.msg}`, file);
      const terms = get(doc, "spec", "terms");
      (Array.isArray(terms) ? terms : []).forEach((t, j) => {
        if (!isObj(t) || !isIri(t.iri) || typeof t.type !== "string" || !TERM_TYPES.includes(t.type)) {
          err("ontology.term-index", `${file}: spec.terms[${j}] needs an absolute iri and a type in ${TERM_TYPES.join(", ")}`, file);
        }
      });
    }
  }

  const imports = Array.isArray(ontology.externalImports) ? ontology.externalImports : [];
  imports.forEach((imp, i) => {
    const at = `spec.ontology.externalImports[${i}]`;
    if (!isObj(imp) || !isIri(imp.iri)) return err("ontology.external-import", `${at} needs an absolute iri`);
    if (!Object.prototype.hasOwnProperty.call(imp, "ref")) return err("ontology.external-import", `${at} needs a ref (spec section 5.1)`);
    const r = externalRefProblems(imp.ref, `${at}.ref`, ctx.extensionNames);
    for (const p of r.errors) err(p.rule, p.msg);
    for (const p of r.warnings) warn(ctx, p.rule, p.msg, "owp.yaml");
  });
}

/** Unmet requirements of one ontology profile alone (spec 3.1 table); profiles are cumulative. */
function profileFailures(ontology: Obj, profile: OntologyProfile): Array<{ rule: string; msg: string }> {
  const entries = (Array.isArray(ontology.entrypoints) ? ontology.entrypoints : []).filter(isObj);
  const withRole = (role: string) => entries.filter((e) => e.role === role);
  switch (profile) {
    case "vocabulary":
      return typeof ontology.iri === "string" && entries.length > 0
        ? []
        : [{ rule: "profile.ontology.vocabulary", msg: "requires spec.ontology.iri and at least one entrypoint" }];
    case "schema": {
      const schema = withRole("schema");
      if (schema.length === 0) return [{ rule: "profile.ontology.schema", msg: "requires an entrypoint with role schema" }];
      if (!schema.some((e) => e.format === "owp-yaml") && !ontology.termIndex) {
        return [{ rule: "profile.ontology.schema", msg: "a schema entrypoint that is not owp-yaml requires spec.ontology.termIndex" }];
      }
      return [];
    }
    case "constrained":
      return withRole("shapes").length ? [] : [{ rule: "profile.ontology.constrained", msg: "requires an entrypoint with role shapes" }];
    case "mapped":
      return withRole("mappings").length ? [] : [{ rule: "profile.ontology.mapped", msg: "requires an entrypoint with role mappings" }];
  }
}

/** Spec 3 + 3.1: OntologyPackage. Sets ctx.declaredProfile / ctx.satisfiedProfile like the World profiles (spec 6.1). */
export function checkOntologyPackage(ctx: Context): void {
  const spec = isObj(ctx.manifest.spec) ? ctx.manifest.spec : undefined;
  const ontology = spec?.ontology;
  if (!isObj(ontology)) {
    error(ctx, "ontology.spec", "OntologyPackage requires a spec.ontology mapping", "owp.yaml");
  } else {
    checkOntologyContract(ctx, ontology);
  }
  const o = isObj(ontology) ? ontology : {};

  let satisfied: OntologyProfile | null = null;
  const failures = new Map<OntologyProfile, Array<{ rule: string; msg: string }>>();
  let chainIntact = true;
  for (const p of ONTOLOGY_PROFILES) {
    const f = profileFailures(o, p);
    failures.set(p, f);
    if (chainIntact && f.length === 0) satisfied = p;
    else chainIntact = false;
  }
  ctx.satisfiedProfile = satisfied;

  // When spec.conformance is absent no ontology profile is required.
  const conf = spec?.conformance;
  if (conf === undefined || conf === null) return;
  const declared = isObj(conf) ? conf.profile : undefined;
  if (typeof declared !== "string" || !(ONTOLOGY_PROFILES as readonly string[]).includes(declared)) {
    error(ctx, "profile.unknown", `spec.conformance.profile must be one of ${ONTOLOGY_PROFILES.join(", ")} for an OntologyPackage (got ${JSON.stringify(declared)})`, "owp.yaml");
    return;
  }
  ctx.declaredProfile = declared;
  for (const p of ONTOLOGY_PROFILES.slice(0, ONTOLOGY_PROFILES.indexOf(declared as OntologyProfile) + 1)) {
    for (const f of failures.get(p) ?? []) error(ctx, f.rule, `declared profile "${declared}" not satisfied: ${f.msg}`, "owp.yaml");
  }
}
