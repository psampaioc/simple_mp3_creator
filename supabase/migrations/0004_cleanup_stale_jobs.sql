-- Fail abandoned jobs quickly so one lost dispatch or worker cannot block a user.
create or replace function public.cleanup_stale_jobs(
  p_queue_timeout_seconds integer default 120,
  p_running_timeout_seconds integer default 900
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  queued_count integer := 0;
  running_count integer := 0;
begin
  with stale_jobs as (
    update public.jobs
    set status = 'failed',
        stage = 'failed',
        finished_at = timezone('utc', now()),
        error_code = 'QUEUE_TIMEOUT',
        error_detail = 'The media worker did not start within the queue timeout.'
    where status = 'queued'
      and created_at < timezone('utc', now()) - make_interval(secs => greatest(p_queue_timeout_seconds, 1))
    returning project_id
  )
  update public.projects
  set status = 'failed'
  where id in (select project_id from stale_jobs)
    and status in ('queued', 'extracting', 'generating', 'tagging', 'uploading');
  get diagnostics queued_count = row_count;

  with stale_jobs as (
    update public.jobs
    set status = 'failed',
        stage = 'failed',
        finished_at = timezone('utc', now()),
        error_code = 'WORKER_TIMEOUT',
        error_detail = 'The media worker exceeded the generation timeout.'
    where status in ('generating', 'tagging', 'uploading')
      and coalesce(locked_at, started_at, created_at) < timezone('utc', now()) - make_interval(secs => greatest(p_running_timeout_seconds, 1))
    returning project_id
  )
  update public.projects
  set status = 'failed'
  where id in (select project_id from stale_jobs)
    and status in ('queued', 'extracting', 'generating', 'tagging', 'uploading');
  get diagnostics running_count = row_count;

  return queued_count + running_count;
end;
$$;

revoke all on function public.cleanup_stale_jobs(integer, integer) from public;
grant execute on function public.cleanup_stale_jobs(integer, integer) to service_role;

-- Run cleanup whenever a worker is dispatched, including after an old worker
-- crashed or a previous dispatch was lost.
create or replace function public.claim_next_job(p_worker_id text, p_job_id uuid default null)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  claimed public.jobs;
  project_row public.projects;
begin
  perform public.cleanup_stale_jobs(120, 900);

  select * into claimed
  from public.jobs
  where status = 'queued'
    and (p_job_id is null or id = p_job_id)
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

revoke all on function public.claim_next_job(text, uuid) from public;
grant execute on function public.claim_next_job(text, uuid) to service_role;
