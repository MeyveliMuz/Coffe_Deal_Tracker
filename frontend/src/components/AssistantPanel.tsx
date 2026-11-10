import { useEffect, useRef, useState } from "react";
import { api, fmtPrice, type AiBudget, type ChatAction, type ChatMessage, type ChatRecommendation, type Preference } from "../api";

interface Props {
  onClose: () => void;
  /** Asistan ayar değiştirdi / tarama başlattı — ana ekranı tazele */
  onAppChanged?: () => void;
}

interface Turn extends ChatMessage {
  recommendations?: ChatRecommendation[];
  actions?: ChatAction[];
}

function actionText(a: ChatAction): string {
  switch (a.type) {
    case "settings_updated":
      return `⚙ Ayarlar değişti: ${(a.changes ?? []).join(", ")}`;
    case "scan_started":
      return "🔎 Tarama başladı — ana ekrandaki ilerleme çubuğundan izleyebilirsin (3–6 dk)";
    case "preference_saved":
      return `📝 Not aldım: ${a.text}`;
    case "preference_removed":
      return `🗑 Unuttum: ${a.text}`;
    case "balance_updated":
      return `💳 Bakiye güncellendi: ${a.text}`;
  }
}

const GREETING =
  "Merhaba! Sana uygun çekirdeği bulalım ☕\nSevdiğin/sevmediğin kahveleri söylersen not alırım; istersen takip ettiğim markaları değiştirip tarama da başlatırım.\nÖnce şunu sorayım: kahveni nasıl demliyorsun?";
const QUICK = ["Espresso makinesi", "Moka pot", "Filtre / V60", "French press", "Tam otomatik makine"];

// Sohbet tarayıcıda kalsın: pencere kapanıp açılınca kaybolmasın
const STORE_KEY = "coffee-assistant-chat";
function loadTurns(): Turn[] {
  try {
    const raw = localStorage.getItem(STORE_KEY);
    if (raw) return JSON.parse(raw);
  } catch {
    /* özel mod / engelli depolama — boş başla */
  }
  return [{ role: "assistant", text: GREETING }];
}

/** Model cevabındaki **kalın** işaretlerini metin olarak değil kalın göster */
function richText(text: string) {
  return text.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith("**") && part.endsWith("**") ? <strong key={i}>{part.slice(2, -2)}</strong> : part
  );
}

const TIER: Record<string, string> = { ucuz: "ucuz dilim", orta: "orta", pahali: "pahalı dilim" };

/** Kahve tavsiye asistanı — sağdan açılan sohbet paneli. */
export function AssistantPanel({ onClose, onAppChanged }: Props) {
  const [turns, setTurns] = useState<Turn[]>(loadTurns);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const [budget, setBudget] = useState<AiBudget | null>(null);
  const [prefs, setPrefs] = useState<Preference[]>([]);
  const [showPrefs, setShowPrefs] = useState(false);
  const [showWallet, setShowWallet] = useState(false);
  const [balanceInput, setBalanceInput] = useState("");
  const [walletMsg, setWalletMsg] = useState<string | null>(null);

  async function saveBalance() {
    // "664,08", "664.08" (AI Studio böyle gösterir), "1.250,50", "1.250" hepsi kabul
    const s = balanceInput.trim().replace(/\s|TL|TRY/gi, "");
    const norm = s.includes(",")
      ? s.replace(/\./g, "").replace(",", ".")
      : /^\d{1,3}(\.\d{3})+$/.test(s)
        ? s.replace(/\./g, "")
        : s;
    const v = Number(norm);
    if (!Number.isFinite(v) || v < 0) {
      setWalletMsg("Geçerli bir tutar yaz (ör. 640,50)");
      return;
    }
    try {
      setBudget(await api.setAiBalance(v));
      setBalanceInput("");
      setWalletMsg("Kaydedildi — aylık pay yeniden hesaplandı.");
    } catch {
      setWalletMsg("Kaydedilemedi.");
    }
  }

  useEffect(() => {
    api.ai().then((r) => setBudget(r.budget)).catch(() => {});
    api.preferences().then(setPrefs).catch(() => {});
  }, []);

  useEffect(() => {
    try {
      localStorage.setItem(STORE_KEY, JSON.stringify(turns.slice(-40)));
    } catch {
      /* yok say */
    }
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, busy]);

  async function send(text: string) {
    const t = text.trim();
    if (!t || busy) return;
    const next: Turn[] = [...turns, { role: "user", text: t }];
    setTurns(next);
    setInput("");
    setErr(null);
    setBusy(true);
    try {
      // Karşılama mesajı modele gitmesin; konuşma kullanıcıyla başlasın
      const history = next.filter((m, i) => !(i === 0 && m.role === "assistant"));
      const r = await api.chat(history.map(({ role, text }) => ({ role, text })));
      setTurns([...next, { role: "assistant", text: r.reply, recommendations: r.recommendations, actions: r.actions }]);
      if (r.budget) setBudget(r.budget);
      if (r.actions?.some((a) => a.type.startsWith("preference"))) api.preferences().then(setPrefs).catch(() => {});
      if (r.actions?.some((a) => a.type === "settings_updated" || a.type === "scan_started")) onAppChanged?.();
    } catch (e) {
      setErr(String(e).includes("503") ? "Gemini anahtarı bulunamadı (.env)." : "Asistan şu an cevap veremedi, tekrar dene.");
    } finally {
      setBusy(false);
    }
  }

  function reset() {
    setTurns([{ role: "assistant", text: GREETING }]);
    setErr(null);
  }

  return (
    <div className="fixed inset-0 z-50 flex justify-end bg-black/40" onClick={onClose}>
      <div
        className="flex h-full w-full max-w-lg flex-col bg-stone-50 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between border-b border-stone-200 bg-white px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold text-stone-800">☕ Kahve Asistanı</h2>
            <p className="text-xs text-stone-500">
              Öneri yapar, ayarları değiştirebilir, tarama başlatabilir
              {budget && (
                <span title={`Model: ${budget.chat_model}`}>
                  {" · "}bu ay {fmtPrice(budget.spent_try)} / {fmtPrice(budget.budget_try)} TL ({budget.chat_mode} mod)
                </span>
              )}
            </p>
          </div>
          <div className="flex gap-1">
            <button
              onClick={() => {
                setShowWallet((v) => !v);
                setWalletMsg(null);
              }}
              className="rounded-lg px-3 py-1 text-sm text-stone-500 hover:bg-stone-100"
              title="Yapay zekâ bakiyesi ve harcama planı"
            >
              💳
            </button>
            <button
              onClick={() => setShowPrefs((v) => !v)}
              className="rounded-lg px-3 py-1 text-sm text-stone-500 hover:bg-stone-100"
              title="Asistanın hatırladığı tercihlerin"
            >
              📝 {prefs.length}
            </button>
            <button onClick={reset} className="rounded-lg px-3 py-1 text-sm text-stone-500 hover:bg-stone-100">
              Yeni sohbet
            </button>
            <button onClick={onClose} className="rounded-lg px-3 py-1 text-stone-500 hover:bg-stone-100">
              ✕
            </button>
          </div>
        </div>

        {showWallet && budget && (
          <div className="space-y-1.5 border-b border-stone-200 bg-sky-50/60 px-5 py-3 text-sm text-stone-700">
            <div className="font-medium">Yapay zekâ harcama planı</div>
            <div>
              Bu ayın payı: <b>{fmtPrice(budget.budget_try)} TL</b> · harcanan {fmtPrice(budget.spent_try)} TL ·{" "}
              {budget.chat_mode === "akıllı" ? "akıllı model (3.8 Flash)" : "tasarruf modeli (3.1 Flash-Lite)"}
            </div>
            {budget.balance_est_try != null && budget.until && (
              <div className="text-xs text-stone-500">
                Tahmini kalan bakiye {fmtPrice(budget.balance_est_try)} TL ·{" "}
                {new Date(budget.until).toLocaleDateString("tr-TR", { month: "long", year: "numeric" })} sonuna kadar
                yetecek şekilde bölünüyor. Kullanılmayan pay sonraki aylara kalır. Tahmin, gerçek faturaya göre ×
                {budget.cost_factor.toLocaleString("tr-TR")} temkin payı içerir.
              </div>
            )}
            <form
              className="flex items-center gap-2 pt-1"
              onSubmit={(e) => {
                e.preventDefault();
                saveBalance();
              }}
            >
              <input
                value={balanceInput}
                onChange={(e) => setBalanceInput(e.target.value)}
                inputMode="decimal"
                placeholder="AI Studio'daki bakiye (TL)"
                className="w-48 rounded-lg border border-stone-300 px-3 py-1 text-sm outline-none focus:border-sky-500"
              />
              <button
                type="submit"
                disabled={!balanceInput.trim()}
                className="rounded-lg bg-sky-600 px-3 py-1 text-sm font-medium text-white hover:bg-sky-500 disabled:opacity-50"
              >
                Güncelle
              </button>
            </form>
            <div className="text-xs text-stone-500">
              {walletMsg ??
                "Ara sıra AI Studio → Billing'deki bakiyeyi buraya yaz: plan gerçek harcamaya göre kendini düzeltir."}
            </div>
          </div>
        )}

        {showPrefs && (
          <div className="border-b border-stone-200 bg-amber-50/60 px-5 py-3 text-sm">
            <div className="mb-1 font-medium text-stone-700">Hatırladıklarım</div>
            {prefs.length === 0 && (
              <div className="text-stone-500">Henüz yok — sevdiğin/sevmediğin kahveleri söyle, not alayım.</div>
            )}
            {prefs.map((p) => (
              <div key={p.text} className="flex items-center justify-between gap-2 py-0.5">
                <span>
                  {p.kind === "like" ? "👍" : p.kind === "dislike" ? "👎" : "•"} {p.text}
                </span>
                <button
                  onClick={() => api.forgetPreference(p.text).then(setPrefs).catch(() => {})}
                  className="text-xs text-stone-400 hover:text-red-600"
                >
                  sil
                </button>
              </div>
            ))}
          </div>
        )}

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {turns.map((m, i) => (
            <div key={i} className={m.role === "user" ? "flex justify-end" : ""}>
              <div
                className={
                  "max-w-[90%] whitespace-pre-line rounded-2xl px-4 py-2.5 text-sm " +
                  (m.role === "user"
                    ? "bg-amber-500 text-stone-900"
                    : "border border-stone-200 bg-white text-stone-800")
                }
              >
                {m.role === "assistant" ? richText(m.text) : m.text}
              </div>
              {m.actions && m.actions.length > 0 && (
                <div className="mt-1.5 space-y-1">
                  {m.actions.map((a, j) => (
                    <div key={j} className="text-xs text-stone-500">
                      {actionText(a)}
                    </div>
                  ))}
                </div>
              )}
              {m.recommendations && m.recommendations.length > 0 && (
                <div className="mt-2 space-y-2">
                  {m.recommendations.map((r) => (
                    <div key={r.url} className="rounded-xl border border-stone-200 bg-white p-3 text-sm shadow-sm">
                      <div className="flex items-start justify-between gap-3">
                        <div>
                          <div className="font-medium text-stone-800">{r.name}</div>
                          <div className="text-xs text-stone-500">
                            <span className="capitalize">{r.site.replace("_tr", "")}</span>
                            {r.weight ? ` · ${r.weight}` : ""}
                          </div>
                        </div>
                        <a
                          href={r.url}
                          target="_blank"
                          rel="noreferrer"
                          className="shrink-0 rounded-lg border border-stone-300 px-2.5 py-1 text-xs text-stone-700 hover:bg-stone-50"
                        >
                          Aç
                        </a>
                      </div>
                      <div className="mt-1.5 text-sm tabular-nums">
                        <span className="font-semibold text-stone-900">{fmtPrice(r.price_tl)} TL</span>
                        {r.price_per_kg != null && (
                          <span className="text-stone-500">
                            {" "}· {fmtPrice(r.price_per_kg)} / kg{r.market ? ` · ${TIER[r.market]}` : ""}
                          </span>
                        )}
                        {r.discount && (
                          <span
                            className={
                              "ml-2 rounded-full px-2 py-0.5 text-xs font-medium " +
                              (r.discount.verdict === "gerçek"
                                ? "bg-green-100 text-green-700"
                                : r.discount.verdict === "sahte"
                                  ? "bg-red-100 text-red-700"
                                  : "bg-stone-100 text-stone-600")
                            }
                          >
                            {r.discount.verdict === "gerçek"
                              ? `gerçek indirim %${r.discount.pct.toFixed(0)}`
                              : r.discount.verdict === "sahte"
                                ? `sahte indirim (sayfa %${(r.discount.page_claim_pct ?? 0).toFixed(0)})`
                                : "indirim doğrulanamadı"}
                          </span>
                        )}
                      </div>
                      {r.reason && <div className="mt-1 text-xs text-stone-600">{r.reason}</div>}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
          {turns.length === 1 && (
            <div className="flex flex-wrap gap-2">
              {QUICK.map((q) => (
                <button
                  key={q}
                  onClick={() => send(q)}
                  className="rounded-full border border-stone-300 bg-white px-3 py-1 text-sm text-stone-700 hover:bg-stone-100"
                >
                  {q}
                </button>
              ))}
            </div>
          )}
          {busy && (
            <div className="text-sm text-stone-500">
              <span className="inline-block animate-pulse">Düşünüyor…</span>
            </div>
          )}
          {err && <div className="text-sm text-red-600">{err}</div>}
          <div ref={endRef} />
        </div>

        <form
          className="flex gap-2 border-t border-stone-200 bg-white p-3"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Yaz… (ör. sütlü içiyorum, çikolatalı tatlar severim)"
            className="flex-1 rounded-xl border border-stone-300 px-4 py-2 text-sm outline-none focus:border-amber-500"
            disabled={busy}
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-xl bg-amber-500 px-4 py-2 text-sm font-medium text-stone-900 hover:bg-amber-400 disabled:opacity-50"
          >
            Gönder
          </button>
        </form>
      </div>
    </div>
  );
}
