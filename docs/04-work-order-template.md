# Work Order Template

Last updated: 2026-08-10

## Purpose

A work order is a scoped, actionable handoff from planning (Desktop) to execution (Code, or eventually a specialized agent). It answers three questions: what needs doing, what "done" looks like, and who/what should do it.

Frontmatter is structured for future machine parsing — once the Supervisor agent is live, it reads `requires_new_agent` and `pillar`/`domain` to decide whether an existing specialized agent can take the order or a new one needs to be spun up (which triggers an order placed back to Eban).

---

## Template

```markdown
---
id: WO-YYYYMMDD-NN
pillar: hackathons | dws | drip
status: draft | ready | in_progress | blocked | done
created: YYYY-MM-DD
assigned_to: unassigned | code | agent-name
requires_new_agent: true | false
priority: high | medium | low
estimated_effort: e.g. "2 hrs" or "1 session"
---

# [Short Title]

## Objective
One or two sentences. What needs to exist or happen when this is done.

## Context
Why this work order exists — link back to the pillar doc or planning conversation that generated it. Enough for someone (or something) with no memory of the conversation to understand the "why."

## Scope
What's in. Explicitly note what's out if there's risk of scope creep.

## Acceptance Criteria
Bullet list. Concrete, checkable. "Done" isn't a feeling, it's a checklist.
- [ ] ...
- [ ] ...

## Dependencies
Anything this is blocked by, or anything it blocks.

## Notes
Anything else — constraints, non-compete flags, style/voice requirements, links.
```

---

## Agent Routing Logic (future state, once Supervisor is live)

1. Supervisor reads incoming work order frontmatter.
2. If `requires_new_agent: false` and a specialized agent matching `pillar`/domain already exists → route directly, agent drafts its own work order for sub-tasks if needed.
3. If `requires_new_agent: true`, or no matching agent exists → Supervisor halts and places an order back to Eban describing the gap (what kind of agent, why, scope) rather than improvising one.
4. Manual mode (now): Eban or Desktop sets `assigned_to` and hands the file to Code directly. No routing logic needed yet — this section is forward documentation, not active behavior.

## Naming Convention

`WO-YYYYMMDD-NN-short-slug.md` — date of creation, sequence number for that day, short slug. Keeps them sortable in a flat folder until/unless a better structure is needed.
