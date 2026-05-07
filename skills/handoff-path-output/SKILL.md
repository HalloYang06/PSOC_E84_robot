---
name: handoff-path-output
description: Enforce handoff-path reporting for any completed task in this workspace. Use when Codex finishes implementation, review, debugging, design, documentation, or validation work here and must update its own role handoff file under docs/ai-handoffs/, explicitly mark identity in that file, then print the real handoff document path in the final response.
---

# Handoff Path Output

Apply this skill as a close-out rule for repository work in this workspace.
Use it for every completed task, even when the change is small, doc-only, or validation-only.

## Required Outcome

Every completed task must leave two visible artifacts:

1. an updated role handoff file under `docs/ai-handoffs/<role>.md`
2. an explicit handoff path line in the final response

Do not treat chat history as the handoff record.
Do not skip the handoff path because the user already knows the file location.

## Before Finishing

Update or create `docs/ai-handoffs/<role>.md`.

Record at least:

- identity header for the owner of the handoff document
- current responsibility scope
- files changed in this task
- verification performed
- next recommended step
- blockers, gaps, or risks

The handoff document must explicitly mark identity near the top.
The identity section is mandatory.

Use this structure:

```md
# Identity

- Role: AI-4
- Scope: Embedded workflow mapping
```

If the role is not a numbered AI, still state the owner clearly, for example:

- `Role: AI-Boss`
- `Role: AI-Review-QA`
- `Role: Runner-Git`

If the task also produced other handoff artifacts, record them in the role handoff file and print their paths too.

## Final Response Rule

The final response must contain a standalone handoff path line for each relevant document.
Place the path line near the end of the response so it is easy to find during handoff.

Use this format:

```text
Handoff Path: D:\ai-collab-product\docs\ai-handoffs\<role>.md
```

If there are multiple handoff files:

```text
Handoff Path: D:\ai-collab-product\docs\ai-handoffs\<role>.md
Handoff Path: D:\ai-collab-product\docs\ai-handoffs\<extra>.md
```

## Guardrails

- Do not say the task is complete until the handoff file exists.
- Do not omit the identity section in the handoff document.
- Do not print a relative path when an absolute path is available.
- Do not point to a missing file.
- Do not skip the path line even if the handoff file was only lightly updated.
- Do not edit unrelated role handoff files.
- Do not finish without at least one handoff path line in the final output.

## Workspace Fit

Use this skill together with role skills and verification skills. It does not replace role-specific instructions. It only enforces the repository handoff discipline and final-response path output.
