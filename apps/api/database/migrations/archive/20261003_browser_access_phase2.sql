begin;

create schema if not exists private;
revoke all on schema private from public, anon;
grant usage on schema private to authenticated;

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

create or replace function private.current_user_role()
returns text
language sql
stable
security definer
set search_path = ''
as $$
  select u.role::text from public.users as u
  where u.id = auth.uid() and coalesce(u.is_active, true)
$$;

revoke all on function private.current_org_id() from public, anon;
revoke all on function private.current_user_role() from public, anon;
grant execute on function private.current_org_id() to authenticated;
grant execute on function private.current_user_role() to authenticated;

drop policy if exists "Service layer can manage organizations" on public.organizations;
drop policy if exists "Browser can read own organization" on public.organizations;
create policy "Browser can read own organization" on public.organizations
  for select to authenticated using (id = (select private.current_org_id()));
drop policy if exists "Clinic admins and doctors can update own organization" on public.organizations;
create policy "Clinic admins and doctors can update own organization" on public.organizations
  for update to authenticated
  using (id = (select private.current_org_id()) and (select private.current_user_role()) in ('admin', 'doctor'))
  with check (id = (select private.current_org_id()));

drop policy if exists "Service layer can manage users" on public.users;
drop policy if exists "Browser can read tenant users" on public.users;
create policy "Browser can read tenant users" on public.users
  for select to authenticated
  using (id = auth.uid() or (org_id = (select private.current_org_id()) and (select private.current_user_role()) in ('admin', 'doctor')));
drop policy if exists "Browser can update own profile" on public.users;
create policy "Browser can update own profile" on public.users
  for update to authenticated using (id = auth.uid() and org_id = (select private.current_org_id()))
  with check (id = auth.uid() and org_id = (select private.current_org_id()));

drop policy if exists "Service layer can manage voice_call_sessions" on public.voice_call_sessions;
drop policy if exists "Browser can read tenant call sessions" on public.voice_call_sessions;
create policy "Browser can read tenant call sessions" on public.voice_call_sessions
  for select to authenticated using (org_id = (select private.current_org_id()));

drop policy if exists "Service layer can manage system_audit_logs" on public.system_audit_logs;

drop policy if exists "Service layer can manage patients" on public.patients;
drop policy if exists "Service layer can manage appointments" on public.appointments;
drop policy if exists "Service layer can manage visit_events" on public.visit_events;
drop policy if exists "Service layer can manage doctor_leaves" on public.doctor_leaves;
drop policy if exists "Service layer can manage voice_call_turns" on public.voice_call_turns;
drop policy if exists "Service layer can manage admin_settings" on public.admin_settings;
drop policy if exists "Service layer can manage payment_receipts" on public.payment_receipts;

revoke all on public.organizations, public.users, public.voice_call_sessions, public.system_audit_logs,
  public.patients, public.appointments, public.visit_events, public.doctor_leaves,
  public.voice_call_turns, public.admin_settings, public.payment_receipts
  from public, anon, authenticated;
grant select on public.organizations to authenticated;
grant update (name, city, address, phone, country, country_code, currency_code, currency_symbol, booking_settings, voice_ai_settings)
  on public.organizations to authenticated;
grant select on public.users to authenticated;
grant update (full_name, specialization, phone_number) on public.users to authenticated;
grant select (id, org_id, start_time, triage_status, call_outcome, attended_by)
  on public.voice_call_sessions to authenticated;

revoke all on public.clinic_closures, public.plans, public.subscriptions from public, anon, authenticated;
do $$
begin
  if to_regclass('public.doctor_schedules') is not null then
    execute 'revoke all on public.doctor_schedules from public, anon, authenticated';
  end if;
end;
$$;


create or replace function public.register_organization_and_admin(
  p_org_name text,
  p_city text,
  p_user_id uuid,
  p_email text,
  p_full_name text,
  p_clinic_specialty text default 'General Practice',
  p_lead_doctor_name text default null,
  p_phone text default null,
  p_hotline text default null,
  p_slot_duration integer default 15
)
returns jsonb
language plpgsql
security definer set search_path = ''
as $$
declare
  v_org_id uuid;
begin
  if auth.uid() is null or p_user_id is distinct from auth.uid() then
    raise exception 'Authenticated user mismatch' using errcode = '42501';
  end if;

  if lower(trim(coalesce(p_email, ''))) is distinct from lower(trim(coalesce(auth.jwt()->>'email', ''))) then
    raise exception 'Authenticated email mismatch' using errcode = '42501';
  end if;

  select u.org_id into v_org_id
  from public.users as u
  where u.id = auth.uid()
    and lower(u.email) = lower(auth.jwt()->>'email')
    and u.role = 'admin';

  if v_org_id is null then
    raise exception 'Clinic membership is not ready' using errcode = '42501';
  end if;

  return jsonb_build_object(
    'org_id', v_org_id,
    'user_id', p_user_id,
    'role', 'admin'
  );
end;
$$;

revoke all on function public.register_organization_and_admin(text, text, uuid, text, text, text, text, text, text, integer) from public, anon;
grant execute on function public.register_organization_and_admin(text, text, uuid, text, text, text, text, text, text, integer) to authenticated;

create or replace function public.handle_new_user_signup()
returns trigger
language plpgsql
security definer set search_path = ''
as $$
declare
  v_org_id uuid;
  v_org_name text;
  v_city text;
  v_full_name text;
  v_role user_role;
  v_staff_name text;
  v_staff_role text;
  v_specialty text;
  v_lead_doc text;
  v_phone text;
  v_slot_dur integer;
  v_existing_id uuid;
begin
  select id into v_existing_id from public.users where id = new.id or lower(email) = lower(new.email) limit 1;
  if v_existing_id is not null then
    return new;
  end if;

  select o.id, (staff->>'full_name'), coalesce(staff->>'role', 'receptionist')
  into v_org_id, v_staff_name, v_staff_role
  from public.organizations o,
       jsonb_array_elements(coalesce(o.booking_settings->'authorized_staff', '[]'::jsonb)) as staff
  where lower(trim(staff->>'email')) = lower(trim(new.email))
  limit 1;

  if v_org_id is not null then
    v_full_name := coalesce(nullif(trim(v_staff_name), ''), 'Front Desk Staff');
    v_role := 'receptionist'::user_role;

    insert into public.users (id, org_id, email, full_name, role, presence_status)
    values (new.id, v_org_id, new.email, v_full_name, v_role, 'available')
    on conflict (id) do update
    set org_id = excluded.org_id,
        full_name = excluded.full_name,
        role = excluded.role,
        email = excluded.email;

    return new;
  end if;

  v_org_name := trim(new.raw_user_meta_data->>'org_name');
  if v_org_name is not null and v_org_name <> '' then
    v_city := coalesce(new.raw_user_meta_data->>'city', 'Default Region');
    v_full_name := coalesce(new.raw_user_meta_data->>'full_name', split_part(new.email, '@', 1));
    v_specialty := coalesce(new.raw_user_meta_data->>'clinic_specialty', 'General Practice');
    v_lead_doc := coalesce(new.raw_user_meta_data->>'lead_doctor_name', v_full_name);
    v_phone := new.raw_user_meta_data->>'phone';

    begin
      v_slot_dur := (new.raw_user_meta_data->>'default_slot_duration_minutes')::integer;
    exception when others then
      v_slot_dur := 15;
    end;

    v_role := 'admin'::user_role;

    insert into public.organizations (
      name, 
      city, 
      phone, 
      booking_settings,
      voice_ai_settings
    )
    values (
      v_org_name, 
      v_city, 
      v_phone, 
      jsonb_build_object(
        'consultation_fee', 500,
        'default_slot_duration_minutes', coalesce(v_slot_dur, 15),
        'slot_buffer_minutes', 5,
        'max_daily_patients', 30,
        'weekly_schedule', '{}'::jsonb,
        'authorized_staff', '[]'::jsonb
      ),
      jsonb_build_object(
        'ai_voice_name', 'priya',
        'ai_language_mode', 'en_hi_bilingual',
        'ai_voice_role', 'receptionist',
        'ai_greeting_prompt', format('Hello! Welcome to %s. How may I assist you today?', v_org_name),
        'clinic_specialty', v_specialty,
        'lead_doctor_name', v_lead_doc,
        'emergency_deflection_phone', '108'
      )
    )
    returning id into v_org_id;

    insert into public.users (id, org_id, email, full_name, role, presence_status)
    values (new.id, v_org_id, new.email, v_full_name, v_role, 'available')
    on conflict (id) do update
    set org_id = excluded.org_id,
        full_name = excluded.full_name,
        role = excluded.role,
        email = excluded.email;

    insert into public.admin_settings (admin_id, org_id, manage_billing, notification_email)
    values (new.id, v_org_id, true, new.email)
    on conflict (admin_id) do nothing;

    insert into public.system_audit_logs (org_id, actor_id, actor_email, action_type, target_id, target_name, metadata)
    values (v_org_id, new.id, new.email, 'CLINIC_REGISTERED', v_org_id, v_org_name,
      jsonb_build_object('specialty', v_specialty, 'lead_doctor', v_lead_doc));

    return new;
  end if;

  return new;
end;
$$;


commit;
