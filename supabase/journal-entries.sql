-- 投资日志云端存储。请在 Supabase SQL Editor 中完整执行。

create table if not exists public.journal_entries (
  id text primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.journal_entries enable row level security;
grant select, insert, update, delete on public.journal_entries to authenticated;

drop policy if exists "Users manage own journal entries" on public.journal_entries;
create policy "Users manage own journal entries"
on public.journal_entries for all to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

create index if not exists journal_entries_user_id_created_at_idx
on public.journal_entries(user_id, created_at desc);
