import fs from "node:fs/promises";

const DATA_FILE = new URL("../data/market-insights.json", import.meta.url);
const SUPABASE_URL = String(process.env.SUPABASE_URL || "").replace(/\/$/, "");
const SUPABASE_KEY = String(process.env.SUPABASE_SERVICE_ROLE_KEY || "");
const PAGE_SIZE = 1000;
const DAY_MS = 86400000;

if (!SUPABASE_URL || !SUPABASE_KEY) throw new Error("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required");

const snapshot = JSON.parse(await fs.readFile(DATA_FILE, "utf8"));
const indexCodeById = { hstech:"HSTECH", hsli:"HSLI", hsmi:"HSMI", hssi:"HSSI" };
const scopeMembers = Object.fromEntries(Object.entries(snapshot.constituents?.indexes || {}).map(([id, item]) => [id, new Set((item.members || []).map((member) => String(member.code).padStart(5, "0")))]));
scopeMembers.all = new Set(Object.values(scopeMembers).flatMap((codes) => [...codes]));

function isoDate(daysAgo) {
  return new Date(Date.now() - daysAgo * DAY_MS).toISOString().slice(0, 10);
}

async function fetchRows(table, query) {
  const rows = [];
  for (let offset = 0; ; offset += PAGE_SIZE) {
    const response = await fetch(`${SUPABASE_URL}/rest/v1/${table}?${query}`, {
      headers: {
        apikey:SUPABASE_KEY,
        authorization:`Bearer ${SUPABASE_KEY}`,
        range:`${offset}-${offset + PAGE_SIZE - 1}`,
        "range-unit":"items"
      }
    });
    if (!response.ok) throw new Error(`${table}: ${response.status} ${await response.text()}`);
    const page = await response.json();
    rows.push(...page);
    if (page.length < PAGE_SIZE) break;
  }
  return rows;
}

function number(value) {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function groupBy(rows, key) {
  const result = new Map();
  rows.forEach((row) => {
    const value = row[key];
    if (!result.has(value)) result.set(value, []);
    result.get(value).push(row);
  });
  return result;
}

function percentile(values, current) {
  const usable = values.filter(Number.isFinite).sort((a, b) => a - b);
  if (!usable.length || !Number.isFinite(current)) return null;
  const lower = usable.filter((value) => value < current).length;
  const equal = usable.filter((value) => value === current).length;
  return usable.length === 1 ? 100 : (lower + .5 * Math.max(0, equal - 1)) / (usable.length - 1) * 100;
}

function finishMetric(label, description, trend, currentCodes, eligibleCodes, asOf) {
  const current = trend.at(-1)?.value ?? null;
  const previous = trend.at(-2)?.value ?? null;
  return {
    label, description, asOf,
    numerator:currentCodes.length,
    denominator:eligibleCodes.length,
    value:current,
    change:Number.isFinite(current) && Number.isFinite(previous) ? current - previous : null,
    percentile:percentile(trend.map((point) => point.value), current),
    matchingCodes:currentCodes,
    eligibleCodes,
    trend:trend.slice(-52)
  };
}

function metricTrend(dates, codes, signalAt) {
  return dates.map((date) => {
    const matching = [], eligible = [];
    codes.forEach((code) => {
      const signal = signalAt(code, date);
      if (signal === null) return;
      eligible.push(code);
      if (signal) matching.push(code);
    });
    return { date, value:eligible.length ? matching.length / eligible.length * 100 : null, numerator:matching.length, denominator:eligible.length };
  }).filter((point) => point.denominator);
}

const [weeklyRows, shortRows, connectRows] = await Promise.all([
  fetchRows("hk_market_insight_metrics_weekly", `select=index_code,stock_code,week_date,bias_5w_pct,bias_speed_30w_pct&week_date=gte.${isoDate(760)}&order=week_date.asc`),
  fetchRows("hk_short_positions_weekly", `select=stock_code,report_date,short_ratio_pct&report_date=gte.${isoDate(420)}&short_ratio_pct=not.is.null&order=report_date.asc`),
  fetchRows("hk_stock_connect_holdings_daily", `select=stock_code,holding_date,total_holding_shares&holding_date=gte.${isoDate(420)}&total_holding_shares=not.is.null&completeness=eq.official_aggregate&order=holding_date.asc`)
]);

const weeklyByIndexCode = new Map();
weeklyRows.forEach((row) => {
  const key = `${row.index_code}:${row.stock_code}`;
  if (!weeklyByIndexCode.has(key)) weeklyByIndexCode.set(key, new Map());
  weeklyByIndexCode.get(key).set(row.week_date, row);
});
const weeklyDates = [...new Set(weeklyRows.map((row) => row.week_date))].sort();
const shortDates = [...new Set(shortRows.map((row) => row.report_date))].sort();
const connectDates = [...new Set(connectRows.map((row) => row.holding_date))].sort();
const shortByCode = new Map([...groupBy(shortRows, "stock_code")].map(([code, rows]) => [code, new Map(rows.map((row) => [row.report_date, number(row.short_ratio_pct)]))]));
const connectByCode = new Map([...groupBy(connectRows, "stock_code")].map(([code, rows]) => [code, new Map(rows.map((row) => [row.holding_date, number(row.total_holding_shares)]))]));

function weekRowsForScope(scopeId, date) {
  const members = scopeMembers[scopeId] || new Set();
  const result = new Map();
  const indexIds = scopeId === "all" ? Object.keys(indexCodeById) : [scopeId];
  indexIds.forEach((id) => members.forEach((code) => {
    if (result.has(code)) return;
    const row = weeklyByIndexCode.get(`${indexCodeById[id]}:${code}`)?.get(date);
    if (row) result.set(code, row);
  }));
  return result;
}

function consecutiveSignal(series, dates, date, intervals, direction = "up") {
  const index = dates.indexOf(date);
  if (index < intervals) return null;
  const window = dates.slice(index - intervals, index + 1).map((day) => series?.get(day));
  if (window.some((value) => !Number.isFinite(value))) return null;
  return window.slice(1).every((value, offset) => direction === "up" ? value > window[offset] : value < window[offset]);
}

function weeklyLastDates(dates) {
  const byWeek = new Map();
  dates.forEach((date) => {
    const value = new Date(`${date}T00:00:00Z`);
    const monday = new Date(value.getTime() - ((value.getUTCDay() + 6) % 7) * DAY_MS).toISOString().slice(0, 10);
    byWeek.set(monday, date);
  });
  return [...byWeek.values()].sort();
}

const scopes = {};
for (const scopeId of ["all", "hstech", "hsli", "hsmi", "hssi"]) {
  const codes = [...scopeMembers[scopeId]];
  // 行情源偶尔会为单只股票写入非标准周日期。只有覆盖当前范围至少六成股票的
  // 日期才可作为市场截面，避免 1/500 之类的残缺周污染广度、连续性和环比。
  const minimumWeeklyCoverage = Math.max(1, Math.ceil(codes.length * .6));
  const scopeWeeklyDates = weeklyDates.filter((date) => weekRowsForScope(scopeId, date).size >= minimumWeeklyCoverage).slice(-104);
  const breadthTrend = scopeWeeklyDates.map((date) => {
    const rows = weekRowsForScope(scopeId, date);
    const eligible = [...rows].filter(([, row]) => number(row.bias_5w_pct) !== null);
    const matching = eligible.filter(([, row]) => number(row.bias_5w_pct) > 0);
    return { date, value:eligible.length ? matching.length / eligible.length * 100 : null, numerator:matching.length, denominator:eligible.length };
  }).filter((point) => point.denominator);
  const momentumTrend = scopeWeeklyDates.map((date, dateIndex) => {
    const matching = [], eligible = [];
    if (dateIndex < 2) return { date, value:null, numerator:0, denominator:0 };
    const dates = scopeWeeklyDates.slice(dateIndex - 2, dateIndex + 1);
    codes.forEach((code) => {
      const values = dates.map((day) => {
        const indexes = scopeId === "all" ? Object.keys(indexCodeById) : [scopeId];
        for (const id of indexes) {
          const value = number(weeklyByIndexCode.get(`${indexCodeById[id]}:${code}`)?.get(day)?.bias_speed_30w_pct);
          if (value !== null) return value;
        }
        return null;
      });
      if (values.some((value) => value === null)) return;
      eligible.push(code);
      if (values.every((value) => value > 0)) matching.push(code);
    });
    return { date, value:eligible.length ? matching.length / eligible.length * 100 : null, numerator:matching.length, denominator:eligible.length };
  }).filter((point) => point.denominator);
  const shortTrend = metricTrend(shortDates.slice(-104), codes, (code, date) => consecutiveSignal(shortByCode.get(code), shortDates, date, 3));
  const connectTrend = metricTrend(weeklyLastDates(connectDates).slice(-104), codes, (code, date) => consecutiveSignal(connectByCode.get(code), connectDates, date, 5));
  const latestWeek = breadthTrend.at(-1)?.date;
  const latestWeekRows = latestWeek ? weekRowsForScope(scopeId, latestWeek) : new Map();
  const breadthEligible = [...latestWeekRows].filter(([, row]) => number(row.bias_5w_pct) !== null).map(([code]) => code);
  const breadthMatching = [...latestWeekRows].filter(([, row]) => number(row.bias_5w_pct) > 0).map(([code]) => code);
  const latestMomentum = momentumTrend.at(-1);
  const latestShort = shortTrend.at(-1);
  const latestConnect = connectTrend.at(-1);
  const signalCodes = (date, dates, series, intervals) => codes.filter((code) => consecutiveSignal(series.get(code), dates, date, intervals) === true);
  const eligibleSignalCodes = (date, dates, series, intervals) => codes.filter((code) => consecutiveSignal(series.get(code), dates, date, intervals) !== null);
  const latestMomentumDate = latestMomentum?.date;
  const momentumDates = latestMomentumDate ? scopeWeeklyDates.slice(scopeWeeklyDates.indexOf(latestMomentumDate) - 2, scopeWeeklyDates.indexOf(latestMomentumDate) + 1) : [];
  const momentumValues = (code) => momentumDates.map((day) => {
    for (const id of (scopeId === "all" ? Object.keys(indexCodeById) : [scopeId])) {
      const value = number(weeklyByIndexCode.get(`${indexCodeById[id]}:${code}`)?.get(day)?.bias_speed_30w_pct);
      if (value !== null) return value;
    }
    return null;
  });
  const momentumEligible = codes.filter((code) => momentumValues(code).every((value) => value !== null));
  const momentumMatching = momentumEligible.filter((code) => momentumValues(code).every((value) => value > 0));
  scopes[scopeId] = { metrics:{
    breadth:finishMetric("短期多头广度", "5周乖离率 > 0", breadthTrend, breadthMatching, breadthEligible, latestWeek),
    momentum:finishMetric("中期趋势持续改善", "30周乖离率速度连续3周 > 0", momentumTrend, momentumMatching, momentumEligible, latestMomentumDate),
    short:finishMetric("空头压力扩散", "空头持仓比例连续3个SFC报告期上升", shortTrend, latestShort ? signalCodes(latestShort.date, shortDates, shortByCode, 3) : [], latestShort ? eligibleSignalCodes(latestShort.date, shortDates, shortByCode, 3) : [], latestShort?.date),
    connect:finishMetric("南向持续增持", "港股通持股数连续5个交易日增加", connectTrend, latestConnect ? signalCodes(latestConnect.date, connectDates, connectByCode, 5) : [], latestConnect ? eligibleSignalCodes(latestConnect.date, connectDates, connectByCode, 5) : [], latestConnect?.date)
  }};
}

snapshot.marketOverview = { generatedAt:new Date().toISOString(), scopes };
snapshot.generatedAt = new Date().toISOString();
await fs.writeFile(DATA_FILE, `${JSON.stringify(snapshot, null, 2)}\n`);
console.log(`Updated market overview from ${weeklyRows.length} weekly, ${shortRows.length} short and ${connectRows.length} connect rows.`);
