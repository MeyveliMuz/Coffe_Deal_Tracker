"""Ürün adından net ağırlık (gramaj) çıkarma.

Gerçek adlardaki yazımlar: "250 gr", "1kg", "1000 GR.", "500G", "2x250gr",
"2 X 1 Kg", "250 gr X 2 Adet", "500 gr - 2 Adet", "1000 gr 2 Lİ",
"2 Adet 1kg", "3 x 1000g", "1 Kg (2 Adet 500 Gr)".

Kural: addaki İLK ağırlık ifadesi esas alınır; hemen önünde/arkasında bir
adet çarpanı varsa (2x, x 2, 2 Adet, 2'li) toplam = adet × paket. Sonradan
gelen parantez içi açıklamalar ("1 Kg (2 Adet 500 Gr)") toplamı değiştirmez.
"""
from __future__ import annotations

import re
from typing import Optional

_SIZE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|kilo|gram|gr|g)(?![a-wyzçğıöşü])", re.IGNORECASE)
_X = r"[x×*]"
_PRE_X = re.compile(rf"(\d+)\s*{_X}\s*$", re.IGNORECASE)                 # "2 x " + 250 gr
_PRE_ADET = re.compile(r"(\d+)\s*adet\s*$", re.IGNORECASE)              # "2 Adet " + 1kg
_POST_X = re.compile(rf"^\s*{_X}\s*(\d+)\b", re.IGNORECASE)              # 1 kg + " x 2"
_POST_ADET = re.compile(
    r"^\s*[-,]?\s*(\d+)\s*(?:adet|paket|'?\s*l[iıuü]\b)", re.IGNORECASE   # 500 gr + " - 2 Adet" / " 2 Lİ"
)


def parse_weight(name: str) -> Optional[dict]:
    """{'total_g', 'pack_g', 'count', 'label'} ya da gramaj yoksa None."""
    m = _SIZE.search(name or "")
    if not m:
        return None
    value = float(m.group(1).replace(",", "."))
    pack_g = value * 1000 if m.group(2).lower() in ("kg", "kilo") else value
    if not 20 <= pack_g <= 20000:  # "%100", model kodu vb. saçmalıkları ele
        return None

    prefix, suffix = name[: m.start()], name[m.end():]
    count = 1
    for rx, text in ((_PRE_X, prefix), (_PRE_ADET, prefix), (_POST_X, suffix), (_POST_ADET, suffix)):
        hit = rx.search(text)
        if hit and 1 < int(hit.group(1)) <= 24:
            count = int(hit.group(1))
            break

    pack_g = round(pack_g)
    unit = f"{pack_g / 1000:g} kg" if pack_g >= 1000 else f"{pack_g} g"
    return {
        "total_g": pack_g * count,
        "pack_g": pack_g,
        "count": count,
        "label": f"{count} × {unit}" if count > 1 else unit,
    }
