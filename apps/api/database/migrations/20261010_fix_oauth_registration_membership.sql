begin;

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
  values (p_user_id, v_org_id, v_auth_email, p_full_name, 'admin', p_clinic_specialty)
  on conflict (id) do update
  set org_id = excluded.org_id,
      full_name = excluded.full_name,
      specialization = excluded.specialization,
      email = excluded.email;

  insert into public.clinic_memberships (org_id, user_id, role, display_name, status, joined_at)
  values (v_org_id, p_user_id, 'admin', p_full_name, 'active', now());

  return jsonb_build_object(
    'org_id', v_org_id,
    'user_id', p_user_id,
    'role', 'admin'
  );
end;
$$;

revoke all on function public.register_organization_and_admin(text, text, text, uuid, text, text, text, text, text, text, text, text, text, text, text, integer, text) from public, anon;
grant execute on function public.register_organization_and_admin(text, text, text, uuid, text, text, text, text, text, text, text, text, text, text, text, integer, text) to authenticated;

commit;
