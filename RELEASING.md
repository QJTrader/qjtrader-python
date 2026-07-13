# Releasing `qjtrader`

Publishing is automated: **push a version tag and GitHub Actions builds and uploads to PyPI** via
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (OIDC — no API token stored anywhere).

## One-time setup (per maintainer / repo)

1. **Create the PyPI project as a trusted publisher.** On [pypi.org](https://pypi.org) → your
   account → *Publishing* → *Add a pending publisher* (or add one to the project once it exists):
   - **PyPI Project Name:** `qjtrader`
   - **Owner:** `QJTrader`
   - **Repository name:** `qjtrader-python`
   - **Workflow name:** `publish.yml`
   - **Environment name:** `pypi`
2. **Create the `pypi` environment** in the GitHub repo (*Settings → Environments → New
   environment → `pypi`*). Optionally add required reviewers so a human approves each release.

That's it — no `PYPI_API_TOKEN` secret needed. (If you'd rather use a token, add it as the
`PYPI_API_TOKEN` secret and set `with: password: ${{ secrets.PYPI_API_TOKEN }}` on the publish step.)

## Cutting a release

1. Update the version in `src/qjtrader/_version.py` (semver).
2. Move the `CHANGELOG.md` entry from *unreleased* to the new version + date.
3. Commit, then tag and push:
   ```bash
   git commit -am "Release 0.1.0"
   git tag v0.1.0
   git push origin main --tags
   ```
4. The **Publish to PyPI** workflow builds the wheel + sdist and uploads them. Confirm at
   https://pypi.org/project/qjtrader/ and test `pip install qjtrader`.

## Manual publish (fallback)

```bash
python -m build
python -m pip install twine
twine upload dist/*      # prompts for a PyPI API token
```

## Versioning

- `0.x` while the API surface may still change; `1.0` once it's stable.
- The wire protocol is versioned separately by the service (`"v"` in the hello messages); the SDK
  targets protocol v1.
