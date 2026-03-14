---
name: localization-integrity
description: Use when changing multilingual content, locale-sensitive behavior, or translation workflows
inclusion: always
---

# Localization Integrity

## Overview

Protect meaning, placeholders, locale behavior, and layout resilience across
supported languages.

## Required Checks

- placeholders, variables, markup, and plural rules remain intact
- fallback behavior and unsupported locale behavior are explicit
- layout expansion, truncation, RTL, and cultural constraints are considered
- source-of-truth content and localization workflow ownership are clear

## Anti-Patterns

- treating translated text as plain string replacement
- locale support with no fallback rules
- shipping content that breaks placeholders or formatting tokens
