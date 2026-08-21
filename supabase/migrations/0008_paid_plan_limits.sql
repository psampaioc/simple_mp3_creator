-- Allow the service-managed paid plan while preventing client self-upgrades.
alter table public.profiles
  drop constraint if exists profiles_plan_check;

alter table public.profiles
  add constraint profiles_plan_check check (plan in ('free', 'paid'));

revoke update on public.profiles from authenticated;
grant update (display_name) on public.profiles to authenticated;
