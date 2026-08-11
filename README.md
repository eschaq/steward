# Steward

Steward is a multi-user estate belongings disposition agent — a tool for families and
executors working through the contents of an estate together. Rather than one person
tracking everything in a spreadsheet, Steward gives each participant a shared view of
the belongings, captures their preferences and claims on individual items, and uses an
agent to help work toward a disposition for each thing in the estate — who receives it,
what gets sold or donated, and what still needs a decision. The system is built as two
Cloud Run services: a static frontend and a backend API that hosts the agent logic.

## Project layout

| Path        | Purpose                                                        |
| ----------- | -------------------------------------------------------------- |
| `frontend/` | Static build, deployed as a Cloud Run service. *(placeholder)*  |
| `backend/`  | API + ADK agent logic, deployed as a Cloud Run service. *(placeholder)* |
| `docs/`     | Planning and design documents.                                  |

## Setup

> **Placeholder** — these steps are stubs to be filled in once the services exist.

### Prerequisites

- [ ] Node version — TBD
- [ ] Python version — TBD
- [ ] `gcloud` CLI, authenticated against the project — project ID TBD
- [ ] Firebase project / credentials — TBD

### Local development

```bash
# 1. Clone
git clone <repo-url> && cd steward

# 2. Frontend — install and run dev server
# TBD

# 3. Backend — create virtualenv, install deps, run API locally
# TBD

# 4. Environment variables — copy the example file and fill in values
# TBD
```

### Deploy

```bash
# Build and deploy each service to Cloud Run
# TBD
```

## Status

Scaffolding only. No application code, dependencies, or business logic yet.
