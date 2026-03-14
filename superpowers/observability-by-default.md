---
name: observability-by-default
description: Use when building or changing systems that need diagnosis, monitoring, or rollout confidence
inclusion: always
---

# Observability By Default

## Overview

Ship changes with enough visibility to detect regressions, investigate failures,
and confirm success.

## Required Checks

- useful logs, metrics, traces, or domain events are identified
- success and failure signals are observable
- high-risk paths have enough context for diagnosis
- noisy or low-signal telemetry is avoided

## Anti-Patterns

- shipping critical behavior with no runtime visibility
- logs that omit identifiers, context, or error cause
- metrics with no clear interpretation
