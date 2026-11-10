import { useEffect, useState } from "react";
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api, fmtPrice, type MarketOverview } from "../api";

const MONTHS = ["Oca", "Şub", "Mar", "Nis", "May", "Haz", "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara"];
const monthLabel = (m: string) => `${MONTHS[Number(m.slice(5, 7)) - 1]} ${m.slice(2, 4)}`;
const tl = (n: number) => `${fmtPrice(n).replace(/,00$/, "")} TL`;

/** Piyasa normu: çekirdek kahvenin kilo fiyatı — ucuz dilim / orta / pahalı dilim. */
export function MarketView() {
  const [size, setSize] = useState("1000");
  const [data, setData] = useState<MarketOverview | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    setErr(null);
    api.market(size).then(setData).catch((e) => setErr(String(e)));
  }, [size]);

  if (err) return <p className="text-sm text-red-600">Piyasa verisi alınamadı: {err}</p>;
  if (!data) return <p className="text-sm text-stone-500">Yükleniyor…</p>;

  const months = data.months;
  const last = months[months.length - 1];
  const ref = months.length > 3 ? months[months.length - 4] : months[0];
  const chart = months.map((m) => ({ ...m, label: monthLabel(m.month), band: [m.low, m.high] }));

  const tile = (title: string, hint: string, now: number, then: number | undefined) => {
    const pct = then ? (now / then - 1) * 100 : null;
    return (
      <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
        <div className="text-xs font-semibold uppercase text-stone-500">{title}</div>
        <div className="mt-1 text-2xl font-semibold tabular-nums text-stone-900">{tl(now)}</div>
        <div className="mt-0.5 text-xs text-stone-500">
          {hint}
          {pct != null && ref !== last && (
            <>
              {" · "}
              {monthLabel(ref.month)}: {tl(then!)} ({pct >= 0 ? "+" : "−"}%{Math.abs(pct).toFixed(0)})
            </>
          )}
        </div>
      </div>
    );
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span className="mr-1 text-stone-500">Paket boyu:</span>
        {data.sizes.map((s) => (
          <button
            key={s.id}
            onClick={() => setSize(s.id)}
            className={
              "rounded-full border px-3 py-1 " +
              (size === s.id
                ? "border-amber-500 bg-amber-500 font-medium text-stone-900"
                : "border-stone-300 bg-white text-stone-600 hover:bg-stone-50")
            }
          >
            {s.label}
          </button>
        ))}
        <span className="ml-2 text-xs text-stone-400">Çekirdek kahve · kilo fiyatı</span>
      </div>

      {!last ? (
        <p className="rounded-2xl border border-stone-200 bg-white px-4 py-12 text-center text-stone-400">
          Bu paket boyu için norm çıkaracak kadar ürün yok.
        </p>
      ) : (
        <>
          <div className="grid gap-3 sm:grid-cols-3">
            {tile("Ucuz dilim", "ürünlerin en ucuz %25'i bu fiyatın altında", last.low, ref.low)}
            {tile("Orta", "ürünlerin yarısı bunun altında", last.mid, ref.mid)}
            {tile("Pahalı dilim", "en pahalı %25 bu fiyatın üstünde", last.high, ref.high)}
          </div>

          <div className="rounded-2xl border border-stone-200 bg-white p-4 shadow-sm">
            <div className="mb-1 flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="text-sm font-semibold text-stone-800">
                {data.size_label} çekirdek kahvenin kilo fiyatı, aylık
              </h3>
              <div className="flex items-center gap-4 text-xs text-stone-500">
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-0.5 w-5 bg-amber-600" /> Orta fiyat
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="inline-block h-3 w-5 rounded-sm bg-amber-200" /> Ucuz–pahalı aralığı
                </span>
              </div>
            </div>
            <div className="h-72 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <ComposedChart data={chart} margin={{ top: 12, right: 16, bottom: 4, left: 8 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#eee" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 12, fill: "#78716c" }} tickLine={false} />
                  <YAxis
                    width={64}
                    tick={{ fontSize: 12, fill: "#78716c" }}
                    tickLine={false}
                    axisLine={false}
                    domain={[0, (max: number) => Math.ceil((max * 1.1) / 500) * 500]}
                    tickFormatter={(v: number) => fmtPrice(v).replace(/,00$/, "")}
                  />
                  <Tooltip
                    content={({ active, payload }) => {
                      if (!active || !payload?.length) return null;
                      const m = payload[0].payload;
                      return (
                        <div className="rounded-lg border border-stone-200 bg-white px-3 py-2 text-xs shadow">
                          <div className="mb-1 font-semibold text-stone-800">{m.label}</div>
                          <div className="tabular-nums text-stone-600">Pahalı dilim: {tl(m.high)}</div>
                          <div className="font-medium tabular-nums text-stone-900">Orta: {tl(m.mid)}</div>
                          <div className="tabular-nums text-stone-600">Ucuz dilim: {tl(m.low)}</div>
                          <div className="mt-1 text-stone-400">{m.products} ürün</div>
                        </div>
                      );
                    }}
                  />
                  <Area dataKey="band" stroke="none" fill="#fde68a" fillOpacity={0.7} isAnimationActive={false} />
                  <Line
                    dataKey="mid"
                    stroke="#d97706"
                    strokeWidth={2}
                    dot={{ r: 4, fill: "#d97706", stroke: "#fff", strokeWidth: 2 }}
                    isAnimationActive={false}
                  />
                </ComposedChart>
              </ResponsiveContainer>
            </div>
            <table className="mt-3 w-full text-right text-xs tabular-nums text-stone-600">
              <thead className="text-stone-400">
                <tr>
                  <th className="py-1 text-left font-medium">Ay</th>
                  <th className="font-medium">Ucuz dilim</th>
                  <th className="font-medium">Orta</th>
                  <th className="font-medium">Pahalı dilim</th>
                  <th className="font-medium">Ürün</th>
                </tr>
              </thead>
              <tbody>
                {months.map((m) => (
                  <tr key={m.month} className="border-t border-stone-100">
                    <td className="py-1 text-left">{monthLabel(m.month)}</td>
                    <td>{tl(m.low)}</td>
                    <td className="font-medium text-stone-900">{tl(m.mid)}</td>
                    <td>{tl(m.high)}</td>
                    <td>{m.products}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
            <h3 className="px-4 pt-4 text-sm font-semibold text-stone-800">
              Markalar — {monthLabel(last.month)} ({data.size_label})
            </h3>
            <table className="mt-2 w-full text-sm">
              <thead className="bg-stone-50 text-xs uppercase text-stone-500">
                <tr>
                  <th className="px-4 py-2 text-left font-semibold">Marka</th>
                  <th className="px-4 py-2 text-right font-semibold">Orta kilo fiyatı</th>
                  <th className="px-4 py-2 text-right font-semibold">En ucuz – en pahalı</th>
                  <th className="px-4 py-2 text-right font-semibold">Önceki aya göre</th>
                  <th className="px-4 py-2 text-right font-semibold">Ürün</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-stone-100">
                {data.brands.map((b) => (
                  <tr key={b.brand}>
                    <td className="px-4 py-2 font-medium capitalize">{b.brand}</td>
                    <td className="px-4 py-2 text-right font-medium tabular-nums">{tl(b.mid)}</td>
                    <td className="px-4 py-2 text-right tabular-nums text-stone-500">
                      {tl(b.min)} – {tl(b.max)}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-stone-500">
                      {b.change_pct == null ? "—" : `${b.change_pct >= 0 ? "+" : "−"}%${Math.abs(b.change_pct).toFixed(1)}`}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums text-stone-500">{b.products}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
