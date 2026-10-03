// The command-line behaviour the Python tests check for `ontle` (tests/test_first_hour.py), for owp-validate:
// compiling with the World's default State Compiler, saying when cross-package rules were not checked, and
// listing a World's Views in a grounding error.
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { parse } from "yaml";
import { ewsEqual } from "../dist/ews.js";

const here = path.dirname(fileURLToPath(import.meta.url));
const repo = path.resolve(here, "..", "..", "..");
const cli = path.join(here, "..", "dist", "cli.js");
const env = { ...process.env, ONTLE_PATH: "" };
const run = (...args) => spawnSync(process.execPath, [cli, ...args], { encoding: "utf8", env });

let bad = 0;
const check = (name, ok, detail = "") => {
  process.stdout.write(`${ok ? "PASS" : "FAIL"} cli: ${name}${ok ? "" : `\n  ${detail}`}\n`);
  if (!ok) bad++;
};

// ews compile without --compiler uses spec.world.defaultStateCompiler.
const starter = path.join(repo, "starters", "github-world-repo");
const c = run("ews", "compile", starter, "--observations", path.join(starter, "examples", "observations.yaml"), "--as-of", "2026-01-02T00:00:00Z");
const expected = parse(fs.readFileSync(path.join(starter, "examples", "expected-ews.yaml"), "utf8"));
check("ews compile defaults to the World's State Compiler", c.status === 0 && ewsEqual(parse(c.stdout), expected).equal, c.stderr || c.stdout);

// Without --resolve, a package with dependencies says that cross-package rules were not checked.
const model = path.join(repo, "examples", "business", "quality-scenario-world-model");
const v = run(model);
check("validate notes unchecked grounding", v.status === 0 && v.stdout.includes("cross-package rules (grounding, dependency direction) need --resolve"), v.stdout + v.stderr);

// A grounding error names the World's Views.
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "owp-cli-"));
fs.cpSync(model, path.join(tmp, "m"), { recursive: true });
const manifest = path.join(tmp, "m", "owp.yaml");
fs.writeFileSync(manifest, fs.readFileSync(manifest, "utf8").replaceAll("#views/quality-incident-task.yaml", "#views/quality-incident.yaml"));
const g = run("--resolve", "--source", path.join(repo, "examples"), path.join(tmp, "m"));
check("grounding error lists the World's Views", g.status === 1 && g.stdout.includes("its Views: views/quality-incident-task.yaml"), g.stdout + g.stderr);
fs.rmSync(tmp, { recursive: true, force: true });

process.exitCode = bad ? 1 : 0;
