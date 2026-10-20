begin;
alter table public.call_logs
  add column if not exists telemetry_summary jsonb not null default '{}'::jsonb,
  add column if not exists call_budget_seconds integer not null default 120;

alter table public.voice_call_turns
  add column if not exists speech_id text,
  add column if not exists prompt_tokens integer not null default 0,
  add column if not exists completion_tokens integer not null default 0;

create unique index if not exists idx_voice_turns_session_speech
on public.voice_call_turns(session_id, speech_id) where speech_id is not null;

do $$
begin
  if not exists (select 1 from pg_constraint where conname = 'chk_call_logs_call_budget') then
    alter table public.call_logs add constraint chk_call_logs_call_budget
      check (call_budget_seconds between 1 and 120);
  end if;
  if not exists (select 1 from pg_constraint where conname = 'chk_voice_turns_token_counts') then
    alter table public.voice_call_turns add constraint chk_voice_turns_token_counts
      check (prompt_tokens >= 0 and completion_tokens >= 0);
  end if;
end $$;

create table if not exists public.voice_token_rate_limits (
  client_hash text not null,
  window_start timestamptz not null,
  attempts integer not null check (attempts > 0),
  primary key (client_hash, window_start)
);
revoke all on public.voice_token_rate_limits from public, anon, authenticated;
alter table public.voice_token_rate_limits enable row level security;
commit;
