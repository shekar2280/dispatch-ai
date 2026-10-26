begin;
alter table public.patients add column if not exists deleted_at timestamptz;
alter table public.patients add column if not exists deleted_by uuid;
create index if not exists idx_patients_active_by_org on public.patients (org_id, created_at desc) where deleted_at is null;
revoke update, delete on public.system_audit_logs from public, anon, authenticated;
grant select, insert on public.system_audit_logs to service_role;
commit;
