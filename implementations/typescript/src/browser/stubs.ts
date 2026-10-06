/** The browser bundle's `node:os`, `node:url`, `node:child_process`, and `node:zlib`: what the validator can do without them. */
export function tmpdir(): string { return "/tmp"; }
export function fileURLToPath(url: string): string { return String(url).replace(/^file:\/\//, ""); }
export function execFileSync(): never { throw new Error("git package sources are not available in the browser"); }
export function inflateRawSync(): never { throw new Error("archives are unpacked before validation in the browser (unzip.ts)"); }
export default { tmpdir, fileURLToPath, execFileSync, inflateRawSync };
