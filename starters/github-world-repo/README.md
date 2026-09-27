# OWP World Repository Starter

Use this directory as the root of a standalone GitHub repository for one World package.

Install ONTLE from an immutable release source, then validate and pack:

```bash
# After a package index release:
python -m pip install ontle-open-world

# Or install from a tagged source release:
# python -m pip install "git+https://github.com/<org>/<ontle-repo>.git@<tag>"

ontle validate .
ontle pack .
```

The workflow under `.github/workflows/owp-ci.yml` assumes `ontle-open-world` is available from the configured Python package index. Before that distribution channel exists, replace the install step with your immutable tagged Git source.
