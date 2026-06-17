# Contributing to DS01 Infrastructure

The full contributing guide — development setup, local CI, commit conventions, the
pull-request flow, and code style — lives in the documentation site:

**→ [Contributing](https://hertie-data-science-lab.github.io/ds01-infra/develop/contributing)**

Source for that page: [`docs-develop/contributing.md`](docs-develop/contributing.md).

## Quick reference

```bash
pre-commit install --hook-type commit-msg   # one-time setup
make check                                   # run the full CI gate locally
```

Commits follow [Conventional Commits](https://www.conventionalcommits.org/)
(`type(scope): subject`). PRs are squash-merged to `main`.
