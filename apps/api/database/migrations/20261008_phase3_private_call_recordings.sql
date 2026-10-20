begin;
insert into storage.buckets (id, name, public)
values ('call-recordings', 'call-recordings', false)
on conflict (id) do update set public = false;

drop policy if exists call_recordings_server_only on storage.objects;
create policy call_recordings_server_only
on storage.objects as restrictive for all to anon, authenticated
using (bucket_id <> 'call-recordings')
with check (bucket_id <> 'call-recordings');
commit;
