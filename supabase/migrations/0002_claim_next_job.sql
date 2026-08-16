-- Atomically claim one queued job for the standalone worker.
create or replace function public.claim_next_job(p_worker_id text)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  claimed public.jobs;
  project_row public.projects;
begin
  select * into claimed
  from public.jobs
  where status = 'queued'
    and next_run_at <= timezone('utc', now())
    and (locked_at is null or locked_at < timezone('utc', now()) - interval '10 minutes')
  order by next_run_at, created_at
  for update skip locked
  limit 1;

  if claimed.id is null then
    return '{}'::jsonb;
  end if;

  update public.jobs
  set status = 'generating', stage = 'generating', attempt = attempt + 1,
      locked_at = timezone('utc', now()), locked_by = p_worker_id
  where id = claimed.id
  returning * into claimed;

  select * into project_row from public.projects where id = claimed.project_id;
  return jsonb_build_object('id', claimed.id, 'project_id', claimed.project_id, 'user_id', claimed.user_id,
    'status', claimed.status, 'stage', claimed.stage, 'attempt', claimed.attempt, 'project', to_jsonb(project_row));
end;
$$;

revoke all on function public.claim_next_job(text) from public;
grant execute on function public.claim_next_job(text) to service_role;
