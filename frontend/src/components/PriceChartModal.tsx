import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
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
  /** Sayfadaki üstü çizili fiyat — geçmişte hiç görülmediyse grafikte boşlukta kalır */
  strike?: number | null;
  /** Önceki 30 günün en düşük fiyatı (yasal indirim referansı) */
  low30?: number | null;
  reason?: string;
}

export function PriceChartModal({ url, title, onClose, strike, low30, reason }: Props) {
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
            {reason && <p className="mt-1 text-sm text-stone-700">{reason}</p>}
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
                  domain={[0, (max: number) => Math.ceil(Math.max(max, strike ?? 0) * 1.08)]}
                  tickFormatter={(v: number) => `${Math.round(v)}`}
                />
                {strike != null && (
                  <ReferenceLine
                    y={strike}
                    stroke="#dc2626"
                    strokeDasharray="6 4"
                    label={{ value: `Üstü çizili ${fmtPrice(strike)}`, position: "insideTopRight", fill: "#dc2626", fontSize: 12 }}
                  />
                )}
                {low30 != null && (
                  <ReferenceLine
                    y={low30}
                    stroke="#16a34a"
                    strokeDasharray="6 4"
                    label={{ value: `30 gün en düşük ${fmtPrice(low30)}`, position: "insideBottomRight", fill: "#16a34a", fontSize: 12 }}
                  />
                )}
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
