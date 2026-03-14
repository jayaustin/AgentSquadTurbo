---
name: superpowers
displayName: Superpowers
version: 1.0.0
description: Complete software development workflow system with systematic TDD, planning, and quality gates
keywords: [development, workflow, tdd, testing, planning, code-review, debugging, git, systematic]
author: Adapted from obra/superpowers, Kiro format by flixfox1
license: MIT
---

# Superpowers for AI agents

A complete software development workflow system that transforms your coding agent into a systematic, test-driven development powerhouse.

## What is Superpowers?

Superpowers is a collection of development skills that guide your AI agent through professional software development workflows. Instead of jumping straight into code, it enforces a systematic approach:

1. **Brainstorming** - Refines ideas through questions and design validation
2. **Planning** - Creates detailed, bite-sized implementation plans
3. **Test-Driven Development** - Enforces RED-GREEN-REFACTOR cycles
4. **Subagent-Driven Development** - Uses fresh subagents for each task with quality reviews
5. **Code Review** - Systematic review processes between tasks
6. **Git Workflows** - Proper branching and worktree management

## Core Skills Included

### Planning And Coordination
- **brainstorming** - Interactive design refinement before coding
- **writing-plans** - Detailed implementation plans with exact steps
- **subagent-driven-development** - Fresh subagents per task with reviews
- **dependency-aware-handoffs** - Package outputs so downstream roles can execute without guessing
- **acceptance-criteria-design** - Turn vague goals into explicit scope, edge cases, and measurable completion checks
- **risk-based-prioritization** - Order work and findings by impact, likelihood, and release exposure

### Engineering And Operations
- **test-driven-development** - Strict RED-GREEN-REFACTOR enforcement
- **requesting-code-review** - Review implementation for spec compliance and code quality
- **systematic-debugging** - Use a structured root-cause workflow instead of guessing
- **strict-type-hinting** - Keep Python contracts explicit and reviewable
- **pep8-compliance** - Preserve Python readability and consistency
- **api-contract-discipline** - Keep interfaces versionable, explicit, and testable
- **schema-and-migration-safety** - Treat durable data changes as rollout-sensitive work
- **observability-by-default** - Ship enough signal to detect regressions and debug failures
- **safe-change-management** - Plan rollout, failure handling, monitoring, and rollback paths
- **using-git-worktrees** - Use isolated workspaces for parallel task execution

### Quality, Release, And Performance
- **evidence-based-validation** - Make findings reproducible, scoped, and evidence-backed
- **automation-reliability** - Keep automated checks deterministic and maintainable
- **release-gate-discipline** - Make ship and no-ship decisions from explicit evidence
- **performance-budgeting** - Tie optimization work to explicit budgets and realistic workloads

### Design, UX, And Content
- **interface-state-modeling** - Define flows, states, transitions, and edge cases explicitly
- **accessibility-by-default** - Bake inclusive behavior into design and implementation from the start
- **localization-integrity** - Protect placeholders, locale behavior, fallback, and layout resilience
- **asset-pipeline-discipline** - Keep art and audio assets production-ready through explicit pipeline rules

### Security
- **threat-modeling** - Start from assets, actors, trust boundaries, and abuse paths before prioritizing fixes

### Meta
- **writing-skills** - Create new skills following TDD-for-documentation best practices

## Philosophy

- **Test-Driven Development**: Write tests first, always
- **Systematic over ad-hoc**: Process over guessing
- **Complexity reduction**: Simplicity as primary goal
- **Evidence over claims**: Verify before declaring success
- **YAGNI**: Build only what's required
- **DRY**: Eliminate duplication
