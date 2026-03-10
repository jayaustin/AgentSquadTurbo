---
name: pep8-compliance
description: Use when writing or revising Python code to maintain consistent, readable style and review velocity
inclusion: always
---

# PEP 8 Compliance

## Overview

Follow PEP 8 conventions to keep Python code readable, predictable, and easy to
review across contributors.

Core principle: style consistency is a delivery multiplier, not cosmetic work.

## When to Use

- New Python implementation work
- Refactors that touch existing modules
- Cleanup passes before review
- Any change that introduces new files or APIs

## Required Practices

1. Use clear, lowercase_snake_case names for variables and functions.
2. Use `CapWords` for class names.
3. Keep line length practical and readable (wrap long expressions cleanly).
4. Keep imports grouped and ordered consistently.
5. Use whitespace intentionally (no crowded expressions).
6. Keep functions focused and reasonably small.
7. Write docstrings for public modules, classes, and functions.

## Formatting and Structure Checklist

- [ ] Names follow Python naming conventions
- [ ] Imports are organized and free of unused entries
- [ ] Spacing and line breaks improve readability
- [ ] No trailing whitespace or noisy formatting churn
- [ ] Public interfaces include docstrings
- [ ] Comments explain why, not obvious what

## Anti-Patterns

- Mixed naming styles in the same file
- Overly long, unreadable lines and nested expressions
- Unused imports and dead code left in commits
- Large unrelated style churn mixed with behavior changes
- Commenting every line instead of writing clearer code

## Review Guidance

- Keep style fixes scoped to touched areas unless a dedicated cleanup task exists.
- Separate behavior changes from broad formatting-only edits when possible.
- If team tooling (formatter/linter) is configured, treat it as the source of
  truth for final style decisions.
