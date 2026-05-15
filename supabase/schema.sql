create table if not exists public.stock_records (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  payload jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.stock_records enable row level security;

grant usage on schema public to anon, authenticated;
grant select, insert, update, delete on public.stock_records to authenticated;

drop policy if exists "Users can read own stock records" on public.stock_records;
create policy "Users can read own stock records"
on public.stock_records for select
to authenticated
using (user_id = auth.uid());

drop policy if exists "Users can create own stock records" on public.stock_records;
create policy "Users can create own stock records"
on public.stock_records for insert
to authenticated
with check (user_id = auth.uid());

drop policy if exists "Users can update own stock records" on public.stock_records;
create policy "Users can update own stock records"
on public.stock_records for update
to authenticated
using (user_id = auth.uid())
with check (user_id = auth.uid());

drop policy if exists "Users can delete own stock records" on public.stock_records;
create policy "Users can delete own stock records"
on public.stock_records for delete
to authenticated
using (user_id = auth.uid());
