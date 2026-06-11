import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  fmtPrice,
  WS_URL,
  type Alert,
  type Config,
  type Deal,
  type Product,
  type ScanStatus,
} from "./api";
import { AlertsModal } from "./components/AlertsModal";
import { FiltersModal } from "./components/FiltersModal";
import { PriceChartModal } from "./components/PriceChartModal";
import { ScanBar } from "./components/ScanBar";

type Tab = "deals" | "all";

function emptyStatus(): ScanStatus {
  return {
    status: "idle",
    running: false,
    last_progress: "",
    products_found: 0,
    deals_found: 0,
    sites_scanned: 0,
    errors: [],
    skipped: [],
    started_at: null,
    finished_at: null,
  };
}

export default function App() {
  const [deals, setDeals] = useState<Deal[]>([]);
  const [products, setProducts] = useState<Product[]>([]);
  const [config, setConfig] = useState<Config | null>(null);
  const [scan, setScan] = useState<ScanStatus | null>(null);
  const [tab, setTab] = useState<Tab>("deals");
  const [q, setQ] = useState("");
  const [chart, setChart] = useState<{ url: string; title: string } | null>(null);
  const [showFilters, setShowFilters] = useState(false);
  const [showAlerts, setShowAlerts] = useState(false);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [toast, setToast] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  function loadAlerts() {
    api.alerts().then(setAlerts).catch(() => {});
  }

  async function refresh() {
    try {
      const [d, p] = await Promise.all([api.deals(), api.products()]);
      setDeals(d);
      setProducts(p);
      setError(null);
    } catch (e) {
      setError(
        "Backend'e ulaşılamadı. Sunucu çalışıyor mu? " +
          "(py -3.14 -m uvicorn backend.main:app --port 8000)"
      );
    }
  }

  useEffect(() => {
    refresh();
    loadAlerts();
    api.config().then(setConfig).catch(() => {});
    api.scanStatus().then(setScan).catch(() => {});

    const ws = new WebSocket(WS_URL);
    wsRef.current = ws;
    ws.onmessage = (ev) => {
      const m = JSON.parse(ev.data);
      switch (m.type) {
        case "status":
          setScan((s) => ({ ...(s ?? emptyStatus()), ...m, status: m.status }));
          break;
        case "progress":
          setScan((s) => ({ ...(s ?? emptyStatus()), running: true, status: "running", last_progress: m.message }));
          break;
        case "product":
          setScan((s) => ({ ...(s ?? emptyStatus()), running: true, products_found: m.products_found }));
          break;
        case "deal":
          setScan((s) => ({ ...(s ?? emptyStatus()), running: true, deals_found: m.deals_found }));
          break;
        case "alert":
          setToast("🔔 Fiyat alarmı tetiklendi!");
          loadAlerts();
          break;
        case "finished":
          setScan((s) => ({ ...(s ?? emptyStatus()), running: false, status: "done" }));
          refresh();
          loadAlerts();
          break;
      }
    };
    return () => ws.close();
  }, []);

  async function onScanClick() {
    if (scan?.running) {
      await api.cancelScan().catch(() => {});
      return;
    }
    setScan({ ...emptyStatus(), running: true, status: "running", last_progress: "Başlatılıyor…" });
    try {
      await api.startScan();
    } catch {
      setError("Tarama başlatılamadı.");
      setScan((s) => ({ ...(s ?? emptyStatus()), running: false }));
    }
  }

  useEffect(() => {
    if (!toast) return;
    const id = setTimeout(() => setToast(null), 4000);
    return () => clearTimeout(id);
  }, [toast]);

  async function addAlert(r: Deal | Product) {
    const input = window.prompt(
      `"${r.brand} — ${r.name}" için hedef fiyat (TL):\nBu fiyatın altına inince alarm tetiklenir.`,
      String(Math.floor(r.price * 0.9))
    );
    if (input == null) return;
    const target = Number(input.replace(",", "."));
    if (!target || target <= 0) {
      setToast("Geçersiz fiyat.");
      return;
    }
    try {
      await api.addAlert(r.url, target);
      setToast(`🔔 Alarm kuruldu: ${fmtPrice(target)} TL`);
      loadAlerts();
    } catch {
      setToast("Alarm kurulamadı.");
    }
  }

  const triggeredCount = alerts.filter((a) => a.triggered_at != null).length;
  const rows: (Deal | Product)[] = tab === "deals" ? deals : products;
  const filtered = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return rows;
    return rows.filter((r) => `${r.brand} ${r.name} ${r.site}`.toLowerCase().includes(t));
  }, [rows, q]);

  return (
    <div className="min-h-screen bg-stone-100 text-stone-800">
      {/* Header */}
      <header className="bg-stone-900 text-stone-100">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
          <div className="flex items-center gap-2">
            <span className="text-2xl">☕</span>
            <h1 className="text-xl font-semibold">Coffee Deal Tracker</h1>
          </div>
          <div className="ml-auto flex items-center gap-2">
            <button
              onClick={() => setShowAlerts(true)}
              className="relative rounded-lg border border-stone-600 px-4 py-2 text-sm hover:bg-stone-800"
            >
              🔔 Alarmlar ({alerts.length})
              {triggeredCount > 0 && (
                <span className="absolute -right-1.5 -top-1.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-green-500 px-1 text-xs font-bold text-white">
                  {triggeredCount}
                </span>
              )}
            </button>
            <button
              onClick={() => setShowFilters(true)}
              className="rounded-lg border border-stone-600 px-4 py-2 text-sm hover:bg-stone-800"
            >
              ⚙ Filtreler
            </button>
            <button
              onClick={onScanClick}
              className={
                "rounded-lg px-5 py-2 text-sm font-medium " +
                (scan?.running
                  ? "bg-red-600 hover:bg-red-700"
                  : "bg-amber-500 text-stone-900 hover:bg-amber-400")
              }
            >
              {scan?.running ? "İptal" : "Taramayı Başlat"}
            </button>
          </div>
        </div>
        {config && (
          <div className="mx-auto max-w-6xl px-6 pb-3 text-xs text-stone-400">
            Siteler: {config.sites.join(", ")} · Markalar: {config.brands.join(", ")} · Pencere:{" "}
            {config.history_days} gün
          </div>
        )}
      </header>

      <main className="mx-auto max-w-6xl space-y-4 px-6 py-6">
        {error && (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        <ScanBar scan={scan} />

        {/* Arama + sekmeler */}
        <div className="flex flex-wrap items-center gap-3">
          <div className="flex rounded-xl bg-stone-200 p-1">
            <TabButton active={tab === "deals"} onClick={() => setTab("deals")}>
              Fırsatlar ({deals.length})
            </TabButton>
            <TabButton active={tab === "all"} onClick={() => setTab("all")}>
              Tüm Ürünler ({products.length})
            </TabButton>
          </div>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="🔍 Sonuçlarda ara… (marka, ürün, site)"
            className="ml-auto w-full max-w-md rounded-xl border border-stone-300 bg-white px-4 py-2 text-sm outline-none focus:border-amber-500"
          />
        </div>

        {/* Tablo */}
        <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-stone-50 text-xs uppercase text-stone-500">
                <tr>
                  <Th>Marka</Th>
                  <Th className="min-w-[220px]">Ürün</Th>
                  <Th>Site</Th>
                  <Th className="text-right">Fiyat</Th>
                  {tab === "deals" && <Th className="text-right">İndirimsiz</Th>}
                  {tab === "deals" && <Th className="text-right">Önceki</Th>}
                  {tab === "deals" && <Th className="text-right">İndirim</Th>}
                  <Th></Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {filtered.map((r) => {
                  const d = r as Deal;
                  const isDeal = tab === "deals";
                  return (
                    <tr key={r.url} className="hover:bg-amber-50/40">
                      <td className="px-4 py-2.5 font-medium capitalize">{r.brand}</td>
                      <td className="px-4 py-2.5 text-stone-700">{r.name}</td>
                      <td className="px-4 py-2.5 capitalize text-stone-500">{r.site}</td>
                      <td className="px-4 py-2.5 text-right font-medium tabular-nums">
                        {fmtPrice(r.price)} {r.currency}
                      </td>
                      {isDeal && (
                        <td className="px-4 py-2.5 text-right tabular-nums text-stone-500">
                          {d.original_price != null ? fmtPrice(d.original_price) : "—"}
                        </td>
                      )}
                      {isDeal && (
                        <td className="px-4 py-2.5 text-right tabular-nums text-stone-500">
                          {d.previous_logged_price != null ? fmtPrice(d.previous_logged_price) : "—"}
                        </td>
                      )}
                      {isDeal && (
                        <td className="px-4 py-2.5 text-right">
                          {d.discount_pct != null ? (
                            <span className="rounded-full bg-green-100 px-2 py-0.5 text-xs font-semibold text-green-700">
                              %{d.discount_pct.toFixed(1)}
                            </span>
                          ) : (
                            "—"
                          )}
                        </td>
                      )}
                      <td className="px-4 py-2.5">
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => addAlert(r)}
                            title="Fiyat alarmı kur"
                            className="rounded-lg border border-stone-300 px-2.5 py-1 text-xs text-stone-700 hover:bg-stone-50"
                          >
                            🔔
                          </button>
                          <button
                            onClick={() =>
                              setChart({ url: r.url, title: `${r.brand} — ${r.name}` })
                            }
                            className="rounded-lg border border-stone-300 px-2.5 py-1 text-xs text-stone-700 hover:bg-stone-50"
                          >
                            📈 Grafik
                          </button>
                          <a
                            href={r.url}
                            target="_blank"
                            rel="noreferrer"
                            className="rounded-lg border border-stone-300 px-2.5 py-1 text-xs text-stone-700 hover:bg-stone-50"
                          >
                            Aç
                          </a>
                        </div>
                      </td>
                    </tr>
                  );
                })}
                {filtered.length === 0 && (
                  <tr>
                    <td colSpan={8} className="px-4 py-12 text-center text-stone-400">
                      {q ? "Aramayla eşleşen sonuç yok." : "Henüz veri yok. Bir tarama başlatın."}
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </main>

      {chart && (
        <PriceChartModal url={chart.url} title={chart.title} onClose={() => setChart(null)} />
      )}
      {showFilters && config && (
        <FiltersModal
          config={config}
          onClose={() => setShowFilters(false)}
          onSaved={(c) => setConfig(c)}
        />
      )}
      {showAlerts && <AlertsModal onClose={() => setShowAlerts(false)} />}

      {toast && (
        <div className="fixed bottom-6 left-1/2 z-50 -translate-x-1/2 rounded-xl bg-stone-900 px-5 py-3 text-sm text-white shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={
        "rounded-lg px-4 py-1.5 text-sm font-medium transition " +
        (active ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700")
      }
    >
      {children}
    </button>
  );
}

function Th({ children, className = "" }: { children?: React.ReactNode; className?: string }) {
  return <th className={"px-4 py-3 font-semibold " + className}>{children}</th>;
}
