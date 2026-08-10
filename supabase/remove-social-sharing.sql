begin;

-- Keep copied/subscribed stocks as ordinary private stocks while removing all
-- social metadata from their JSON payloads.
update public.stock_records
set
  payload = payload - array[
    'publishNote',
    'isShared',
    'lastPublishedAt',
    'sourceUserId',
    'sourceStockId',
    'sourceNickname',
    'sourceType',
    'sourceSeenPublishedAt',
    'lastSourceUpdatedAt',
    'sourceStopped',
    'sourceDeletedAt',
    'hasSourceUpdate',
    'adminHidden'
  ],
  updated_at = now();

drop policy if exists "Users can read shared stock records" on public.stock_records;
drop policy if exists "Admins can read all stock records" on public.stock_records;
drop policy if exists "Admins can moderate stock records" on public.stock_records;
drop policy if exists "Admins can update profiles" on public.profiles;

drop function if exists public.mark_subscriptions_source_deleted(uuid, timestamptz);

drop table if exists public.moderation_actions;
drop table if exists public.follows;
drop table if exists public.stock_subscriptions;
drop table if exists public.stock_publications;
drop table if exists public.admin_users;

alter table public.stock_records
  drop column if exists source_user_id,
  drop column if exists source_stock_id,
  drop column if exists source_nickname,
  drop column if exists source_type,
  drop column if exists last_source_updated_at,
  drop column if exists source_seen_published_at,
  drop column if exists is_shared,
  drop column if exists last_published_at,
  drop column if exists admin_hidden;

drop policy if exists "Profiles are readable by signed in users" on public.profiles;
drop policy if exists "Users can read own profile" on public.profiles;
create policy "Users can read own profile"
on public.profiles for select
to authenticated
using (id = auth.uid());

alter table public.profiles
  drop column if exists bio,
  drop column if exists share_visibility,
  drop column if exists square_hidden,
  drop column if exists share_banned,
  drop column if exists admin_note;

commit;

select 'social sharing removal ok' as result;
