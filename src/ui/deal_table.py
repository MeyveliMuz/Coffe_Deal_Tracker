"""Ürün/fırsat tablosu widget."""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QHeaderView,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from src.core.models import Deal, ProductListing
from src.storage.db import PriceDatabase
from src.ui.price_chart import PriceChartDialog


class _NumericItem(QTableWidgetItem):
    """Sayısal sıralama için QTableWidgetItem alt sınıfı.
    Görüntüde formatlı metin (ör. "1.460,00 TRY") tutar; karşılaştırmada
    saklanan float değeri kullanır."""

    def __init__(self, text: str, value: float) -> None:
        super().__init__(text)
        self._value = value

    def __lt__(self, other) -> bool:  # type: ignore[override]
        if isinstance(other, _NumericItem):
            return self._value < other._value
        return super().__lt__(other)


HEADERS_ALL = ["Marka", "Ürün", "Site", "Fiyat", "Grafik", "Aç"]
HEADERS_DEALS = [
    "Marka", "Ürün", "Site", "Fiyat", "Önceki En Düşük",
    "İndirim (min'e göre)", "Grafik", "Aç",
]


class DealTable(QTableWidget):
    def __init__(
        self,
        mode: str,
        parent: Optional[QWidget] = None,
        *,
        db_path: Optional[str] = None,
    ) -> None:
        """mode: 'all' veya 'deals'"""
        super().__init__(0, 0, parent)
        self._mode = mode
        self._db_path = db_path
        headers = HEADERS_DEALS if mode == "deals" else HEADERS_ALL
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)
        # Başlığa tıklayınca sıralama (alfabetik / sayısal — _NumericItem'la
        # rakamlı sütunlar doğru sıralanır)
        self.setSortingEnabled(True)
        self.horizontalHeader().setSortIndicatorShown(True)

        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        # Ürün sütunu esneyecek; buton sütunları sabit; geri kalan içeriğe göre
        chart_col = self.columnCount() - 2
        open_col = self.columnCount() - 1
        for i in range(self.columnCount()):
            if i == 1:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Stretch)
            elif i in (chart_col, open_col):
                # Sabit genişlik — ResizeToContents cellWidget'ı bazen
                # ölçemiyor ve buton sıkışıp görünmüyor.
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.Fixed)
            else:
                header.setSectionResizeMode(i, QHeaderView.ResizeMode.ResizeToContents)
        self.setColumnWidth(chart_col, 110)
        self.setColumnWidth(open_col, 64)

        # URL'leri duplicate tespiti için sakla
        self._seen_urls: set[str] = set()
        # Aktif arama metni (sonuçlarda filtreleme). Boş = tümü görünür.
        self._filter_text: str = ""
        # NOT: Satır → meta eşlemesi yerine ürün adı sütununun item'ında
        # UserRole+1/+2'de saklıyoruz; sıralamada satır indeksleri değişiyor.

        # Çift tıklama: ürünün fiyat geçmişi grafiği
        self.cellDoubleClicked.connect(self._on_row_double_clicked)

    def set_db_path(self, db_path: str) -> None:
        self._db_path = db_path

    def clear_rows(self) -> None:
        self.setRowCount(0)
        self._seen_urls.clear()

    # -- Arama / filtreleme ---------------------------------------------------
    def apply_filter(self, text: str) -> None:
        """Marka/ürün/site sütunlarında geçen metne göre satırları göster/gizle."""
        self._filter_text = text.strip().lower()
        for row in range(self.rowCount()):
            self.setRowHidden(row, not self._row_matches(row))

    def _row_matches(self, row: int) -> bool:
        if not self._filter_text:
            return True
        # Marka (0), Ürün (1), Site (2) sütunlarında ara
        for col in (0, 1, 2):
            item = self.item(row, col)
            if item is not None and self._filter_text in item.text().lower():
                return True
        return False

    def visible_row_count(self) -> int:
        return sum(
            1 for row in range(self.rowCount()) if not self.isRowHidden(row)
        )

    def add_product(self, listing: ProductListing) -> None:
        if self._mode != "all":
            return
        if listing.url in self._seen_urls:
            return
        self._seen_urls.add(listing.url)

        # Satır eklerken sıralamayı kapat — yoksa header indikatörüne göre
        # her insert'te sıralanır ve satır indeksleri (cellWidget'lar dahil)
        # kayar.
        was_sorting = self.isSortingEnabled()
        self.setSortingEnabled(False)
        try:
            row = self.rowCount()
            self.insertRow(row)
            self._set(row, 0, listing.brand.title())
            title = f"{listing.brand.title()} — {listing.name}"
            self._set(row, 1, listing.name)
            name_item = self.item(row, 1)
            if name_item is not None:
                name_item.setData(Qt.ItemDataRole.UserRole, listing.url)
                name_item.setData(Qt.ItemDataRole.UserRole + 1, title)
            self._set(row, 2, listing.site.title())
            self._set_numeric(
                row, 3,
                f"{listing.price:,.2f} {listing.currency}",
                listing.price,
            )
            self._set_chart_button(row, 4, listing.url, title)
            self._set_open_button(row, 5, listing.url)
        finally:
            self.setSortingEnabled(was_sorting)
        # Aktif arama varsa yeni satır da filtreye uysun (sıralama sonrası
        # satır indeksleri değiştiği için tüm tabloyu yeniden tara).
        if self._filter_text:
            self.apply_filter(self._filter_text)

    def add_deal(self, deal: Deal) -> None:
        if self._mode != "deals":
            return
        key = deal.listing.url
        if key in self._seen_urls:
            return
        self._seen_urls.add(key)

        l = deal.listing
        was_sorting = self.isSortingEnabled()
        self.setSortingEnabled(False)
        try:
            row = self.rowCount()
            self.insertRow(row)
            self._set(row, 0, l.brand.title())
            title = f"{l.brand.title()} — {l.name}"
            self._set(row, 1, l.name)
            name_item = self.item(row, 1)
            if name_item is not None:
                name_item.setData(Qt.ItemDataRole.UserRole, l.url)
                name_item.setData(Qt.ItemDataRole.UserRole + 1, title)
            self._set(row, 2, l.site.title())
            self._set_numeric(row, 3, f"{l.price:,.2f} {l.currency}", l.price)
            self._set_numeric(
                row, 4, f"{deal.historical_min:,.2f}", deal.historical_min
            )
            if deal.discount_pct is not None:
                self._set_numeric(
                    row, 5, f"%{deal.discount_pct:.1f}", deal.discount_pct
                )
            else:
                self._set_numeric(row, 5, "—", -1.0)
            self._set_chart_button(row, 6, l.url, title)
            self._set_open_button(row, 7, l.url)
        finally:
            self.setSortingEnabled(was_sorting)
        if self._filter_text:
            self.apply_filter(self._filter_text)

    # internal
    def _set(self, row: int, col: int, text: str, *, align_right: bool = False) -> None:
        item = QTableWidgetItem(text)
        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, col, item)

    def _set_numeric(self, row: int, col: int, text: str, value: float) -> None:
        item = _NumericItem(text, value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, col, item)

    def _set_open_button(self, row: int, col: int, url: str) -> None:
        btn = QPushButton("Aç")
        btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
        self.setCellWidget(row, col, btn)

    def _set_chart_button(self, row: int, col: int, url: str, title: str) -> None:
        btn = QPushButton("📈 Grafik")
        btn.setToolTip("Fiyat geçmişi grafiğini göster")
        btn.clicked.connect(
            lambda _=False, u=url, t=title: self._open_chart(u, t)
        )
        self.setCellWidget(row, col, btn)

    def _open_chart(self, url: str, title: str) -> None:
        if not self._db_path:
            return
        try:
            db = PriceDatabase(self._db_path)
        except Exception as exc:
            import logging
            logging.getLogger(__name__).exception("DB açılamadı: %s", exc)
            return
        try:
            history = db.price_history(url, window_days=90)
        finally:
            db.close()
        dlg = PriceChartDialog(title, history, url, parent=self)
        dlg.exec()

    def _on_row_double_clicked(self, row: int, col: int) -> None:
        last_col = self.columnCount() - 1
        if col >= last_col - 1:
            return
        name_item = self.item(row, 1)
        if name_item is None:
            return
        url = name_item.data(Qt.ItemDataRole.UserRole)
        title = name_item.data(Qt.ItemDataRole.UserRole + 1)
        if not url:
            return
        self._open_chart(url, title or "")
