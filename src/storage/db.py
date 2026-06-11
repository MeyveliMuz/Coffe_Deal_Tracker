"""SQLite depolama katmanı: ürünler ve fiyat geçmişi."""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from src.core.models import ProductListing


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    url        TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    brand      TEXT NOT NULL,
    site       TEXT NOT NULL,
    image_url  TEXT,
    first_seen TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS price_history (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    product_url    TEXT NOT NULL REFERENCES products(url) ON DELETE CASCADE,
    price          REAL NOT NULL,
    currency       TEXT NOT NULL DEFAULT 'TRY',
    recorded_at    TIMESTAMP NOT NULL,
    original_price REAL
);

CREATE INDEX IF NOT EXISTS idx_price_history_product_time
    ON price_history(product_url, recorded_at);

CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    product_url     TEXT NOT NULL,
    target_price    REAL NOT NULL,
    created_at      TIMESTAMP NOT NULL,
    triggered_at    TIMESTAMP,
    triggered_price REAL
);
"""


class PriceDatabase:
    """Thread-safe basit SQLite wrapper.

    Kullanım:
        with PriceDatabase(path) as db:
            db.upsert_product(listing)
            db.record_price(listing.url, listing.price)
            low = db.min_price_since(listing.url, 30)
    """

    def __init__(self, db_path: Path | str) -> None:
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn: Optional[sqlite3.Connection] = None
        self._open()
        self._init_schema()

    # --- lifecycle -----------------------------------------------------------
    def _open(self) -> None:
        self._conn = sqlite3.connect(
            self._path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA journal_mode = WAL")

    def _init_schema(self) -> None:
        assert self._conn is not None
        with self._lock:
            self._conn.executescript(SCHEMA)
            # Migration: eski DB'lerde original_price kolonu yoksa ekle
            cols = [
                r[1] for r in self._conn.execute(
                    "PRAGMA table_info(price_history)"
                ).fetchall()
            ]
            if "original_price" not in cols:
                self._conn.execute(
                    "ALTER TABLE price_history ADD COLUMN original_price REAL"
                )
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "PriceDatabase":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # --- helpers -------------------------------------------------------------
    @contextmanager
    def _cursor(self):
        assert self._conn is not None, "Database is closed"
        with self._lock:
            cur = self._conn.cursor()
            try:
                yield cur
                self._conn.commit()
            finally:
                cur.close()

    # --- writes --------------------------------------------------------------
    def upsert_product(self, listing: ProductListing) -> None:
        """Ürün yoksa ekle; varsa ad/resim gibi alanları güncelle."""
        now = datetime.now()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO products(url, name, brand, site, image_url, first_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    name = excluded.name,
                    image_url = COALESCE(excluded.image_url, products.image_url)
                """,
                (
                    listing.url,
                    listing.name,
                    listing.brand.lower(),
                    listing.site,
                    listing.image_url,
                    now,
                ),
            )

    def record_price(
        self,
        product_url: str,
        price: float,
        currency: str = "TRY",
        recorded_at: Optional[datetime] = None,
        original_price: Optional[float] = None,
    ) -> None:
        when = recorded_at or datetime.now()
        with self._cursor() as cur:
            cur.execute(
                """
                INSERT INTO price_history(product_url, price, currency, recorded_at, original_price)
                VALUES (?, ?, ?, ?, ?)
                """,
                (product_url, float(price), currency, when, original_price),
            )

    def record_listing(self, listing: ProductListing) -> datetime:
        """upsert_product + record_price bir arada. Yazılan fiyatın
        `recorded_at` zamanını döndürür — deal_detector bunu kullanarak
        kendini hariç tutabilir."""
        now = datetime.now()
        self.upsert_product(listing)
        self.record_price(
            listing.url,
            listing.price,
            listing.currency,
            recorded_at=now,
            original_price=listing.original_price,
        )
        return now

    # --- reads ---------------------------------------------------------------
    def min_price_since(self, product_url: str, window_days: int) -> Optional[float]:
        """Verilen pencere içindeki en düşük fiyat. Kayıt yoksa None."""
        with self._cursor() as cur:
            cur.execute(
                f"""
                SELECT MIN(price) FROM price_history
                WHERE product_url = ?
                  AND recorded_at >= datetime('now', '-{int(window_days)} days')
                """,
                (product_url,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None

    def previous_min_price(
        self,
        product_url: str,
        window_days: int,
        *,
        before: Optional[datetime] = None,
    ) -> Optional[float]:
        """Mevcut kaydı HARİÇ tutarak pencere içindeki en düşük fiyat.
        Bir taramada yeni fiyat kaydedildikten sonra "önceki en düşük"
        karşılaştırması için kullanılır."""
        with self._cursor() as cur:
            if before is None:
                cur.execute(
                    f"""
                    SELECT MIN(price) FROM price_history
                    WHERE product_url = ?
                      AND recorded_at >= datetime('now', '-{int(window_days)} days')
                    """,
                    (product_url,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT MIN(price) FROM price_history
                    WHERE product_url = ?
                      AND recorded_at >= datetime('now', '-{int(window_days)} days')
                      AND recorded_at < ?
                    """,
                    (product_url, before),
                )
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None

    def previous_logged_price(
        self,
        product_url: str,
        *,
        before: Optional[datetime] = None,
        different_from: Optional[float] = None,
        tolerance: float = 0.01,
    ) -> Optional[float]:
        """Önceki tarama fiyatı.
        `different_from` verilirse o değerden farklı (|fark| > tolerance) en yeni
        kaydın fiyatını döner — yani 'son değişim öncesi fiyat'. Verilmezse
        zaman olarak hemen önceki kaydın fiyatı."""
        with self._cursor() as cur:
            params: list = [product_url]
            sql = "SELECT price FROM price_history WHERE product_url = ?"
            if before is not None:
                sql += " AND recorded_at < ?"
                params.append(before)
            if different_from is not None:
                sql += " AND ABS(price - ?) > ?"
                params.extend([different_from, tolerance])
            sql += " ORDER BY recorded_at DESC LIMIT 1"
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None

    def avg_price_since(self, product_url: str, window_days: int) -> Optional[float]:
        with self._cursor() as cur:
            cur.execute(
                f"""
                SELECT AVG(price) FROM price_history
                WHERE product_url = ?
                  AND recorded_at >= datetime('now', '-{int(window_days)} days')
                """,
                (product_url,),
            )
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else None

    def history_count(
        self,
        product_url: str,
        window_days: int,
        *,
        before: Optional[datetime] = None,
    ) -> int:
        with self._cursor() as cur:
            if before is None:
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM price_history
                    WHERE product_url = ?
                      AND recorded_at >= datetime('now', '-{int(window_days)} days')
                    """,
                    (product_url,),
                )
            else:
                cur.execute(
                    f"""
                    SELECT COUNT(*) FROM price_history
                    WHERE product_url = ?
                      AND recorded_at >= datetime('now', '-{int(window_days)} days')
                      AND recorded_at < ?
                    """,
                    (product_url, before),
                )
            row = cur.fetchone()
            return int(row[0]) if row else 0

    def price_history(
        self, product_url: str, window_days: int = 90
    ) -> list[tuple[datetime, float]]:
        """Verilen ürün için (zaman, fiyat) geçmişini eskiden yeniye döndür."""
        with self._cursor() as cur:
            cur.execute(
                f"""
                SELECT recorded_at, price FROM price_history
                WHERE product_url = ?
                  AND recorded_at >= datetime('now', '-{int(window_days)} days')
                ORDER BY recorded_at ASC
                """,
                (product_url,),
            )
            rows = cur.fetchall()
        out: list[tuple[datetime, float]] = []
        for ts, price in rows:
            if isinstance(ts, str):
                try:
                    ts = datetime.fromisoformat(ts)
                except ValueError:
                    continue
            out.append((ts, float(price)))
        return out

    def all_products(self) -> list[tuple]:
        with self._cursor() as cur:
            cur.execute("SELECT url, name, brand, site, image_url FROM products ORDER BY name")
            return cur.fetchall()

    # --- fiyat alarmları -----------------------------------------------------
    def latest_price(self, product_url: str) -> Optional[float]:
        """Bir ürünün en son kaydedilen fiyatı (yoksa None)."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT price FROM price_history
                WHERE product_url = ?
                ORDER BY recorded_at DESC LIMIT 1
                """,
                (product_url,),
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else None

    def add_alert(self, product_url: str, target_price: float) -> int:
        """Bir ürün için hedef-fiyat alarmı ekle; alarm id'sini döndürür."""
        with self._cursor() as cur:
            cur.execute(
                "INSERT INTO alerts(product_url, target_price, created_at) VALUES (?, ?, ?)",
                (product_url, float(target_price), datetime.now()),
            )
            return int(cur.lastrowid)

    def delete_alert(self, alert_id: int) -> None:
        with self._cursor() as cur:
            cur.execute("DELETE FROM alerts WHERE id = ?", (int(alert_id),))

    def list_alerts(self) -> list[dict]:
        """Tüm alarmlar — ürün adı ve güncel fiyatla birlikte."""
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT a.id, a.product_url, p.name, a.target_price,
                       a.created_at, a.triggered_at, a.triggered_price
                FROM alerts a
                LEFT JOIN products p ON p.url = a.product_url
                ORDER BY a.created_at DESC
                """
            )
            rows = cur.fetchall()
        out: list[dict] = []
        for r in rows:
            out.append(
                {
                    "id": int(r[0]),
                    "product_url": r[1],
                    "name": r[2],
                    "target_price": float(r[3]),
                    "current_price": self.latest_price(r[1]),
                    "created_at": r[4].isoformat() if isinstance(r[4], datetime) else r[4],
                    "triggered_at": r[5].isoformat() if isinstance(r[5], datetime) else r[5],
                    "triggered_price": float(r[6]) if r[6] is not None else None,
                }
            )
        return out

    def check_alerts(self) -> list[dict]:
        """Henüz tetiklenmemiş alarmları kontrol et: güncel fiyat hedefin
        altına/eşiğine indiyse tetiklenmiş işaretle. Yeni tetiklenenleri döndür."""
        newly: list[dict] = []
        with self._cursor() as cur:
            cur.execute(
                "SELECT id, product_url, target_price FROM alerts WHERE triggered_at IS NULL"
            )
            pending = cur.fetchall()
        for alert_id, url, target in pending:
            current = self.latest_price(url)
            if current is not None and current <= float(target):
                now = datetime.now()
                with self._cursor() as cur:
                    cur.execute(
                        "UPDATE alerts SET triggered_at = ?, triggered_price = ? WHERE id = ?",
                        (now, current, int(alert_id)),
                    )
                newly.append(
                    {
                        "id": int(alert_id),
                        "product_url": url,
                        "target_price": float(target),
                        "triggered_price": current,
                    }
                )
        return newly

    def latest_snapshot(self, hours: int = 48) -> list[tuple[ProductListing, datetime]]:
        """Her URL için son `hours` saat içindeki en yeni fiyat kaydı.
        `(listing, recorded_at)` çiftleri döndürür — recorded_at'i bilmek
        deal hesaplamasında bu kaydı hariç tutmayı sağlar.
        Uygulama açılırken en son tarama sonuçlarını UI'ya yüklemek için."""
        with self._cursor() as cur:
            cur.execute(
                f"""
                SELECT p.url, p.name, p.brand, p.site, p.image_url,
                       ph.price, ph.currency, ph.recorded_at, ph.original_price
                FROM products p
                JOIN (
                    SELECT product_url, price, currency, recorded_at, original_price,
                           ROW_NUMBER() OVER (
                               PARTITION BY product_url
                               ORDER BY recorded_at DESC
                           ) AS rn
                    FROM price_history
                    WHERE recorded_at >= datetime('now', '-{int(hours)} hours')
                ) ph ON ph.product_url = p.url AND ph.rn = 1
                ORDER BY p.site, p.brand, p.name
                """
            )
            rows = cur.fetchall()

        out: list[tuple[ProductListing, datetime]] = []
        for r in rows:
            recorded_at = r[7]
            if isinstance(recorded_at, str):
                try:
                    recorded_at = datetime.fromisoformat(recorded_at)
                except ValueError:
                    recorded_at = datetime.now()
            op = r[8] if len(r) > 8 else None
            listing = ProductListing(
                url=r[0],
                name=r[1],
                brand=r[2],
                site=r[3],
                image_url=r[4],
                price=float(r[5]),
                currency=r[6] or "TRY",
                original_price=float(op) if op is not None else None,
            )
            out.append((listing, recorded_at))
        return out
