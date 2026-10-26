begin;

create table if not exists public.voice_workflow_checkpoints (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  call_id uuid not null,
  resumed_from_call_id uuid,
  workflow_version integer not null default 1,
  state_version integer not null default 1,
  status text not null default 'active',
  stage text not null default 'intake',
  safe_state jsonb not null default '{}'::jsonb,
  last_completed_event_id text,
  expires_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  resumed_at timestamptz,
  constraint chk_checkpoint_status check (status in ('active', 'completed', 'failed', 'resumed', 'expired')),
  constraint voice_workflow_checkpoints_tenant_call_fk foreign key (org_id, call_id)
    references public.call_logs(org_id, id) on delete cascade not valid
);

alter table public.voice_workflow_checkpoints validate constraint voice_workflow_checkpoints_tenant_call_fk;

create unique index if not exists idx_workflow_checkpoints_org_call
  on public.voice_workflow_checkpoints(org_id, call_id);

create index if not exists idx_workflow_checkpoints_expiry_status
  on public.voice_workflow_checkpoints(expires_at, status);

create index if not exists idx_workflow_checkpoints_resumed_from
  on public.voice_workflow_checkpoints(org_id, resumed_from_call_id)
  where resumed_from_call_id is not null;

alter table public.call_logs add column if not exists resumed_from_call_id uuid references public.call_logs(id) on delete set null;

create index if not exists idx_call_logs_resumed_from
  on public.call_logs(org_id, resumed_from_call_id)
  where resumed_from_call_id is not null;

create index if not exists idx_call_logs_org_phone
  on public.call_logs(org_id, caller_phone, start_time desc);

create table if not exists public.voice_mutation_operations (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  call_id uuid references public.call_logs(id) on delete set null,
  operation_key varchar(255) not null,
  operation_type varchar(64) not null,
  status varchar(32) not null default 'completed',
  response_payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint uq_voice_mutation_key unique (operation_key),
  constraint chk_voice_mutation_status check (status in ('in_progress', 'completed', 'failed'))
);

create index if not exists idx_voice_mutations_org_key
  on public.voice_mutation_operations(org_id, operation_key);

create table if not exists public.outbox_events (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  event_type varchar(128) not null,
  payload jsonb not null default '{}'::jsonb,
  status varchar(32) not null default 'pending',
  attempts integer not null default 0,
  last_attempt_at timestamptz,
  published_at timestamptz,
  error_detail text,
  created_at timestamptz not null default now(),
  constraint chk_outbox_event_status check (status in ('pending', 'processing', 'published', 'failed'))
);

create index if not exists idx_outbox_events_status_created
  on public.outbox_events(status, created_at);

create index if not exists idx_outbox_events_org_created
  on public.outbox_events(org_id, created_at);

create table if not exists public.voice_recording_chunks (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  call_id uuid not null references public.call_logs(id) on delete cascade,
  chunk_index integer not null,
  storage_path text not null,
  duration_seconds numeric(6, 2) not null default 0.0,
  offset_seconds numeric(7, 2) not null default 0.0,
  size_bytes integer not null default 0,
  created_at timestamptz not null default now(),
  constraint uq_voice_recording_chunk unique (call_id, chunk_index)
);

create index if not exists idx_voice_recording_chunks_call_index
  on public.voice_recording_chunks(call_id, chunk_index);

create index if not exists idx_voice_recording_chunks_org_created
  on public.voice_recording_chunks(org_id, created_at);

create index if not exists idx_call_logs_org_open
  on public.call_logs(org_id, end_time) where end_time is null;

create index if not exists idx_call_logs_global_open
  on public.call_logs(end_time) where end_time is null;

alter table public.voice_workflow_checkpoints enable row level security;
alter table public.voice_mutation_operations enable row level security;
alter table public.outbox_events enable row level security;
alter table public.voice_recording_chunks enable row level security;

revoke all on public.voice_workflow_checkpoints from public, anon, authenticated;
revoke all on public.voice_mutation_operations from public, anon, authenticated;
revoke all on public.outbox_events from public, anon, authenticated;
revoke all on public.voice_recording_chunks from public, anon, authenticated;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'service_role') then
    execute 'create policy "Service role can manage voice_workflow_checkpoints" on public.voice_workflow_checkpoints for all to service_role using (true) with check (true)';
    execute 'grant all on public.voice_workflow_checkpoints to service_role';
    execute 'create policy "Service role can manage voice_mutation_operations" on public.voice_mutation_operations for all to service_role using (true) with check (true)';
    execute 'grant all on public.voice_mutation_operations to service_role';
    execute 'create policy "Service role can manage outbox_events" on public.outbox_events for all to service_role using (true) with check (true)';
    execute 'grant all on public.outbox_events to service_role';
    execute 'create policy "Service role can manage voice_recording_chunks" on public.voice_recording_chunks for all to service_role using (true) with check (true)';
    execute 'grant all on public.voice_recording_chunks to service_role';
  end if;
end $$;

commit;
