# Listing a package in the catalog

The [package catalog](https://ontle-world.github.io/open-world-package/catalog/) shows this repository's examples and community packages. A community package is listed in [`packages.yaml`](packages.yaml) by a pull request. Its archive stays where you publish it; the catalog shows its card and report, links to your source, and serves the archive you listed, unchanged. Each listed package resolves through the catalog's index, like the examples: `--source index:https://ontle-world.github.io/open-world-package/catalog/index.json`.

There is no upload server yet. A reviewed list keeps it simple until there is a need for one.

## Steps

1. Check and pack the package:

   ```bash
   ontle validate --resolve .
   ontle inspect . --report          # fix what the hints point at: description, card sections, pinned references
   ontle pack . --output dist/
   ontle inspect dist/<archive>.owp.zip --report   # integrity.digest is the digest to list
   ```

2. Publish the archive at a stable https URL that will not change, such as a GitHub release asset of your repository. Do not replace a published archive: publish a new version instead.

3. Add an entry to `packages.yaml`:

   ```yaml
   - identity: acme/line-world@1.0.0
     archive: https://github.com/acme/line-world/releases/download/v1.0.0/acme-line-world-1.0.0.owp.zip
     digest: sha256:<integrity.digest>
     source: https://github.com/acme/line-world
     submittedBy: <your GitHub handle>
   ```

4. Run `python scripts/registry.py check` and open a pull request. CI runs the same check.

## What the check requires

- The archive at `archive` has exactly the listed `digest`, and verifies (`owp.lock.json`).
- Its `owp.yaml` has the listed `identity`, and `metadata.license`.
- The identity is listed once and is not the identity of an example.
- The namespace is not reserved: `openworld`, `openworld-examples`, `conformance`, `ontle`, `owp`, `scale`.
- The package validates with its dependencies resolved from the examples and the other listed packages.

The report's hints (a description, the recommended card sections, pinned references) are printed as notes. They do not fail the check, but a reviewer may ask you to address them.

## Review

A maintainer reviews the pull request. Beyond the check, the review looks at:

- The card says what the package is for and what it leaves out (`Scope`, `Use it for`, `Limitations`).
- The package does not impersonate another organization, and its data may be shared under its license.
- `source` is public and matches the package.

## Versions and removal

A new version is a new entry; keep the old one so dependents still resolve. A maintainer may remove an entry whose archive is gone or that breaks the rules above.
