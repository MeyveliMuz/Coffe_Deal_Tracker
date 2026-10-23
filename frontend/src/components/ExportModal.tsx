import { useState } from "react";
import { exportUrl, type ExportDataset, type ExportFormat } from "../api";

interface Props {
  onClose: () => void;
}

const DATASETS: { id: ExportDataset; label: string; desc: string }[] = [
  { id: "history", label: "Fiyat geçmişi", desc: "Her tarama kaydı bir satır — zaman serisi, pivot, trend analizi" },
  { id: "products", label: "Ürün özeti", desc: "Ürün başına min / maks / ortalama / son fiyat" },
  { id: "deals", label: "Güncel fırsatlar", desc: "İndirim etiketli ürünler — gerçek / sahte kararı ve açıklamasıyla" },
  { id: "all", label: "Hepsi", desc: "Üç veri seti birden (Excel'de 3 sayfa, CSV'de zip)" },
];

const FORMATS: { id: ExportFormat; label: string }[] = [
  { id: "xlsx", label: "Excel (.xlsx)" },
  { id: "csv", label: "CSV" },
  { id: "json", label: "JSON" },
];

const RANGES = [
  { days: 0, label: "Tümü" },
  { days: 30, label: "Son 30 gün" },
  { days: 90, label: "Son 90 gün" },
  { days: 365, label: "Son 1 yıl" },
];

export function ExportModal({ onClose }: Props) {
  const [dataset, setDataset] = useState<ExportDataset>("history");
  const [format, setFormat] = useState<ExportFormat>("xlsx");
  const [days, setDays] = useState(0);

  const chip = (active: boolean) =>
    "rounded-lg border px-3 py-1.5 text-sm " +
    (active ? "border-amber-500 bg-amber-50 font-medium text-stone-900" : "border-stone-300 text-stone-600 hover:bg-stone-50");

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4" onClick={onClose}>
      <div
        className="max-h-[90vh] w-full max-w-lg overflow-y-auto rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-stone-800">⬇ Veriyi dışa aktar</h2>
          <button onClick={onClose} className="rounded-lg px-3 py-1 text-stone-500 hover:bg-stone-100">✕</button>
        </div>

        <h3 className="mb-2 text-sm font-semibold text-stone-700">Veri seti</h3>
        <div className="mb-5 space-y-2">
          {DATASETS.map((d) => (
            <label
              key={d.id}
              className={
                "flex cursor-pointer gap-3 rounded-xl border p-3 " +
                (dataset === d.id ? "border-amber-500 bg-amber-50" : "border-stone-200 hover:bg-stone-50")
              }
            >
              <input type="radio" checked={dataset === d.id} onChange={() => setDataset(d.id)} className="mt-1 accent-amber-500" />
              <span>
                <span className="block text-sm font-medium text-stone-800">{d.label}</span>
                <span className="block text-xs text-stone-500">{d.desc}</span>
              </span>
            </label>
          ))}
        </div>

        <h3 className="mb-2 text-sm font-semibold text-stone-700">Biçim</h3>
        <div className="mb-5 flex flex-wrap gap-2">
          {FORMATS.map((f) => (
            <button key={f.id} onClick={() => setFormat(f.id)} className={chip(format === f.id)}>{f.label}</button>
          ))}
        </div>

        {dataset !== "deals" && (
          <>
            <h3 className="mb-2 text-sm font-semibold text-stone-700">Zaman aralığı</h3>
            <div className="mb-5 flex flex-wrap gap-2">
              {RANGES.map((r) => (
                <button key={r.days} onClick={() => setDays(r.days)} className={chip(days === r.days)}>{r.label}</button>
              ))}
            </div>
          </>
        )}

        <p className="mb-4 text-xs text-stone-500">
          Sayılar ondalık noktalı, tarihler ISO biçiminde (pandas / R / Excel'e doğrudan yüklenir).
          Excel'de çalışacaksan .xlsx öner — Türkçe Excel CSV'de ';' ayırıcı bekler.
        </p>

        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50">
            İptal
          </button>
          <a
            href={exportUrl(dataset, format, dataset === "deals" ? 0 : days)}
            download
            className="rounded-lg bg-amber-500 px-5 py-2 text-sm font-medium text-stone-900 hover:bg-amber-400"
          >
            İndir
          </a>
        </div>
      </div>
    </div>
  );
}
