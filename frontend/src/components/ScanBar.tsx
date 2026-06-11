import type { ScanStatus } from "../api";

interface Props {
  scan: ScanStatus | null;
}

// Tarama sırasında canlı ilerleme şeridi (WebSocket'ten beslenir).
export function ScanBar({ scan }: Props) {
  if (!scan || !scan.running) return null;
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3">
      <div className="flex items-center gap-3">
        <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-amber-500" />
        <span className="text-sm font-medium text-amber-800">
          {scan.last_progress || "Taranıyor…"}
        </span>
        <span className="ml-auto text-sm text-amber-700">
          {scan.products_found} ürün · {scan.deals_found} fırsat
        </span>
      </div>
      <div className="mt-2 h-1 w-full overflow-hidden rounded-full bg-amber-200">
        <div className="h-full w-1/3 animate-pulse rounded-full bg-amber-500" />
      </div>
    </div>
  );
}
