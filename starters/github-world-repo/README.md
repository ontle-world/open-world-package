# OWP World Repository Starter

Use this directory as the root of a standalone GitHub repository for one World package.

Install ONTLE from an immutable release source, then validate and pack:

```bash
# From PyPI (alpha releases need --pre):
python -m pip install --pre ontle

# Or install from a tagged source release:
# python -m pip install "git+https://github.com/<org>/<ontle-repo>.git@<tag>"

ontle validate .
ontle pack .
```

The workflow under `.github/workflows/owp-ci.yml` installs `ontle` from PyPI. Pin a version (`ontle==<version>`) so CI results do not change when a new release comes out.
