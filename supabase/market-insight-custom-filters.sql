-- 市场洞察自定义筛选的账号级云端存储。
-- 请在 Supabase SQL Editor 中完整执行；本文件可重复执行。

create table if not exists public.market_insight_custom_filters (
  id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  name text not null check (char_length(name) between 1 and 30),
  conditions jsonb not null default '[]'::jsonb,
  is_active boolean not null default false,
  sort_order integer not null default 0,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint market_insight_custom_filters_conditions_array
    check (jsonb_typeof(conditions) = 'array'),
  constraint market_insight_custom_filters_conditions_count
    check (jsonb_array_length(conditions) between 1 and 50)
);

alter table public.market_insight_custom_filters enable row level security;

grant select, insert, update, delete
on public.market_insight_custom_filters
to authenticated;

drop policy if exists "Users manage own market insight custom filters"
on public.market_insight_custom_filters;

create policy "Users manage own market insight custom filters"
on public.market_insight_custom_filters
for all
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

create index if not exists market_insight_custom_filters_user_sort_idx
on public.market_insight_custom_filters(user_id, sort_order, created_at);

create or replace function public.touch_market_insight_custom_filter_updated_at()
returns trigger
language plpgsql
set search_path = public
as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

drop trigger if exists touch_market_insight_custom_filter_updated_at
on public.market_insight_custom_filters;

create trigger touch_market_insight_custom_filter_updated_at
before update on public.market_insight_custom_filters
for each row
execute function public.touch_market_insight_custom_filter_updated_at();
