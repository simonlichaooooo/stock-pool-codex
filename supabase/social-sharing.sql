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
  add column if not exists share_visibility text not null default 'private';

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
  add column if not exists last_published_at timestamptz;

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

grant select, insert, update, delete on public.stock_records to authenticated;

drop policy if exists "Users can read shared stock records" on public.stock_records;
create policy "Users can read shared stock records"
on public.stock_records for select
to authenticated
using (is_shared = true);

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

alter table public.stock_publications enable row level security;

grant select, insert on public.stock_publications to authenticated;

drop policy if exists "Publications are readable by signed in users" on public.stock_publications;
create policy "Publications are readable by signed in users"
on public.stock_publications for select
to authenticated
using (true);

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
