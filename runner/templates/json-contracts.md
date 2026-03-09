# operator_plan

```json
{
  "summary": "Short planning summary",
  "decision_log": [
    "Chose discovery-first sequencing due unknown localization constraints."
  ],
  "unexpected_events": [
    "WARNING: Market launch locale is unspecified."
  ],
  "human_feedback": {
    "summary": "Need clarification on launch markets before final sequencing.",
    "questions": [
      "Which locales are mandatory for v1?",
      "Is launch date fixed or flexible by 2 weeks?"
    ],
    "requires_response": true
  },
  "tasks": [
    {
      "task_id": "T-001",
      "title": "Task title",
      "description": "Detailed description",
      "owner": "technical-architect",
      "milestone": "M1",
      "status": "Todo",
      "dependencies": []
    }
  ],
  "initial_role_sequence": [
    "technical-architect",
    "development-engineer-python",
    "qa-manager"
  ]
}
```

`owner` rules:

- `owner` must be a valid non-operator role ID.
- `owner: "operator"` is forbidden.
- `initial_role_sequence` must not include `operator`.
- `human_feedback` is optional and should be present when Operator needs user input.
- `decision_log` entries should be concise and actionable.
- `unexpected_events` entries should include severity prefixes:
  `ERROR: ...` or `WARNING: ...`.

# agent_result

```json
{
  "task_id": "T-001",
  "status": "In Validation",
  "summary": "What was completed",
  "updates": {
    "owner": "qa-manager"
  },
  "new_tasks": [],
  "handoff_request": {
    "target_role": "qa-manager",
    "reason": "Requires validation.",
    "requested_task_ids": [
      "T-001"
    ]
  },
  "notes_update": "Optional note text.",
  "decision_log": [
    "Kept parser pure and moved side effects to orchestrator boundary."
  ],
  "unexpected_events": [
    "ERROR: Input sample contained malformed CSV row 184."
  ],
  "human_feedback": {
    "summary": "Need user preference for default locale fallback order.",
    "questions": [
      "Should fallback be en-US then en, or en then project default?"
    ],
    "requires_response": true
  },
  "role_feedback": [
    {
      "target_role": "technical-architect",
      "summary": "Need decision on cache invalidation strategy before final refactor.",
      "questions": [
        "Is write-through cache mandatory for this subsystem?"
      ],
      "requested_action": "Provide architectural direction for cache policy.",
      "related_task_ids": [
        "T-001"
      ]
    }
  ]
}
```

`agent_result` ownership rules:

- `updates.owner` may not be `operator`.
- Non-operator roles may not create tasks in `new_tasks`; this field must be
  empty for non-operator invocations.
- If additional work is required, request task creation through Operator using
  `role_feedback`, `human_feedback`, or `handoff_request`.
- `human_feedback` and `role_feedback` are optional but should be used when
  communication is required.
- `role_feedback.target_role` must be a known role ID.
- `unexpected_events` entries should include severity prefixes:
  `ERROR: ...` or `WARNING: ...`.
