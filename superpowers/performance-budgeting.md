---
name: performance-budgeting
description: Use when changes can affect latency, throughput, memory, frame time, or resource usage
inclusion: always
---

# Performance Budgeting

## Overview

Make performance decisions against explicit budgets and realistic workloads.

## Required Checks

- the relevant budget or baseline is identified
- likely hotspots and scaling risks are named
- measurement plan and evidence are defined
- tradeoffs between speed, cost, quality, and complexity are explicit

## Anti-Patterns

- calling something performant without measurement
- optimizing irrelevant code paths first
- regressions accepted because no budget was stated
