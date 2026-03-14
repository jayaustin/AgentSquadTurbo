---
name: safe-change-management
description: Use when designing or implementing changes that can affect runtime behavior, migrations, rollout safety, or operational stability
inclusion: always
---

# Safe Change Management

## Overview

Plan and implement changes so they can be shipped, observed, and recovered from
without unnecessary drama.

## Required Checks

- backward compatibility and migration impact
- failure modes and fallback behavior
- rollout controls, sequencing, or guardrails
- observability needed to confirm success
- rollback or recovery path if the change misbehaves

## Anti-Patterns

- irreversible changes without a recovery plan
- migrations with no sequencing or validation
- shipping behavior changes with no observability
- assuming production conditions match local assumptions
