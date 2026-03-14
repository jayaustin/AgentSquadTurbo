---
name: schema-and-migration-safety
description: Use when changing schemas, persistent data, queries, or data movement workflows
inclusion: always
---

# Schema And Migration Safety

## Overview

Treat durable data changes as rollout-sensitive work with explicit compatibility
and recovery paths.

## Required Checks

- schema or shape changes are backward-compatible or intentionally sequenced
- migrations, backfills, and indexes are validated for scale and rollback
- data correctness rules and failure handling are explicit
- operational impact and observability for the change are defined

## Anti-Patterns

- destructive changes without sequencing
- assuming local-scale migration behavior matches production
- silent data coercion or lossy transforms
