---
title: Docs deployment & previews
sidebar_position: 8
---

# Docs deployment & previews

DS01 documentation is built with **Docusaurus** from the content roots in this repo
(`docs-user/`, `docs-admin/`, `docs-develop/`) by the site in `website/`.

## Two sites, one source of truth

| Site | Repo | Content | URL |
|---|---|---|---|
| **Full site** | `ds01-infra` (this repo) | all three pillars | `https://hertie-data-science-lab.github.io/ds01-infra/` |
| **End-user site** | `ds01-hub` | `docs-user/` only (synced) | `https://hertie-data-science-lab.github.io/ds01/` |

The end-user site is a separate Docusaurus build in `ds01-hub`, fed by
`sync-docs-to-hub.yml`. See that repo for its deploy workflow.

## Production (GitHub Pages)

`.github/workflows/docs.yml` builds on every docs-touching PR (build-only,
`onBrokenLinks: 'throw'` as the correctness gate) and deploys to this repo's own
GitHub Pages on push to `main` via `actions/deploy-pages`.

**One-time setup:** repo **Settings → Pages → Build and deployment → Source =
GitHub Actions**.

## Per-PR previews (Cloudflare Pages)

Previews are deployed to **Cloudflare Pages** via the CF GitHub App. Production stays
on GitHub Pages; CF handles the preview-URL surface only. The build at preview time
runs `scripts/cloudflare-build.sh`, which mirrors the production build but sets
`DOCUSAURUS_BASE_URL=/` (CF serves previews at `*.pages.dev/`, not under
`/ds01-infra/`).

**One-time setup:**

1. Create a Cloudflare account (free tier is sufficient).
2. Workers & Pages → Create application → Pages → Connect to Git → authorise the
   Cloudflare GitHub App for `hertie-data-science-lab/ds01-infra`.
3. Build settings:
   | Field | Value |
   |---|---|
   | Build command | `bash scripts/cloudflare-build.sh` |
   | Build output directory | `website/build` |
   | Root directory | `/` (default) |
   | Production branch | `main` |
4. Node/`.nvmrc` is read automatically (pinned to `20`); no env vars required.

No GitHub Actions secrets are needed — the GitHub App handles auth. Open or push to a
docs PR and the CF App comments a `*.pages.dev` preview URL once the build completes.

## Local preview

```bash
make docs-serve     # docusaurus start (live reload from the content roots)
make docs-build     # production build
make docs-check     # build with the broken-link gate (mirrors CI)
```
