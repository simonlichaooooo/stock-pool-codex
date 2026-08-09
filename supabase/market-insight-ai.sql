-- 市场洞察 AI 解读缓存；在 Supabase SQL Editor 中执行一次。

create table if not exists public.market_insight_ai_analyses (
  id uuid primary key default gen_random_uuid(),
  index_code text not null check (index_code in ('HSTECH', 'HSLI', 'HSMI', 'HSSI')),
  stock_code text not null references public.market_securities(stock_code) on delete cascade,
  range_key text not null check (range_key in ('2Y', '1Y', 'YTD')),
  data_fingerprint text not null,
  analysis jsonb not null,
  evidence jsonb not null default '{}'::jsonb,
  model text not null,
  prompt_version text not null,
  price_as_of date,
  short_as_of date,
  connect_as_of date,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (index_code, stock_code, range_key, data_fingerprint)
);

create index if not exists market_insight_ai_latest_idx
  on public.market_insight_ai_analyses(index_code, stock_code, range_key, created_at desc);

alter table public.market_insight_ai_analyses enable row level security;

grant select on public.market_insight_ai_analyses to authenticated;
grant select, insert, update, delete on public.market_insight_ai_analyses to service_role;

drop policy if exists "Authenticated users read market insight AI analyses"
  on public.market_insight_ai_analyses;
create policy "Authenticated users read market insight AI analyses"
on public.market_insight_ai_analyses for select to authenticated using (true);
