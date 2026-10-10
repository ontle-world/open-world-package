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

export const FORMATS = ["owp-yaml", "turtle", "jsonld", "rdf-xml", "owl-xml", "ntriples", "linkml", "sssom-tsv"];
export const ROLES = ["schema", "shapes", "mappings", "labels"];
export const TERM_TYPES = ["class", "property", "individual", "datatype", "concept"];
const PREFIX_RE = /^[A-Za-z][A-Za-z0-9_-]*$/;
const IRI_RE = /^[A-Za-z][A-Za-z0-9+.-]*:\S+$/;
export const CURIE_RE = /^([A-Za-z][A-Za-z0-9_-]*):([^\s/]\S*)$/;

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
  const prefixes: Record<string, string> = Object.create(null);
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

/** Experimental (Appendix C.1): a term's lifecycle status; absent means stable. */
export const TERM_STATUSES = ["candidate", "stable", "deprecated"];

type LifecycleDoc = { file: string; format: "owp-yaml" | "term-index"; entries: Array<[string, Obj]> };

/** [where, entry] for every type, property, and relation a SemanticProfile defines. */
function definingEntries(doc: Obj | undefined): Array<[string, Obj]> {
  const spec = doc && isObj(doc.spec) ? doc.spec : {};
  const out: Array<[string, Obj]> = [];
  (Array.isArray(spec.types) ? spec.types : []).forEach((t, i) => {
    if (!isObj(t)) return;
    out.push([`spec.types[${i}]`, t]);
    (Array.isArray(t.properties) ? t.properties : []).forEach((p, j) => {
      if (isObj(p)) out.push([`spec.types[${i}].properties[${j}]`, p]);
    });
  });
  (Array.isArray(spec.relations) ? spec.relations : []).forEach((r, i) => {
    if (isObj(r)) out.push([`spec.relations[${i}]`, r]);
  });
  return out;
}

/** The owp-yaml entrypoints and the term index: where `status` and `replacedBy` live. */
function lifecycleDocs(dir: string, ontology: Obj): LifecycleDoc[] {
  const out: LifecycleDoc[] = [];
  for (const e of Array.isArray(ontology.entrypoints) ? ontology.entrypoints : []) {
    if (!isObj(e) || e.format !== "owp-yaml") continue;
    const abs = packageFileAt(dir, e.path);
    if (abs !== null) out.push({ file: e.path as string, format: "owp-yaml", entries: definingEntries(loadDoc(abs)) });
  }
  const abs = packageFileAt(dir, ontology.termIndex);
  if (abs !== null) {
    const terms = get(loadDoc(abs), "spec", "terms");
    const entries: Array<[string, Obj]> = [];
    (Array.isArray(terms) ? terms : []).forEach((t, j) => {
      if (isObj(t)) entries.push([`spec.terms[${j}]`, t]);
    });
    out.push({ file: ontology.termIndex as string, format: "term-index", entries });
  }
  return out;
}

/** The `removed` lists (tombstones) of the owp-yaml entrypoints and the term index; a `removed` that is not a list is one entry at `spec.removed`. */
function removedDocs(dir: string, ontology: Obj): Array<{ file: string; format: LifecycleDoc["format"]; entries: Array<[string, unknown]> }> {
  const out: Array<{ file: string; format: LifecycleDoc["format"]; entries: Array<[string, unknown]> }> = [];
  const add = (file: string, format: LifecycleDoc["format"], listed: unknown) => {
    if (listed === undefined || listed === null) return;
    out.push({ file, format, entries: Array.isArray(listed) ? listed.map((e, i) => [`spec.removed[${i}]`, e]) : [["spec.removed", listed]] });
  };
  for (const e of Array.isArray(ontology.entrypoints) ? ontology.entrypoints : []) {
    if (!isObj(e) || e.format !== "owp-yaml") continue;
    const abs = packageFileAt(dir, e.path);
    if (abs !== null) add(e.path as string, "owp-yaml", get(loadDoc(abs), "spec", "removed"));
  }
  const abs = packageFileAt(dir, ontology.termIndex);
  if (abs !== null) add(ontology.termIndex as string, "term-index", get(loadDoc(abs), "spec", "removed"));
  return out;
}

/** The identifiers of a `replacedBy`: a non-empty string or a non-empty list of them; null when malformed. */
function replacedByValues(value: unknown): string[] | null {
  const values = Array.isArray(value) ? value : [value];
  return values.length > 0 && values.every((v) => typeof v === "string" && v.trim() !== "") ? (values as string[]) : null;
}

/** An identifier as an IRI: a term index lists absolute IRIs; owp-yaml uses CURIEs or absolute IRIs. */
function identifier(format: LifecycleDoc["format"], value: unknown, prefixes: Record<string, unknown>): string | null {
  if (typeof value !== "string") return null;
  if (format === "term-index") return isIri(value) ? value : null;
  return expandCurie(value, prefixes);
}

function ontologyOf(manifest: Obj): { ontology: Obj; prefixes: Record<string, unknown> } {
  const o = get(manifest, "spec", "ontology");
  const ontology = isObj(o) ? o : {};
  return { ontology, prefixes: isObj(ontology.prefixes) ? ontology.prefixes : {} };
}

/** Every well-formed `replacedBy` identifier of an OntologyPackage (Appendix C.1). */
export function replacedByRefs(dir: string, manifest: Obj): Array<{ file: string; where: string; value: string; iri: string }> {
  const { ontology, prefixes } = ontologyOf(manifest);
  const out: Array<{ file: string; where: string; value: string; iri: string }> = [];
  for (const d of [...lifecycleDocs(dir, ontology), ...removedDocs(dir, ontology)]) {
    for (const [where, entry] of d.entries) {
      if (!isObj(entry) || !("replacedBy" in entry)) continue;
      for (const value of replacedByValues(entry.replacedBy) ?? []) {
        const iri = identifier(d.format, value, prefixes);
        if (iri !== null) out.push({ file: d.file, where: `${where}.replacedBy`, value, iri });
      }
    }
  }
  return out;
}

/**
 * Term IRI -> status and replacements, for the terms an OntologyPackage marks candidate or deprecated (Appendix C.1).
 * A term marked in several places takes the strongest mark: deprecated, then candidate.
 */
export function termStatuses(dir: string, manifest: Obj): Map<string, { status: string; replacedBy: string[] }> {
  const { ontology, prefixes } = ontologyOf(manifest);
  const out = new Map<string, { status: string; replacedBy: string[] }>();
  for (const d of lifecycleDocs(dir, ontology)) {
    for (const [, entry] of d.entries) {
      const status = entry.status;
      const iri = identifier(d.format, d.format === "term-index" ? entry.iri : entry.id, prefixes);
      if (iri === null || (status !== "candidate" && status !== "deprecated")) continue;
      const replaced: string[] = [];
      if (status === "deprecated") {
        for (const value of replacedByValues(entry.replacedBy) ?? []) {
          const full = identifier(d.format, value, prefixes);
          if (full !== null) replaced.push(full);
        }
      }
      const old = out.get(iri) ?? { status: "stable", replacedBy: [] };
      if (status === "deprecated" || old.status !== "deprecated") {
        out.set(iri, { status, replacedBy: old.status === status ? [...new Set([...old.replacedBy, ...replaced])] : replaced });
      }
    }
  }
  return out;
}

/** Term IRI -> replacements and removedIn, for the terms an OntologyPackage lists as removed (Appendix C.1 tombstones). */
export function removedTerms(dir: string, manifest: Obj): Map<string, { replacedBy: string[]; removedIn: string | null }> {
  const { ontology, prefixes } = ontologyOf(manifest);
  const out = new Map<string, { replacedBy: string[]; removedIn: string | null }>();
  for (const d of removedDocs(dir, ontology)) {
    for (const [, entry] of d.entries) {
      const iri = isObj(entry) ? identifier(d.format, d.format === "term-index" ? entry.iri : entry.id, prefixes) : null;
      if (iri === null || !isObj(entry)) continue;
      const replaced = (replacedByValues(entry.replacedBy) ?? []).map((v) => identifier(d.format, v, prefixes)).filter((v): v is string => v !== null);
      const old = out.get(iri) ?? { replacedBy: [], removedIn: null };
      out.set(iri, { replacedBy: [...new Set([...old.replacedBy, ...replaced])], removedIn: old.removedIn ?? (typeof entry.removedIn === "string" ? entry.removedIn : null) });
    }
  }
  return out;
}

/** An IRI as a CURIE with the longest matching prefix, or the IRI itself when none matches. */
export function compactIri(iri: string, prefixes: Record<string, unknown>): string {
  let best: [string, string] | null = null;
  for (const [name, ns] of Object.entries(prefixes)) {
    if (typeof ns === "string" && ns && iri.startsWith(ns) && CURIE_RE.test(`${name}:${iri.slice(ns.length)}`)) {
      if (best === null || ns.length > best[1].length) best = [name, ns];
    }
  }
  return best ? `${best[0]}:${iri.slice(best[1].length)}` : iri;
}

/** Appendix C.1 (experimental, warnings only): `status` and `replacedBy` of the terms an ontology defines. */
export function lifecycleProblems(dir: string, manifest: Obj): Array<{ rule: string; msg: string; file: string }> {
  const { ontology, prefixes } = ontologyOf(manifest);
  const out: Array<{ rule: string; msg: string; file: string }> = [];
  for (const d of lifecycleDocs(dir, ontology)) {
    const add = (rule: string, msg: string) => out.push({ rule, msg: `${d.file}: ${msg}`, file: d.file });
    for (const [where, entry] of d.entries) {
      if ("status" in entry && !TERM_STATUSES.includes(entry.status as string)) {
        add("experimental.value", `${where}.status ${JSON.stringify(entry.status)} must be one of ${TERM_STATUSES.join(", ")}`);
      }
      if (!("replacedBy" in entry)) continue;
      const values = replacedByValues(entry.replacedBy);
      if (values === null) {
        add("experimental.field", `${where}.replacedBy must be an identifier or a non-empty list of identifiers`);
        continue;
      }
      if (entry.status !== "deprecated") add("experimental.field", `${where}.replacedBy is only for a term with status deprecated`);
      for (const value of values) {
        if (identifier(d.format, value, prefixes) !== null) continue;
        const need = d.format === "term-index" ? "an absolute IRI" : "a CURIE with a declared prefix or an absolute IRI";
        add("experimental.field", `${where}.replacedBy ${JSON.stringify(value)} must be ${need}`);
      }
    }
  }
  const defined = ontologyTerms(dir, manifest).terms;
  for (const d of removedDocs(dir, ontology)) {
    const add = (rule: string, msg: string) => out.push({ rule, msg: `${d.file}: ${msg}`, file: d.file });
    if (d.entries.length > 0 && d.entries[0][0] === "spec.removed") {
      add("experimental.field", "spec.removed must be a list");
      continue;
    }
    const key = d.format === "term-index" ? "iri" : "id";
    const need = d.format === "term-index" ? "an absolute IRI" : "a CURIE with a declared prefix or an absolute IRI";
    for (const [where, entry] of d.entries) {
      const iri = isObj(entry) ? identifier(d.format, entry[key], prefixes) : null;
      if (iri === null || !isObj(entry)) {
        add("experimental.field", `${where} needs ${key}, ${need}`);
        continue;
      }
      if (defined.has(iri)) add("experimental.field", `${where} ${JSON.stringify(entry[key])} is listed as removed, but the ontology still defines it`);
      if ("removedIn" in entry && typeof entry.removedIn !== "string") add("experimental.field", `${where}.removedIn must be a version string`);
      if (!("replacedBy" in entry)) continue;
      const values = replacedByValues(entry.replacedBy);
      if (values === null) add("experimental.field", `${where}.replacedBy must be an identifier or a non-empty list of identifiers`);
      for (const value of values ?? []) {
        if (identifier(d.format, value, prefixes) === null) add("experimental.field", `${where}.replacedBy ${JSON.stringify(value)} must be ${need}`);
      }
    }
  }
  const namespace = ontology.iri;
  if (typeof namespace === "string" && namespace.length > 0) {
    for (const r of replacedByRefs(dir, manifest)) {
      if (r.iri.startsWith(namespace) && !defined.has(r.iri)) {
        out.push({ rule: "experimental.reference", msg: `${r.file}: ${r.where} ${JSON.stringify(r.value)} (${r.iri}) is not a term this ontology defines`, file: r.file });
      }
    }
  }
  return out;
}

/** What an OntologyPackage's owp-yaml schema entrypoints declare, by expanded IRI (spec 14 binding warnings). */
export interface SchemaModel {
  classes: Set<string>;
  parents: Map<string, Set<string>>;
  declaredOn: Map<string, Set<string>>;
  range: Map<string, string>;
  enums: Map<string, Set<string>>;
}

export function emptySchemaModel(): SchemaModel {
  return { classes: new Set(), parents: new Map(), declaredOn: new Map(), range: new Map(), enums: new Map() };
}

/**
 * Classes, their parents (subClassOf), the classes each property is declared on (types[].properties and relations'
 * domain), each property's range, and the values of each enum type. RDF entrypoints are not read (spec 14).
 */
export function schemaModel(dir: string, manifest: Obj): SchemaModel {
  const { prefixes } = ontologyTerms(dir, manifest);
  const o = isObj(get(manifest, "spec", "ontology")) ? (get(manifest, "spec", "ontology") as Obj) : {};
  const m = emptySchemaModel();
  const iri = (v: unknown): string | null => (typeof v === "string" ? expandCurie(v, prefixes) : null);
  const declare = (prop: string, cls: string | null, rng: unknown) => {
    if (!m.declaredOn.has(prop)) m.declaredOn.set(prop, new Set());
    if (cls) m.declaredOn.get(prop)!.add(cls);
    const r = iri(rng);
    if (r && !m.range.has(prop)) m.range.set(prop, r);
  };
  for (const e of Array.isArray(o.entrypoints) ? o.entrypoints : []) {
    if (!isObj(e) || e.format !== "owp-yaml" || e.role !== "schema" || typeof e.path !== "string") continue;
    const norm = normalizeRelPath(e.path);
    const doc = norm === null ? undefined : loadDoc(path.join(dir, norm));
    const spec = doc && isObj(doc.spec) ? doc.spec : {};
    for (const t of Array.isArray(spec.types) ? spec.types : []) {
      const cls = isObj(t) ? iri(t.id) : null;
      if (!cls || !isObj(t)) continue;
      if (Array.isArray(t.enum)) {
        m.enums.set(cls, new Set(t.enum.filter((v): v is string => typeof v === "string")));
        continue;
      }
      m.classes.add(cls);
      if (!m.parents.has(cls)) m.parents.set(cls, new Set());
      for (const p of Array.isArray(t.subClassOf) ? t.subClassOf : [t.subClassOf]) {
        const parent = iri(p);
        if (parent) m.parents.get(cls)!.add(parent);
      }
      for (const p of Array.isArray(t.properties) ? t.properties : []) {
        const prop = isObj(p) ? iri(p.id) : null;
        if (prop && isObj(p)) declare(prop, cls, p.range);
      }
    }
    for (const r of Array.isArray(spec.relations) ? spec.relations : []) {
      const prop = isObj(r) ? iri(r.id) : null;
      if (prop && isObj(r)) declare(prop, iri(r.domain), r.range);
    }
  }
  return m;
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

  for (const p of lifecycleProblems(ctx.root, { spec: { ontology } })) warn(ctx, p.rule, p.msg, p.file);
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
