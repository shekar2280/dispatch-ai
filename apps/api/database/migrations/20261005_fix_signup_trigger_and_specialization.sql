ALTER TABLE public.users ADD COLUMN IF NOT EXISTS specialization text;

DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'clinic_closures') THEN
    ALTER TABLE public.clinic_closures RENAME TO schedule_overrides;
  END IF;
  IF EXISTS (SELECT 1 FROM pg_indexes WHERE schemaname = 'public' AND indexname = 'idx_clinic_closures_dates') THEN
    ALTER INDEX public.idx_clinic_closures_dates RENAME TO idx_schedule_overrides_dates;
  END IF;
END $$;

CREATE TABLE IF NOT EXISTS public.schedule_overrides (
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

ALTER TABLE public.schedule_overrides ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS "Service layer can manage clinic_closures" ON public.schedule_overrides;
DROP POLICY IF EXISTS "Service layer can manage schedule_overrides" ON public.schedule_overrides;
CREATE POLICY "Service layer can manage schedule_overrides" ON public.schedule_overrides FOR ALL USING (true) WITH CHECK (true);

CREATE OR REPLACE FUNCTION public.register_organization_and_admin(
  p_org_name text,
  p_slug text,
  p_city text,
  p_user_id uuid,
  p_email text,
  p_full_name text,
  p_clinic_specialty text default 'General Practice',
  p_lead_doctor_name text default null,
  p_phone text default null,
  p_country text default 'India',
  p_country_code text default 'IN',
  p_currency_code text default 'INR',
  p_currency_symbol text default '₹',
  p_timezone text default 'UTC',
  p_address text default null,
  p_slot_duration integer default 15
)
RETURNS jsonb
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
  v_org_id uuid;
BEGIN
  SELECT id INTO v_org_id 
  FROM public.organizations 
  WHERE slug = lower(trim(p_slug))
  LIMIT 1;

  IF v_org_id IS NULL THEN
    INSERT INTO public.organizations (
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
    VALUES (
      trim(p_org_name), 
      lower(trim(p_slug)),
      p_city,
      p_address,
      p_phone, 
      p_country,
      p_country_code,
      p_currency_code,
      p_currency_symbol,
      coalesce(nullif(trim(p_timezone), ''), 'UTC'),
      jsonb_build_object(
        'consultation_fee', 500,
        'default_slot_duration_minutes', coalesce(p_slot_duration, 15),
        'slot_buffer_minutes', 5,
        'max_daily_patients', 30,
        'weekly_schedule', '{}'::jsonb
      ),
      jsonb_build_object(
        'ai_voice_name', 'priya',
        'ai_language_mode', 'en_hi_bilingual',
        'ai_voice_role', 'receptionist',
        'ai_greeting_prompt', format('Hello! Thank you for calling %s. How may I assist you today?', trim(p_org_name)),
        'clinic_specialty', p_clinic_specialty,
        'lead_doctor_name', p_lead_doctor_name,
        'emergency_deflection_phone', '108'
      )
    )
    RETURNING id INTO v_org_id;
  END IF;

  INSERT INTO public.users (id, org_id, email, full_name, role, specialization)
  VALUES (p_user_id, v_org_id, p_email, p_full_name, 'admin', p_clinic_specialty)
  ON CONFLICT (id) DO UPDATE
  SET org_id = excluded.org_id,
      full_name = excluded.full_name,
      specialization = excluded.specialization,
      email = excluded.email;

  RETURN jsonb_build_object(
    'org_id', v_org_id,
    'user_id', p_user_id,
    'role', 'admin'
  );
END;
$$;

CREATE OR REPLACE FUNCTION public.handle_new_user_signup()
RETURNS trigger
LANGUAGE plpgsql
SECURITY DEFINER SET search_path = public
AS $$
DECLARE
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
  v_existing_id uuid;
  v_staff_name text;
  v_staff_role text;
BEGIN
  SELECT id INTO v_existing_id FROM public.users WHERE id = new.id OR lower(email) = lower(new.email) LIMIT 1;
  IF v_existing_id IS NOT NULL THEN
    RETURN new;
  END IF;

  SELECT o.id, (staff->>'full_name'), coalesce(staff->>'role', 'receptionist')
  INTO v_org_id, v_staff_name, v_staff_role
  FROM public.organizations o,
       jsonb_array_elements(coalesce(o.booking_settings->'authorized_staff', '[]'::jsonb)) AS staff
  WHERE lower(trim(staff->>'email')) = lower(trim(new.email))
  LIMIT 1;

  IF v_org_id IS NOT NULL THEN
    v_full_name := coalesce(nullif(trim(v_staff_name), ''), 'Front Desk Staff');
    v_role := 'receptionist'::user_role;

    INSERT INTO public.users (id, org_id, email, full_name, role, specialization, is_active)
    VALUES (new.id, v_org_id, new.email, v_full_name, v_role, null, true)
    ON CONFLICT (id) DO UPDATE
    SET org_id = excluded.org_id,
        full_name = excluded.full_name,
        role = excluded.role,
        specialization = excluded.specialization,
        email = excluded.email;

    RETURN new;
  END IF;

  v_full_name := coalesce(
    nullif(trim(new.raw_user_meta_data->>'full_name'), ''),
    nullif(trim(new.raw_user_meta_data->>'name'), ''),
    split_part(new.email, '@', 1)
  );
  v_org_name := coalesce(
    nullif(trim(new.raw_user_meta_data->>'org_name'), ''),
    v_full_name || '''s Practice'
  );
  v_slug := coalesce(
    nullif(trim(new.raw_user_meta_data->>'slug'), ''),
    regexp_replace(lower(trim(v_org_name)), '[^a-z0-9]+', '-', 'g')
  ) || '-' || substr(gen_random_uuid()::text, 1, 6);
  v_city := coalesce(nullif(trim(new.raw_user_meta_data->>'city'), ''), 'Bengaluru');
  v_address := coalesce(nullif(trim(new.raw_user_meta_data->>'address'), ''), '100 Feet Road, Indiranagar');
  v_timezone := coalesce(nullif(trim(new.raw_user_meta_data->>'timezone'), ''), 'Asia/Kolkata');
  v_specialty := coalesce(nullif(trim(new.raw_user_meta_data->>'clinic_specialty'), ''), 'General Practice');
  v_lead_doc := coalesce(nullif(trim(new.raw_user_meta_data->>'lead_doctor_name'), ''), 'Dr. ' || v_full_name);
  v_phone := new.raw_user_meta_data->>'phone';
  v_country := coalesce(nullif(trim(new.raw_user_meta_data->>'country'), ''), 'India');
  v_country_code := coalesce(nullif(trim(new.raw_user_meta_data->>'country_code'), ''), 'IN');
  v_currency_code := coalesce(nullif(trim(new.raw_user_meta_data->>'currency_code'), ''), 'INR');
  v_currency_symbol := coalesce(nullif(trim(new.raw_user_meta_data->>'currency_symbol'), ''), '₹');

  BEGIN
    v_slot_dur := (new.raw_user_meta_data->>'default_slot_duration_minutes')::integer;
  EXCEPTION WHEN others THEN
    v_slot_dur := 15;
  END;

  v_role := 'admin'::user_role;

  INSERT INTO public.organizations (
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
  VALUES (
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
      'consultation_fee', 500,
      'default_slot_duration_minutes', coalesce(v_slot_dur, 15),
      'slot_buffer_minutes', 5,
      'max_daily_patients', 30,
      'booking_quota_per_window', 2,
      'window_duration_minutes', 30,
      'weekly_schedule', jsonb_build_object(
        'monday', jsonb_build_array(jsonb_build_object('start', '09:00', 'end', '13:00'), jsonb_build_object('start', '17:00', 'end', '20:00')),
        'tuesday', jsonb_build_array(jsonb_build_object('start', '09:00', 'end', '13:00'), jsonb_build_object('start', '17:00', 'end', '20:00')),
        'wednesday', jsonb_build_array(jsonb_build_object('start', '09:00', 'end', '13:00'), jsonb_build_object('start', '17:00', 'end', '20:00')),
        'thursday', jsonb_build_array(jsonb_build_object('start', '09:00', 'end', '13:00'), jsonb_build_object('start', '17:00', 'end', '20:00')),
        'friday', jsonb_build_array(jsonb_build_object('start', '09:00', 'end', '13:00'), jsonb_build_object('start', '17:00', 'end', '20:00')),
        'saturday', jsonb_build_array(jsonb_build_object('start', '09:00', 'end', '13:00'), jsonb_build_object('start', '17:00', 'end', '20:00')),
        'sunday', '[]'::jsonb
      )
    ),
    jsonb_build_object(
      'ai_voice_name', 'priya',
      'ai_language_mode', 'en_hi_bilingual',
      'ai_voice_role', 'receptionist',
      'ai_greeting_prompt', format('Hello! Welcome to %s. How can I help you today?', v_org_name),
      'clinic_specialty', v_specialty,
      'lead_doctor_name', v_lead_doc,
      'emergency_deflection_phone', '108',
      'demo_voice_balance_seconds', 1800,
      'demo_voice_total_seconds', 1800
    )
  )
  RETURNING id INTO v_org_id;

  INSERT INTO public.users (id, org_id, email, full_name, role, specialization)
  VALUES (new.id, v_org_id, new.email, v_full_name, v_role, v_specialty)
  ON CONFLICT (id) DO UPDATE
  SET org_id = excluded.org_id,
      full_name = excluded.full_name,
      role = excluded.role,
      specialization = excluded.specialization,
      email = excluded.email;

  RETURN new;
END;
$$;
