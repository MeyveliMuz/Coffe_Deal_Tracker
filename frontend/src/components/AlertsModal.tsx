import { useEffect, useState } from "react";
import { api, fmtPrice, type Alert } from "../api";

interface Props {
  onClose: () => void;
}

export function AlertsModal({ onClose }: Props) {
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [loading, setLoading] = useState(true);

  async function load() {
    try {
      setAlerts(await api.alerts());
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
  }, []);

  async function remove(id: number) {
    await api.deleteAlert(id);
    load();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-stone-800">🔔 Fiyat alarmları</h2>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-stone-500 hover:bg-stone-100">
            ✕
          </button>
        </div>

        {loading && <p className="text-sm text-stone-500">Yükleniyor…</p>}
        {!loading && alerts.length === 0 && (
          <p className="py-10 text-center text-stone-400">
            Henüz alarm yok. Tablodaki bir ürünün 🔔 butonuyla hedef fiyat belirleyin.
          </p>
        )}

        {alerts.length > 0 && (
          <div className="divide-y divide-stone-100">
            {alerts.map((a) => {
              const triggered = a.triggered_at != null;
              return (
                <div
                  key={a.id}
                  className={
                    "flex items-center gap-3 py-3 " + (triggered ? "bg-green-50/60" : "")
                  }
                >
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-stone-700">
                      {a.name || a.product_url}
                    </p>
                    <p className="text-xs text-stone-500">
                      Hedef: {fmtPrice(a.target_price)} TL · Güncel:{" "}
                      {a.current_price != null ? fmtPrice(a.current_price) + " TL" : "—"}
                    </p>
                  </div>
                  {triggered ? (
                    <span className="rounded-full bg-green-100 px-2.5 py-1 text-xs font-semibold text-green-700">
                      ✓ {a.triggered_price != null ? fmtPrice(a.triggered_price) + " TL" : "tetiklendi"}
                    </span>
                  ) : (
                    <span className="rounded-full bg-stone-100 px-2.5 py-1 text-xs text-stone-500">
                      bekliyor
                    </span>
                  )}
                  <a
                    href={a.product_url}
                    target="_blank"
                    rel="noreferrer"
                    className="rounded-lg border border-stone-300 px-2.5 py-1 text-xs text-stone-700 hover:bg-stone-50"
                  >
                    Aç
                  </a>
                  <button
                    onClick={() => remove(a.id)}
                    className="rounded-lg px-2 py-1 text-xs text-red-600 hover:bg-red-50"
                  >
                    Sil
                  </button>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
