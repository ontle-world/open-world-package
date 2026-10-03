#!/usr/bin/env node
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { stringify } from "yaml";
import { validatePackage, ValidationResult } from "./validate.js";
import { validateWithResolution } from "./resolve.js";
import { checkEws, compileEws } from "./ews.js";
import { checkDetachedEvidence } from "./evidence.js";
import { get, loadYamlFile } from "./util.js";
import { API_VERSION } from "./vocab.js";

const USAGE = `usage:
  owp-validate [--json] [--resolve] [--source <src>]... <package-dir> [...]
  owp-validate ews check <ews.yaml> --world <world-dir> [--json]
  owp-validate ews compile <world-dir> [--compiler <path>] --observations <file> [--observations <file> ...] --as-of <timestamp>
  owp-validate evidence check <evidence.yaml> --package <archive.owp.zip> [--json]

Package sources for --resolve: each --source (directory, *.owp.zip, git+<url>@<rev>[#subdir=<p>], index:<local PackageIndex>),
then entries of $ONTLE_PATH (separated by '${path.delimiter}').
`;

function takeOpt(args: string[], name: string, multi = false): string[] {
  const out: string[] = [];
  for (let i = 0; i < args.length; ) {
    if (args[i] === name && i + 1 < args.length) {
      out.push(args[i + 1]);
      args.splice(i, 2);
      if (!multi) break;
    } else i++;
  }
  return out;
}

function takeFlag(args: string[], name: string): boolean {
  const i = args.indexOf(name);
  if (i >= 0) args.splice(i, 1);
  return i >= 0;
}

function printResult(label: string, r: ValidationResult & { resolved?: unknown[] }): void {
  const prof = r.satisfiedProfile !== undefined ? ` (declared: ${r.declaredProfile ?? "none"}, satisfied: ${r.satisfiedProfile ?? "none"})` : "";
  process.stdout.write(`${r.valid ? "VALID" : "INVALID"} ${label}${prof}\n`);
  for (const e of r.errors) process.stdout.write(`  error   [${e.code}] ${e.message}\n`);
  for (const w of r.warnings) process.stdout.write(`  warning [${w.code}] ${w.message}\n`);
  if (r.resolved) for (const p of r.resolved as Array<{ identity: string; source: string; revision?: string }>) {
    process.stdout.write(`  resolved ${p.identity} from ${p.source}${p.revision ? ` (${p.revision})` : ""}\n`);
  }
}

function ewsMain(args: string[], json: boolean): number {
  const sub = args.shift();
  if (sub === "check") {
    const world = takeOpt(args, "--world")[0];
    const file = args[0];
    if (!world || !file) return usage();
    const doc = loadYamlFile(file);
    const r = doc.ok ? checkEws(doc.value, world) : { valid: false, errors: [{ code: "ews.kind", message: `not parseable YAML: ${doc.error}` }] };
    if (json) process.stdout.write(JSON.stringify(r, null, 2) + "\n");
    else {
      process.stdout.write(`${r.valid ? "VALID" : "INVALID"} ${file}\n`);
      for (const e of r.errors) process.stdout.write(`  error   [${e.code}] ${e.message}\n`);
    }
    return r.valid ? 0 : 1;
  }
  if (sub === "compile") {
    const obsFiles = takeOpt(args, "--observations", true);
    const asOf = takeOpt(args, "--as-of")[0];
    const world = args[0];
    // Without --compiler, the World's default State Compiler (spec.world.defaultStateCompiler).
    const manifest = world ? loadYamlFile(path.join(world, "owp.yaml")) : undefined;
    const compiler = takeOpt(args, "--compiler")[0] ?? (manifest?.ok ? (get(manifest.value, "spec", "world", "defaultStateCompiler") as string | undefined) : undefined);
    if (!compiler || obsFiles.length === 0 || !asOf || !world) return usage();
    // Repeated --observations files are merged into one ObservationSet (duplicate ids stay invalid input).
    const docs = obsFiles.map((f) => loadYamlFile(f));
    const bad = docs.find((d) => !d.ok);
    const merged = docs.length === 1 && docs[0].ok ? docs[0].value : {
      apiVersion: API_VERSION,
      kind: "ObservationSet",
      spec: { observations: docs.flatMap((d) => (d.ok && Array.isArray(get(d.value, "spec", "observations")) ? (get(d.value, "spec", "observations") as unknown[]) : [])) },
    };
    const r = bad && !bad.ok ? { ok: false as const, errors: [`ews.input: ${bad.error}`] } : compileEws(world, compiler, merged, asOf);
    if (!r.ok) {
      process.stderr.write(`refused: ${r.errors.join("; ")}\n`);
      return 1;
    }
    process.stdout.write(json ? JSON.stringify(r.ews, null, 2) + "\n" : stringify(r.ews));
    return 0;
  }
  return usage();
}

/** Spec 9.1: detached CompatibilityEvidence against a package archive. */
function evidenceMain(args: string[], json: boolean): number {
  if (args.shift() !== "check") return usage();
  const archive = takeOpt(args, "--package")[0];
  const file = args[0];
  if (!archive || !file) return usage();
  const doc = loadYamlFile(file);
  const cacheDir = path.resolve(process.env.OWP_CACHE_DIR ?? path.join(path.dirname(fileURLToPath(import.meta.url)), "..", ".owp-cache"));
  const r = doc.ok
    ? checkDetachedEvidence(doc.value, archive, cacheDir)
    : { valid: false, errors: [{ code: "evidence.detached-subject", message: `${file} is not parseable YAML: ${doc.error}` }] };
  if (json) process.stdout.write(JSON.stringify(r, null, 2) + "\n");
  else {
    process.stdout.write(`${r.valid ? "VALID" : "INVALID"} ${file} (subject ${archive})\n`);
    for (const e of r.errors) process.stdout.write(`  error   [${e.code}] ${e.message}\n`);
  }
  return r.valid ? 0 : 1;
}

function usage(): number {
  process.stderr.write(USAGE);
  return 2;
}

function main(argv: string[]): number {
  const args = [...argv];
  if (args.includes("--help") || args.includes("-h") || args.length === 0) return usage();
  const json = takeFlag(args, "--json");
  if (args[0] === "ews") return ewsMain(args.slice(1), json);
  if (args[0] === "evidence") return evidenceMain(args.slice(1), json);
  const resolve = takeFlag(args, "--resolve");
  const sources = takeOpt(args, "--source", true);
  if (process.env.ONTLE_PATH) sources.push(...process.env.ONTLE_PATH.split(path.delimiter).filter(Boolean));
  if (args.length === 0) return usage();

  let allValid = true;
  const results = args.map((d) => ({ package: d, ...(resolve ? validateWithResolution(d, { sources }) : validatePackage(d)) }));
  for (const r of results) allValid &&= r.valid;
  if (json) process.stdout.write(JSON.stringify(results.length === 1 ? results[0] : results, null, 2) + "\n");
  else {
    for (const r of results) {
      printResult(r.package, r);
      const manifest = loadYamlFile(path.join(r.package, "owp.yaml"));
      const deps = manifest.ok ? get(manifest.value, "spec", "dependencies") : undefined;
      if (!resolve && r.valid && Array.isArray(deps) && deps.length > 0) {
        process.stdout.write("  note    this package only; cross-package rules (grounding, dependency direction) need --resolve --source <dir|zip>\n");
      }
    }
  }
  return allValid ? 0 : 1;
}

process.exitCode = main(process.argv.slice(2));
