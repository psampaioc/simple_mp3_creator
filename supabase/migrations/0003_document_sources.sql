-- 2026-08-17: add a small extraction/review stage for private TXT/PDF/DOCX sources.

alter table public.projects
  drop constraint if exists projects_source_text_check,
  drop constraint if exists projects_character_count_check,
  drop constraint if exists projects_status_check;

alter table public.projects
  alter column source_text drop not null,
  alter column character_count drop not null,
  add column if not exists source_type text not null default 'pasted',
  add column if not exists source_asset_id uuid,
  add column if not exists source_storage_path text,
  add column if not exists source_filename text,
  add column if not exists source_content_type text,
  add column if not exists extraction_status text not null default 'not_needed',
  add column if not exists extraction_error text;

alter table public.projects
  add constraint projects_source_text_check check (source_text is null or char_length(source_text) between 1 and 10000),
  add constraint projects_character_count_check check (character_count is null or character_count between 1 and 10000),
  add constraint projects_source_type_check check (source_type in ('pasted', 'txt', 'pdf', 'docx')),
  add constraint projects_extraction_status_check check (extraction_status in ('not_needed', 'queued', 'extracting', 'ready', 'failed')),
  add constraint projects_status_check check (status in ('queued', 'extracting', 'review', 'generating', 'tagging', 'uploading', 'ready', 'failed'));

alter table public.jobs
  drop constraint if exists jobs_status_check,
  drop constraint if exists jobs_stage_check;

alter table public.jobs
  add constraint jobs_status_check check (status in ('queued', 'extracting', 'review', 'generating', 'tagging', 'uploading', 'ready', 'failed')),
  add constraint jobs_stage_check check (stage in ('queued', 'extracting', 'review', 'generating', 'tagging', 'uploading', 'ready', 'failed'));

alter table public.assets
  drop constraint if exists assets_kind_check;

alter table public.assets
  add constraint assets_kind_check check (kind in ('cover_original', 'cover_normalized', 'source_original', 'mp3'));

alter table public.projects
  add constraint projects_source_asset_fk
  foreign key (source_asset_id) references public.assets(id) on delete set null;
