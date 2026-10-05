/**
 * Spec section 14: SemanticBinding — World names, EWS fields, observation types, and actions bound to
 * ontology terms. Single-package rules here; cross-package grounding (prefixes and terms of the
 * dependency OntologyPackages) is `bindingGroundingProblems`, called by the resolver.
 */
import { Context, error, warn } from "../context.js";
import { FIELD_BINDING, Problem, SEMANTIC_BINDING, structureProblems } from "../structure.js";
import { get, isObj, Obj } from "../util.js";
import { localViewIncludes } from "./experimental.js";
import { emptySchemaModel, expandCurie, SchemaModel } from "./ontology.js";
import { compilerFields } from "./world.js";

const CURIE_RE = /^([A-Za-z][A-Za-z0-9_-]*):([^\s/]\S*)$/;
const isCurie = (v: unknown): v is string => typeof v === "string" && CURIE_RE.test(v);
const SECTIONS = ["terms", "fields", "observationTypes", "actions"];

/** [where, value] for every ontology reference in a SemanticBinding document. */
const own = (o: unknown, k: string): boolean => isObj(o) && Object.prototype.hasOwnProperty.call(o, k);
/** ISO 29002-5 IRDI, such as 0173-1#02-AAO677#002 (ECLASS) or 0112/2///61360_4#AAE530#002 (IEC CDD). */
const IRDI_RE = /^[0-9]{4}[-/][^#\s]+#(?:[0-9A-Z]{2}-)?[0-9A-Z]{3,}#[0-9]{1,3}$/;
const absoluteIri = (v: unknown): boolean => typeof v === "string" && !v.includes(" ") && (v.includes("://") || v.startsWith("urn:"));

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
      if ("unit" in v) out.push([`spec.fields.${field}.unit`, v.unit]); // a unit term (e.g. QUDT) of a dependency ontology (spec 14)
      const values = isObj(v.values) ? v.values : {};
      if ("scheme" in values) out.push([`spec.fields.${field}.values.scheme`, values.scheme]); // the concept scheme of coded values
      if (isObj(values.map)) for (const [code, concept] of Object.entries(values.map)) out.push([`spec.fields.${field}.values.map.${code}`, concept]);
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
    if (spec.subjects !== undefined && spec.subjects !== null) {
      const types = isObj(spec.observationTypes) ? spec.observationTypes : {};
      if (!isObj(spec.subjects)) report({ rule: "binding.subjects", msg: "spec.subjects must be a mapping of observation type to {base} or {iri: true}" });
      else for (const [otype, r] of Object.entries(spec.subjects)) {
        if (!own(types, otype)) report({ rule: "binding.subjects", msg: `spec.subjects.${otype} is not listed in spec.observationTypes` });
        const ok = isObj(r) && Object.keys(r).length === 1
          && ((typeof r.base === "string" && /^[A-Za-z][A-Za-z0-9+.-]*:/.test(r.base)) || r.iri === true);
        if (!ok) report({ rule: "binding.subjects", msg: `spec.subjects.${otype} must be {base: <absolute IRI prefix>} or {iri: true}` });
      }
    }
    // Spec 14: coded values tied to concepts, {scheme?, base?, map?} with base or map.
    if (isObj(spec.fields)) {
      for (const [field, v] of Object.entries(spec.fields)) {
        if (!isObj(v) || !("values" in v)) continue;
        const at = `spec.fields.${field}.values`;
        const vals = v.values;
        if (!isObj(vals) || !("base" in vals || "map" in vals)) {
          report({ rule: "binding.values", msg: `${at} must be a mapping with base, map, or both (and optionally scheme)` });
          continue;
        }
        if ("base" in vals && !absoluteIri(vals.base)) report({ rule: "binding.values", msg: `${at}.base must be an absolute IRI prefix` });
        if ("map" in vals && !(isObj(vals.map) && Object.keys(vals.map).length > 0 && Object.keys(vals.map).every((k) => k.length > 0))) {
          report({ rule: "binding.values", msg: `${at}.map must be a non-empty mapping from code to concept CURIE` });
        }
      }
    }
    // Spec 14: external dictionary identifiers (IRDIs or IRIs) attached to bound names, by section.
    if (spec.semanticIds !== undefined && spec.semanticIds !== null) {
      const ids = spec.semanticIds;
      if (!isObj(ids)) report({ rule: "binding.semantic-ids", msg: "spec.semanticIds must be a mapping of section (terms, fields, observationTypes, actions) to name to identifiers" });
      else for (const [section, names] of Object.entries(ids)) {
        if (!SECTIONS.includes(section) || !isObj(names)) {
          report({ rule: "binding.semantic-ids", msg: `spec.semanticIds.${section} must be terms, fields, observationTypes, or actions, mapping names to identifier lists` });
          continue;
        }
        const bound = isObj(spec[section]) ? (spec[section] as Obj) : {};
        for (const [name, list] of Object.entries(names)) {
          if (!own(bound, name)) report({ rule: "binding.semantic-ids", msg: `spec.semanticIds.${section}.${name} is not bound in spec.${section}` });
          if (!Array.isArray(list) || list.length === 0) {
            report({ rule: "binding.semantic-ids", msg: `spec.semanticIds.${section}.${name} must be a non-empty list of IRDIs or absolute IRIs` });
            continue;
          }
          for (const x of list) {
            if (!(typeof x === "string" && (IRDI_RE.test(x) || absoluteIri(x)))) {
              report({ rule: "binding.semantic-ids", msg: `spec.semanticIds.${section}.${name}: ${JSON.stringify(x)} is neither an IRDI (ISO 29002-5, such as 0173-1#02-AAO677#002) nor an absolute IRI` });
            }
          }
        }
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
  const prefixes: Record<string, string> = Object.create(null); // no prototype: a prefix named "constructor" is a prefix
  const owner: Record<string, string> = Object.create(null);
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

/** Merge the schema models of several ontologies (the first range of a property wins, as for prefixes). */
export function mergeSchemaModels(models: SchemaModel[]): SchemaModel {
  const out = emptySchemaModel();
  for (const m of models) {
    for (const c of m.classes) out.classes.add(c);
    for (const key of ["parents", "declaredOn"] as const) {
      for (const [k, v] of m[key]) {
        if (!out[key].has(k)) out[key].set(k, new Set());
        for (const x of v) out[key].get(k)!.add(x);
      }
    }
    for (const [k, v] of m.range) if (!out.range.has(k)) out.range.set(k, v);
    for (const [k, v] of m.enums) if (!out.enums.has(k)) out.enums.set(k, v);
  }
  return out;
}

function ancestors(cls: string, parents: Map<string, Set<string>>): Set<string> {
  const seen = new Set<string>();
  const todo = [cls];
  while (todo.length) {
    const c = todo.pop()!;
    if (seen.has(c)) continue;
    seen.add(c);
    todo.push(...[...(parents.get(c) ?? [])].sort());
  }
  return seen;
}

/**
 * Spec 14 warnings from the owp-yaml schemas of the dependency ontologies: binding.path-domain (a path step that the
 * schemas declare on other classes than its class, or the previous step's range class) and binding.value-range
 * (a values.map code outside the enum range of the field's last property). Terms the schemas do not declare are not judged.
 */
export function bindingSemanticProblems(bindingDocs: Array<[string, unknown]>, prefixes: Record<string, string>, model: SchemaModel): Problem[] {
  const out: Problem[] = [];
  for (const [file, doc] of [...bindingDocs].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))) {
    const fields = get(doc, "spec", "fields");
    if (!isObj(fields)) continue;
    for (const field of Object.keys(fields).sort()) {
      const entry = fields[field];
      if (!isObj(entry) || !Array.isArray(entry.path)) continue;
      const cls = typeof entry.class === "string" ? expandCurie(entry.class, prefixes) : null;
      let current: string | null = cls !== null && model.classes.has(cls) ? cls : null;
      let last: string | null = null;
      for (let i = 0; i < entry.path.length; i++) {
        const step = entry.path[i];
        const prop = typeof step === "string" ? expandCurie(step, prefixes) : null;
        if (current === null || prop === null || !model.declaredOn.has(prop)) {
          last = null;
          break;
        }
        const owners = model.declaredOn.get(prop)!;
        const up = ancestors(current, model.parents);
        if (owners.size > 0 && ![...owners].some((o) => up.has(o))) {
          const where = i === 0 ? String(entry.class) : `the range of path[${i - 1}]`;
          out.push({ rule: "binding.path-domain", msg: `${file}: spec.fields.${field}.path[${i}] "${String(step)}" is not a property of ${where} (${current}); its schema declares it on ${[...owners].sort().join(", ")}` });
          last = null;
          break;
        }
        last = prop;
        const rng = model.range.get(prop);
        current = rng !== undefined && model.classes.has(rng) ? rng : null;
      }
      const values = isObj(entry.values) ? entry.values : undefined;
      const rng = last !== null ? model.range.get(last) : undefined;
      const enumValues = rng !== undefined ? model.enums.get(rng) : undefined;
      if (enumValues && values && isObj(values.map)) {
        const outside = Object.keys(values.map).filter((k) => !enumValues.has(k)).sort();
        if (outside.length) {
          out.push({ rule: "binding.value-range", msg: `${file}: spec.fields.${field}.values.map codes ${outside.map((c) => JSON.stringify(c)).join(", ")} are not values of ${rng} (${[...enumValues].sort().join(", ")})` });
        }
      }
    }
  }
  return out;
}
