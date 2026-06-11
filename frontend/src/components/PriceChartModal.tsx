import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, fmtPrice, type HistoryPoint } from "../api";

interface Props {
  url: string;
  title: string;
  onClose: () => void;
}

export function PriceChartModal({ url, title, onClose }: Props) {
  const [points, setPoints] = useState<HistoryPoint[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .history(url)
      .then(setPoints)
      .catch((e) => setErr(String(e)));
  }, [url]);

  const data = (points ?? []).map((p) => ({
    date: new Date(p.t).toLocaleDateString("tr-TR", { day: "2-digit", month: "2-digit" }),
    price: p.price,
  }));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-2xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-4 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-semibold text-stone-800">Fiyat geçmişi</h2>
            <p className="text-sm text-stone-500">{title}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-lg px-3 py-1 text-stone-500 hover:bg-stone-100"
          >
            ✕
          </button>
        </div>

        {err && <p className="text-sm text-red-600">Geçmiş alınamadı: {err}</p>}
        {!err && points && points.length === 0 && (
          <p className="py-12 text-center text-stone-500">
            Henüz fiyat geçmişi yok. Birkaç gün üst üste tarayınca grafik dolacak.
          </p>
        )}
        {!err && data.length > 0 && (
          <div className="h-72 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={data} margin={{ top: 8, right: 16, bottom: 8, left: 8 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#eee" />
                <XAxis dataKey="date" tick={{ fontSize: 12, fill: "#78716c" }} />
                <YAxis
                  tick={{ fontSize: 12, fill: "#78716c" }}
                  width={70}
                  tickFormatter={(v: number) => `${Math.round(v)}`}
                />
                <Tooltip
                  formatter={(v: number) => [`${fmtPrice(v)} TL`, "Fiyat"]}
                  labelStyle={{ color: "#44403c" }}
                />
                <Line
                  type="monotone"
                  dataKey="price"
                  stroke="#d97706"
                  strokeWidth={2}
                  dot={{ r: 3, fill: "#d97706" }}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        <div className="mt-4 flex justify-end gap-2">
          <a
            href={url}
            target="_blank"
            rel="noreferrer"
            className="rounded-lg border border-stone-300 px-4 py-2 text-sm text-stone-700 hover:bg-stone-50"
          >
            Ürünü aç
          </a>
          <button
            onClick={onClose}
            className="rounded-lg bg-stone-800 px-4 py-2 text-sm text-white hover:bg-stone-700"
          >
            Kapat
          </button>
        </div>
      </div>
    </div>
  );
}
