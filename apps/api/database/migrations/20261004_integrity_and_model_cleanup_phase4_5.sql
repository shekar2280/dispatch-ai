create extension if not exists "btree_gist";

create type schedule_override_type as enum (
  'leave',
  'vacation',
  'overtime',
  'clinic_closure'
);

create table if not exists public.doctor_schedule_overrides (
  id uuid primary key default gen_random_uuid(),
  org_id uuid not null references public.organizations(id) on delete cascade,
  doctor_id uuid references public.users(id) on delete cascade,
  override_type schedule_override_type not null,
  start_time timestamp with time zone not null,
  end_time timestamp with time zone not null,
  is_available boolean not null default false,
  reason text,
  created_by uuid references public.users(id) on delete set null,
  created_at timestamp with time zone default timezone('utc'::text, now()) not null,
  constraint ck_override_time_range check (end_time > start_time)
);

create index if not exists idx_schedule_overrides_lookup 
  on public.doctor_schedule_overrides (org_id, doctor_id, start_time, end_time);

alter table public.voice_call_sessions 
  add column if not exists turns jsonb default '[]'::jsonb,
  add column if not exists ai_speaking_seconds integer default 0,
  add column if not exists user_speaking_seconds integer default 0,
  add column if not exists stt_total_ms integer default 0,
  add column if not exists tts_total_ms integer default 0;

alter table public.appointments
  add column if not exists checked_in_by uuid references public.users(id) on delete set null;

create index if not exists idx_patients_org_phone 
  on public.patients (org_id, phone_number);

create index if not exists idx_appointments_slot_range 
  on public.appointments (org_id, doctor_id, start_time, end_time) 
  where (status not in ('cancelled', 'no_show'));

alter table public.doctor_schedule_overrides enable row level security;
drop policy if exists "Service layer can manage doctor_schedule_overrides" on public.doctor_schedule_overrides;
create policy "Service layer can manage doctor_schedule_overrides" on public.doctor_schedule_overrides for all using (true) with check (true);
