---
name: api-contract-discipline
description: Use when designing, implementing, or validating APIs, integrations, and service contracts
inclusion: always
---

# API Contract Discipline

## Overview

Keep interfaces explicit, versionable, and testable across producers and consumers.

## Required Checks

- request and response shapes are defined precisely
- validation, error envelopes, and status behavior are specified
- auth, idempotency, pagination, and compatibility expectations are explicit where relevant
- examples and edge cases match the real contract

## Anti-Patterns

- changing payload shape without migration or compatibility notes
- undocumented optional fields or hidden defaults
- hand-wavy error behavior
