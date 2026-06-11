// Backend API istemcisi + tipler. Tek değişiklik noktası: API_BASE.
export const API_BASE =
  (import.meta.env.VITE_API_BASE as string | undefined) || "http://localhost:8000";
export const WS_URL = API_BASE.replace(/^http/, "ws") + "/ws/scan";

export interface Product {
  url: string;
  name: string;
  brand: string;
  site: string;
  price: number;
  currency: string;
  image_url: string | null;
}

export interface Deal extends Product {
  historical_min: number | null;
  discount_pct: number | null;
  original_price: number | null;
  previous_logged_price: number | null;
  history_points: number;
}

export interface Config {
  brands: string[];
  sites: string[];
  history_days: number;
  max_products_per_brand_per_site: number;
  request_delay_ms: number;
  headless: boolean;
  search_suffix: string;
  product_types: string[];
  start_with_windows: boolean;
  auto_scan_on_launch: boolean;
}

export interface ScanStatus {
  status: string;
  running: boolean;
  last_progress: string;
  products_found: number;
  deals_found: number;
  sites_scanned: number;
  errors: string[];
  skipped: string[];
  started_at: string | null;
  finished_at: string | null;
}

export interface HistoryPoint {
  t: string;
  price: number;
}

async function asJson<T>(r: Response): Promise<T> {
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return (await r.json()) as T;
}

export const api = {
  deals: () => fetch(`${API_BASE}/api/deals`).then((r) => asJson<Deal[]>(r)),
  products: () => fetch(`${API_BASE}/api/products`).then((r) => asJson<Product[]>(r)),
  config: () => fetch(`${API_BASE}/api/config`).then((r) => asJson<Config>(r)),
  saveConfig: (c: Config) =>
    fetch(`${API_BASE}/api/config`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(c),
    }).then((r) => asJson<Config>(r)),
  scanStatus: () => fetch(`${API_BASE}/api/scan`).then((r) => asJson<ScanStatus>(r)),
  startScan: () => fetch(`${API_BASE}/api/scan`, { method: "POST" }),
  cancelScan: () => fetch(`${API_BASE}/api/scan/cancel`, { method: "POST" }),
  history: (url: string) =>
    fetch(`${API_BASE}/api/history?url=${encodeURIComponent(url)}`).then((r) =>
      asJson<HistoryPoint[]>(r)
    ),
};

export function fmtPrice(n: number): string {
  return n.toLocaleString("tr-TR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export const PRODUCT_TYPES: Record<string, string> = {
  cekirdek: "Çekirdek",
  ogutulmus: "Öğütülmüş",
  kapsul: "Kapsül",
  filtre: "Filtre",
  turk: "Türk Kahvesi",
  instant: "Granül / Hazır",
};

export const POPULAR_BRANDS: [string, string][] = [
  ["lavazza", "Lavazza"],
  ["illy", "Illy"],
  ["meinl", "Meinl"],
  ["tchibo", "Tchibo"],
  ["segafredo", "Segafredo"],
  ["dallmayr", "Dallmayr"],
  ["starbucks", "Starbucks"],
  ["kicking horse", "Kicking Horse"],
  ["mehmet efendi", "Mehmet Efendi"],
  ["kahve dünyası", "Kahve Dünyası"],
  ["nescafe", "Nescafé"],
  ["jacobs", "Jacobs"],
  ["mokarabia", "Mokarabia"],
  ["kimbo", "Kimbo"],
  ["melitta", "Melitta"],
  ["probador", "Probador"],
  ["cafemarkt", "Cafemarkt"],
  ["espressolab", "Espressolab"],
  ["whirl", "Whirl"],
];
