# OWP — Experimental profiles (informative)

Part of the Open World Package specification; section numbers are shared across its documents (see the document map in `OWP_SPEC.md`). Everything here may change or be removed; checks produce warnings only.

## Appendix C. Experimental asset kinds and fields (informative)

The work, actor, artifact, and knowledge kinds that were here are standard since this alpha (sections 16-19). What remains experimental is below. A validator reports `asset.kind-experimental` for each use of an experimental kind and checks it against `schemas/experimental/` with warnings only (`experimental.field`, `experimental.value`, `experimental.reference`). Extension rules (section 13) still apply and remain errors.

| Kind | Purpose | Main fields |
|---|---|---|
| `ArtifactTemplate` | template for an artifact contract | `artifactContractRef` (ArtifactContract), `format`, `content` (`path` or ExternalRef) |

ArtifactTemplate stays experimental until it is used in example packages of three domains (`docs/PROFILE_PROMOTION.md`).

**World View specialization.** A WorldViewProfile MAY declare the experimental fields `spec.specializes` (the local path of another WorldViewProfile) and `spec.projection.exclude`. The resolved View is the base View's resolved spec with: `projection.include` = base include ∪ include − exclude; `purpose` and `conditioning` overridden key by key; other fields replaced. `specializes` naming anything other than a local WorldViewProfile, or a cycle, is `experimental.reference`. State Compilers keep binding to the specialized View's own path. The reference CLI shows resolved Views with `ontle inspect --resolved-views`.

**World View composition.** A WorldViewProfile MAY declare the experimental field `spec.composes`, a non-empty list of local WorldViewProfile paths. The resolved View has: `projection.include` = the union of the composed Views' resolved includes, in list order, ∪ its own include − its own exclude; `conditioning` and the other `projection` keys taken from the composed Views (the first View that sets a key wins), then overridden key by key by its own; `purpose` and the other fields its own. Composition is the union; filtering is `projection.exclude`, and overriding is `specializes`. Warnings: an entry that is not a local WorldViewProfile, or a cycle through `composes` and `specializes`, is `experimental.reference`; `composes` that is not a non-empty list of strings, a composed View without its own non-empty `purpose`, `composes` and `specializes` in the same View (it then resolves by `specializes`), and composed Views that disagree on a `conditioning` or `projection` key the View does not set itself, are `experimental.field`.

**Reference graph.** `ontle inspect --graph` lists the package, its assets, and the references between them with informative relation names (`contains`, `depends_on`, `uses_extension`, `grounded_in`, `valid_for_view`, `valid_for_compiler`, `uses_adapter`, `compiles_view`, `specializes`, `composes`, `uses_pattern`, `requires_view`, `requires_knowledge`, `produces_artifact`, `evaluated_by`, `template_for`, `represents_view`, `consumes_contract`, `conforms_to`, `evidences`, `for_actor`, `for_role`, `for_task`, `occupies_role`, `assigned_role`, `assigned_task`, `has_capability`, `implemented_by`, `member_of`, `delegated_by`, `delegated_to`, `produces_contract`, `evaluates`, `evaluated_by_actor`, `baseline`, `uses_engine`, `performed_by`, `may_use_scenario`). These names are not part of the package contract.

### C.1 Experimental fields of standard kinds

| Kind | Experimental fields | Checks (warnings) |
|---|---|---|
| `WorldViewProfile` | `specializes`, `projection.exclude` (View specialization, above); `composes` (View composition, above) | `specializes` and `composes` name local WorldViewProfiles, without cycles |

View specialization stays experimental while View composition is open: a View built from several Views (union, filter, overlay) may replace or generalize it.
