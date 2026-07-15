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

## Current setup — OIDC Trusted Publishing (active, no stored secret)

This repo publishes via **OIDC Trusted Publishing** — no API token is stored anywhere. The trusted
publisher is registered on the PyPI project (table above), so pushing a tag is all it takes. Each
release is uploaded with **PEP 740 digital attestations** (in-toto provenance), which appear in the
*Provenance* section of the PyPI project page and cryptographically link every file to this repo +
workflow. The run log's "Select PyPI credential mode" step prints `using OIDC Trusted Publishing`.

> Note: attestations are attached **at upload time** and cannot be added retroactively. A version
> that was already on PyPI when OIDC was enabled won't gain provenance — only newly uploaded
> versions do.

## Emergency fallback — scoped API token

If OIDC ever breaks (e.g. the trusted publisher is deleted), publishing without a fix would stall.
To unblock, add a **project-scoped** `PYPI_API_TOKEN` repo secret (Settings → Secrets and variables →
Actions); the workflow detects it and switches to its "Publish (scoped API token)" step
automatically. Remove the secret once OIDC is restored to return to attested, secret-free releases.
Never paste a token into chat, an issue, or a commit — if one leaks, delete it on PyPI immediately.

**Re-registering the trusted publisher** (if it's ever lost): pypi.org → *Your projects* →
`qjtrader` → *Manage* → *Publishing* → *Add a publisher*. An account-level *pending* publisher only
applies to projects that **don't exist yet**; since `qjtrader` already exists, add the publisher
from the project's own *Publishing* page (a pending publisher would be silently ignored — the usual
reason OIDC "never works").

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
