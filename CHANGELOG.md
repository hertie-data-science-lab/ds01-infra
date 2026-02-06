# 1.0.0 (2026-02-06)


### Bug Fixes

* correct container-retire path in session exit handler ([fc3455a](https://github.com/hertie-data-science-lab/ds01-infra/commit/fc3455a0b64c5ad5642d09b9d4aff1c871a48b48))
* disable GDM on compute server to free GPU handles ([9e054aa](https://github.com/hertie-data-science-lab/ds01-infra/commit/9e054aa60835f0a35547b6352683ab5ed66a62c7))
* flush stdin buffer before all prompts in mig-configure ([b220b69](https://github.com/hertie-data-science-lab/ds01-infra/commit/b220b691b7ef542bf3b688256a15ef0de3b5a320))
* mig-configure handles pending state and GPU reset ([b668c4a](https://github.com/hertie-data-science-lab/ds01-infra/commit/b668c4a9b536f2f7de3e56aadd859ad3f72125c3))
* mig-configure instance count handles disabled GPUs ([3ae8dd6](https://github.com/hertie-data-science-lab/ds01-infra/commit/3ae8dd66fc7a9ebd994e150a63ff6be70964a503))
* resolve domain variants to canonical username for docker group ([e824b90](https://github.com/hertie-data-science-lab/ds01-infra/commit/e824b90ed5bb0db7025da974658a4cb4756c5d3a))
* set HOME env var for VS Code server compatibility ([2c0c4f6](https://github.com/hertie-data-science-lab/ds01-infra/commit/2c0c4f66483f2dcc08736b30aac7e052c74eaf8f))
* sync alias-list with deployed version, add mig-configure ([52d5d89](https://github.com/hertie-data-science-lab/ds01-infra/commit/52d5d89fb0a9cb060b7d307b71590832a38f6ccf))
* use ds01 recording rules in user and DCGM dashboards ([b093267](https://github.com/hertie-data-science-lab/ds01-infra/commit/b09326744ffbaf66c0516eed3529ca90b4dcda92))


### Features

* **01-04:** replace commitizen with semantic-release ([2d92f93](https://github.com/hertie-data-science-lab/ds01-infra/commit/2d92f9394be96b07b0ff8889b6c85c6882d07839))
* add interactive MIG configuration CLI ([b035cb7](https://github.com/hertie-data-science-lab/ds01-infra/commit/b035cb7ebc8711455e3ae72f11c7fe99b20c20cb))
* Add persistent container alias system and fix username display ([7d1c3b3](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d1c3b3ef3f676e08c0394d8b6d0779dfded013a))
* add Prometheus/Grafana monitoring stack ([d9ccd0e](https://github.com/hertie-data-science-lab/ds01-infra/commit/d9ccd0e40e6b36fa566a37a07d8082980b0dba50))
* add real-time container ownership tracking system ([7d2347a](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d2347af7f9c6b6f7f932690245a53c1455158af))
* add semantic versioning with commitizen ([e924cdf](https://github.com/hertie-data-science-lab/ds01-infra/commit/e924cdfec6e0dd171fb39f9b01ef943766cc9507))
* add unmanaged GPU container detection and monitoring ([d1729e8](https://github.com/hertie-data-science-lab/ds01-infra/commit/d1729e82e3b4bd122f7a7720d31fce165c69730d))
* add VS Code dev container integration ([4675c94](https://github.com/hertie-data-science-lab/ds01-infra/commit/4675c94b058a3a0d37dd28b186bd9e171a54a915))
* Clarify container vs host commands and add VS Code container setup guide ([f3e1dda](https://github.com/hertie-data-science-lab/ds01-infra/commit/f3e1dda9798c731bc8953cdf5747a6646adc886e))
* Improve container workflow and fix name clash issues ([b410b51](https://github.com/hertie-data-science-lab/ds01-infra/commit/b410b51c8aa26b11b69977207bfeede0cdb2f7a3))
* Improve user onboarding workflows and rename commands ([458f59d](https://github.com/hertie-data-science-lab/ds01-infra/commit/458f59dd83b401c8ca79e2efae835451cb7965e0))
* Make all host commands available inside containers ([d8ec348](https://github.com/hertie-data-science-lab/ds01-infra/commit/d8ec3481475384f7870fdddd0a82e2b6314e7f76))
* mig-configure force reset with process detection ([f6ff7ee](https://github.com/hertie-data-science-lab/ds01-infra/commit/f6ff7ee6b97f6406cf4ea05184032f0e546bcb4f))
* per-user aggregate resource enforcement via systemd cgroup slices ([5b82ecf](https://github.com/hertie-data-science-lab/ds01-infra/commit/5b82ecf0f67d36d2cd0a17e6490ecbfd9846cf03))
* Phase 3.1 hardening and container-retire bug fix ([7e3460b](https://github.com/hertie-data-science-lab/ds01-infra/commit/7e3460b0effe0060ac37a2ff2ee5cda50c147703))
* Phase 3.2 architecture audit, code quality fixes, and config consolidation ([70404b6](https://github.com/hertie-data-science-lab/ds01-infra/commit/70404b60cfb845ac7c9a59955235e9fc3ddcc2e8))
* prefer full GPUs for users with allow_full_gpu permission ([11e6dc3](https://github.com/hertie-data-science-lab/ds01-infra/commit/11e6dc326bbf057df74773b497fdc29717974f3b))
* Unify workflows into project-init with --guided flag + rollback docker socket ([4318200](https://github.com/hertie-data-science-lab/ds01-infra/commit/43182004b3a5a9ec3b27500c42fe0122bc0e3047))
* universal container management for all GPU containers ([d0e8b08](https://github.com/hertie-data-science-lab/ds01-infra/commit/d0e8b08f692fe49230058e21e7ebd1357f956e4e))

# 1.0.0 (2026-02-06)


### Bug Fixes

* correct container-retire path in session exit handler ([fc3455a](https://github.com/hertie-data-science-lab/ds01-infra/commit/fc3455a0b64c5ad5642d09b9d4aff1c871a48b48))
* disable GDM on compute server to free GPU handles ([9e054aa](https://github.com/hertie-data-science-lab/ds01-infra/commit/9e054aa60835f0a35547b6352683ab5ed66a62c7))
* flush stdin buffer before all prompts in mig-configure ([b220b69](https://github.com/hertie-data-science-lab/ds01-infra/commit/b220b691b7ef542bf3b688256a15ef0de3b5a320))
* mig-configure handles pending state and GPU reset ([b668c4a](https://github.com/hertie-data-science-lab/ds01-infra/commit/b668c4a9b536f2f7de3e56aadd859ad3f72125c3))
* mig-configure instance count handles disabled GPUs ([3ae8dd6](https://github.com/hertie-data-science-lab/ds01-infra/commit/3ae8dd66fc7a9ebd994e150a63ff6be70964a503))
* resolve domain variants to canonical username for docker group ([e824b90](https://github.com/hertie-data-science-lab/ds01-infra/commit/e824b90ed5bb0db7025da974658a4cb4756c5d3a))
* set HOME env var for VS Code server compatibility ([2c0c4f6](https://github.com/hertie-data-science-lab/ds01-infra/commit/2c0c4f66483f2dcc08736b30aac7e052c74eaf8f))
* sync alias-list with deployed version, add mig-configure ([52d5d89](https://github.com/hertie-data-science-lab/ds01-infra/commit/52d5d89fb0a9cb060b7d307b71590832a38f6ccf))
* use ds01 recording rules in user and DCGM dashboards ([b093267](https://github.com/hertie-data-science-lab/ds01-infra/commit/b09326744ffbaf66c0516eed3529ca90b4dcda92))


### Features

* **01-04:** replace commitizen with semantic-release ([2d92f93](https://github.com/hertie-data-science-lab/ds01-infra/commit/2d92f9394be96b07b0ff8889b6c85c6882d07839))
* add interactive MIG configuration CLI ([b035cb7](https://github.com/hertie-data-science-lab/ds01-infra/commit/b035cb7ebc8711455e3ae72f11c7fe99b20c20cb))
* Add persistent container alias system and fix username display ([7d1c3b3](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d1c3b3ef3f676e08c0394d8b6d0779dfded013a))
* add Prometheus/Grafana monitoring stack ([d9ccd0e](https://github.com/hertie-data-science-lab/ds01-infra/commit/d9ccd0e40e6b36fa566a37a07d8082980b0dba50))
* add real-time container ownership tracking system ([7d2347a](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d2347af7f9c6b6f7f932690245a53c1455158af))
* add semantic versioning with commitizen ([e924cdf](https://github.com/hertie-data-science-lab/ds01-infra/commit/e924cdfec6e0dd171fb39f9b01ef943766cc9507))
* add unmanaged GPU container detection and monitoring ([d1729e8](https://github.com/hertie-data-science-lab/ds01-infra/commit/d1729e82e3b4bd122f7a7720d31fce165c69730d))
* add VS Code dev container integration ([4675c94](https://github.com/hertie-data-science-lab/ds01-infra/commit/4675c94b058a3a0d37dd28b186bd9e171a54a915))
* Clarify container vs host commands and add VS Code container setup guide ([f3e1dda](https://github.com/hertie-data-science-lab/ds01-infra/commit/f3e1dda9798c731bc8953cdf5747a6646adc886e))
* Improve container workflow and fix name clash issues ([b410b51](https://github.com/hertie-data-science-lab/ds01-infra/commit/b410b51c8aa26b11b69977207bfeede0cdb2f7a3))
* Improve user onboarding workflows and rename commands ([458f59d](https://github.com/hertie-data-science-lab/ds01-infra/commit/458f59dd83b401c8ca79e2efae835451cb7965e0))
* Make all host commands available inside containers ([d8ec348](https://github.com/hertie-data-science-lab/ds01-infra/commit/d8ec3481475384f7870fdddd0a82e2b6314e7f76))
* mig-configure force reset with process detection ([f6ff7ee](https://github.com/hertie-data-science-lab/ds01-infra/commit/f6ff7ee6b97f6406cf4ea05184032f0e546bcb4f))
* Phase 3.1 hardening and container-retire bug fix ([7e3460b](https://github.com/hertie-data-science-lab/ds01-infra/commit/7e3460b0effe0060ac37a2ff2ee5cda50c147703))
* Phase 3.2 architecture audit, code quality fixes, and config consolidation ([70404b6](https://github.com/hertie-data-science-lab/ds01-infra/commit/70404b60cfb845ac7c9a59955235e9fc3ddcc2e8))
* prefer full GPUs for users with allow_full_gpu permission ([11e6dc3](https://github.com/hertie-data-science-lab/ds01-infra/commit/11e6dc326bbf057df74773b497fdc29717974f3b))
* Unify workflows into project-init with --guided flag + rollback docker socket ([4318200](https://github.com/hertie-data-science-lab/ds01-infra/commit/43182004b3a5a9ec3b27500c42fe0122bc0e3047))
* universal container management for all GPU containers ([d0e8b08](https://github.com/hertie-data-science-lab/ds01-infra/commit/d0e8b08f692fe49230058e21e7ebd1357f956e4e))

# 1.0.0 (2026-02-06)


### Bug Fixes

* correct container-retire path in session exit handler ([fc3455a](https://github.com/hertie-data-science-lab/ds01-infra/commit/fc3455a0b64c5ad5642d09b9d4aff1c871a48b48))
* disable GDM on compute server to free GPU handles ([9e054aa](https://github.com/hertie-data-science-lab/ds01-infra/commit/9e054aa60835f0a35547b6352683ab5ed66a62c7))
* flush stdin buffer before all prompts in mig-configure ([b220b69](https://github.com/hertie-data-science-lab/ds01-infra/commit/b220b691b7ef542bf3b688256a15ef0de3b5a320))
* mig-configure handles pending state and GPU reset ([b668c4a](https://github.com/hertie-data-science-lab/ds01-infra/commit/b668c4a9b536f2f7de3e56aadd859ad3f72125c3))
* mig-configure instance count handles disabled GPUs ([3ae8dd6](https://github.com/hertie-data-science-lab/ds01-infra/commit/3ae8dd66fc7a9ebd994e150a63ff6be70964a503))
* resolve domain variants to canonical username for docker group ([e824b90](https://github.com/hertie-data-science-lab/ds01-infra/commit/e824b90ed5bb0db7025da974658a4cb4756c5d3a))
* set HOME env var for VS Code server compatibility ([2c0c4f6](https://github.com/hertie-data-science-lab/ds01-infra/commit/2c0c4f66483f2dcc08736b30aac7e052c74eaf8f))
* sync alias-list with deployed version, add mig-configure ([52d5d89](https://github.com/hertie-data-science-lab/ds01-infra/commit/52d5d89fb0a9cb060b7d307b71590832a38f6ccf))
* use ds01 recording rules in user and DCGM dashboards ([b093267](https://github.com/hertie-data-science-lab/ds01-infra/commit/b09326744ffbaf66c0516eed3529ca90b4dcda92))


### Features

* **01-04:** replace commitizen with semantic-release ([2d92f93](https://github.com/hertie-data-science-lab/ds01-infra/commit/2d92f9394be96b07b0ff8889b6c85c6882d07839))
* add interactive MIG configuration CLI ([b035cb7](https://github.com/hertie-data-science-lab/ds01-infra/commit/b035cb7ebc8711455e3ae72f11c7fe99b20c20cb))
* Add persistent container alias system and fix username display ([7d1c3b3](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d1c3b3ef3f676e08c0394d8b6d0779dfded013a))
* add Prometheus/Grafana monitoring stack ([d9ccd0e](https://github.com/hertie-data-science-lab/ds01-infra/commit/d9ccd0e40e6b36fa566a37a07d8082980b0dba50))
* add real-time container ownership tracking system ([7d2347a](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d2347af7f9c6b6f7f932690245a53c1455158af))
* add semantic versioning with commitizen ([e924cdf](https://github.com/hertie-data-science-lab/ds01-infra/commit/e924cdfec6e0dd171fb39f9b01ef943766cc9507))
* add unmanaged GPU container detection and monitoring ([d1729e8](https://github.com/hertie-data-science-lab/ds01-infra/commit/d1729e82e3b4bd122f7a7720d31fce165c69730d))
* add VS Code dev container integration ([4675c94](https://github.com/hertie-data-science-lab/ds01-infra/commit/4675c94b058a3a0d37dd28b186bd9e171a54a915))
* Clarify container vs host commands and add VS Code container setup guide ([f3e1dda](https://github.com/hertie-data-science-lab/ds01-infra/commit/f3e1dda9798c731bc8953cdf5747a6646adc886e))
* Improve container workflow and fix name clash issues ([b410b51](https://github.com/hertie-data-science-lab/ds01-infra/commit/b410b51c8aa26b11b69977207bfeede0cdb2f7a3))
* Improve user onboarding workflows and rename commands ([458f59d](https://github.com/hertie-data-science-lab/ds01-infra/commit/458f59dd83b401c8ca79e2efae835451cb7965e0))
* Make all host commands available inside containers ([d8ec348](https://github.com/hertie-data-science-lab/ds01-infra/commit/d8ec3481475384f7870fdddd0a82e2b6314e7f76))
* mig-configure force reset with process detection ([f6ff7ee](https://github.com/hertie-data-science-lab/ds01-infra/commit/f6ff7ee6b97f6406cf4ea05184032f0e546bcb4f))
* Phase 3.1 hardening and container-retire bug fix ([7e3460b](https://github.com/hertie-data-science-lab/ds01-infra/commit/7e3460b0effe0060ac37a2ff2ee5cda50c147703))
* Phase 3.2 architecture audit, code quality fixes, and config consolidation ([70404b6](https://github.com/hertie-data-science-lab/ds01-infra/commit/70404b60cfb845ac7c9a59955235e9fc3ddcc2e8))
* prefer full GPUs for users with allow_full_gpu permission ([11e6dc3](https://github.com/hertie-data-science-lab/ds01-infra/commit/11e6dc326bbf057df74773b497fdc29717974f3b))
* Unify workflows into project-init with --guided flag + rollback docker socket ([4318200](https://github.com/hertie-data-science-lab/ds01-infra/commit/43182004b3a5a9ec3b27500c42fe0122bc0e3047))
* universal container management for all GPU containers ([d0e8b08](https://github.com/hertie-data-science-lab/ds01-infra/commit/d0e8b08f692fe49230058e21e7ebd1357f956e4e))

# 1.0.0 (2026-02-05)


### Bug Fixes

* correct container-retire path in session exit handler ([fc3455a](https://github.com/hertie-data-science-lab/ds01-infra/commit/fc3455a0b64c5ad5642d09b9d4aff1c871a48b48))
* disable GDM on compute server to free GPU handles ([9e054aa](https://github.com/hertie-data-science-lab/ds01-infra/commit/9e054aa60835f0a35547b6352683ab5ed66a62c7))
* flush stdin buffer before all prompts in mig-configure ([b220b69](https://github.com/hertie-data-science-lab/ds01-infra/commit/b220b691b7ef542bf3b688256a15ef0de3b5a320))
* mig-configure handles pending state and GPU reset ([b668c4a](https://github.com/hertie-data-science-lab/ds01-infra/commit/b668c4a9b536f2f7de3e56aadd859ad3f72125c3))
* mig-configure instance count handles disabled GPUs ([3ae8dd6](https://github.com/hertie-data-science-lab/ds01-infra/commit/3ae8dd66fc7a9ebd994e150a63ff6be70964a503))
* resolve domain variants to canonical username for docker group ([e824b90](https://github.com/hertie-data-science-lab/ds01-infra/commit/e824b90ed5bb0db7025da974658a4cb4756c5d3a))
* set HOME env var for VS Code server compatibility ([2c0c4f6](https://github.com/hertie-data-science-lab/ds01-infra/commit/2c0c4f66483f2dcc08736b30aac7e052c74eaf8f))
* sync alias-list with deployed version, add mig-configure ([52d5d89](https://github.com/hertie-data-science-lab/ds01-infra/commit/52d5d89fb0a9cb060b7d307b71590832a38f6ccf))
* use ds01 recording rules in user and DCGM dashboards ([b093267](https://github.com/hertie-data-science-lab/ds01-infra/commit/b09326744ffbaf66c0516eed3529ca90b4dcda92))


### Features

* **01-04:** replace commitizen with semantic-release ([2d92f93](https://github.com/hertie-data-science-lab/ds01-infra/commit/2d92f9394be96b07b0ff8889b6c85c6882d07839))
* add interactive MIG configuration CLI ([b035cb7](https://github.com/hertie-data-science-lab/ds01-infra/commit/b035cb7ebc8711455e3ae72f11c7fe99b20c20cb))
* Add persistent container alias system and fix username display ([7d1c3b3](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d1c3b3ef3f676e08c0394d8b6d0779dfded013a))
* add Prometheus/Grafana monitoring stack ([d9ccd0e](https://github.com/hertie-data-science-lab/ds01-infra/commit/d9ccd0e40e6b36fa566a37a07d8082980b0dba50))
* add real-time container ownership tracking system ([7d2347a](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d2347af7f9c6b6f7f932690245a53c1455158af))
* add semantic versioning with commitizen ([e924cdf](https://github.com/hertie-data-science-lab/ds01-infra/commit/e924cdfec6e0dd171fb39f9b01ef943766cc9507))
* add unmanaged GPU container detection and monitoring ([d1729e8](https://github.com/hertie-data-science-lab/ds01-infra/commit/d1729e82e3b4bd122f7a7720d31fce165c69730d))
* add VS Code dev container integration ([4675c94](https://github.com/hertie-data-science-lab/ds01-infra/commit/4675c94b058a3a0d37dd28b186bd9e171a54a915))
* Clarify container vs host commands and add VS Code container setup guide ([f3e1dda](https://github.com/hertie-data-science-lab/ds01-infra/commit/f3e1dda9798c731bc8953cdf5747a6646adc886e))
* Improve container workflow and fix name clash issues ([b410b51](https://github.com/hertie-data-science-lab/ds01-infra/commit/b410b51c8aa26b11b69977207bfeede0cdb2f7a3))
* Improve user onboarding workflows and rename commands ([458f59d](https://github.com/hertie-data-science-lab/ds01-infra/commit/458f59dd83b401c8ca79e2efae835451cb7965e0))
* Make all host commands available inside containers ([d8ec348](https://github.com/hertie-data-science-lab/ds01-infra/commit/d8ec3481475384f7870fdddd0a82e2b6314e7f76))
* mig-configure force reset with process detection ([f6ff7ee](https://github.com/hertie-data-science-lab/ds01-infra/commit/f6ff7ee6b97f6406cf4ea05184032f0e546bcb4f))
* Phase 3.1 hardening and container-retire bug fix ([7e3460b](https://github.com/hertie-data-science-lab/ds01-infra/commit/7e3460b0effe0060ac37a2ff2ee5cda50c147703))
* Phase 3.2 architecture audit, code quality fixes, and config consolidation ([70404b6](https://github.com/hertie-data-science-lab/ds01-infra/commit/70404b60cfb845ac7c9a59955235e9fc3ddcc2e8))
* prefer full GPUs for users with allow_full_gpu permission ([11e6dc3](https://github.com/hertie-data-science-lab/ds01-infra/commit/11e6dc326bbf057df74773b497fdc29717974f3b))
* Unify workflows into project-init with --guided flag + rollback docker socket ([4318200](https://github.com/hertie-data-science-lab/ds01-infra/commit/43182004b3a5a9ec3b27500c42fe0122bc0e3047))
* universal container management for all GPU containers ([d0e8b08](https://github.com/hertie-data-science-lab/ds01-infra/commit/d0e8b08f692fe49230058e21e7ebd1357f956e4e))

# 1.0.0 (2026-02-04)


### Bug Fixes

* correct container-retire path in session exit handler ([fc3455a](https://github.com/hertie-data-science-lab/ds01-infra/commit/fc3455a0b64c5ad5642d09b9d4aff1c871a48b48))
* disable GDM on compute server to free GPU handles ([9e054aa](https://github.com/hertie-data-science-lab/ds01-infra/commit/9e054aa60835f0a35547b6352683ab5ed66a62c7))
* flush stdin buffer before all prompts in mig-configure ([b220b69](https://github.com/hertie-data-science-lab/ds01-infra/commit/b220b691b7ef542bf3b688256a15ef0de3b5a320))
* mig-configure handles pending state and GPU reset ([b668c4a](https://github.com/hertie-data-science-lab/ds01-infra/commit/b668c4a9b536f2f7de3e56aadd859ad3f72125c3))
* mig-configure instance count handles disabled GPUs ([3ae8dd6](https://github.com/hertie-data-science-lab/ds01-infra/commit/3ae8dd66fc7a9ebd994e150a63ff6be70964a503))
* resolve domain variants to canonical username for docker group ([e824b90](https://github.com/hertie-data-science-lab/ds01-infra/commit/e824b90ed5bb0db7025da974658a4cb4756c5d3a))
* set HOME env var for VS Code server compatibility ([2c0c4f6](https://github.com/hertie-data-science-lab/ds01-infra/commit/2c0c4f66483f2dcc08736b30aac7e052c74eaf8f))
* sync alias-list with deployed version, add mig-configure ([52d5d89](https://github.com/hertie-data-science-lab/ds01-infra/commit/52d5d89fb0a9cb060b7d307b71590832a38f6ccf))
* use ds01 recording rules in user and DCGM dashboards ([b093267](https://github.com/hertie-data-science-lab/ds01-infra/commit/b09326744ffbaf66c0516eed3529ca90b4dcda92))


### Features

* **01-04:** replace commitizen with semantic-release ([2d92f93](https://github.com/hertie-data-science-lab/ds01-infra/commit/2d92f9394be96b07b0ff8889b6c85c6882d07839))
* add interactive MIG configuration CLI ([b035cb7](https://github.com/hertie-data-science-lab/ds01-infra/commit/b035cb7ebc8711455e3ae72f11c7fe99b20c20cb))
* Add persistent container alias system and fix username display ([7d1c3b3](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d1c3b3ef3f676e08c0394d8b6d0779dfded013a))
* add Prometheus/Grafana monitoring stack ([d9ccd0e](https://github.com/hertie-data-science-lab/ds01-infra/commit/d9ccd0e40e6b36fa566a37a07d8082980b0dba50))
* add real-time container ownership tracking system ([7d2347a](https://github.com/hertie-data-science-lab/ds01-infra/commit/7d2347af7f9c6b6f7f932690245a53c1455158af))
* add semantic versioning with commitizen ([e924cdf](https://github.com/hertie-data-science-lab/ds01-infra/commit/e924cdfec6e0dd171fb39f9b01ef943766cc9507))
* add unmanaged GPU container detection and monitoring ([d1729e8](https://github.com/hertie-data-science-lab/ds01-infra/commit/d1729e82e3b4bd122f7a7720d31fce165c69730d))
* add VS Code dev container integration ([4675c94](https://github.com/hertie-data-science-lab/ds01-infra/commit/4675c94b058a3a0d37dd28b186bd9e171a54a915))
* Clarify container vs host commands and add VS Code container setup guide ([f3e1dda](https://github.com/hertie-data-science-lab/ds01-infra/commit/f3e1dda9798c731bc8953cdf5747a6646adc886e))
* Improve container workflow and fix name clash issues ([b410b51](https://github.com/hertie-data-science-lab/ds01-infra/commit/b410b51c8aa26b11b69977207bfeede0cdb2f7a3))
* Improve user onboarding workflows and rename commands ([458f59d](https://github.com/hertie-data-science-lab/ds01-infra/commit/458f59dd83b401c8ca79e2efae835451cb7965e0))
* Make all host commands available inside containers ([d8ec348](https://github.com/hertie-data-science-lab/ds01-infra/commit/d8ec3481475384f7870fdddd0a82e2b6314e7f76))
* mig-configure force reset with process detection ([f6ff7ee](https://github.com/hertie-data-science-lab/ds01-infra/commit/f6ff7ee6b97f6406cf4ea05184032f0e546bcb4f))
* Phase 3.1 hardening and container-retire bug fix ([7e3460b](https://github.com/hertie-data-science-lab/ds01-infra/commit/7e3460b0effe0060ac37a2ff2ee5cda50c147703))
* prefer full GPUs for users with allow_full_gpu permission ([11e6dc3](https://github.com/hertie-data-science-lab/ds01-infra/commit/11e6dc326bbf057df74773b497fdc29717974f3b))
* Unify workflows into project-init with --guided flag + rollback docker socket ([4318200](https://github.com/hertie-data-science-lab/ds01-infra/commit/43182004b3a5a9ec3b27500c42fe0122bc0e3047))
* universal container management for all GPU containers ([d0e8b08](https://github.com/hertie-data-science-lab/ds01-infra/commit/d0e8b08f692fe49230058e21e7ebd1357f956e4e))

# [1.2.0](https://github.com/hertie-data-science-lab/ds01-infra/compare/v1.1.0...v1.2.0) (2026-01-30)


### Bug Fixes

* correct container-retire path in session exit handler ([750f0d4](https://github.com/hertie-data-science-lab/ds01-infra/commit/750f0d4ed1aba77c8389089b60cc1eedc6b10f04))
* disable GDM on compute server to free GPU handles ([f949d87](https://github.com/hertie-data-science-lab/ds01-infra/commit/f949d873a3fc1e668c18e5265f027abfacf43efa))
* flush stdin buffer before all prompts in mig-configure ([b9fb303](https://github.com/hertie-data-science-lab/ds01-infra/commit/b9fb30397fe29725ebd7380301835a052567f73e))
* mig-configure handles pending state and GPU reset ([d9ffe6c](https://github.com/hertie-data-science-lab/ds01-infra/commit/d9ffe6ca4ea1d232f78977d647f2956a53cf1e1e))
* mig-configure instance count handles disabled GPUs ([d99846d](https://github.com/hertie-data-science-lab/ds01-infra/commit/d99846dee4b32b73e0eff2ec26bff18f75cd4b5f))
* resolve domain variants to canonical username for docker group ([e4eb58e](https://github.com/hertie-data-science-lab/ds01-infra/commit/e4eb58e21f267aad79738eefd38adbc28395d457))
* set HOME env var for VS Code server compatibility ([03c1562](https://github.com/hertie-data-science-lab/ds01-infra/commit/03c15629d2ae47a30fea9835946ec623b55290d2))
* sync alias-list with deployed version, add mig-configure ([77484e2](https://github.com/hertie-data-science-lab/ds01-infra/commit/77484e238adee6f63bb21fd8b5ee6be36c976c12))
* use ds01 recording rules in user and DCGM dashboards ([45531f8](https://github.com/hertie-data-science-lab/ds01-infra/commit/45531f8aba46b7cf33eb6eac6c84bef04b9616c8))


### Features

* **01-04:** replace commitizen with semantic-release ([7113835](https://github.com/hertie-data-science-lab/ds01-infra/commit/711383509fdee74a2b321a4505782819a0cbdb80))
* add interactive MIG configuration CLI ([1b99fde](https://github.com/hertie-data-science-lab/ds01-infra/commit/1b99fde99966babbe246ba381e6477eb77277f51))
* add Prometheus/Grafana monitoring stack ([2d1ad6c](https://github.com/hertie-data-science-lab/ds01-infra/commit/2d1ad6c87970fd147123d62e83b9692a8ab5f5d9))
* add real-time container ownership tracking system ([1be6507](https://github.com/hertie-data-science-lab/ds01-infra/commit/1be65072025bcda5cc77d156f0714d8ea810b4b2))
* add unmanaged GPU container detection and monitoring ([8fbee85](https://github.com/hertie-data-science-lab/ds01-infra/commit/8fbee85c87ed7a3d7dbd0bb7d915f29d816bb590))
* add VS Code dev container integration ([945600d](https://github.com/hertie-data-science-lab/ds01-infra/commit/945600d612abd6cf88a812d6b8a194d64bc7a442))
* mig-configure force reset with process detection ([10970dd](https://github.com/hertie-data-science-lab/ds01-infra/commit/10970dd0c30abe6df233a73c4e3efcc9aef3e800))
* prefer full GPUs for users with allow_full_gpu permission ([8e03dcb](https://github.com/hertie-data-science-lab/ds01-infra/commit/8e03dcb9ad660b4e62efd7fae5ec64b24a6787de))
* universal container management for all GPU containers ([4e634f7](https://github.com/hertie-data-science-lab/ds01-infra/commit/4e634f780d1f72ff68f8b4735edf5f309f24a897))

# Changelog

All notable changes to DS01 Infrastructure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Hybrid monitoring architecture:
  - DS01 Exporter as systemd service (`ds01-exporter.service`) for allocation/business metrics
  - Prometheus container (`ds01-prometheus`) for metrics storage
  - Grafana container (`ds01-grafana`) for dashboards
  - Node Exporter container for system metrics
  - Alertmanager container for alert routing
  - DCGM Exporter for GPU metrics (Phase 3 complete)
- Metric collection cron jobs (GPU, CPU, memory, disk, containers - every 5 min)

### Known Issues
- DCGM Exporter container crashed (needs restart)
- Grafana dashboard provisioning misconfigured
- Event log empty (`/var/log/ds01/events.jsonl`)
- Dev Containers lack GPU assignment and label tracking

## v1.1.0 (2026-01-07)

### Added
- Semantic versioning with commitizen
- Interactive MIG configuration CLI (`mig-configure`)
- Real-time container ownership tracking system (`container-owner-tracker.py`)
- Force reset with process detection for MIG configuration

### Fixed
- Container-retire path in session exit handler
- Domain variants resolved to canonical username for docker group
- MIG instance count handling for disabled GPUs
- Pending state and GPU reset in mig-configure
- Stdin buffer flushed before all prompts in mig-configure
- GDM disabled on compute server to free GPU handles

### Testing
- Unit tests for username canonicalisation

## v1.0.0 (2025-12-02)

### Added
- 5-layer command architecture (L0: Docker → L1: MLC → L2: Atomic → L3: Orchestrators → L4: Wizards)
- User-facing commands: `container deploy`, `container retire`, `project init`, `project launch`
- Admin dashboard with GPU, container, and system monitoring
- Centralised event logging system
- 4-tier help system across all CLI commands (`--help`, `--info`, `--concepts`, `--guided`)
- DS01 UI/UX design guide for CLI consistency
- Per-user Docker container isolation system
- Docker wrapper with ownership tracking and visibility filtering
- Requirements.txt import support in image-create
- Auto-detect CUDA architecture based on host driver
- Shared Dockerfile generator library
- Project-centric workflow with project launch L4 wizard
- GitHub Actions workflow to sync docs to ds01-hub

### Fixed
- Silent exit code 2 failures in container creation
- MIG device visibility (CUDA_VISIBLE_DEVICES)
- Multi-MIG allocation and full GPU preference
- Image preservation in container retire workflow
- Username sanitisation consistency
- Dashboard and container-list owner detection
- Docker proxy HTTP/2 support

### Changed
- Tier → Layer (L0-L4) terminology
- Command reorganisation: clean user names, ds01-* admin prefix
- docs/ renamed to docs-user/ for clarity
- Comprehensive user documentation restructured for modularity

## v0.9.0 (2025-11-25) - Pre-release

### Added
- Layered architecture with universal enforcement (cgroups, OPA, Docker wrapper)
- Comprehensive pytest-based test suite (149 tests)
- LDAP/SSSD username support with auto docker group management
- Resource monitoring, alerts, and soft limits (Phase 7)
- Centralised logging for resource allocation audits
- Container session command unification
- Dashboard redesign with improved visual design and modular architecture
- 4-tier group model with faculty tier
- Group management system with auto-sync
- Container-unpause command
- User-activity-report admin tool
- Home directory enforcement via profile.d
- Maintenance scripts for permissions management

### Fixed
- LDAP user container deployment and diagnostics
- VS Code setup duplication and onboarding-create bug
- Git remote prompt duplication in project-init
- GID mapping debugging

### Changed
- User-setup wizard redesigned with skill-adaptive SSH flow
- Onboarding flows decoupled for shorter, focused setup
- Wizard output streamlined and verbosity reduced

## v0.8.0 (2025-10-01) - Foundation

### Added
- MIG partition configuration
- GPU status dashboard (`gpu-status-dashboard.py`)
- Resource limits system (`get_resource_limits.py`, `gpu_allocator.py`)
- Container setup wizard MVP
- User container scripts (create, start, stop, remove)
- mlc-create wrapper for AIME integration
- Systemd control groups with /var/log structure
- Initial monitoring: modular collectors

### Infrastructure
- Transferred scripts from home workspace
- DSL sudo protections
- Log mirrors and symlinks
