-- Remove implicit organization and payment values. Existing rows are preserved.
alter table public.organizations alter column timezone drop default;
alter table public.organizations alter column country drop default;
alter table public.organizations alter column country_code drop default;
alter table public.organizations alter column currency_code drop default;
alter table public.organizations alter column currency_symbol drop default;
alter table public.organizations alter column booking_settings set default '{}'::jsonb;
alter table public.organizations alter column voice_ai_settings set default '{}'::jsonb;
alter table public.organizations add constraint ck_organizations_required_config check (
  nullif(trim(name), '') is not null and nullif(trim(timezone), '') is not null
  and nullif(trim(country), '') is not null and nullif(trim(country_code), '') is not null
  and nullif(trim(currency_code), '') is not null and nullif(trim(currency_symbol), '') is not null
) not valid;
alter table public.payments alter column status drop default;
alter table public.appointments add column if not exists appointment_timezone text;
update public.appointments a
set appointment_timezone = nullif(trim(o.timezone), '')
from public.organizations o
where a.org_id = o.id and a.appointment_timezone is null and nullif(trim(o.timezone), '') is not null;
do $$
begin
  if exists (select 1 from public.appointments where appointment_timezone is null or trim(appointment_timezone) = '') then
    raise exception 'Cannot enforce NOT NULL on appointments.appointment_timezone: unassigned appointments found';
  end if;
end $$;
alter table public.appointments alter column appointment_timezone set not null;

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

drop trigger if exists set_appointment_timezone_before_write on public.appointments;
create trigger set_appointment_timezone_before_write
  before insert or update of org_id on public.appointments
  for each row execute function public.set_appointment_timezone();

drop function if exists public.register_organization_and_admin(text, text, uuid, text, text, text, text, text, text, integer);
drop function if exists public.register_organization_and_admin(text, text, text, uuid, text, text, text, text, text, text, text, text, text, text, text, integer);
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
begin
  if auth.uid() is null or p_user_id is distinct from auth.uid() then
    raise exception 'Authenticated user mismatch' using errcode = '42501';
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
  values (p_user_id, v_org_id, p_email, p_full_name, 'admin', p_clinic_specialty)
  on conflict (id) do update
  set org_id = excluded.org_id,
      full_name = excluded.full_name,
      specialization = excluded.specialization,
      email = excluded.email;

  return jsonb_build_object(
    'org_id', v_org_id,
    'user_id', p_user_id,
    'role', 'admin'
  );
end;
$$;

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

  v_role := 'admin'::user_role;

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
  values (v_org_id, new.id, v_role, v_full_name, 'active', now())
  on conflict (org_id, user_id) do update
  set role = excluded.role,
      display_name = excluded.display_name,
      status = 'active',
      revoked_at = null,
      updated_at = now();

  return new;
end;
$$;
