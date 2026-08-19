-- Keep failed generations out of the user's audio list while retaining a
-- small troubleshooting record that contains no source text.
create table if not exists public.generation_errors (
  id uuid primary key default gen_random_uuid(),
  project_id uuid,
  user_id uuid not null references auth.users(id) on delete cascade,
  error_code text not null,
  error_detail text,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists generation_errors_user_created_idx
  on public.generation_errors(user_id, created_at desc);

alter table public.generation_errors enable row level security;
revoke all on public.generation_errors from anon, authenticated;
grant all on public.generation_errors to service_role;

create or replace function public.cleanup_stale_jobs(
  p_queue_timeout_seconds integer default 3600,
  p_running_timeout_seconds integer default 900
)
returns integer
language plpgsql
security definer
set search_path = public
as $$
declare
  cleaned_count integer := 0;
begin
  with stale_jobs as (
    update public.jobs
    set status = 'failed', stage = 'failed', finished_at = timezone('utc', now()),
        error_code = case when status = 'queued' then 'QUEUE_TIMEOUT' else 'WORKER_TIMEOUT' end,
        error_detail = case when status = 'queued'
          then 'The media worker did not start within the queue timeout.'
          else 'The media worker exceeded the generation timeout.' end
    where (status = 'queued' and created_at < timezone('utc', now()) - make_interval(secs => greatest(p_queue_timeout_seconds, 1)))
       or (status in ('generating', 'tagging', 'uploading') and coalesce(locked_at, started_at, created_at) < timezone('utc', now()) - make_interval(secs => greatest(p_running_timeout_seconds, 1)))
    returning project_id, user_id, error_code, error_detail
  ), logged_jobs as (
    insert into public.generation_errors(project_id, user_id, error_code, error_detail)
    select project_id, user_id, error_code, error_detail from stale_jobs
    returning project_id
  )
  delete from public.projects p using logged_jobs l where p.id = l.project_id;

  get diagnostics cleaned_count = row_count;

  delete from public.projects p
  where p.status in ('queued', 'extracting', 'generating', 'tagging', 'uploading')
    and p.created_at < timezone('utc', now()) - make_interval(secs => greatest(p_queue_timeout_seconds, 1))
    and not exists (select 1 from public.jobs j where j.project_id = p.id);

  return cleaned_count;
end;
$$;

revoke all on function public.cleanup_stale_jobs(integer, integer) from public;
grant execute on function public.cleanup_stale_jobs(integer, integer) to service_role;
