import fs from "node:fs/promises";

const DATA_FILE = new URL("../data/market-insights.json", import.meta.url);
const SFC_PAGE = "https://www.sfc.hk/en/Regulatory-functions/Market/Short-position-reporting/Aggregated-reportable-short-positions-of-specified-shares";

const current = JSON.parse(await fs.readFile(DATA_FILE, "utf8"));
const trackedCodes = new Set(Object.keys(current.shortPositions.byCode));

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

async function updateShortPositions(next) {
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
  if (Object.keys(byCode).length < trackedCodes.size * 0.8) throw new Error("SFC CSV returned too few tracked constituents");
  next.shortPositions = { asOf: latest.date, sourceUrl: current.shortPositions.sourceUrl, reportUrl: latest.url, byCode };
}

const next = structuredClone(current);
await updateShortPositions(next);

const comparableCurrent = { ...current, generatedAt: undefined };
const comparableNext = { ...next, generatedAt: undefined };
if (JSON.stringify(comparableCurrent) === JSON.stringify(comparableNext)) {
  console.log("Market insight snapshot is already current.");
  process.exit(0);
}
next.generatedAt = new Date().toISOString();
await fs.writeFile(DATA_FILE, `${JSON.stringify(next, null, 2)}\n`);
console.log(`Updated market insight snapshot: SFC ${next.shortPositions.asOf}`);
