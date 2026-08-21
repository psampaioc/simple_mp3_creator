-- Local-reviewable schema for the managed boundary.
-- Apply only to a disposable/local Supabase instance first.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  plan text not null default 'free' check (plan in ('free', 'paid')),
  monthly_char_limit integer not null default 20000 check (monthly_char_limit > 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now())
);

create table if not exists public.projects (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  title text not null check (char_length(title) between 1 and 200),
  source_text text not null check (char_length(source_text) between 1 and 10000),
  character_count integer not null check (character_count between 1 and 10000),
  voice_id text not null,
  locale text not null,
  speech_rate text not null check (speech_rate in ('slow', 'normal', 'fast')),
  author text,
  output_format text not null default 'mp3' check (output_format = 'mp3'),
  cover_asset_id uuid,
  status text not null check (status in ('queued', 'generating', 'tagging', 'uploading', 'ready', 'failed')),
  duration_ms integer check (duration_ms is null or duration_ms > 0),
  output_size_bytes bigint check (output_size_bytes is null or output_size_bytes > 0),
  output_bitrate integer check (output_bitrate is null or output_bitrate > 0),
  created_at timestamptz not null default timezone('utc', now()),
  updated_at timestamptz not null default timezone('utc', now()),
  deleted_at timestamptz
);

alter table public.projects
  add column if not exists expires_at timestamptz not null default timezone('utc', now()) + interval '24 hours';

create table if not exists public.jobs (
  id uuid primary key default gen_random_uuid(),
  project_id uuid not null unique references public.projects(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  status text not null check (status in ('queued', 'generating', 'tagging', 'uploading', 'ready', 'failed')),
  stage text not null check (stage in ('queued', 'generating', 'tagging', 'uploading', 'ready', 'failed')),
  attempt integer not null default 0 check (attempt >= 0),
  max_attempts integer not null default 3 check (max_attempts between 1 and 3),
  locked_at timestamptz,
  locked_by text,
  next_run_at timestamptz not null default timezone('utc', now()),
  error_code text,
  error_detail text,
  created_at timestamptz not null default timezone('utc', now()),
  started_at timestamptz,
  finished_at timestamptz
);

create table if not exists public.assets (
  id uuid primary key default gen_random_uuid(),
  project_id uuid references public.projects(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  kind text not null check (kind in ('cover_original', 'cover_normalized', 'mp3')),
  storage_path text not null unique,
  content_type text not null,
  size_bytes bigint not null check (size_bytes > 0),
  checksum text,
  created_at timestamptz not null default timezone('utc', now()),
  expires_at timestamptz
);

alter table public.assets
  alter column expires_at set default timezone('utc', now()) + interval '24 hours';

create index if not exists projects_expiry_idx on public.projects(expires_at);
create index if not exists assets_expiry_idx on public.assets(expires_at);

alter table public.projects
  add constraint projects_cover_asset_fk
  foreign key (cover_asset_id) references public.assets(id) on delete set null;

create table if not exists public.usage_ledger (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  project_id uuid not null references public.projects(id) on delete cascade,
  characters integer not null check (characters > 0),
  event_type text not null check (event_type in ('reserve', 'consume', 'refund')),
  billing_period date not null,
  created_at timestamptz not null default timezone('utc', now())
);

create index if not exists projects_user_created_idx on public.projects(user_id, created_at desc);
create index if not exists jobs_due_idx on public.jobs(status, next_run_at);
create index if not exists assets_user_idx on public.assets(user_id);
create index if not exists usage_user_period_idx on public.usage_ledger(user_id, billing_period);

create or replace function public.touch_updated_at()
returns trigger
language plpgsql
security invoker
set search_path = public
as $$
begin
  new.updated_at = timezone('utc', now());
  return new;
end;
$$;

drop trigger if exists profiles_touch_updated_at on public.profiles;
create trigger profiles_touch_updated_at before update on public.profiles
for each row execute function public.touch_updated_at();

drop trigger if exists projects_touch_updated_at on public.projects;
create trigger projects_touch_updated_at before update on public.projects
for each row execute function public.touch_updated_at();

alter table public.profiles enable row level security;
alter table public.projects enable row level security;
alter table public.jobs enable row level security;
alter table public.assets enable row level security;
alter table public.usage_ledger enable row level security;

-- Keep Data API exposure explicit when default privileges are disabled.
grant usage on schema public to authenticated, service_role;
grant select, update on public.profiles to authenticated;
grant select, insert, update, delete on public.projects to authenticated;
grant select on public.jobs to authenticated;
grant select, insert, delete on public.assets to authenticated;
grant select on public.usage_ledger to authenticated;
grant all on public.profiles, public.projects, public.jobs, public.assets, public.usage_ledger to service_role;

create policy profiles_select_own on public.profiles for select using (auth.uid() = id);
create policy profiles_update_own on public.profiles for update using (auth.uid() = id) with check (auth.uid() = id);

create policy projects_select_own on public.projects for select using (auth.uid() = user_id);
create policy projects_insert_own on public.projects for insert with check (auth.uid() = user_id);
create policy projects_update_own on public.projects for update using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy projects_delete_own on public.projects for delete using (auth.uid() = user_id);

-- Jobs and usage transitions are backend-service operations only.
create policy jobs_select_own on public.jobs for select using (auth.uid() = user_id);
create policy jobs_insert_own on public.jobs for insert with check (auth.uid() = user_id);

create policy assets_select_own on public.assets for select using (auth.uid() = user_id);
create policy assets_insert_own on public.assets for insert with check (auth.uid() = user_id);
create policy assets_delete_own on public.assets for delete using (auth.uid() = user_id);

create policy usage_select_own on public.usage_ledger for select using (auth.uid() = user_id);

grant insert on table public.jobs to authenticated;

insert into storage.buckets (id, name, public)
values ('project-assets', 'project-assets', false)
on conflict (id) do nothing;

create policy project_assets_select_own on storage.objects for select
using (bucket_id = 'project-assets' and (storage.foldername(name))[1] = auth.uid()::text);
create policy project_assets_insert_own on storage.objects for insert
with check (bucket_id = 'project-assets' and (storage.foldername(name))[1] = auth.uid()::text);
create policy project_assets_delete_own on storage.objects for delete
using (bucket_id = 'project-assets' and (storage.foldername(name))[1] = auth.uid()::text);
