---
name: automation-reliability
description: Use when building or validating automated tests, CI checks, or scripted verification flows
inclusion: always
---

# Automation Reliability

## Overview

Automation must be deterministic, maintainable, and trustworthy under repeated
execution.

## Required Checks

- tests or scripts have stable setup, teardown, and data assumptions
- flaky timing, selector, or environment dependencies are controlled
- failures produce actionable evidence
- automation scope is targeted to meaningful regression risk

## Anti-Patterns

- brittle selectors or sleeps used as core synchronization
- tests that only pass in one local environment
- opaque failures that require manual archaeology
