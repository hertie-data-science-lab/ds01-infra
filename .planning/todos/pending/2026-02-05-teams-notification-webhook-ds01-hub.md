---
created: 2026-02-05T16:39
title: Add Teams notification webhook for ds01-hub
area: tooling
files: []
---

## Problem

ds01-hub (the GitHub repository) needs a Microsoft Teams notification webhook configured. This would enable automated notifications to a Teams channel for events like CI/CD pipeline results, new releases, or PR activity. Currently no Teams integration exists for the repository.

## Solution

TBD — configure an incoming webhook in the relevant Teams channel, then add it as a GitHub Actions secret or webhook integration in the ds01-hub repository settings.
