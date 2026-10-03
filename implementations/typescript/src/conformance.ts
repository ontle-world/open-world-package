#!/usr/bin/env node
/**
 * Runs the language-neutral OWP conformance suite (all sections present in expected.yaml):
 *   cases           cases/<id>/                              spec 6.1, 8, 9
 *   resolutionCases resolution/<id>/root + /packages           spec 11
 *   ewsCases        ews/<id>/world, observations.yaml, expected-ews.yaml   spec 12.2
 *   ewsCheckCases   ews-check/<id>/world, ews.yaml              spec 12.1
 *   extractionCases extraction/<id>/profile.yaml, results.json, expected-observations.yaml   Appendix C.1
 * usage: node dist/conformance.js [--suite <dir>] [--section <name>] [--verbose] [--json]
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { validatePackage } from "./validate.js";
import { validateWithResolution } from "./resolve.js";
import { canon, checkEws, compileEws, ewsEqual } from "./ews.js";
import { transformExtraction } from "./extraction.js";
import { isObj, loadYamlFile } from "./util.js";

interface Row {
  section: string;
  id: string;
  expected: string;
  got: string;
  ok: boolean;
  details: string[];
}

/** ids: reported error rule ids; warnIds: reported warning ids (when the section reports warnings). */
type RunOut = Omit<Row, "section" | "id"> & { ids: string[]; warnIds?: string[] };
type Runner = (dir: string, id: string, exp: Record<string, unknown>) => RunOut;

const idOf = (m: string) => m.split(": ")[0];

const fmt = (v: unknown) => (v === undefined ? "-" : v === null ? "null" : String(v));

const runCase: Runner = (dir, id, exp) => {
  const r = validatePackage(path.join(dir, "cases", id));
  const checkProfile = Object.prototype.hasOwnProperty.call(exp, "satisfiedProfile");
  let ok = r.valid === exp.valid;
  if (checkProfile) ok &&= (r.satisfiedProfile ?? null) === (exp.satisfiedProfile ?? null);
  return {
    expected: `valid=${fmt(exp.valid)}` + (checkProfile ? ` profile=${fmt(exp.satisfiedProfile)}` : ""),
    got: `valid=${fmt(r.valid)}` + (checkProfile ? ` profile=${fmt(r.satisfiedProfile ?? null)}` : ""),
    ok,
    details: [...r.errors.map((e) => `[${e.code}] ${e.message}`), ...r.warnings.map((w) => `warning [${w.code}] ${w.message}`)],
    ids: r.errors.map((e) => e.code),
    warnIds: r.warnings.map((w) => w.code),
  };
};

let cacheDir: string;
const runResolution: Runner = (dir, id, exp) => {
  const base = path.join(dir, "resolution", id);
  const r = validateWithResolution(path.join(base, "root"), { sources: [path.join(base, "packages")], cacheDir });
  // `resolved`: every package of the closure except the root, with its recorded revision (null: none).
  const checkResolved = isObj(exp.resolved);
  const recorded = canon(Object.fromEntries(r.resolved.map((p) => [p.identity, p.revision ?? null])));
  const revisionsOk = !checkResolved || recorded === canon(exp.resolved);
  return {
    expected: `valid=${fmt(exp.valid)}` + (checkResolved ? ` resolved=${canon(exp.resolved)}` : ""),
    got: `valid=${fmt(r.valid)}` + (checkResolved ? ` resolved=${recorded}` : ""),
    ok: r.valid === exp.valid && revisionsOk,
    details: [
      ...r.errors.map((e) => `[${e.code}] ${e.message}`),
      ...r.resolved.map((p) => `resolved ${p.identity}${p.revision ? ` ${p.revision}` : ""}`),
    ],
    ids: r.errors.map((e) => e.code),
    warnIds: r.warnings.map((w) => w.code),
  };
};

const runEws: Runner = (dir, id, exp) => {
  const base = path.join(dir, "ews", id);
  const obs = loadYamlFile(path.join(base, "observations.yaml"));
  const r = obs.ok
    ? compileEws(path.join(base, "world"), String(exp.compiler), obs.value, String(exp.asOf))
    : { ok: false as const, errors: [`ews.input: ${obs.error}`] };
  const ids = r.ok ? [] : r.errors.map(idOf);
  if (exp.error === true) {
    return { expected: "refuse", got: r.ok ? "compiled" : "refused", ok: !r.ok, details: r.ok ? [] : r.errors, ids };
  }
  if (!r.ok) return { expected: "equal EWS", got: "refused", ok: false, details: r.errors, ids };
  const want = loadYamlFile(path.join(base, "expected-ews.yaml"));
  if (!want.ok) return { expected: "equal EWS", got: "no expected-ews.yaml", ok: false, details: [want.error], ids };
  const eq = ewsEqual(r.ews, want.value);
  return { expected: "equal EWS", got: eq.equal ? "equal EWS" : "different EWS", ok: eq.equal, details: eq.diffs, ids };
};

const runEwsCheck: Runner = (dir, id, exp) => {
  const base = path.join(dir, "ews-check", id);
  const doc = loadYamlFile(path.join(base, "ews.yaml"));
  const r = doc.ok ? checkEws(doc.value, path.join(base, "world")) : { valid: false, errors: [{ code: "ews.kind", message: `not parseable YAML: ${doc.error}` }] };
  return {
    expected: `valid=${fmt(exp.valid)}`,
    got: `valid=${fmt(r.valid)}`,
    ok: r.valid === exp.valid,
    details: r.errors.map((e) => `[${e.code}] ${e.message}`),
    ids: r.errors.map((e) => e.code),
  };
};

const runExtraction: Runner = (dir, id, exp) => {
  const base = path.join(dir, "extraction", id);
  const profile = loadYamlFile(path.join(base, "profile.yaml"));
  let rows: unknown;
  try {
    rows = JSON.parse(fs.readFileSync(path.join(base, "results.json"), "utf8"));
  } catch (e) {
    return { expected: "-", got: "unreadable results.json", ok: false, details: [(e as Error).message], ids: [] };
  }
  if (!profile.ok) return { expected: "-", got: "unreadable profile.yaml", ok: false, details: [profile.error], ids: [] };
  const params = isObj(exp.parameters) ? exp.parameters : {};
  const snapshot = typeof exp.snapshot === "string" ? exp.snapshot : undefined;
  const r = transformExtraction(profile.value, rows, params, snapshot);
  const ids = r.ok ? [] : r.errors.map(idOf);
  if (exp.error === true) {
    return { expected: "refuse", got: r.ok ? "extracted" : "refused", ok: !r.ok, details: r.ok ? [] : r.errors, ids };
  }
  if (!r.ok) return { expected: "equal ObservationSet", got: "refused", ok: false, details: r.errors, ids };
  const want = loadYamlFile(path.join(base, "expected-observations.yaml"));
  if (!want.ok) return { expected: "equal ObservationSet", got: "no expected-observations.yaml", ok: false, details: [want.error], ids };
  // Spec 12: JSON value equality (canonical JSON with sorted keys; numbers compare numerically).
  const equal = canon(r.observations) === canon(want.value);
  return {
    expected: "equal ObservationSet",
    got: equal ? "equal ObservationSet" : "different ObservationSet",
    ok: equal,
    details: equal ? [] : [`got:  ${canon(r.observations)}`, `want: ${canon(want.value)}`],
    ids,
  };
};

/** Section name -> [fixture subdirectory, runner]. Extend here for new sections. */
const SECTIONS: Record<string, [string, Runner]> = {
  cases: ["cases", runCase],
  resolutionCases: ["resolution", runResolution],
  ewsCases: ["ews", runEws],
  ewsCheckCases: ["ews-check", runEwsCheck],
  extractionCases: ["extraction", runExtraction],
};

function arg(name: string): string | undefined {
  const i = process.argv.indexOf(name);
  return i >= 0 ? process.argv[i + 1] : undefined;
}

function main(): number {
  const here = path.dirname(fileURLToPath(import.meta.url));
  const suite = path.resolve(arg("--suite") ?? process.env.OWP_CONFORMANCE_DIR ?? path.join(here, "..", "..", "..", "conformance"));
  const only = arg("--section");
  const verbose = process.argv.includes("--verbose");
  const asJson = process.argv.includes("--json");
  const cacheParent = path.resolve(process.env.OWP_CACHE_DIR ?? path.join(here, "..", ".owp-cache"));
  fs.mkdirSync(cacheParent, { recursive: true });
  cacheDir = fs.mkdtempSync(path.join(cacheParent, "conformance-"));

  const doc = parse(fs.readFileSync(path.join(suite, "expected.yaml"), "utf8")) as Record<string, unknown>;
  // reference-ids.json: every id the reference implementations report; this implementation must report exactly these.
  const refFile = path.join(suite, "reference-ids.json");
  const reference = fs.existsSync(refFile)
    ? (JSON.parse(fs.readFileSync(refFile, "utf8")) as Record<string, Record<string, { errors: string[]; warnings: string[] }>>)
    : undefined;
  const rows: Row[] = [];
  const unlisted: string[] = [];
  for (const [section, [subdir, run]] of Object.entries(SECTIONS)) {
    if (only && only !== section) continue;
    const cases = doc[section] as Record<string, Record<string, unknown>> | undefined;
    if (!cases) continue;
    for (const [id, exp] of Object.entries(cases)) {
      let row: RunOut;
      try {
        row = run(suite, id, exp);
      } catch (e) {
        row = { expected: "-", got: "exception", ok: false, details: [(e as Error).stack ?? String(e)], ids: [] };
      }
      // Appendix A: expected error and warning ids must be subsets of the reported ids.
      for (const [key, label, have] of [
        ["errors", "ids", row.ids],
        ["warnings", "warnings", row.warnIds ?? []],
      ] as const) {
        const want = Array.isArray(exp[key]) ? (exp[key] as string[]) : [];
        if (!want.length) continue;
        const missing = want.filter((x) => !have.includes(x));
        row.expected += ` ${label}⊇[${want.join(",")}]`;
        if (missing.length) {
          row.ok = false;
          row.got += ` missing ${label} [${missing.join(",")}]`;
        }
      }
      const ref = reference?.[section]?.[id];
      if (reference?.[section] && row.got !== "exception") {
        const uniq = (xs: string[]) => [...new Set(xs)].sort();
        const same = (a: string[], b: string[]) => JSON.stringify(uniq(a)) === JSON.stringify(uniq(b));
        if (!ref) {
          row.ok = false;
          row.got += " (not in reference-ids.json)";
        } else if (!same(row.ids, ref.errors) || !same(row.warnIds ?? [], ref.warnings)) {
          row.ok = false;
          row.got += ` ids differ from reference-ids.json: errors [${uniq(row.ids).join(",")}] warnings [${uniq(row.warnIds ?? []).join(",")}]`;
        }
      }
      const { ids: _ids, warnIds: _warnIds, ...rest } = row;
      rows.push({ section, id, ...rest });
    }
    const fixtures = path.join(suite, subdir);
    if (fs.existsSync(fixtures)) {
      for (const d of fs.readdirSync(fixtures)) {
        if (fs.statSync(path.join(fixtures, d)).isDirectory() && !(d in cases)) unlisted.push(`${subdir}/${d}`);
      }
    }
  }
  fs.rmSync(cacheDir, { recursive: true, force: true });

  const bySection = new Map<string, { pass: number; total: number }>();
  for (const r of rows) {
    const s = bySection.get(r.section) ?? { pass: 0, total: 0 };
    s.total++;
    if (r.ok) s.pass++;
    bySection.set(r.section, s);
  }
  const passed = rows.filter((r) => r.ok).length;

  if (asJson) {
    process.stdout.write(JSON.stringify({ suite: doc.suite, passed, total: rows.length, sections: Object.fromEntries(bySection), unlisted, rows }, null, 2) + "\n");
  } else {
    const w = Math.max(...rows.map((r) => r.id.length), 4);
    const we = Math.max(...rows.map((r) => r.expected.length), 8);
    const wg = Math.max(...rows.map((r) => r.got.length), 3);
    let current = "";
    for (const r of rows) {
      if (r.section !== current) {
        current = r.section;
        process.stdout.write(`\n== ${current}\n${"case".padEnd(w)}  ${"expected".padEnd(we)}  ${"got".padEnd(wg)}  result\n`);
      }
      process.stdout.write(`${r.id.padEnd(w)}  ${r.expected.padEnd(we)}  ${r.got.padEnd(wg)}  ${r.ok ? "PASS" : "FAIL"}\n`);
      if ((verbose || !r.ok) && r.details.length) for (const d of r.details) process.stdout.write(`    ${d}\n`);
    }
    process.stdout.write("\nSummary\n");
    for (const [s, c] of bySection) process.stdout.write(`  ${s.padEnd(16)} ${c.pass}/${c.total}\n`);
    process.stdout.write(`  ${"total".padEnd(16)} ${passed}/${rows.length}\n`);
    if (unlisted.length) process.stdout.write(`fixture directories not listed in expected.yaml: ${unlisted.join(", ")}\n`);
  }
  return passed === rows.length && unlisted.length === 0 ? 0 : 1;
}

process.exitCode = main();
