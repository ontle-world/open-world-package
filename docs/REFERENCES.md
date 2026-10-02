# Which reference goes where

OWP has six reference forms. Each one is used in fixed places, so you never have to choose between them: look up the field you are filling.

| Form | Example | Points at | Used in |
|---|---|---|---|
| Local path | `views/manager.yaml` | a file in this package | most `...Ref` fields inside assets (`worldViewRef`, `actorRef`, `subject.ref`, ...), `spec.assets[].path` (PackageExample) |
| Package reference | `acme/quality-world@1.2.0` | a whole package, exact version | `spec.dependencies[].ref`, `semanticGrounding.worldRef`, `verifierRef` (pinned form) |
| Asset in another package | `acme/quality-world@1.2.0#views/manager.yaml` | one asset of a dependency | `compatibleWorldViews`, `compatibleStateCompilers`, `subject.ref` across packages |
| CURIE | `qual:Defect` | an ontology term | SemanticBinding, ontology term index; the prefix comes from a dependency OntologyPackage (section 14) |
| Extension name | `acme-quality:LineBalancingProfile` | a publisher-defined kind or value | asset `kind`, value-set fields, ExternalRef `provider`; the prefix is the `as` name of a declared extension (section 13) |
| ExternalRef | `{provider: oci, uri: ..., digest: sha256:...}` | an artifact outside any package | `spec.assets[].ref`, `artifactRef`, `standardBindings.<name>.ref`, knowledge `content` (section 5.1) |

How to tell them apart at a glance:

- contains `#` → an asset in another package
- contains `@` but no `#` → a package
- `<word>:<Word>` with a capital letter after `:` → an extension kind; with a declared ontology prefix → a CURIE
- a mapping with `provider` → an ExternalRef
- anything else → a local path

Rules that apply to all of them:

- Versions are exact. Ranges are written only in `spec.dependencies` (section 11).
- Local paths are package-relative, use `/`, and must stay inside the package.
- A reference to something that does not exist is an error with the rule id of the field, never silently ignored.
