import { useState } from "react";
import { api, POPULAR_BRANDS, PRODUCT_TYPES, type Config } from "../api";

interface Props {
  config: Config;
  onClose: () => void;
  onSaved: (c: Config) => void;
}

export function FiltersModal({ config, onClose, onSaved }: Props) {
  const popularKeys = new Set(POPULAR_BRANDS.map(([k]) => k));
  const initialBrands = new Set(config.brands.map((b) => b.toLowerCase()));

  const [brands, setBrands] = useState<Set<string>>(new Set(initialBrands));
  const [custom, setCustom] = useState(
    config.brands.filter((b) => !popularKeys.has(b.toLowerCase())).join(", ")
  );
  const [types, setTypes] = useState<Set<string>>(
    new Set(config.product_types.map((t) => t.toLowerCase()))
  );
  const [days, setDays] = useState(config.history_days);
  const [scheduleEnabled, setScheduleEnabled] = useState(config.schedule_enabled);
  const [scheduleTime, setScheduleTime] = useState(config.schedule_time || "09:00");
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  function toggle(set: Set<string>, key: string): Set<string> {
    const next = new Set(set);
    next.has(key) ? next.delete(key) : next.add(key);
    return next;
  }

  async function save() {
    const finalBrands = [
      ...POPULAR_BRANDS.filter(([k]) => brands.has(k)).map(([k]) => k),
      ...custom
        .split(",")
        .map((s) => s.trim().toLowerCase())
        .filter(Boolean),
    ];
    const dedup = Array.from(new Set(finalBrands));
    const finalTypes = Object.keys(PRODUCT_TYPES).filter((k) => types.has(k));
    if (dedup.length === 0) return setErr("En az bir marka seçin.");
    if (finalTypes.length === 0) return setErr("En az bir ürün türü seçin.");

    setSaving(true);
    setErr(null);
    try {
      const saved = await api.saveConfig({
        ...config,
        brands: dedup,
        product_types: finalTypes,
        history_days: days,
        schedule_enabled: scheduleEnabled,
        schedule_time: scheduleTime,
      });
      onSaved(saved);
      onClose();
    } catch (e) {
      setErr("Kaydedilemedi: " + String(e));
      setSaving(false);
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-stone-800">Filtreler ve ayarlar</h2>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-stone-500 hover:bg-stone-100">
            ✕
          </button>
        </div>

        <section className="mb-5">
          <h3 className="mb-2 text-sm font-semibold text-amber-700">Markalar</h3>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
            {POPULAR_BRANDS.map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-sm text-stone-700">
                <input
                  type="checkbox"
                  className="accent-amber-600"
                  checked={brands.has(k)}
                  onChange={() => setBrands((s) => toggle(s, k))}
                />
                {label}
              </label>
            ))}
          </div>
          <input
            value={custom}
            onChange={(e) => setCustom(e.target.value)}
            placeholder="Diğer markalar (virgülle): ör. arabica, mokarabia"
            className="mt-3 w-full rounded-lg border border-stone-300 px-3 py-2 text-sm"
          />
        </section>

        <section className="mb-5">
          <h3 className="mb-2 text-sm font-semibold text-amber-700">Ürün türleri</h3>
          <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
            {Object.entries(PRODUCT_TYPES).map(([k, label]) => (
              <label key={k} className="flex items-center gap-2 text-sm text-stone-700">
                <input
                  type="checkbox"
                  className="accent-amber-600"
                  checked={types.has(k)}
                  onChange={() => setTypes((s) => toggle(s, k))}
                />
                {label}
              </label>
            ))}
          </div>
        </section>

        <section className="mb-5">
          <h3 className="mb-2 text-sm font-semibold text-amber-700">İndirim penceresi</h3>
          <div className="flex items-center gap-2 text-sm text-stone-700">
            Son
            <input
              type="number"
              min={1}
              max={365}
              value={days}
              onChange={(e) => setDays(Number(e.target.value))}
              className="w-20 rounded-lg border border-stone-300 px-2 py-1"
            />
            günün en düşüğünün altı fırsattır.
          </div>
        </section>

        <section className="mb-5">
          <h3 className="mb-2 text-sm font-semibold text-amber-700">Zamanlanmış tarama</h3>
          <label className="flex items-center gap-2 text-sm text-stone-700">
            <input
              type="checkbox"
              className="accent-amber-600"
              checked={scheduleEnabled}
              onChange={(e) => setScheduleEnabled(e.target.checked)}
            />
            Her gün otomatik tara (sunucu çalışırken)
          </label>
          {scheduleEnabled && (
            <div className="mt-2 flex items-center gap-2 text-sm text-stone-700">
              Saat:
              <input
                type="time"
                value={scheduleTime}
                onChange={(e) => setScheduleTime(e.target.value)}
                className="rounded-lg border border-stone-300 px-2 py-1"
              />
            </div>
          )}
        </section>

        {err && <p className="mb-3 text-sm text-red-600">{err}</p>}

        <div className="flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50"
          >
            İptal
          </button>
          <button
            onClick={save}
            disabled={saving}
            className="rounded-lg bg-amber-600 px-4 py-2 text-sm font-medium text-white hover:bg-amber-700 disabled:opacity-50"
          >
            {saving ? "Kaydediliyor…" : "Kaydet"}
          </button>
        </div>
      </div>
    </div>
  );
}
