import fs from "node:fs/promises";

const DATA_FILE = new URL("../data/market-insights.json", import.meta.url);
const SFC_PAGE = "https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares";
const HSI_CONSTITUENT_SOURCES = [
  { id: "hstech", label: "恒生科技", code: "HSTECH", quoteId: "124.HSTECH", url: "https://www.hsi.com.hk/data/chi/rt/index-series/hstech/constituents.do", officialName: "恒生科技指數" },
  { id: "hsli", label: "大型股", code: "HSLI", quoteId: "124.HSLI", url: "https://www.hsi.com.hk/data/chi/rt/index-series/sizeindexes/constituents.do", officialName: "恒生綜合大型股指數" },
  { id: "hsmi", label: "中型股", code: "HSMI", quoteId: "124.HSMI", url: "https://www.hsi.com.hk/data/chi/rt/index-series/sizeindexes/constituents.do", officialName: "恒生綜合中型股指數" },
  { id: "hssi", label: "小型股", code: "HSSI", quoteId: "124.HSSI", url: "https://www.hsi.com.hk/data/chi/rt/index-series/sizeindexes/constituents.do", officialName: "恒生綜合小型股指數" }
];

const current = JSON.parse(await fs.readFile(DATA_FILE, "utf8"));

function decodeHtml(value) {
  return String(value || "")
    .replaceAll("&amp;", "&")
    .replaceAll("&quot;", '"')
    .replaceAll("&#39;", "'")
    .replaceAll("&nbsp;", " ");
}

async function fetchText(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(url, {
      signal: controller.signal,
      headers: {
        "user-agent": "Mozilla/5.0 (compatible; stock-pool-market-insights/1.0)",
        "accept-language": "en-US,en;q=0.9,zh-HK;q=0.8"
      }
    });
    if (!response.ok) throw new Error(`${response.status} ${response.statusText}`);
    return await response.text();
  } finally {
    clearTimeout(timer);
  }
}

function parseCsvLine(line) {
  const result = [];
  let value = "";
  let quoted = false;
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index];
    if (char === '"') {
      if (quoted && line[index + 1] === '"') { value += '"'; index += 1; }
      else quoted = !quoted;
    } else if (char === "," && !quoted) {
      result.push(value);
      value = "";
    } else value += char;
  }
  result.push(value);
  return result;
}

async function updateConstituents(next) {
  const payloads = new Map();
  for (const source of HSI_CONSTITUENT_SOURCES) {
    if (!payloads.has(source.url)) payloads.set(source.url, JSON.parse(await fetchText(source.url)));
  }
  const indexes = {};
  for (const source of HSI_CONSTITUENT_SOURCES) {
    const payload = payloads.get(source.url);
    const series = payload?.indexSeriesList?.[0];
    const index = series?.indexList?.find((item) => item.indexName === source.officialName);
    if (!index?.constituentContent?.length) throw new Error(`HSI did not return constituents for ${source.code}`);
    indexes[source.id] = {
      label: source.label,
      code: source.code,
      quoteId: source.quoteId,
      asOf: String(series.constituentsDate || payload.requestDate || "").slice(0, 10),
      sourceUrl: source.url,
      members: index.constituentContent.map((item) => ({
        code: String(item.code || "").padStart(4, "0"),
        name: item.constituentName
      })).filter((item) => item.code && item.name)
    };
  }
  next.constituents = { indexes };
  return new Set(Object.values(indexes).flatMap((index) => index.members.map((item) => item.code)));
}

async function updateShortPositions(next, trackedCodes) {
  const page = await fetchText(SFC_PAGE);
  const links = [...page.matchAll(/href=["']([^"']*\/spr\/(\d{4})\/(\d{2})\/(\d{2})\/[^"']+\.csv[^"']*)["']/gi)]
    .map((match) => ({ url: new URL(decodeHtml(match[1]), SFC_PAGE).href, date: `${match[2]}-${match[3]}-${match[4]}` }))
    .sort((a, b) => b.date.localeCompare(a.date));
  if (!links.length) throw new Error("SFC page did not expose a report CSV link");
  const latest = links[0];
  const csv = await fetchText(latest.url);
  const byCode = {};
  for (const line of csv.replace(/^\uFEFF/, "").split(/\r?\n/).slice(1)) {
    if (!line.trim()) continue;
    const [date, code, name, shares, valueHkd] = parseCsvLine(line);
    const normalizedCode = String(code || "").trim().padStart(4, "0");
    if (!trackedCodes.has(normalizedCode)) continue;
    byCode[normalizedCode] = { shares: Number(shares), valueHkd: Number(valueHkd), name };
    if (!next.shortPositions.asOf && date) next.shortPositions.asOf = date;
  }
  if (Object.keys(byCode).length < 100) throw new Error("SFC CSV returned too few tracked constituents");
  next.shortPositions = { asOf: latest.date, sourceUrl: current.shortPositions.sourceUrl, reportUrl: latest.url, byCode };
}

const next = structuredClone(current);
const trackedCodes = await updateConstituents(next);
await updateShortPositions(next, trackedCodes);

const comparableCurrent = { ...current, generatedAt: undefined };
const comparableNext = { ...next, generatedAt: undefined };
if (JSON.stringify(comparableCurrent) === JSON.stringify(comparableNext)) {
  console.log("Market insight snapshot is already current.");
  process.exit(0);
}
next.generatedAt = new Date().toISOString();
await fs.writeFile(DATA_FILE, `${JSON.stringify(next, null, 2)}\n`);
console.log(`Updated market insight snapshot: SFC ${next.shortPositions.asOf}`);
