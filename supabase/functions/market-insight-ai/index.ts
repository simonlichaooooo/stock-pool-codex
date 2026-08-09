import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

const SUPABASE_URL = Deno.env.get("SUPABASE_URL")!;
const SERVICE_ROLE_KEY = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!;
const DEEPSEEK_API_KEY = Deno.env.get("DEEPSEEK_API_KEY")!;
const DEEPSEEK_MODEL = Deno.env.get("DEEPSEEK_MARKET_INSIGHT_MODEL") || "deepseek-v4-pro";
const PROMPT_VERSION = "market-insight-deepseek-thinking-v1";
const supabase = createClient(SUPABASE_URL, SERVICE_ROLE_KEY);

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

type Point = { date: string; value: number; quality?: string };

function jsonResponse(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { ...corsHeaders, "Content-Type": "application/json" } });
}

function cutoffFor(rangeKey: string) {
  const date = new Date();
  if (rangeKey === "YTD") date.setUTCMonth(0, 1);
  else date.setUTCFullYear(date.getUTCFullYear() - (rangeKey === "1Y" ? 1 : 2));
  return date.toISOString().slice(0, 10);
}

function finite(value: unknown) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function summarize(points: Point[]) {
  if (!points.length) return null;
  const values = points.map((point) => point.value);
  const low = points.reduce((best, point) => point.value < best.value ? point : best);
  const high = points.reduce((best, point) => point.value > best.value ? point : best);
  const start = points[0], end = points.at(-1)!;
  return {
    start, end, low, high,
    change: end.value - start.value,
    change_pct: start.value ? (end.value / start.value - 1) * 100 : null,
    observations: values.length,
  };
}

function weeklyLast(points: Point[]) {
  const byWeek = new Map<string, Point>();
  for (const point of points) {
    const date = new Date(`${point.date}T00:00:00Z`);
    const monday = new Date(date);
    monday.setUTCDate(date.getUTCDate() - ((date.getUTCDay() + 6) % 7));
    byWeek.set(monday.toISOString().slice(0, 10), point);
  }
  return [...byWeek.values()].sort((a, b) => a.date.localeCompare(b.date));
}

function latestAtOrBefore(points: Point[], date: string) {
  let result: Point | undefined;
  for (const point of points) {
    if (point.date > date) break;
    result = point;
  }
  return result;
}

function pearson(pairs: Array<[number, number]>) {
  if (pairs.length < 4) return null;
  const xMean = pairs.reduce((sum, pair) => sum + pair[0], 0) / pairs.length;
  const yMean = pairs.reduce((sum, pair) => sum + pair[1], 0) / pairs.length;
  let numerator = 0, xSquare = 0, ySquare = 0;
  for (const [x, y] of pairs) {
    numerator += (x - xMean) * (y - yMean);
    xSquare += (x - xMean) ** 2;
    ySquare += (y - yMean) ** 2;
  }
  const denominator = Math.sqrt(xSquare * ySquare);
  return denominator ? numerator / denominator : null;
}

function relationshipEvidence(price: Point[], holdings: Point[]) {
  const aligned = price.flatMap((point) => {
    const holding = latestAtOrBefore(holdings, point.date);
    return holding ? [{ date: point.date, price: point.value, holding: holding.value }] : [];
  });
  const simultaneous: Array<[number, number]> = [];
  const holdingToNextPrice: Array<[number, number]> = [];
  for (let index = 1; index < aligned.length; index++) {
    const priceReturn = aligned[index - 1].price ? aligned[index].price / aligned[index - 1].price - 1 : 0;
    const holdingChange = aligned[index].holding - aligned[index - 1].holding;
    simultaneous.push([holdingChange, priceReturn]);
    if (index + 1 < aligned.length) {
      const nextPriceReturn = aligned[index].price ? aligned[index + 1].price / aligned[index].price - 1 : 0;
      holdingToNextPrice.push([holdingChange, nextPriceReturn]);
    }
  }
  return {
    aligned_observations: aligned.length,
    holding_change_vs_same_week_price_return: pearson(simultaneous),
    holding_change_vs_next_week_price_return: pearson(holdingToNextPrice),
  };
}

async function fingerprint(value: unknown) {
  const bytes = new TextEncoder().encode(JSON.stringify(value));
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

function analysisSchema() {
  const hypothesis = {
    type: "object",
    additionalProperties: false,
    properties: {
      label: { type: "string" },
      explanation: { type: "string" },
      supporting_evidence: { type: "array", items: { type: "string" } },
      counter_evidence: { type: "array", items: { type: "string" } },
      confidence: { type: "string", enum: ["低", "中", "高"] },
    },
    required: ["label", "explanation", "supporting_evidence", "counter_evidence", "confidence"],
  };
  return {
    type: "object",
    additionalProperties: false,
    properties: {
      headline: { type: "string" },
      overall_assessment: { type: "string" },
      short_position: { type: "object", additionalProperties: false, properties: { conclusion: { type: "string" }, hypotheses: { type: "array", items: hypothesis } }, required: ["conclusion", "hypotheses"] },
      stock_connect: { type: "object", additionalProperties: false, properties: { conclusion: { type: "string" }, hypotheses: { type: "array", items: hypothesis } }, required: ["conclusion", "hypotheses"] },
      interaction: { type: "string" },
      key_evidence: { type: "array", items: { type: "string" } },
      counter_evidence: { type: "array", items: { type: "string" } },
      watch_items: { type: "array", items: { type: "string" } },
      confidence: { type: "string", enum: ["低", "中", "高"] },
      data_limitations: { type: "array", items: { type: "string" } },
    },
    required: ["headline", "overall_assessment", "short_position", "stock_connect", "interaction", "key_evidence", "counter_evidence", "watch_items", "confidence", "data_limitations"],
  };
}

function validateAnalysis(value: any) {
  const stringFields = ["headline", "overall_assessment", "interaction", "confidence"];
  const arrayFields = ["key_evidence", "counter_evidence", "watch_items", "data_limitations"];
  if (!value || typeof value !== "object" || Array.isArray(value)) throw new Error("模型返回的解读不是 JSON 对象");
  for (const field of stringFields) if (typeof value[field] !== "string") throw new Error(`模型返回缺少字段 ${field}`);
  for (const field of arrayFields) if (!Array.isArray(value[field]) || value[field].some((item: unknown) => typeof item !== "string")) throw new Error(`模型返回字段 ${field} 格式无效`);
  if (!["低", "中", "高"].includes(value.confidence)) throw new Error("模型返回的综合置信度无效");
  for (const partyName of ["short_position", "stock_connect"]) {
    const party = value[partyName];
    if (!party || typeof party.conclusion !== "string" || !Array.isArray(party.hypotheses)) throw new Error(`模型返回字段 ${partyName} 格式无效`);
    for (const hypothesis of party.hypotheses) {
      if (!hypothesis || typeof hypothesis.label !== "string" || typeof hypothesis.explanation !== "string" || !Array.isArray(hypothesis.supporting_evidence) || !Array.isArray(hypothesis.counter_evidence) || !["低", "中", "高"].includes(hypothesis.confidence)) throw new Error(`模型返回字段 ${partyName}.hypotheses 格式无效`);
    }
  }
  return value;
}

async function requestDeepSeek(evidence: unknown) {
  const schema = analysisSchema();
  const messages = [
    { role: "system", content: `你是一名严谨的港股市场行为研究员。根据提供的客观时间序列和统计证据，分析股价、空头持仓比例与港股通持仓比例的关系。区分观察事实与推测；提出竞争性假设并列出支持证据和反向证据；不得把相关性写成因果，不得断言操纵、打压或具体交易者意图；数据不足时降低置信度。使用简洁中文，不构成投资建议。只输出一个合法 JSON 对象，不要输出 Markdown 或额外文字。JSON 必须严格符合以下结构：${JSON.stringify(schema)}` },
    { role: "user", content: `请分析以下数据。重点判断空头更接近高位建仓后下跌平仓、顺势追空，还是对冲/事件驱动；港股通更接近逆势承接、趋势增持、反弹减持或持续撤离。不要套用固定分类，若数据支持其他解释请提出。请输出 JSON。\n\n${JSON.stringify(evidence)}` },
  ];
  let lastError: Error | null = null;
  for (let attempt = 0; attempt < 2; attempt++) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180000);
    try {
      const modelResponse = await fetch("https://api.deepseek.com/chat/completions", {
        method: "POST",
        headers: { "Authorization": `Bearer ${DEEPSEEK_API_KEY}`, "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
          model: DEEPSEEK_MODEL,
          messages,
          thinking: { type: "enabled" },
          reasoning_effort: "high",
          response_format: { type: "json_object" },
          max_tokens: 6000,
          stream: false,
        }),
      });
      const responseJson = await modelResponse.json();
      if (!modelResponse.ok) throw new Error(responseJson?.error?.message || `DeepSeek HTTP ${modelResponse.status}`);
      const choice = responseJson?.choices?.[0];
      if (choice?.finish_reason === "length") throw new Error("模型输出被截断");
      const content = choice?.message?.content;
      if (!content) throw new Error("模型未返回可解析的 JSON 解读");
      return validateAnalysis(JSON.parse(content));
    } catch (error) {
      lastError = error instanceof Error ? error : new Error(String(error));
      if (lastError.name === "AbortError") throw new Error("DeepSeek 思考超过 180 秒，请稍后重试");
      const canRetry = /JSON|格式|字段|截断|未返回/.test(lastError.message);
      if (!canRetry || attempt > 0) throw lastError;
    } finally {
      clearTimeout(timeoutId);
    }
  }
  throw lastError || new Error("DeepSeek 解读生成失败");
}

Deno.serve(async (request) => {
  if (request.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (request.method !== "POST") return jsonResponse({ error: "Method not allowed" }, 405);
  try {
    const authorization = request.headers.get("Authorization") || "";
    const token = authorization.replace(/^Bearer\s+/i, "");
    const { data: authData, error: authError } = await supabase.auth.getUser(token);
    if (authError || !authData.user) return jsonResponse({ error: "Unauthorized" }, 401);
    if (!DEEPSEEK_API_KEY) return jsonResponse({ error: "DEEPSEEK_API_KEY 尚未配置" }, 503);

    const body = await request.json();
    const stockCode = String(body.stock_code || "").padStart(5, "0");
    const indexCode = String(body.index_code || "").toUpperCase();
    const rangeKey = ["2Y", "1Y", "YTD"].includes(body.range_key) ? body.range_key : "2Y";
    if (!/^\d{5}$/.test(stockCode) || !["HSTECH", "HSLI", "HSMI", "HSSI"].includes(indexCode)) return jsonResponse({ error: "请求参数无效" }, 400);
    const cutoff = cutoffFor(rangeKey);

    const [securityResult, priceResult, shortResult, connectResult] = await Promise.all([
      supabase.from("market_securities").select("name_zh,name_en").eq("stock_code", stockCode).maybeSingle(),
      supabase.from("hk_market_insight_metrics_weekly").select("week_date,close_price,price_source").eq("index_code", indexCode).eq("stock_code", stockCode).gte("week_date", cutoff).order("week_date"),
      supabase.from("hk_short_positions_weekly").select("report_date,short_ratio_pct,ratio_quality").eq("stock_code", stockCode).gte("report_date", cutoff).not("short_ratio_pct", "is", null).order("report_date"),
      supabase.from("hk_stock_connect_holdings_daily").select("holding_date,holding_ratio_pct,ratio_quality,completeness").eq("stock_code", stockCode).gte("holding_date", cutoff).not("holding_ratio_pct", "is", null).order("holding_date"),
    ]);
    for (const result of [priceResult, shortResult, connectResult]) if (result.error) throw result.error;

    const price: Point[] = (priceResult.data || []).flatMap((row: any) => finite(row.close_price) === null ? [] : [{ date: row.week_date, value: Number(row.close_price), quality: row.price_source }]);
    const short: Point[] = (shortResult.data || []).flatMap((row: any) => finite(row.short_ratio_pct) === null ? [] : [{ date: row.report_date, value: Number(row.short_ratio_pct), quality: row.ratio_quality }]);
    const connectDaily: Point[] = (connectResult.data || []).flatMap((row: any) => finite(row.holding_ratio_pct) === null ? [] : [{ date: row.holding_date, value: Number(row.holding_ratio_pct), quality: `${row.ratio_quality}/${row.completeness}` }]);
    const connect = weeklyLast(connectDaily);
    if (price.length < 6) return jsonResponse({ error: "股价周线数据不足，暂不能生成 AI 解读" }, 422);
    if (short.length < 2 && connect.length < 2) return jsonResponse({ error: "空头与港股通历史比例数据不足，暂不能生成 AI 解读" }, 422);

    const evidence = {
      stock: { code: stockCode, name: securityResult.data?.name_zh || securityResult.data?.name_en || stockCode, index: indexCode, range: rangeKey },
      summaries: { price: summarize(price), short_position_ratio: summarize(short), stock_connect_ratio: summarize(connect) },
      relationships: { short_vs_price: relationshipEvidence(price, short), connect_vs_price: relationshipEvidence(price, connect) },
      series: { price, short_position_ratio: short, stock_connect_ratio_weekly: connect },
      disclosure_notes: {
        short_position: "香港证监会合计须申报淡仓，周度披露，不代表全部空头，且不能识别具体交易者。",
        stock_connect: "港股通为沪港通与深港通相关持仓汇总；完整性和股本分母质量见每个数据点 quality。",
      },
    };
    const dataFingerprint = await fingerprint(evidence);
    const { data: cached } = await supabase.from("market_insight_ai_analyses").select("analysis,evidence,model,prompt_version,price_as_of,short_as_of,connect_as_of,created_at").eq("index_code", indexCode).eq("stock_code", stockCode).eq("range_key", rangeKey).eq("data_fingerprint", dataFingerprint).eq("model", DEEPSEEK_MODEL).eq("prompt_version", PROMPT_VERSION).maybeSingle();
    if (cached) return jsonResponse({ analysis: cached.analysis, meta: { ...cached, analysis: undefined, evidence: undefined, generated_at: cached.created_at, cached: true } });

    const analysis = await requestDeepSeek(evidence);
    const row = {
      index_code: indexCode, stock_code: stockCode, range_key: rangeKey, data_fingerprint: dataFingerprint,
      analysis, evidence, model: DEEPSEEK_MODEL, prompt_version: PROMPT_VERSION,
      price_as_of: price.at(-1)?.date || null, short_as_of: short.at(-1)?.date || null, connect_as_of: connect.at(-1)?.date || null,
      updated_at: new Date().toISOString(),
    };
    const { error: cacheError } = await supabase.from("market_insight_ai_analyses").upsert(row, { onConflict: "index_code,stock_code,range_key,data_fingerprint" });
    if (cacheError) throw cacheError;
    return jsonResponse({ analysis, meta: { model: DEEPSEEK_MODEL, prompt_version: PROMPT_VERSION, price_as_of: row.price_as_of, short_as_of: row.short_as_of, connect_as_of: row.connect_as_of, generated_at: row.updated_at, cached: false } });
  } catch (error) {
    console.error(error);
    return jsonResponse({ error: error instanceof Error ? error.message : String(error) }, 500);
  }
});
