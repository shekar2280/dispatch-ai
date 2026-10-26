begin;

do $$
declare
  target_table text;
  policy_name text;
begin
  for target_table, policy_name in
    select * from (values
      ('schedule_overrides', 'Service layer can manage schedule_overrides'),
      ('payments', 'Service layer can manage payments'),
      ('doctor_schedule_overrides', 'Service layer can manage doctor_schedule_overrides')
    ) as targets(table_name, policy_name)
  loop
    if to_regclass(format('public.%I', target_table)) is not null then
      execute format('drop policy if exists %I on public.%I', policy_name, target_table);
      execute format(
        'create policy %I on public.%I for all to service_role using (true) with check (true)',
        policy_name,
        target_table
      );
      execute format('revoke all on public.%I from public, anon, authenticated', target_table);
    end if;
  end loop;
end $$;

update public.organizations
set booking_settings = booking_settings - 'staff_pin'
where booking_settings ? 'staff_pin';

commit;
