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

That's it — no `PYPI_API_TOKEN` secret needed once the two steps above match **exactly** (a single
character off — org case, workflow filename, environment name — makes PyPI reject the OIDC token).

The publish step already reads `password: ${{ secrets.PYPI_API_TOKEN }}`. That input is a **safety
net, not a requirement**: with no such secret it expands to an empty string and the action falls
back to Trusted Publishing (OIDC). So OIDC is the default, and a token only kicks in if you add one.

## If Trusted Publishing fails (OIDC 403 / "not a trusted publisher")

This is almost always a **registration mismatch**, not a code problem — the workflow YAML is correct.
Check, in order:

1. **The pending/trusted publisher on PyPI matches the table above verbatim** — Owner `QJTrader`
   (case-sensitive), Repository `qjtrader-python`, Workflow `publish.yml` (filename only, no path),
   Environment `pypi`. Re-add it if the project already existed when you first tried to publish
   (a *pending* publisher only applies to projects that don't exist yet).
2. **The `pypi` GitHub environment exists** in *Settings → Environments*. If a required reviewer is
   set, the run pauses for approval — that looks like a "stuck" publish, not a failure.
3. **You pushed the tag to `QJTrader/qjtrader-python`** (not a fork) — OIDC is scoped to that repo.

**Unblock immediately without solving OIDC:** add a project-scoped PyPI API token as the repo secret
`PYPI_API_TOKEN` (*Settings → Secrets and variables → Actions*), then re-run the workflow (it has a
`workflow_dispatch` trigger, so you don't need a new tag). The publish step uses the token
automatically. Remove the secret later once OIDC is fixed to return to no-stored-secret publishing.

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
