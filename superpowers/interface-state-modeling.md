---
name: interface-state-modeling
description: Use when defining or implementing user-facing flows, screens, interactions, or structured states
inclusion: always
---

# Interface And State Modeling

## Overview

Define states, transitions, inputs, outputs, and failure paths explicitly so
downstream implementation does not invent behavior.

## Required Checks

- primary flow, alternate flow, and blocked flow are explicit
- empty, loading, error, retry, and success states are covered
- important transitions, triggers, and side effects are named
- permissions, platform limits, and accessibility implications are called out

## Anti-Patterns

- describing only the happy path
- hiding behavior inside vague phrases like "handle gracefully"
- leaving state ownership or transitions implicit
