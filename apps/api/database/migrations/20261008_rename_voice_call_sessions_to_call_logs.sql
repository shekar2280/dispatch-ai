do $$
begin
  if exists (
    select 1 from information_schema.tables 
    where table_schema = 'public' and table_name = 'voice_call_sessions' and table_type = 'BASE TABLE'
  ) then
    alter table public.voice_call_sessions rename to call_logs;
  end if;
end $$;

alter table public.call_logs
  add column if not exists recording_status varchar(20) default 'disabled',
  add column if not exists recording_storage_path text;

update public.call_logs
  set recording_status = 'ready'
  where audio_recording_url is not null and (recording_status is null or recording_status = 'disabled');

update public.call_logs
  set recording_status = 'disabled'
  where recording_status is null;

alter table public.call_logs
  alter column recording_status set not null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'chk_call_logs_duration') then
    alter table public.call_logs add constraint chk_call_logs_duration check (duration_seconds >= 0);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chk_call_logs_turns') then
    alter table public.call_logs add constraint chk_call_logs_turns check (total_turns >= 0);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chk_call_logs_recording_status') then
    alter table public.call_logs add constraint chk_call_logs_recording_status check (recording_status in ('disabled', 'processing', 'ready', 'failed'));
  end if;
end $$;

create unique index if not exists uq_call_logs_room_org on public.call_logs(org_id, room_name) where (room_name is not null);

do $$
begin
  if exists (select 1 from pg_class where relname = 'idx_call_sessions_org') then
    alter index public.idx_call_sessions_org rename to idx_call_logs_org;
  end if;
  if exists (select 1 from pg_class where relname = 'idx_call_sessions_caller') then
    alter index public.idx_call_sessions_caller rename to idx_call_logs_caller;
  end if;
  if exists (select 1 from pg_class where relname = 'idx_call_sessions_patient') then
    alter index public.idx_call_sessions_patient rename to idx_call_logs_patient;
  end if;
end $$;

create table if not exists public.voice_call_turns (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null references public.call_logs(id) on delete cascade,
  org_id uuid not null references public.organizations(id) on delete cascade,
  turn_number integer not null,
  user_transcript text,
  user_audio_url text,
  ai_filler_text text,
  ai_filler_audio_url text,
  ai_response_text text,
  ai_response_audio_url text,
  stt_latency_ms integer,
  llm_latency_ms integer,
  tts_latency_ms integer,
  total_latency_ms integer,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create index if not exists idx_voice_call_turns_session on public.voice_call_turns(session_id, turn_number);
create index if not exists idx_voice_call_turns_org on public.voice_call_turns(org_id, created_at desc);

create schema if not exists private;
revoke all on schema private from public, anon;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'grant usage on schema private to authenticated';
  end if;
end $$;

create or replace function private.current_org_id()
returns uuid
language sql
stable
security definer
set search_path = ''
as $$
  select u.org_id from public.users as u
  where u.id = auth.uid() and coalesce(u.is_active, true)
$$;

revoke all on function private.current_org_id() from public, anon;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'grant execute on function private.current_org_id() to authenticated';
  end if;
end $$;

alter table public.call_logs enable row level security;
alter table public.voice_call_turns enable row level security;

revoke all on public.call_logs, public.voice_call_turns, public.voice_call_sessions from public, anon, authenticated;

do $$
begin
  drop policy if exists "Browser can read tenant call logs" on public.call_logs;
  drop policy if exists "Browser can read tenant call turns" on public.voice_call_turns;
  drop policy if exists "Service role can manage call_logs" on public.call_logs;
  drop policy if exists "Service role can manage voice_call_turns" on public.voice_call_turns;
  drop policy if exists "Service layer can manage call_logs" on public.call_logs;
  drop policy if exists "Service layer can manage voice_call_sessions" on public.call_logs;
  drop policy if exists "Service layer can manage voice_call_turns" on public.voice_call_turns;

  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'grant select (id, org_id, caller_phone, caller_name, patient_id, session_type, triage_status, call_outcome, attended_by, chief_complaint, total_turns, duration_seconds, full_transcript, recording_status, audio_recording_url, room_name, start_time, end_time) on public.call_logs to authenticated';
    execute 'grant select on public.voice_call_turns to authenticated';
    execute 'create policy "Browser can read tenant call logs" on public.call_logs for select to authenticated using (org_id = (select private.current_org_id()))';
    execute 'create policy "Browser can read tenant call turns" on public.voice_call_turns for select to authenticated using (org_id = (select private.current_org_id()))';
  end if;

  if exists (select 1 from pg_roles where rolname = 'service_role') then
    execute 'create policy "Service role can manage call_logs" on public.call_logs for all to service_role using (true) with check (true)';
    execute 'create policy "Service role can manage voice_call_turns" on public.voice_call_turns for all to service_role using (true) with check (true)';
  end if;
end $$;

create or replace view public.voice_call_sessions with (security_invoker = true) as select * from public.call_logs;

revoke all on public.voice_call_sessions from public, anon, authenticated;

do $$
begin
  if exists (select 1 from pg_publication where pubname = 'supabase_realtime') then
    begin
      alter publication supabase_realtime add table public.call_logs;
    exception when others then
      null;
    end;
  end if;
end $$;
