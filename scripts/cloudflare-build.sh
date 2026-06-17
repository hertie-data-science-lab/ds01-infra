#!/usr/bin/env bash
# Cloudflare Pages build entrypoint for the DS01 full documentation site.
#
# Mirrors the production build in .github/workflows/docs.yml, but builds at the
# site root (DOCUSAURUS_BASE_URL=/) because CF Pages serves previews at
# *.pages.dev/, not under the /ds01-infra/ GitHub Pages subpath.
#
# CF Pages project settings:
#   Build command:            bash scripts/cloudflare-build.sh
#   Build output directory:   website/build
#   Root directory:           / (default)
set -euo pipefail

cd "$(dirname "$0")/../website"
npm ci
DOCUSAURUS_BASE_URL=/ npm run build
