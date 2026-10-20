begin;
alter table public.organizations
  add column if not exists voice_seconds_used integer not null default 0 check (voice_seconds_used >= 0),
  add column if not exists inbound_voice_number text unique;
alter table public.call_logs
  add column if not exists caller_identity text,
  add column if not exists provider_call_sid text,
  add column if not exists admission_expires_at timestamptz,
  add column if not exists provider_started_at timestamptz,
  add column if not exists deadline_at timestamptz,
  add column if not exists quota_charged_at timestamptz,
  add column if not exists charged_seconds integer not null default 0 check (charged_seconds >= 0),
  add column if not exists end_reason text,
  add column if not exists media_terminated_at timestamptz,
  add column if not exists booking_proposal jsonb,
  add column if not exists booking_result jsonb;
alter table public.voice_call_turns
  add column if not exists event_id text,
  add column if not exists interrupted boolean not null default false;
alter table public.voice_token_rate_limits
  add column if not exists tokens bigint not null default 0 check (tokens >= 0);
alter table public.appointments
  add column if not exists booking_metadata jsonb default '{}'::jsonb,
  add column if not exists queue_state text not null default 'not_checked_in',
  add column if not exists encounter_state text not null default 'not_started',
  add column if not exists called_at timestamptz,
  add column if not exists call_count integer not null default 0;
create unique index if not exists idx_voice_turn_event on public.voice_call_turns(session_id, event_id) where event_id is not null;
create unique index if not exists idx_call_logs_tenant_id on public.call_logs(org_id, id);
create index if not exists idx_voice_open_deadline on public.call_logs(deadline_at) where end_time is null;
create index if not exists idx_voice_limit_expiry on public.voice_token_rate_limits(window_start);
do $$ declare item record; begin
  for item in select conname from pg_constraint where conrelid = 'public.call_logs'::regclass
    and contype = 'c' and pg_get_constraintdef(oid) like '%recording_status%' loop
    execute format('alter table public.call_logs drop constraint %I', item.conname);
  end loop;
  alter table public.call_logs add constraint chk_voice_recording_status
    check (recording_status in ('disabled', 'processing', 'ready', 'partial', 'failed'));
end $$;
do $$ begin
  if not exists (select 1 from pg_constraint where conname = 'voice_turn_tenant_session_fk') then
    alter table public.voice_call_turns add constraint voice_turn_tenant_session_fk
      foreign key (org_id, session_id) references public.call_logs(org_id, id) on delete cascade not valid;
    alter table public.voice_call_turns validate constraint voice_turn_tenant_session_fk;
  end if;
end $$;

-- Idempotent one-time legacy backfill. Keep historical usage after log retention/deletion.
update public.call_logs set media_terminated_at = end_time
where end_time is not null and media_terminated_at is null and provider_started_at is null;
with unsettled as (
  update public.call_logs set charged_seconds = greatest(coalesce(duration_seconds, 0), 0),
    quota_charged_at = coalesce(end_time, now())
  where end_time is not null and quota_charged_at is null
  returning org_id, charged_seconds
), totals as (select org_id, sum(charged_seconds)::integer seconds from unsettled group by org_id)
update public.organizations o set voice_seconds_used = o.voice_seconds_used + totals.seconds
from totals where o.id = totals.org_id;
update public.call_logs set
  provider_started_at = agent_joined_at,
  admission_expires_at = start_time + interval '45 seconds',
  deadline_at = case when agent_joined_at is not null then agent_joined_at + make_interval(secs => call_budget_seconds) end
where end_time is null and admission_expires_at is null;

-- Every terminal writer (worker, webhook, reconciler) uses the same atomic settlement.
create or replace function public.settle_voice_allowance() returns trigger
language plpgsql security definer set search_path = public, pg_temp as $$
begin
  if new.org_id is distinct from old.org_id or new.call_budget_seconds is distinct from old.call_budget_seconds then
    raise exception 'Call tenant and allocation are immutable';
  end if;
  if old.provider_started_at is not null and new.provider_started_at is distinct from old.provider_started_at then
    raise exception 'Provider activation is immutable';
  end if;
  if old.quota_charged_at is not null then
    new.charged_seconds := old.charged_seconds;
    new.quota_charged_at := old.quota_charged_at;
    new.end_time := old.end_time;
    new.duration_seconds := greatest(old.duration_seconds, new.duration_seconds);
  elsif new.end_time is not null then
    new.charged_seconds := case when new.provider_started_at is null then 0 else
      least(new.call_budget_seconds, greatest(0, ceil(extract(epoch from
        (new.end_time - new.provider_started_at)))::integer)) end;
    new.quota_charged_at := now();
    update public.organizations set voice_seconds_used = voice_seconds_used + new.charged_seconds
      where id = new.org_id;
  end if;
  return new;
end $$;
drop trigger if exists settle_voice_allowance on public.call_logs;
create trigger settle_voice_allowance before update on public.call_logs
for each row execute function public.settle_voice_allowance();
revoke all on function public.settle_voice_allowance() from public, anon, authenticated;
create or replace function public.protect_active_voice_call() returns trigger
language plpgsql set search_path = public, pg_temp as $$
begin
  if old.end_time is null or (old.provider_started_at is not null and old.media_terminated_at is null) then
    raise exception 'End the active voice call before deleting its record or clinic';
  end if;
  return old;
end $$;
drop trigger if exists protect_active_voice_call on public.call_logs;
create trigger protect_active_voice_call before delete on public.call_logs
for each row execute function public.protect_active_voice_call();
revoke all on function public.protect_active_voice_call() from public, anon, authenticated;
create or replace function public.validate_voice_booking_call() returns trigger
language plpgsql set search_path = public, pg_temp as $$
begin
  if new.call_session_id is not null and not exists (
    select 1 from public.call_logs c where c.id = new.call_session_id and c.org_id = new.org_id
      and c.end_time is null and c.provider_started_at is not null and c.deadline_at > clock_timestamp()
  ) then
    raise exception 'Voice call is expired or does not belong to this clinic' using errcode = '23514';
  end if;
  return new;
end $$;
drop trigger if exists validate_voice_booking_call on public.appointments;
create trigger validate_voice_booking_call before insert on public.appointments
for each row execute function public.validate_voice_booking_call();
revoke all on function public.validate_voice_booking_call() from public, anon, authenticated;
-- Existing column grants for editable clinic settings are preserved.
revoke update on public.organizations from authenticated;
revoke update (voice_seconds_used, inbound_voice_number) on public.organizations from authenticated;
revoke all on public.voice_token_rate_limits from public, anon, authenticated;
alter table public.voice_token_rate_limits enable row level security;
commit;
