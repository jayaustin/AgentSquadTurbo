---
name: strict-type-hinting
description: Use when writing or refactoring Python to enforce precise static types and reduce runtime defects
inclusion: always
---

# Strict Type Hinting

## Overview

Apply complete, precise Python type hints so code is easier to reason about,
safer to change, and friendlier to static analysis tools.

Core principle: if a public function signature is ambiguous, behavior is
ambiguous. Make types explicit.

## When to Use

- New Python modules, functions, and classes
- Refactors that change data flow or public interfaces
- Bug fixes involving invalid inputs or shape mismatches
- Shared utility code consumed by multiple modules

## Required Practices

1. Type all function/method parameters and return values.
2. Use explicit container element types (for example `list[str]`, `dict[str, int]`).
3. Use `Optional[T]`/`T | None` only when `None` is a true valid state.
4. Prefer `TypedDict`, `dataclass`, or dedicated classes for structured payloads.
5. Type class attributes and instance fields.
6. Keep type aliases short, meaningful, and local unless broadly reused.
7. Avoid `Any` unless there is no practical alternative.

## Quality Checklist

- [ ] Public API signatures are fully typed
- [ ] Return types match actual behavior
- [ ] `None` cases are explicit and intentional
- [ ] Collection and mapping element types are specified
- [ ] Complex payloads use `TypedDict` or class types
- [ ] No unnecessary `Any`

## Anti-Patterns

- Omitting return types on public functions
- Using broad `dict`/`list` types with no element detail
- Using `Any` to silence type errors without justification
- Treating optional inputs as required (or vice versa)
- Ignoring type mismatches discovered during review

## Integration Notes

- Align tests with typed contracts, especially edge/error cases.
- Keep runtime validation where external input can violate static assumptions.
- If strict typing conflicts with an external library boundary, isolate the
  boundary and keep internal code strongly typed.
