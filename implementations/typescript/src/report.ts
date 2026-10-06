/**
 * Package reports (informative, schemas/package-report.schema.json): what a catalog or registry shows for a
 * package, derived from the package itself. The same as the reference CLI's `ontle inspect --report`, except
 * `validator` and the wording of errors and warnings; scripts/report_parity.py compares the two.
 */
import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { localAssetKinds, packageDocuments } from "./discovery.js";
import { loadArchive } from "./resolve.js";
import { ontologyTerms } from "./rules/ontology.js";
import { outputSchemaFields } from "./rules/world.js";
import { get, isObj, loadYamlFile, Obj, packageFile } from "./util.js";
import { validatePackage } from "./validate.js";
import { readZip } from "./zip.js";

declare const __OWP_VERSION__: string | undefined; // set by scripts/bundle.mjs: the browser has no package.json to read
const VERSION = (() => {
  if (typeof __OWP_VERSION__ === "string") return __OWP_VERSION__;
  try {
    return String(JSON.parse(fs.readFileSync(new URL("../package.json", import.meta.url), "utf8")).version);
  } catch {
    return "unknown";
  }
})();
export const CARD_SECTIONS = ["Scope", "Sources", "Use it for", "Limitations", "Versions"];
const DEFAULT_CARDS: Record<string, string> = { WorldPackage: "WORLD.md", WorldModelPackage: "WORLDMODEL.md", OntologyPackage: "ONTOLOGY.md" };
const CARD_SPEC_KEY: Record<string, string> = { WorldPackage: "world", WorldModelPackage: "worldModel", OntologyPackage: "ontology" };
const DESCRIPTION_LIMIT = 160;
const COMMIT_RE = /^(?:[0-9a-f]{40}|[0-9a-f]{64})$/;
// Text the init templates ship for the author to replace (src/ontle/templates/*).
const TEMPLATE_DESCRIPTION = /^One line on (the|what) /;
const TEMPLATE_CARD_TEXT = ["Describe in one paragraph", "Add included entities", "Add intentional exclusions", "Three to five "];
const CARD_PATH = /`([A-Za-z0-9_.-]+\/[A-Za-z0-9_./-]*\.(?:ya?ml|json|md|ttl|csv|py))`/g;

const obj = (v: unknown): Obj => (isObj(v) ? v : {});
const list = (v: unknown): unknown[] => (Array.isArray(v) ? v : []);
const has = (o: Obj, k: string): boolean => Object.prototype.hasOwnProperty.call(o, k);
const chars = (s: string): number => [...s].length; // code points, as Python's len

/** An ExternalRef is pinned by a digest, or by a commit-hash revision for git and Hugging Face (spec 5.1). */
export function isPinned(ref: Obj): boolean {
  return typeof ref.digest === "string" ||
    ((ref.provider === "git" || ref.provider === "huggingface") && typeof ref.revision === "string" && COMMIT_RE.test(ref.revision));
}

/** Second-level headings of a card, as written. */
export function cardSections(text: string): string[] {
  return [...text.matchAll(/^##[ \t]+(.+?)[ \t#]*$/gm)].map((m) => m[1].trim());
}

const bound = (ref: unknown): ref is Obj => isObj(ref) && (ref.status === undefined || ref.status === null || ref.status === "bound");

/** PackageReport for a package directory or .owp.zip archive. */
export function packageReport(target: string): Obj {
  const abs = path.resolve(target);
  if (!(fs.existsSync(abs) && fs.statSync(abs).isFile())) return report(abs);
  const cache = fs.mkdtempSync(path.join(os.tmpdir(), "owp-report-"));
  try {
    const cand = loadArchive(abs, cache, target);
    if (!cand || cand.error) throw new Error(`${target} does not verify: ${cand?.error ?? "unreadable"}`);
    const data = fs.readFileSync(abs);
    const out = report(cand.dir);
    out.integrity = {
      digest: `sha256:${createHash("sha256").update(data).digest("hex")}`,
      size: data.length,
      files: readZip(data).length,
      signatureBundle: fs.existsSync(`${abs}.sigstore.json`),
    };
    return out;
  } finally {
    fs.rmSync(cache, { recursive: true, force: true });
  }
}

function report(root: string): Obj {
  const result = validatePackage(root);
  const loaded = loadYamlFile(path.join(root, "owp.yaml"));
  if (!loaded.ok || !isObj(loaded.value)) throw new Error(`cannot read ${path.join(root, "owp.yaml")}`);
  const manifest = loaded.value;
  const kind = typeof manifest.kind === "string" ? manifest.kind : "";
  const md = obj(manifest.metadata);
  const declared = get(manifest, "spec", "conformance", "profile"); // as written: the report shows the declaration, valid or not
  const spec = obj(manifest.spec);
  const identity = `${md.namespace ?? "?"}/${md.name ?? "?"}@${md.version ?? "?"}`;
  const kinds = localAssetKinds(root, manifest);
  const docs = new Map<string, unknown>();
  for (const d of packageDocuments(root)) if (d.ok && kinds.has(d.rel)) docs.set(d.rel, d.value); // assets only, as Python's local_assets
  const specOf = (rel: string): Obj => obj(get(docs.get(rel), "spec"));

  const byKind: Record<string, number> = {};
  for (const k of kinds.values()) byKind[k] = (byKind[k] ?? 0) + 1;
  for (const a of list(spec.assets)) {
    if (isObj(a) && isObj(a.ref) && typeof a.kind === "string") byKind[a.kind] = (byKind[a.kind] ?? 0) + 1;
  }
  const errors = result.errors.map((e) => `${e.code}: ${e.message}`);
  const warnings = result.warnings.map((w) => `${w.code}: ${w.message}`);
  const out: Obj = {
    kind: "PackageReport",
    identity,
    packageKind: manifest.kind,
    validator: { implementation: "owp-validator-ts", version: VERSION },
    valid: result.valid,
    errors,
    warnings,
    warningIds: [...new Set(result.warnings.map((w) => w.code))].sort(),
    metadata: Object.fromEntries(["title", "description", "license"].filter((k) => typeof md[k] === "string").map((k) => [k, md[k]])),
    domains: list(spec.domains).filter((d) => typeof d === "string"),
    assets: {
      total: Object.values(byKind).reduce((a, b) => a + b, 0),
      byKind: Object.fromEntries(Object.entries(byKind).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))),
    },
  };

  if (kind === "WorldPackage") {
    out.profile = { declared: typeof declared === "string" ? declared : "descriptive", satisfied: result.satisfiedProfile ?? null };
    const fields = new Set<string>();
    const boundFields = new Set<string>();
    let compilers = 0;
    for (const [rel, k] of kinds) {
      if (k !== "StateCompilerProfile") continue;
      compilers++;
      const listed = outputSchemaFields(root, specOf(rel), rel).fields ?? [];
      const bindings = obj(specOf(rel).bindings);
      for (const f of listed) {
        fields.add(f);
        if (has(bindings, f)) boundFields.add(f);
      }
    }
    out.state = { stateCompilers: compilers, fields: fields.size, withBinding: boundFields.size };
    const bindingRel = get(spec, "world", "semanticBinding");
    if (typeof bindingRel === "string") {
      const semantic = Object.keys(obj(specOf(bindingRel).fields));
      out.semanticCoverage = { boundToTerms: semantic.filter((f) => fields.has(f)).length, fields: fields.size };
    }
  } else if (kind === "OntologyPackage") {
    out.profile = { declared: typeof declared === "string" ? declared : null, satisfied: result.satisfiedProfile ?? null };
    out.ontology = { terms: ontologyTerms(root, manifest).terms.size };
  }

  const refs: Obj[] = [];
  for (const a of list(spec.assets)) if (isObj(a) && bound(a.ref)) refs.push(a.ref);
  for (const imp of list(get(spec, "ontology", "externalImports"))) if (isObj(imp) && bound(imp.ref)) refs.push(imp.ref);
  const standards = new Set<string>();
  let boundRefs = 0;
  let licensedRefs = 0;
  for (const [rel, k] of [...kinds].sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))) {
    const aspec = specOf(rel);
    if (k === "KnowledgeAsset" || k === "Dataset") {
      const content = get(aspec, "content", "ref");
      if (bound(content)) refs.push(content);
    }
    for (const b of Object.values(obj(aspec.standardBindings))) {
      if (!isObj(b)) continue;
      if (typeof b.standard === "string") standards.add(b.standard);
      if (bound(b.ref)) {
        refs.push(b.ref);
        boundRefs++;
        if (typeof b.license === "string") licensedRefs++;
      }
    }
  }
  const pinned = refs.filter(isPinned).length;
  out.externalRefs = { total: refs.length, pinned };
  out.standardBindings = { standards: [...standards].sort(), boundRefs, licensedRefs };

  const evidence = [...kinds].filter(([, k]) => k === "CompatibilityEvidence").map(([rel]) => specOf(rel));
  out.evidence = {
    included: evidence.length,
    subjects: [...new Set(evidence.map((e) => e.subject).filter((s): s is string => typeof s === "string"))].sort(),
    statuses: [...new Set(evidence.map((e) => get(e, "result", "status")).filter((s): s is string => typeof s === "string"))].sort(),
  };

  const hints: string[] = [];
  const description = md.description;
  if (typeof description !== "string" || description.trim() === "") {
    hints.push("metadata.description is missing: catalogs show it as the package's one-line summary");
  } else if (chars(description) > DESCRIPTION_LIMIT) {
    hints.push(`metadata.description has ${chars(description)} characters; catalogs show about ${DESCRIPTION_LIMIT}`);
  } else if (TEMPLATE_DESCRIPTION.test(description)) {
    hints.push("metadata.description is still the template text");
  }
  if (typeof md.license !== "string") hints.push("metadata.license is missing");
  const declaredCard = get(spec, CARD_SPEC_KEY[kind] ?? "", "description");
  const cardRel = typeof declaredCard === "string" && declaredCard.endsWith(".md") ? declaredCard : DEFAULT_CARDS[kind];
  const cardFile = cardRel ? packageFile(root, cardRel) : null;
  if (cardRel && cardFile !== null && fs.statSync(cardFile).isFile()) {
    const cardText = fs.readFileSync(cardFile, "utf8");
    const present = cardSections(cardText);
    const lowered = new Set(present.map((s) => s.toLowerCase()));
    const missing = CARD_SECTIONS.filter((s) => !lowered.has(s.toLowerCase()));
    out.card = { path: cardRel, sections: present, missingRecommended: missing };
    if (missing.length) hints.push(`${cardRel} has no section ${missing.join(", ")} (recommended card sections: ${CARD_SECTIONS.join(", ")})`);
    if (TEMPLATE_CARD_TEXT.some((t) => cardText.includes(t))) hints.push(`${cardRel} still has template text to replace`);
    const named = [...new Set([...cardText.matchAll(CARD_PATH)].map((m) => m[1]))].sort();
    // Only paths under a directory the package has: a World Model card may name files of the World it is grounded in.
    const absent = named.filter((p) => {
      const top = path.join(root, p.split("/")[0]);
      if (!(fs.existsSync(top) && fs.statSync(top).isDirectory())) return false;
      const abs = packageFile(root, p);
      return abs === null || !fs.existsSync(abs);
    });
    if (absent.length) hints.push(`${cardRel} names files that are not in the package: ${absent.join(", ")}`);
  } else if (cardRel) {
    hints.push(`no card ${cardRel}`);
  }
  const unpinned = refs.length - pinned;
  if (unpinned) hints.push(`${unpinned} external ${unpinned === 1 ? "reference is" : "references are"} not pinned (ontle lock pins https references)`);
  out.hints = hints;
  return out;
}
