/**
 * Spec section 14: SemanticBinding — World names, EWS fields, observation types, and actions bound to
 * ontology terms. Single-package rules here; cross-package grounding (prefixes and terms of the
 * dependency OntologyPackages) is `bindingGroundingProblems`, called by the resolver.
 */
import { Context, error, warn } from "../context.js";
import { FIELD_BINDING, Problem, SEMANTIC_BINDING, structureProblems } from "../structure.js";
import { get, isObj, Obj } from "../util.js";
import { localViewIncludes } from "./experimental.js";
import { expandCurie } from "./ontology.js";
import { compilerFields } from "./world.js";

const CURIE_RE = /^([A-Za-z][A-Za-z0-9_-]*):([^\s/]\S*)$/;
const isCurie = (v: unknown): v is string => typeof v === "string" && CURIE_RE.test(v);
const SECTIONS = ["terms", "fields", "observationTypes", "actions"];

/** [where, value] for every ontology reference in a SemanticBinding document. */
export function bindingCuries(doc: unknown): Array<[string, unknown]> {
  const spec = get(doc, "spec");
  const s = isObj(spec) ? spec : {};
  const out: Array<[string, unknown]> = [];
  for (const section of ["terms", "observationTypes", "actions"]) {
    const m = s[section];
    if (isObj(m)) for (const [k, v] of Object.entries(m)) out.push([`spec.${section}.${k}`, v]);
  }
  if (isObj(s.fields)) {
    for (const [field, v] of Object.entries(s.fields)) {
      if (!isObj(v)) continue;
      out.push([`spec.fields.${field}.class`, v.class]);
      (Array.isArray(v.path) ? v.path : []).forEach((step, i) => out.push([`spec.fields.${field}.path[${i}]`, step]));
    }
  }
  return out;
}

/** Spec 14 single-package rules, after all assets are collected. */
export function checkSemanticBindings(ctx: Context): void {
  const world = get(ctx.manifest, "spec", "world");
  const w = isObj(world) ? world : {};
  const named = w.semanticBinding;
  if (named !== undefined && named !== null && !ctx.localAssets.some((a) => a.kind === "SemanticBinding" && a.rawPath === named)) {
    error(ctx, "binding.asset", `spec.world.semanticBinding ${JSON.stringify(named)} must be a listed local SemanticBinding asset`, "owp.yaml");
  }
  const bindings = ctx.localAssets.filter((a) => a.kind === "SemanticBinding" && isObj(a.doc));
  if (bindings.length === 0) return;

  const schemaFields = new Set<string>();
  for (const a of ctx.localAssets) {
    if (a.kind !== "StateCompilerProfile") continue;
    for (const x of compilerFields(ctx, a).fields ?? []) schemaFields.add(x);
  }
  const boundary = get(w, "boundary", "included");
  const scope = new Set([...(Array.isArray(boundary) ? boundary.filter((x): x is string => typeof x === "string") : []), ...localViewIncludes(ctx)]);

  for (const a of bindings) {
    const file = a.rawPath;
    const doc = a.doc as Obj;
    const report = (p: Problem) => error(ctx, p.rule, `${file}: ${p.msg}`, file);
    structureProblems(doc, SEMANTIC_BINDING, ctx.extensionNames).forEach(report);
    const spec = isObj(doc.spec) ? doc.spec : {};
    for (const section of SECTIONS) {
      if (section in spec && !isObj(spec[section])) report({ rule: "binding.curie", msg: `spec.${section} must be a mapping` });
    }
    if (isObj(spec.fields)) {
      for (const [field, v] of Object.entries(spec.fields)) {
        const at = `spec.fields.${field}`;
        if (!isObj(v)) {
          report({ rule: "binding.curie", msg: `${at} must be a mapping with class and path` });
          continue;
        }
        structureProblems(v, FIELD_BINDING, ctx.extensionNames).forEach((p) => report({ rule: p.rule, msg: `${at}: ${p.msg}` }));
        if ("path" in v && !Array.isArray(v.path)) report({ rule: "binding.curie", msg: `${at}.path must be a list of CURIEs` });
        if (!schemaFields.has(field)) report({ rule: "binding.field-unknown", msg: `${at} is not an EWS field of any local State Compiler` });
      }
    }
    for (const [where, value] of bindingCuries(doc)) {
      if (!isCurie(value)) report({ rule: "binding.curie", msg: `${where} ${JSON.stringify(value)} must be a CURIE <prefix>:<local name>` });
    }
    // Spec 14: spec.subjects maps observation types listed in observationTypes to {base} or {iri: true}.
    if ("subjects" in spec) {
      const types = isObj(spec.observationTypes) ? spec.observationTypes : {};
      if (!isObj(spec.subjects)) report({ rule: "binding.subjects", msg: "spec.subjects must be a mapping of observation type to {base} or {iri: true}" });
      else for (const [otype, r] of Object.entries(spec.subjects)) {
        if (!(otype in types)) report({ rule: "binding.subjects", msg: `spec.subjects.${otype} is not listed in spec.observationTypes` });
        const ok = isObj(r) && Object.keys(r).length === 1
          && ((typeof r.base === "string" && /^[A-Za-z][A-Za-z0-9+.-]*:/.test(r.base)) || r.iri === true);
        if (!ok) report({ rule: "binding.subjects", msg: `spec.subjects.${otype} must be {base: <absolute IRI prefix>} or {iri: true}` });
      }
    }
    // Skipped when neither the World boundary nor any View projection lists names.
    if (scope.size > 0 && isObj(spec.terms)) {
      for (const name of Object.keys(spec.terms)) {
        if (!scope.has(name)) {
          warn(ctx, "binding.term-unscoped", `${file}: spec.terms.${name} is neither in spec.world.boundary.included nor in any local View's projection.include`, file);
        }
      }
    }
  }
}

/**
 * Spec 14 cross-package rules for one package: prefixes of its dependency OntologyPackages are merged
 * in dependency order (conflicts are errors), and every binding CURIE expands to a term they define.
 */
export function bindingGroundingProblems(
  bindingDocs: Array<[string, unknown]>,
  ontologies: Array<{ ref: string; prefixes: Record<string, string>; terms: Set<string> }>,
): Problem[] {
  const out: Problem[] = [];
  const prefixes: Record<string, string> = {};
  const owner: Record<string, string> = {};
  for (const o of ontologies) {
    for (const [name, iri] of Object.entries(o.prefixes)) {
      if (name in prefixes && prefixes[name] !== iri) {
        out.push({ rule: "grounding.prefix-conflict", msg: `prefix "${name}" is ${prefixes[name]} in ${owner[name]} and ${iri} in ${o.ref}` });
      } else if (!(name in prefixes)) {
        prefixes[name] = iri;
        owner[name] = o.ref;
      }
    }
  }
  const known = new Set(ontologies.flatMap((o) => [...o.terms]));
  for (const [file, doc] of bindingDocs) {
    for (const [where, value] of bindingCuries(doc)) {
      if (!isCurie(value)) continue; // reported as binding.curie
      const iri = expandCurie(value, prefixes);
      if (iri === null) {
        out.push({ rule: "grounding.prefix-unknown", msg: `${file}: ${where} "${value}" uses a prefix that no dependency OntologyPackage declares` });
      } else if (!known.has(iri)) {
        out.push({ rule: "grounding.ontology-term", msg: `${file}: ${where} "${value}" (${iri}) is not a term of any dependency OntologyPackage` });
      }
    }
  }
  return out;
}
