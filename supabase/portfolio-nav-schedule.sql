-- 执行前只替换下面两个占位符：
-- YOUR_PROJECT_REF：Supabase 项目 URL 中的项目编号。
-- REPLACE_WITH_LONG_RANDOM_SECRET：自定义的长随机字符串，需与 Edge Function 的 CRON_SECRET 完全一致。

select vault.create_secret(
  'https://YOUR_PROJECT_REF.supabase.co/functions/v1/daily-portfolio-nav',
  'daily_nav_function_url',
  '日终净值 Edge Function URL'
);

select vault.create_secret(
  'REPLACE_WITH_LONG_RANDOM_SECRET',
  'daily_nav_cron_secret',
  '日终净值定时任务密钥'
);

do $$
declare existing_job record;
begin
  for existing_job in select jobid from cron.job where jobname = 'daily-portfolio-nav'
  loop
    perform cron.unschedule(existing_job.jobid);
  end loop;
end $$;

-- 每天 UTC 23:30 执行。该时点晚于美股常规交易收盘，并覆盖夏令时和冬令时。
select cron.schedule(
  'daily-portfolio-nav',
  '30 23 * * *',
  $$
  select net.http_post(
    url := (select decrypted_secret from vault.decrypted_secrets where name = 'daily_nav_function_url'),
    headers := jsonb_build_object(
      'Content-Type', 'application/json',
      'x-cron-secret', (select decrypted_secret from vault.decrypted_secrets where name = 'daily_nav_cron_secret')
    ),
    body := '{}'::jsonb,
    timeout_milliseconds := 120000
  );
  $$
);
