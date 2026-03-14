---
name: release-gate-discipline
description: Use when deciding whether work is ready to ship, promote, or pass a formal gate
inclusion: always
---

# Release Gate Discipline

## Overview

Make ship/no-ship decisions from explicit evidence, remaining risk, and recovery
options.

## Required Checks

- blocking criteria and waiver conditions are explicit
- open defects, known risks, and required approvals are separated clearly
- monitoring, rollback, and recovery expectations are defined
- the recommendation is tied to concrete evidence rather than optimism

## Anti-Patterns

- calling work ready because the deadline is close
- mixing release blockers with nice-to-have cleanup
- passing a gate without stating residual risk
