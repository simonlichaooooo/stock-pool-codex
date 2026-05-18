create table if not exists public.admin_users (
  github_username text primary key,
  created_at timestamptz not null default now()
);

insert into public.admin_users (github_username)
values ('simonlichaooooo')
on conflict (github_username) do nothing;

alter table public.admin_users enable row level security;

grant select on public.admin_users to authenticated;

drop policy if exists "Admins can read own admin marker" on public.admin_users;
create policy "Admins can read own admin marker"
on public.admin_users for select
to authenticated
using (
  github_username = coalesce(
    auth.jwt() -> 'user_metadata' ->> 'user_name',
    auth.jwt() -> 'user_metadata' ->> 'preferred_username',
    auth.jwt() -> 'user_metadata' ->> 'name'
  )
);

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  email text,
  nickname text not null unique,
  bio text,
  share_visibility text not null default 'private' check (share_visibility in ('public', 'private')),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.profiles
  add column if not exists bio text,
  add column if not exists share_visibility text not null default 'private',
  add column if not exists square_hidden boolean not null default false,
  add column if not exists share_banned boolean not null default false,
  add column if not exists admin_note text;

alter table public.profiles enable row level security;

grant select, insert, update on public.profiles to authenticated;

drop policy if exists "Profiles are readable by signed in users" on public.profiles;
create policy "Profiles are readable by signed in users"
on public.profiles for select
to authenticated
using (true);

drop policy if exists "Users can create own profile" on public.profiles;
create policy "Users can create own profile"
on public.profiles for insert
to authenticated
with check (id = auth.uid());

drop policy if exists "Users can update own profile" on public.profiles;
create policy "Users can update own profile"
on public.profiles for update
to authenticated
using (id = auth.uid())
with check (id = auth.uid());

alter table public.stock_records
  add column if not exists source_user_id uuid references auth.users(id) on delete set null,
  add column if not exists source_stock_id uuid references public.stock_records(id) on delete set null,
  add column if not exists source_nickname text,
  add column if not exists source_type text not null default 'self',
  add column if not exists last_source_updated_at timestamptz,
  add column if not exists source_seen_published_at timestamptz,
  add column if not exists is_shared boolean not null default false,
  add column if not exists last_published_at timestamptz,
  add column if not exists admin_hidden boolean not null default false;

drop policy if exists "Admins can update profiles" on public.profiles;
create policy "Admins can update profiles"
on public.profiles for update
to authenticated
using (
  exists (
    select 1 from public.admin_users
    where admin_users.github_username = coalesce(
      auth.jwt() -> 'user_metadata' ->> 'user_name',
      auth.jwt() -> 'user_metadata' ->> 'preferred_username',
      auth.jwt() -> 'user_metadata' ->> 'name'
    )
  )
)
with check (
  exists (
    select 1 from public.admin_users
    where admin_users.github_username = coalesce(
      auth.jwt() -> 'user_metadata' ->> 'user_name',
      auth.jwt() -> 'user_metadata' ->> 'preferred_username',
      auth.jwt() -> 'user_metadata' ->> 'name'
    )
  )
);

create table if not exists public.stock_subscriptions (
  id uuid primary key default gen_random_uuid(),
  subscriber_id uuid not null references auth.users(id) on delete cascade,
  publisher_id uuid not null references auth.users(id) on delete cascade,
  source_stock_id uuid not null references public.stock_records(id) on delete cascade,
  target_stock_id uuid references public.stock_records(id) on delete set null,
  status text not null default 'active' check (status in ('active', 'cancelled', 'stopped')),
  last_seen_published_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(subscriber_id, publisher_id, source_stock_id)
);

alter table public.stock_subscriptions enable row level security;

grant select, insert, update, delete on public.stock_subscriptions to authenticated;

drop policy if exists "Users can read own stock subscriptions" on public.stock_subscriptions;
create policy "Users can read own stock subscriptions"
on public.stock_subscriptions for select
to authenticated
using (subscriber_id = auth.uid());

drop policy if exists "Users can create own stock subscriptions" on public.stock_subscriptions;
create policy "Users can create own stock subscriptions"
on public.stock_subscriptions for insert
to authenticated
with check (subscriber_id = auth.uid());

drop policy if exists "Users can update own stock subscriptions" on public.stock_subscriptions;
create policy "Users can update own stock subscriptions"
on public.stock_subscriptions for update
to authenticated
using (subscriber_id = auth.uid())
with check (subscriber_id = auth.uid());

drop policy if exists "Users can delete own stock subscriptions" on public.stock_subscriptions;
create policy "Users can delete own stock subscriptions"
on public.stock_subscriptions for delete
to authenticated
using (subscriber_id = auth.uid());

create or replace function public.mark_subscriptions_source_deleted(
  p_stock_id uuid,
  p_deleted_at timestamptz default now()
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not exists (
    select 1
    from public.stock_records
    where id = p_stock_id
      and user_id = auth.uid()
  ) then
    raise exception 'stock not found or permission denied';
  end if;

  update public.stock_records
  set
    payload = payload || jsonb_build_object(
      'latestMarketCapCny', null,
      'marketCapUpdatedAt', '',
      'expectedProfitCny', null,
      'expectedPE', null,
      'expectedPERemark', '',
      'netCashCny', null,
      'netCashScope', '',
      'netCashDiscountRate', null,
      'expectedDividendCny', null,
      'expectedBuybackCny', null,
      'expectedShareholderReturnCny', null,
      'shareholderReturnRemark', '',
      'investmentNote', '',
      'publishNote', '',
      'sourceStockId', '',
      'sourceSeenPublishedAt', '',
      'lastSourceUpdatedAt', p_deleted_at,
      'sourceStopped', false,
      'sourceDeletedAt', p_deleted_at,
      'hasSourceUpdate', false
    ),
    updated_at = p_deleted_at,
    source_stock_id = null,
    last_source_updated_at = p_deleted_at,
    source_seen_published_at = null
  where source_stock_id = p_stock_id
    and source_type = 'subscribed';
end;
$$;

grant execute on function public.mark_subscriptions_source_deleted(uuid, timestamptz) to authenticated;

grant select, insert, update, delete on public.stock_records to authenticated;

drop policy if exists "Users can read shared stock records" on public.stock_records;
create policy "Users can read shared stock records"
on public.stock_records for select
to authenticated
using (is_shared = true and admin_hidden = false);

drop policy if exists "Admins can read all stock records" on public.stock_records;
create policy "Admins can read all stock records"
on public.stock_records for select
to authenticated
using (
  exists (
    select 1 from public.admin_users
    where admin_users.github_username = coalesce(
      auth.jwt() -> 'user_metadata' ->> 'user_name',
      auth.jwt() -> 'user_metadata' ->> 'preferred_username',
      auth.jwt() -> 'user_metadata' ->> 'name'
    )
  )
);

drop policy if exists "Admins can moderate stock records" on public.stock_records;
create policy "Admins can moderate stock records"
on public.stock_records for update
to authenticated
using (
  exists (
    select 1 from public.admin_users
    where admin_users.github_username = coalesce(
      auth.jwt() -> 'user_metadata' ->> 'user_name',
      auth.jwt() -> 'user_metadata' ->> 'preferred_username',
      auth.jwt() -> 'user_metadata' ->> 'name'
    )
  )
)
with check (
  exists (
    select 1 from public.admin_users
    where admin_users.github_username = coalesce(
      auth.jwt() -> 'user_metadata' ->> 'user_name',
      auth.jwt() -> 'user_metadata' ->> 'preferred_username',
      auth.jwt() -> 'user_metadata' ->> 'name'
    )
  )
);

create table if not exists public.stock_publications (
  id uuid primary key default gen_random_uuid(),
  stock_id uuid not null references public.stock_records(id) on delete cascade,
  publisher_id uuid not null references auth.users(id) on delete cascade,
  version_number integer not null,
  change_note text,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(stock_id, version_number)
);

create index if not exists stock_publications_stock_version_idx
on public.stock_publications(stock_id, version_number desc);

create index if not exists stock_publications_publisher_created_idx
on public.stock_publications(publisher_id, created_at desc);

alter table public.stock_publications enable row level security;

grant select, insert on public.stock_publications to authenticated;

drop policy if exists "Publications are readable by signed in users" on public.stock_publications;
create policy "Publications are readable by signed in users"
on public.stock_publications for select
to authenticated
using (
  publisher_id = auth.uid()
  or exists (
    select 1 from public.stock_records
    where stock_records.id = stock_publications.stock_id
      and stock_records.is_shared = true
      and stock_records.admin_hidden = false
  )
  or exists (
    select 1 from public.admin_users
    where admin_users.github_username = coalesce(
      auth.jwt() -> 'user_metadata' ->> 'user_name',
      auth.jwt() -> 'user_metadata' ->> 'preferred_username',
      auth.jwt() -> 'user_metadata' ->> 'name'
    )
  )
);

drop policy if exists "Users can publish own stock records" on public.stock_publications;
create policy "Users can publish own stock records"
on public.stock_publications for insert
to authenticated
with check (
  publisher_id = auth.uid()
  and exists (
    select 1 from public.stock_records
    where stock_records.id = stock_publications.stock_id
      and stock_records.user_id = auth.uid()
  )
);

create table if not exists public.follows (
  follower_id uuid not null references auth.users(id) on delete cascade,
  publisher_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now(),
  primary key (follower_id, publisher_id),
  check (follower_id <> publisher_id)
);

alter table public.follows enable row level security;

grant select, insert, delete on public.follows to authenticated;

drop policy if exists "Users can read own follows" on public.follows;
create policy "Users can read own follows"
on public.follows for select
to authenticated
using (follower_id = auth.uid());

drop policy if exists "Users can follow publishers" on public.follows;
create policy "Users can follow publishers"
on public.follows for insert
to authenticated
with check (follower_id = auth.uid());

drop policy if exists "Users can unfollow publishers" on public.follows;
create policy "Users can unfollow publishers"
on public.follows for delete
to authenticated
using (follower_id = auth.uid());

create table if not exists public.moderation_actions (
  id uuid primary key default gen_random_uuid(),
  admin_github_username text not null,
  action_type text not null,
  target_user_id uuid references auth.users(id) on delete set null,
  target_stock_id uuid references public.stock_records(id) on delete set null,
  reason text,
  created_at timestamptz not null default now()
);

alter table public.moderation_actions enable row level security;

grant select, insert on public.moderation_actions to authenticated;

drop policy if exists "Admins can read moderation actions" on public.moderation_actions;
create policy "Admins can read moderation actions"
on public.moderation_actions for select
to authenticated
using (
  exists (
    select 1 from public.admin_users
    where admin_users.github_username = coalesce(
      auth.jwt() -> 'user_metadata' ->> 'user_name',
      auth.jwt() -> 'user_metadata' ->> 'preferred_username',
      auth.jwt() -> 'user_metadata' ->> 'name'
    )
  )
);

drop policy if exists "Admins can create moderation actions" on public.moderation_actions;
create policy "Admins can create moderation actions"
on public.moderation_actions for insert
to authenticated
with check (
  exists (
    select 1 from public.admin_users
    where admin_users.github_username = coalesce(
      auth.jwt() -> 'user_metadata' ->> 'user_name',
      auth.jwt() -> 'user_metadata' ->> 'preferred_username',
      auth.jwt() -> 'user_metadata' ->> 'name'
    )
  )
);

select 'social sharing migration ok' as result;
