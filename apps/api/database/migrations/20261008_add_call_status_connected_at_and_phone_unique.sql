alter table public.call_logs
  add column if not exists call_status varchar(20) default 'ringing',
  add column if not exists connected_at timestamp with time zone null,
  add column if not exists agent_joined_at timestamp with time zone null;

create index if not exists idx_call_logs_org_call_status on public.call_logs(org_id, call_status);

update public.call_logs
  set call_status = 'missed'
  where lower(coalesce(triage_status, '')) = 'missed'
     or lower(coalesce(call_outcome, '')) in ('no_answer', 'line_busy', 'service_unavailable', 'caller_abandoned', 'speech_unrecognized');

update public.call_logs
  set call_status = 'completed'
  where duration_seconds > 0
    and call_status != 'missed'
    and end_time is not null;

update public.call_logs
  set call_status = 'missed'
  where duration_seconds = 0
    and end_time is not null
    and call_status != 'missed';

update public.call_logs
  set call_status = 'ringing'
  where end_time is null;

alter table public.call_logs alter column call_status set not null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'chk_call_logs_call_status') then
    alter table public.call_logs add constraint chk_call_logs_call_status check (call_status in ('ringing', 'in_progress', 'completed', 'missed'));
  end if;
end $$;

update public.organizations
  set phone = regexp_replace(phone, '\s+', '', 'g')
  where phone is not null;

create unique index if not exists idx_organizations_phone_unique on public.organizations (phone) where (phone is not null);

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'authenticated') then
    execute 'grant select (call_status, connected_at, agent_joined_at) on public.call_logs to authenticated';
  end if;
end $$;

create or replace view public.voice_call_sessions with (security_invoker = true) as select * from public.call_logs;
revoke all on public.voice_call_sessions from public, anon, authenticated;
