---
created: 2026-02-05T18:10
title: Systematic review of resource limits by user group
area: policy
files:
  - config/runtime/resource-limits.yaml
---

## Problem

The actual resource limit values for different user groups (student, researcher, faculty, admin) need a systematic review to ensure they:
1. Match actual user needs and use patterns
2. Are fair and appropriate for the shared infrastructure
3. Don't over-provision or under-provision

Current values were set somewhat arbitrarily and haven't been audited against real usage patterns.

## Solution

Review and document rationale for each group's limits:

### Current Values (to review)

| Resource | Student | Researcher | Faculty | Admin |
|----------|---------|------------|---------|-------|
| max_mig_instances | 1 | 2 | 2 | unlimited |
| max_cpus | 8 | 16 | 32 | unlimited |
| memory | 32g | 64g | 128g | unlimited |
| max_containers | 2 | 5 | 10 | unlimited |
| max_runtime | 24h | 48h | 168h | unlimited |
| idle_timeout | 30m | 1h | 2h | unlimited |

### Questions to Answer

1. What are typical workload patterns for each group?
2. Are students being over-constrained for legitimate use cases?
3. Should researchers have more GPU time during thesis periods?
4. Is 1 MIG instance sufficient for student coursework?
5. Should memory limits be tied to GPU allocation (more GPU = more memory)?

### Data to Collect

- Historical GPU utilisation by group
- Container runtime distributions
- Memory high-water marks
- User feedback on hitting limits

## Notes

- This is a policy decision, not a technical implementation
- May want to create a user feedback mechanism
- Consider seasonal variations (exam periods, thesis deadlines)
