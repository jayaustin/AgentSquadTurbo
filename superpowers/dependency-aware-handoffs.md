---
name: dependency-aware-handoffs
description: Use when handing work to another role so the next step is executable, traceable, and low ambiguity
inclusion: always
---

# Dependency-Aware Handoffs

## Overview

Package outputs so the next role can act immediately without reconstructing
intent or dependencies.

## Required Handoff Content

- what was decided, changed, or validated
- which files, docs, or artifacts matter
- dependencies already satisfied and dependencies still blocking progress
- acceptance checks the next role must satisfy
- assumptions, risks, and unresolved questions

## Anti-Patterns

- "continue from here" with no concrete state
- missing blockers or hidden dependencies
- conclusions without supporting context
- asking downstream roles to rediscover requirements
