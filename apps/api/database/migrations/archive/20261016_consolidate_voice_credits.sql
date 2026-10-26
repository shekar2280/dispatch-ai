-- Consolidate credits into the existing audit log. Never reset clinic usage.
begin;

do $$
begin
  if to_regclass('public.voice_credit_grants') is not null then
    lock table public.voice_credit_grants in access exclusive mode;
    insert into public.system_audit_logs
      (id, org_id, actor_email, action_type, target_id, target_name, new_state, created_at)
    select id, org_id, granted_by, 'VOICE_CREDIT_GRANTED', org_id, recipient_email,
      jsonb_build_object('seconds', seconds, 'recipient_email', recipient_email, 'reason', reason), created_at
    from public.voice_credit_grants on conflict (id) do nothing;
    -- A UUID collision must not silently discard or alter a grant.
    if exists (
      select 1 from public.voice_credit_grants g
      left join public.system_audit_logs a on a.id = g.id
      where a.id is null or a.action_type <> 'VOICE_CREDIT_GRANTED'
        or a.org_id is distinct from g.org_id or a.actor_email is distinct from g.granted_by
        or a.created_at is distinct from g.created_at
        or a.new_state is distinct from jsonb_build_object(
          'seconds', g.seconds, 'recipient_email', g.recipient_email, 'reason', g.reason)
    ) then
      raise exception 'Credit migration verification failed; no tables were removed';
    end if;
  end if;
end $$;

drop function if exists public.grant_voice_minutes(text, integer, text, uuid);
-- No CASCADE: unexpected external dependencies must stop the migration.
drop table if exists public.voice_credit_grants;
drop view if exists public.voice_call_sessions;

create index if not exists idx_audit_voice_credits on public.system_audit_logs(org_id)
  where action_type = 'VOICE_CREDIT_GRANTED';
revoke all on public.system_audit_logs from public, anon, authenticated;
grant select, insert on public.system_audit_logs to service_role;

create function public.grant_voice_minutes(
  recipient text, minutes integer, grant_reason text, request_id uuid
) returns table(id uuid, org_id uuid, recipient_email text, seconds bigint,
                reason text, granted_by text, created_at timestamptz)
language plpgsql security definer set search_path = '' as $$
declare
  clinic_id uuid;
  normalized_email text := lower(btrim(recipient));
  result public.system_audit_logs;
begin
  if minutes is null or minutes < 1 or minutes > 100000 or request_id is null
     or grant_reason is null or length(btrim(grant_reason)) not between 1 and 500 then
    raise exception 'Provide 1-100000 minutes, a reason (1-500 characters), and a unique request ID';
  end if;
  select u.org_id into strict clinic_id from public.users u
    where lower(btrim(u.email)) = normalized_email and u.is_active and u.org_id is not null;
  insert into public.system_audit_logs
    (id, org_id, actor_email, action_type, target_id, target_name, new_state)
  values(request_id, clinic_id, session_user, 'VOICE_CREDIT_GRANTED', clinic_id, normalized_email,
    jsonb_build_object('seconds', minutes::bigint * 60, 'recipient_email', normalized_email,
                      'reason', btrim(grant_reason)))
  on conflict do nothing returning * into result;
  if result.id is null then
    select a.* into strict result from public.system_audit_logs a where a.id = request_id;
    if result.action_type <> 'VOICE_CREDIT_GRANTED' or result.org_id is distinct from clinic_id
       or result.new_state is distinct from jsonb_build_object(
         'seconds', minutes::bigint * 60, 'recipient_email', normalized_email, 'reason', btrim(grant_reason)) then
      raise exception 'Request ID already belongs to a different grant';
    end if;
  end if;
  return query select result.id, result.org_id, result.new_state->>'recipient_email',
    (result.new_state->>'seconds')::bigint, result.new_state->>'reason', result.actor_email, result.created_at;
exception
  when no_data_found then raise exception 'No active clinic account matches this email';
  when too_many_rows then raise exception 'Email matches multiple accounts; resolve the ambiguity first';
end $$;
revoke all on function public.grant_voice_minutes(text, integer, text, uuid) from public, anon, authenticated;
grant execute on function public.grant_voice_minutes(text, integer, text, uuid) to service_role;
commit;
