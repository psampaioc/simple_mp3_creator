-- Also fail old projects that were inserted without a corresponding job.
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
  orphan_count integer := 0;
begin
  with stale_jobs as (
    update public.jobs
    set status = 'failed', stage = 'failed', finished_at = timezone('utc', now()),
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
    set status = 'failed', stage = 'failed', finished_at = timezone('utc', now()),
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

  update public.projects p
  set status = 'failed'
  where p.status in ('queued', 'extracting', 'generating', 'tagging', 'uploading')
    and p.created_at < timezone('utc', now()) - make_interval(secs => greatest(p_queue_timeout_seconds, 1))
    and not exists (select 1 from public.jobs j where j.project_id = p.id);
  get diagnostics orphan_count = row_count;

  return queued_count + running_count + orphan_count;
end;
$$;

revoke all on function public.cleanup_stale_jobs(integer, integer) from public;
grant execute on function public.cleanup_stale_jobs(integer, integer) to service_role;
