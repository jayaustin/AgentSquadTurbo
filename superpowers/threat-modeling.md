---
name: threat-modeling
description: Use when evaluating attack surface, trust boundaries, abuse cases, or control gaps
inclusion: always
---

# Threat Modeling

## Overview

Model how systems can be abused before focusing on individual fixes.

## Required Checks

- assets, actors, trust boundaries, and entry points are identified
- likely abuse paths and control weaknesses are named
- impact, exploitability, and detection difficulty are considered together
- mitigations are tied to concrete controls or backlog work

## Anti-Patterns

- focusing only on implementation bugs without system context
- severity claims without impact framing
- control recommendations with no owner or validation path
