import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const CRON_SECRET = Deno.env.get("CRON_SECRET")!;
const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

const benchmarkSymbols: Record<string, string> = {
  CSI300: "sh000300", HSI: "hkHSI", HSTECH: "hkHSTECH", SP500: "usINX", NDX100: "usNDX"
};

function marketSymbol(position: any) {
  const raw = String(position.rawCode || position.code || "").replace(/\.(HK|SH|SZ)$/i, "");
  if (position.market === "HK") return `hk${raw.padStart(5, "0")}`;
  if (position.market === "CN") return `${raw.startsWith("6") ? "sh" : "sz"}${raw}`;
  return position.market === "US" ? `us${raw.toUpperCase()}` : "";
}

async function quoteMap(symbols: string[]) {
  const unique = [...new Set(symbols.filter(Boolean))];
  if (!unique.length) return new Map<string, number>();
  const text = await fetch(`https://qt.gtimg.cn/q=${unique.join(",")}`).then((response) => response.text());
  const result = new Map<string, number>();
  for (const line of text.split(";")) {
    const match = line.match(/v_([^=]+)="([^"]+)"/);
    if (!match) continue;
    const price = Number(match[2].split("~")[3]);
    if (price > 0) result.set(match[1], price);
  }
  return result;
}

function dateAt(timeZone: string) {
  return new Intl.DateTimeFormat("en-CA", { timeZone, year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}

Deno.serve(async (request) => {
  if (request.headers.get("x-cron-secret") !== CRON_SECRET) return new Response("Unauthorized", { status: 401 });
  const { data: portfolios, error } = await supabase.from("portfolios").select("id,user_id,payload");
  if (error) throw error;
  const allSymbols = (portfolios || []).flatMap((row: any) => (row.payload?.positions || []).map(marketSymbol));
  const quotes = await quoteMap([...allSymbols, ...Object.values(benchmarkSymbols)]);
  const fx = await fetch("https://open.er-api.com/v6/latest/CNY").then((response) => response.json());
  const hkdToCny = 1 / Number(fx?.rates?.HKD || 1.08);
  const usdToCny = 1 / Number(fx?.rates?.USD || 0.14);
  const navRows = (portfolios || []).map((row: any) => {
    const p = row.payload || {};
    const base = p.accountType === "HKUS" ? "USD" : "CNY";
    const rate = (currency: string) => base === "CNY" ? ({ CNY: 1, HKD: hkdToCny, USD: usdToCny }[currency] || 1) : ({ USD: 1, HKD: hkdToCny / usdToCny, CNY: 1 / usdToCny }[currency] || 1);
    const positionValue = (p.positions || []).reduce((sum: number, position: any) => sum + Number(position.shares || 0) * Number(quotes.get(marketSymbol(position)) || position.latestPrice || position.averageCost || 0) * rate(position.currency), 0);
    const cashValue = p.accountType === "HKUS" ? Number(p.cash?.USD || 0) + Number(p.cash?.HKD || 0) * rate("HKD") : Number(p.cash?.CNY || 0);
    const units = Number(p.totalUnits || p.startBase || 0);
    return { portfolio_id: row.id, user_id: row.user_id, nav_date: dateAt(base === "USD" ? "America/New_York" : "Asia/Shanghai"), base_currency: base, total_assets: positionValue + cashValue, total_units: units, unit_nav: units ? (positionValue + cashValue) / units : 1, cash_value: cashValue, position_value: positionValue, fx_rates: { HKD_CNY: hkdToCny, USD_CNY: usdToCny }, price_status: { generated_at: new Date().toISOString(), source: "tencent" } };
  });
  if (navRows.length) {
    const { error: navError } = await supabase.from("portfolio_daily_nav").upsert(navRows, { onConflict: "portfolio_id,nav_date" });
    if (navError) throw navError;
  }
  const benchmarkDate = dateAt("America/New_York");
  const benchmarkRows = Object.entries(benchmarkSymbols).flatMap(([code, symbol]) => {
    const close = quotes.get(symbol); return close ? [{ benchmark_code: code, trade_date: benchmarkDate, close_value: close, currency: code.startsWith("CSI") ? "CNY" : code.startsWith("HS") ? "HKD" : "USD", source: "tencent" }] : [];
  });
  if (benchmarkRows.length) await supabase.from("benchmark_daily_close").upsert(benchmarkRows, { onConflict: "benchmark_code,trade_date" });
  return Response.json({ portfolios: navRows.length, benchmarks: benchmarkRows.length });
});
