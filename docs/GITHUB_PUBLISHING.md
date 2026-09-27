# GitHub Publishing

## Tool repository

This repository contains the ONTLE reference CLI, OWP schemas/spec, templates, and examples. CI validates the CLI, all examples, and deterministic package creation.

## Standalone World repository

A World package can live in its own Git repository. See `starters/github-world-repo/`.

Recommended flow:

```text
Git commit
-> validate owp.yaml
-> run package-specific tests
-> deterministic ontle pack
-> verify archive digest
-> attach artifact or publish to a registry later
```

Git history is source history. OWP lineage is semantic/package lineage and should be explicit in package metadata rather than inferred from Git forks alone.
