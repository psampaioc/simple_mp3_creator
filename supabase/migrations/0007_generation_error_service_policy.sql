-- Keep the error log service-only while documenting the intended RLS policy.
create policy generation_errors_service_only
  on public.generation_errors
  for all
  to service_role
  using (true)
  with check (true);
