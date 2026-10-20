create extension if not exists "btree_gist";

drop trigger if exists on_auth_user_created on auth.users cascade;
drop function if exists public.handle_new_user_signup() cascade;

do $$
declare
  r record;
begin
  for r in (
    select oid::regprocedure as func_signature
    from pg_proc
    where proname = 'register_organization_and_admin'
      and pronamespace = 'public'::regnamespace
  ) loop
    execute 'drop function ' || r.func_signature || ' cascade';
  end loop;
end $$;

drop table if exists public.payments cascade;
drop table if exists public.visit_events cascade;
drop table if exists public.appointments cascade;
drop table if exists public.schedule_overrides cascade;
drop table if exists public.clinic_closures cascade;
drop view if exists public.voice_call_sessions cascade;
drop table if exists public.voice_call_turns cascade;
drop table if exists public.call_logs cascade;
drop table if exists public.voice_token_rate_limits cascade;
drop table if exists public.voice_call_sessions cascade;
drop table if exists public.patients cascade;
drop table if exists public.system_audit_logs cascade;
drop table if exists public.users cascade;
drop table if exists public.clinic_memberships cascade;
drop table if exists public.voice_credit_grants cascade;
drop table if exists public.organizations cascade;

drop type if exists user_role cascade;
drop type if exists appointment_status cascade;
drop type if exists appointment_source cascade;
drop type if exists payment_status cascade;
drop type if exists clinic_appointment_status cascade;
drop type if exists clinic_appointment_source cascade;
drop type if exists clinic_override_type cascade;
drop type if exists clinic_payment_status cascade;
drop type if exists presence_status cascade;

create type user_role as enum ('admin', 'doctor', 'receptionist', 'staff');
create type appointment_status as enum ('scheduled', 'in_progress', 'completed', 'cancelled', 'no_show', 'arrived', 'skipped');
create type appointment_source as enum ('ai_voice', 'walk_in', 'manual');
create type payment_status as enum ('paid', 'pending', 'refunded');

create table public.organizations (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  slug text not null unique,
  city text,
  address text,
  phone text,
  voice_seconds_used integer not null default 0 check (voice_seconds_used >= 0),
  inbound_voice_number text unique,
  timezone text not null,
  country text not null,
  country_code text not null,
  currency_code varchar not null,
  currency_symbol varchar not null,
  booking_settings jsonb default '{}'::jsonb,
  voice_ai_settings jsonb default '{}'::jsonb,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
  constraint ck_organizations_required_config check (
    nullif(trim(name), '') is not null and nullif(trim(timezone), '') is not null
    and nullif(trim(country), '') is not null and nullif(trim(country_code), '') is not null
    and nullif(trim(currency_code), '') is not null and nullif(trim(currency_symbol), '') is not null
  )
);

create table public.users (
  id uuid primary key references auth.users(id) on delete cascade,
  org_id uuid references public.organizations(id) on delete set null,
  email text not null unique,
  full_name text not null,
  role user_role not null default 'receptionist',
  specialization text,
  phone_number text,
  is_active boolean default true,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create table public.clinic_memberships (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  user_id uuid references public.users(id) on delete cascade,
  invited_email text,
  role user_role not null default 'receptionist',
  display_name text,
  status text not null default 'active',
  total_consultations integer not null default 0,
  total_minutes_worked integer not null default 0,
  total_walkins_triaged integer not null default 0,
  total_revenue_collected numeric(12, 2) not null default 0.00,
  joined_at timestamp with time zone default timezone('utc'::text, now()) not null,
  revoked_at timestamp with time zone,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
  constraint uq_clinic_memberships_org_user unique (org_id, user_id)
);

create index idx_clinic_memberships_org_status on public.clinic_memberships(org_id, status);
create index idx_clinic_memberships_user on public.clinic_memberships(user_id);
create index idx_clinic_memberships_email on public.clinic_memberships(org_id, lower(invited_email));

create table public.patients (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  phone_number text not null,
  first_name text not null,
  last_name text,
  dob date,
  gender text,
  blood_group text,
  email text,
  address text,
  medical_history jsonb default '{}'::jsonb,
  recent_diagnosis text,
  created_by_type text default 'VOICE_AI',
  created_by uuid references public.users(id) on delete set null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
  constraint uq_patients_org_id unique (org_id, id)
);

create table public.call_logs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  caller_phone text not null,
  caller_name text,
  patient_id uuid references public.patients(id) on delete set null,
  session_type text default 'voice_simulator',
  triage_status text default 'admin',
  call_outcome text default 'inquiry',
  attended_by text default 'AI Receptionist',
  chief_complaint text,
  total_turns integer default 0 check (total_turns >= 0),
  duration_seconds integer default 0 check (duration_seconds >= 0),
  ai_speaking_seconds integer default 0,
  user_speaking_seconds integer default 0,
  stt_total_ms integer default 0,
  tts_total_ms integer default 0,
  turns jsonb default '[]'::jsonb,
  full_transcript text,
  sentiment_score text default 'satisfied',
  security_flagged boolean default false,
  recording_status varchar(20) default 'disabled' not null check (recording_status in ('disabled', 'processing', 'ready', 'failed')),
  recording_storage_path text,
  audio_recording_url text,
  telemetry_summary jsonb not null default '{}'::jsonb,
  call_budget_seconds integer not null default 120 check (call_budget_seconds between 1 and 120),
  caller_identity text,
  provider_call_sid text,
  admission_expires_at timestamp with time zone,
  provider_started_at timestamp with time zone,
  deadline_at timestamp with time zone,
  quota_charged_at timestamp with time zone,
  charged_seconds integer not null default 0 check (charged_seconds >= 0),
  end_reason text,
  booking_proposal jsonb,
  booking_result jsonb,
  room_name varchar,
  call_status varchar(20) default 'ringing' not null,
  intent_classification varchar default 'UNCLASSIFIED',
  triage_latency_ms integer default 0,
  start_time timestamp with time zone default timezone('utc'::text, now()) not null,
  connected_at timestamp with time zone,
  agent_joined_at timestamp with time zone,
  end_time timestamp with time zone,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  constraint uq_call_logs_org_id unique (org_id, id)
);




create table public.voice_call_turns (
  id uuid primary key default gen_random_uuid(),
  session_id uuid not null,
  org_id uuid not null references public.organizations(id) on delete cascade,
  event_id text,
  speech_id text,
  turn_number integer not null,
  user_transcript text,
  user_audio_url text,
  ai_filler_text text,
  ai_filler_audio_url text,
  ai_response_text text,
  ai_response_audio_url text,
  interrupted boolean not null default false,
  prompt_tokens integer not null default 0 check (prompt_tokens >= 0),
  completion_tokens integer not null default 0 check (completion_tokens >= 0),
  stt_latency_ms integer,
  llm_latency_ms integer,
  tts_latency_ms integer,
  total_latency_ms integer,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  constraint voice_turn_tenant_session_fk foreign key (org_id, session_id) references public.call_logs(org_id, id) on delete cascade
);

create unique index if not exists idx_voice_turn_event on public.voice_call_turns(session_id, event_id) where event_id is not null;
create unique index if not exists idx_voice_turns_session_speech on public.voice_call_turns(session_id, speech_id) where speech_id is not null;
create index if not exists idx_voice_open_deadline on public.call_logs(deadline_at) where end_time is null;

create table if not exists public.voice_token_rate_limits (
  client_hash text not null,
  window_start timestamp with time zone not null,
  attempts integer not null check (attempts > 0),
  tokens bigint not null default 0 check (tokens >= 0),
  primary key (client_hash, window_start)
);
create index if not exists idx_voice_limit_expiry on public.voice_token_rate_limits(window_start);
revoke all on public.voice_token_rate_limits from public, anon, authenticated;

create table public.appointments (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  patient_id uuid not null,
  doctor_id uuid,
  start_time timestamp with time zone not null,
  end_time timestamp with time zone not null,
  appointment_timezone text not null,
  status appointment_status not null default 'scheduled',
  queue_state text not null default 'not_checked_in' check (queue_state in ('not_checked_in', 'waiting', 'called', 'stepped_out', 'served')),
  encounter_state text not null default 'not_started' check (encounter_state in ('not_started', 'in_progress', 'completed')),
  called_at timestamp with time zone,
  call_count integer not null default 0,
  booking_metadata jsonb default '{}'::jsonb,
  source appointment_source not null default 'ai_voice',
  chief_complaint text,
  doctor_notes text,
  token_number integer,
  display_token varchar(10),
  shift_type varchar(10),
  call_session_id uuid references public.call_logs(id) on delete set null,
  cancellation_reason text,
  checked_in_at timestamp with time zone,
  checked_in_by uuid references public.users(id) on delete set null,
  consultation_started_at timestamp with time zone,
  consultation_ended_at timestamp with time zone,
  actual_duration_seconds integer,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  updated_at timestamp with time zone default timezone('utc'::text, now()) not null,
  constraint ck_appointment_time_range check (end_time > start_time),
  constraint fk_appointments_patient foreign key (org_id, patient_id) references public.patients(org_id, id) on delete cascade,
  constraint fk_appointments_doctor foreign key (doctor_id) references public.users(id) on delete set null
);

create or replace function public.set_appointment_timezone()
returns trigger
language plpgsql
security definer set search_path = public
as $$
begin
  if new.appointment_timezone is null or trim(new.appointment_timezone) = '' then
    select nullif(trim(timezone), '') into new.appointment_timezone
    from public.organizations where id = new.org_id;
  end if;
  if new.appointment_timezone is null then
    raise exception 'Clinic timezone is required for appointments';
  end if;
  return new;
end;
$$;

create trigger set_appointment_timezone_before_write
  before insert or update of org_id on public.appointments
  for each row execute function public.set_appointment_timezone();

create table public.visit_events (
  id uuid primary key default gen_random_uuid(),
  visit_id uuid not null references public.appointments(id) on delete cascade,
  org_id uuid not null,
  event_type text not null,
  occurred_at timestamp with time zone not null default timezone('utc'::text, now()),
  actor_id uuid,
  actor_type text not null default 'staff',
  notes text,
  event_metadata jsonb not null default '{}'::jsonb
);

create table public.payments (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  appointment_id uuid not null references public.appointments(id) on delete cascade,
  amount numeric(12, 2) not null,
  status payment_status not null,
  method varchar not null,
  reference varchar,
  received_by uuid references public.users(id) on delete set null,
  received_at timestamp with time zone default now() not null
);

create table public.schedule_overrides (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  doctor_id uuid references public.users(id) on delete cascade,
  title text not null default 'Schedule Override',
  override_type text not null default 'vacation',
  is_available boolean not null default false,
  start_date date not null,
  end_date date not null,
  custom_hours jsonb,
  reason text,
  emergency_phone text,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create table public.system_audit_logs (
  id uuid primary key default gen_random_uuid(),
  org_id uuid references public.organizations(id) on delete cascade,
  actor_id uuid references public.users(id) on delete set null,
  actor_email text not null,
  action_type text not null,
  target_id uuid,
  target_name text,
  old_state jsonb default '{}'::jsonb,
  new_state jsonb default '{}'::jsonb,
  metadata jsonb default '{}'::jsonb,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null
);

create index idx_schedule_overrides_dates on public.schedule_overrides(org_id, start_date, end_date);
create index idx_users_org_role on public.users(org_id, role, is_active);
create index idx_patients_org_phone on public.patients(org_id, phone_number);
create index idx_patients_name on public.patients(org_id, lower(first_name), lower(coalesce(last_name, '')));
create index idx_appointments_org_time on public.appointments(org_id, start_time);
create index idx_appointments_doctor_schedule on public.appointments(org_id, doctor_id, start_time) where (status not in ('cancelled', 'no_show'));
create index idx_appointments_patient on public.appointments(patient_id, status);
create index idx_visit_events_visit_time on public.visit_events(org_id, visit_id, occurred_at);
create index idx_call_logs_org on public.call_logs(org_id, start_time desc);
create index idx_call_logs_caller on public.call_logs(caller_phone);
create index idx_call_logs_patient on public.call_logs(org_id, patient_id, start_time desc) where (patient_id is not null);
create unique index uq_call_logs_room_org on public.call_logs(org_id, room_name) where (room_name is not null);
create index idx_voice_call_turns_session on public.voice_call_turns(session_id, turn_number);
create index idx_voice_call_turns_org on public.voice_call_turns(org_id, created_at desc);
create index idx_payments_org_date on public.payments(org_id, received_at desc);
create index idx_payments_appointment on public.payments(appointment_id);
create index idx_audit_logs_org_date on public.system_audit_logs(org_id, created_at desc);

alter table public.organizations enable row level security;
alter table public.users enable row level security;
alter table public.patients enable row level security;
alter table public.appointments enable row level security;
alter table public.visit_events enable row level security;
alter table public.schedule_overrides enable row level security;
alter table public.call_logs enable row level security;
alter table public.voice_call_turns enable row level security;
alter table public.system_audit_logs enable row level security;
alter table public.payments enable row level security;

create policy "Service layer can manage organizations" on public.organizations for all to service_role using (true) with check (true);
create policy "Service layer can manage users" on public.users for all to service_role using (true) with check (true);
create policy "Service layer can manage patients" on public.patients for all to service_role using (true) with check (true);
create policy "Service layer can manage appointments" on public.appointments for all to service_role using (true) with check (true);
create policy "Service layer can manage visit_events" on public.visit_events for all to service_role using (true) with check (true);
create policy "Service layer can manage schedule_overrides" on public.schedule_overrides for all to service_role using (true) with check (true);
create policy "Browser can read tenant call logs" on public.call_logs for select to authenticated using (org_id = (select private.current_org_id()));
create policy "Browser can read tenant call turns" on public.voice_call_turns for select to authenticated using (org_id = (select private.current_org_id()));
create policy "Service role can manage call_logs" on public.call_logs for all to service_role using (true) with check (true);
create policy "Service role can manage voice_call_turns" on public.voice_call_turns for all to service_role using (true) with check (true);
create policy "Service layer can manage system_audit_logs" on public.system_audit_logs for all to service_role using (true) with check (true);
create policy "Service layer can manage payments" on public.payments for all to service_role using (true) with check (true);

create or replace function public.register_organization_and_admin(
  p_org_name text,
  p_slug text,
  p_city text,
  p_user_id uuid,
  p_email text,
  p_full_name text,
  p_clinic_specialty text default null,
  p_lead_doctor_name text default null,
  p_phone text default null,
  p_country text default null,
  p_country_code text default null,
  p_currency_code text default null,
  p_currency_symbol text default null,
  p_timezone text default null,
  p_address text default null,
  p_slot_duration integer default null,
  p_emergency_phone text default null
)
returns jsonb
language plpgsql
security definer set search_path = public
as $$
declare
  v_org_id uuid;
  v_auth_email text;
begin
  if auth.uid() is null or p_user_id is distinct from auth.uid() then
    raise exception 'Authenticated user mismatch' using errcode = '42501';
  end if;
  select email into v_auth_email from auth.users where id = p_user_id;
  if v_auth_email is null or lower(trim(p_email)) is distinct from lower(v_auth_email) then
    raise exception 'Authenticated email mismatch' using errcode = '42501';
  end if;
  if exists(select 1 from public.users where id = p_user_id and org_id is not null) then
    raise exception 'User already belongs to a clinic';
  end if;
  if nullif(trim(p_org_name), '') is null or nullif(trim(p_city), '') is null
     or nullif(trim(p_country), '') is null or nullif(trim(p_country_code), '') is null
     or nullif(trim(p_currency_code), '') is null or nullif(trim(p_currency_symbol), '') is null
     or nullif(trim(p_timezone), '') is null or nullif(trim(p_clinic_specialty), '') is null
     or nullif(trim(p_emergency_phone), '') is null then
    raise exception 'Clinic name, city, country, currency, timezone, specialty, and emergency contact are required';
  end if;
  select id into v_org_id 
  from public.organizations 
  where slug = lower(trim(p_slug))
  limit 1;

  if v_org_id is not null then
    raise exception 'Clinic slug already exists';
  end if;
    insert into public.organizations (
      name, 
      slug,
      city,
      address,
      phone, 
      country,
      country_code,
      currency_code,
      currency_symbol,
      timezone,
      booking_settings,
      voice_ai_settings
    )
    values (
      trim(p_org_name), 
      lower(trim(p_slug)),
      p_city,
      p_address,
      p_phone, 
      p_country,
      p_country_code,
      p_currency_code,
      p_currency_symbol,
      p_timezone,
      jsonb_build_object(
        'default_slot_duration_minutes', p_slot_duration,
        'weekly_schedule', '{}'::jsonb
      ),
      jsonb_build_object(
        'ai_voice_name', 'priya',
        'ai_language_mode', 'en_hi_bilingual',
        'ai_voice_role', 'receptionist',
        'ai_greeting_prompt', format('Hello! Thank you for calling %s. How may I assist you today?', trim(p_org_name)),
        'clinic_specialty', p_clinic_specialty,
        'lead_doctor_name', p_lead_doctor_name,
        'emergency_deflection_phone', nullif(trim(p_emergency_phone), '')
      )
    )
    returning id into v_org_id;

  insert into public.users (id, org_id, email, full_name, role, specialization)
  values (p_user_id, v_org_id, v_auth_email, p_full_name, 'doctor', p_clinic_specialty)
  on conflict (id) do update
  set org_id = excluded.org_id,
      full_name = excluded.full_name,
      role = excluded.role,
      specialization = excluded.specialization,
      email = excluded.email;

  insert into public.clinic_memberships (org_id, user_id, role, display_name, status, joined_at)
  values (v_org_id, p_user_id, 'admin', p_full_name, 'active', now());

  return jsonb_build_object(
    'org_id', v_org_id,
    'user_id', p_user_id,
    'role', 'doctor'
  );
end;
$$;

revoke all on function public.register_organization_and_admin(text, text, text, uuid, text, text, text, text, text, text, text, text, text, text, text, integer, text) from public, anon;
grant execute on function public.register_organization_and_admin(text, text, text, uuid, text, text, text, text, text, text, text, text, text, text, text, integer, text) to authenticated;

create or replace function public.handle_new_user_signup()
returns trigger
language plpgsql
security definer set search_path = public
as $$
declare
  v_org_id uuid;
  v_org_name text;
  v_slug text;
  v_city text;
  v_address text;
  v_timezone text;
  v_full_name text;
  v_role user_role;
  v_specialty text;
  v_lead_doc text;
  v_phone text;
  v_country text;
  v_country_code text;
  v_currency_code text;
  v_currency_symbol text;
  v_slot_dur integer;
  v_invite_id uuid;
  v_staff_name text;
  v_emergency_phone text;
begin
  v_full_name := coalesce(
    nullif(trim(new.raw_user_meta_data->>'full_name'), ''),
    nullif(trim(new.raw_user_meta_data->>'name'), ''),
    split_part(new.email, '@', 1)
  );

  select id, org_id, role, display_name
  into v_invite_id, v_org_id, v_role, v_staff_name
  from public.clinic_memberships
  where lower(invited_email) = lower(trim(new.email)) and status = 'invited'
  order by created_at desc
  limit 1;

  if v_org_id is null then
    select o.id, (staff->>'full_name'), coalesce(staff->>'role', 'receptionist')::user_role
    into v_org_id, v_staff_name, v_role
    from public.organizations o,
         jsonb_array_elements(coalesce(o.booking_settings->'authorized_staff', '[]'::jsonb)) as staff
    where lower(trim(staff->>'email')) = lower(trim(new.email))
    limit 1;
  end if;

  if v_org_id is not null then
    v_staff_name := coalesce(nullif(trim(v_staff_name), ''), v_full_name, 'Front Desk Staff');
    v_role := coalesce(v_role, 'receptionist'::user_role);

    insert into public.users (id, org_id, email, full_name, role, specialization, is_active)
    values (new.id, v_org_id, new.email, v_staff_name, v_role, null, true)
    on conflict (id) do update
    set org_id = coalesce(excluded.org_id, public.users.org_id),
        email = excluded.email,
        full_name = coalesce(excluded.full_name, public.users.full_name),
        role = excluded.role,
        is_active = true;

    if v_invite_id is not null then
      update public.clinic_memberships
      set user_id = new.id,
          display_name = v_staff_name,
          status = 'active',
          revoked_at = null,
          joined_at = coalesce(joined_at, now()),
          updated_at = now()
      where id = v_invite_id;
    else
      insert into public.clinic_memberships (org_id, user_id, role, display_name, status, joined_at)
      values (v_org_id, new.id, v_role, v_staff_name, 'active', now())
      on conflict (org_id, user_id) do update
      set role = excluded.role,
          display_name = excluded.display_name,
          status = 'active',
          revoked_at = null,
          updated_at = now();
    end if;

    return new;
  end if;

  v_full_name := coalesce(
    nullif(trim(new.raw_user_meta_data->>'full_name'), ''),
    nullif(trim(new.raw_user_meta_data->>'name'), ''),
    split_part(new.email, '@', 1)
  );
  v_org_name := nullif(trim(new.raw_user_meta_data->>'org_name'), '');
  if v_org_name is null then
    return new;
  end if;
  v_slug := coalesce(
    nullif(trim(new.raw_user_meta_data->>'slug'), ''),
    regexp_replace(lower(trim(v_org_name)), '[^a-z0-9]+', '-', 'g')
  ) || '-' || substr(gen_random_uuid()::text, 1, 6);
  v_city := nullif(trim(new.raw_user_meta_data->>'city'), '');
  v_address := nullif(trim(new.raw_user_meta_data->>'address'), '');
  v_emergency_phone := nullif(trim(new.raw_user_meta_data->>'emergency_deflection_phone'), '');
  v_timezone := nullif(trim(new.raw_user_meta_data->>'timezone'), '');
  v_specialty := nullif(trim(new.raw_user_meta_data->>'clinic_specialty'), '');
  v_lead_doc := nullif(trim(new.raw_user_meta_data->>'lead_doctor_name'), '');
  v_phone := new.raw_user_meta_data->>'phone';
  v_country := nullif(trim(new.raw_user_meta_data->>'country'), '');
  v_country_code := nullif(trim(new.raw_user_meta_data->>'country_code'), '');
  v_currency_code := nullif(trim(new.raw_user_meta_data->>'currency_code'), '');
  v_currency_symbol := nullif(trim(new.raw_user_meta_data->>'currency_symbol'), '');
  if v_city is null or v_country is null or v_country_code is null
     or v_currency_code is null or v_currency_symbol is null or v_timezone is null
     or v_specialty is null or v_lead_doc is null or v_emergency_phone is null then
    raise exception 'Clinic signup metadata is incomplete';
  end if;

  begin
    v_slot_dur := (new.raw_user_meta_data->>'default_slot_duration_minutes')::integer;
  exception when others then
    v_slot_dur := null;
  end;

  v_role := 'doctor'::user_role;

  insert into public.organizations (
    name, 
    slug,
    city,
    address,
    phone, 
    country,
    country_code,
    currency_code,
    currency_symbol,
    timezone,
    booking_settings,
    voice_ai_settings
  )
  values (
    v_org_name, 
    v_slug,
    v_city,
    v_address,
    v_phone, 
    v_country,
    v_country_code,
    v_currency_code,
    v_currency_symbol,
    v_timezone,
    jsonb_build_object(
      'default_slot_duration_minutes', v_slot_dur,
      'slot_buffer_minutes', null,
      'max_daily_patients', null,
      'weekly_schedule', '{}'::jsonb
    ),
    jsonb_build_object(
      'ai_voice_name', 'priya',
      'ai_language_mode', 'en_hi_bilingual',
      'ai_voice_role', 'receptionist',
      'ai_greeting_prompt', format('Hello! Welcome to %s. How can I help you today?', v_org_name),
      'clinic_specialty', v_specialty,
      'lead_doctor_name', v_lead_doc,
      'emergency_deflection_phone', v_emergency_phone,
      'demo_voice_balance_seconds', 1800,
      'demo_voice_total_seconds', 1800
    )
  )
  returning id into v_org_id;

  insert into public.users (id, org_id, email, full_name, role, specialization, is_active)
  values (new.id, v_org_id, new.email, v_full_name, v_role, v_specialty, true)
  on conflict (id) do update
  set org_id = excluded.org_id,
      full_name = excluded.full_name,
      role = excluded.role,
      specialization = excluded.specialization,
      email = excluded.email,
      is_active = true;

  insert into public.clinic_memberships (org_id, user_id, role, display_name, status, joined_at)
  values (v_org_id, new.id, 'admin', v_full_name, 'active', now())
  on conflict (org_id, user_id) do update
  set role = excluded.role,
      display_name = excluded.display_name,
      status = 'active',
      revoked_at = null,
      updated_at = now();

  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute function public.handle_new_user_signup();

-- Voice lifecycle hardening (kept in sync with 20261012_voice_hardening.sql).
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
