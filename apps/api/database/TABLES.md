# Database Architecture & Tables

This document outlines the core domain tables and schema design for the Dispatch AI clinic platform.

## Core Domain Entities

| Table | Domain Responsibility |
| :--- | :--- |
| `organizations` | Multi-tenant clinic profiles, operating hours, lead doctor metadata, and telephony settings. |
| `patients` | Patient profiles, contact details, and clinic association. |
| `appointments` | Current visit state machine (scheduled, checked-in, in-consultation, completed, cancelled). |
| `visit_events` | Append-only audit ledger tracking every status change, actor, and timestamp across a visit's lifecycle. |
| `call_logs` | Inbound voice call metadata, admission tokens, recording URLs, and telephonic triage summaries. |
| `voice_call_turns` | Granular conversational turns between caller and AI receptionist, preserving verifiable booking consent readbacks. |
| `system_audit_logs` | Immutable security and operational audit trails, including role elevations and credit adjustments. |
| `voice_token_rate_limits` | Ephemeral admission counters enforcing per-tenant concurrency limits and provider guardrails. |

---

## Setup & Initialization

### Fresh Installation
For a new database instance or Supabase project, apply the consolidated baseline schema:

```bash
# Apply baseline schema via psql or Supabase SQL Editor:
psql "$DATABASE_URL" -f apps/api/database/schemas/schema.sql
```

The baseline script configures:
* All table definitions and foreign key constraints.
* Row-Level Security (RLS) policies enforcing multi-tenant isolation.
* Operational indexes on `room_name`, `org_id`, and `caller_phone`.

### Schema Migrations
The `apps/api/database/migrations/` directory contains chronological DDL upgrade scripts tracking the platform's schema evolution. For new deployments, `schema.sql` already includes all cumulative migrations.
