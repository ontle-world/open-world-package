# GitHub Public Release Checklist

Repository contents are designed to be publishable as-is. Before making the repository public, confirm the organization-level settings that cannot live in the ZIP:

- [ ] Choose the final GitHub repository name and description.
- [ ] Enable Issues and private vulnerability reporting if desired.
- [ ] Configure branch protection / required CI checks.
- [ ] Confirm organization contact/security route.
- [ ] Confirm trademark/branding text with counsel if a stronger policy is needed.
- [ ] Create the first tag after CI passes.
- [ ] If publishing to PyPI later, configure Trusted Publishing separately.
- [ ] If publishing OWP archives to a hosted Registry/OCI transport later, configure credentials separately.

No hosted Registry, external credentials, or customer data are required for the current public-alpha repository.

- [ ] Business and Physical AI examples follow the common package skeleton.
- [ ] Generic and multimodal WorldModel starters both include ModelArtifact, RepresentationAdapter, and EvaluationProfile.
- [ ] No `package.yaml`, `world.yaml`, or `worldpkg` legacy surfaces remain.
- [ ] `conformance/` suite passes and `expected.yaml` lists every case directory.
- [ ] Example World Models validate with `--resolve --source examples`, and example EWS files match `ontle ews compile` output.
