---
name: accessibility-by-default
description: Use when defining, building, or validating interfaces so accessibility is treated as a first-class requirement
inclusion: always
---

# Accessibility By Default

## Overview

Treat accessibility as a baseline quality bar, not a post-hoc patch.

## Required Checks

- semantic structure and readable labels are explicit
- keyboard, controller, or equivalent non-pointer access is covered
- contrast, focus visibility, scaling, and motion sensitivity are considered
- error states, instructions, and feedback remain understandable to assistive technologies

## Anti-Patterns

- relying on color alone
- hiding critical actions behind hover-only or gesture-only behavior
- assuming responsive layout automatically means accessible layout
