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


HEADERS_ALL = ["Marka", "Ürün", "Site", "Fiyat", "Aç"]
HEADERS_DEALS = ["Marka", "Ürün", "Site", "Fiyat", "Önceki En Düşük", "İndirim (min'e göre)", "Aç"]


class DealTable(QTableWidget):
    def __init__(self, mode: str, parent: Optional[QWidget] = None) -> None:
        """mode: 'all' veya 'deals'"""
        super().__init__(0, 0, parent)
        self._mode = mode
        headers = HEADERS_DEALS if mode == "deals" else HEADERS_ALL
        self.setColumnCount(len(headers))
        self.setHorizontalHeaderLabels(headers)
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.setAlternatingRowColors(True)

        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        # Ürün sütunu esneyecek, diğerleri içeriğe göre
        for i in range(self.columnCount()):
            mode_ = (
                QHeaderView.ResizeMode.Stretch if i == 1 else QHeaderView.ResizeMode.ResizeToContents
            )
            header.setSectionResizeMode(i, mode_)

        # URL'leri duplicate tespiti için sakla
        self._seen_urls: set[str] = set()

    def clear_rows(self) -> None:
        self.setRowCount(0)
        self._seen_urls.clear()

    def add_product(self, listing: ProductListing) -> None:
        if self._mode != "all":
            return
        if listing.url in self._seen_urls:
            return
        self._seen_urls.add(listing.url)

        row = self.rowCount()
        self.insertRow(row)
        self._set(row, 0, listing.brand.title())
        self._set(row, 1, listing.name)
        self._set(row, 2, listing.site.title())
        self._set(row, 3, f"{listing.price:,.2f} {listing.currency}", align_right=True)
        self._set_open_button(row, 4, listing.url)

    def add_deal(self, deal: Deal) -> None:
        if self._mode != "deals":
            return
        key = deal.listing.url
        if key in self._seen_urls:
            return
        self._seen_urls.add(key)

        l = deal.listing
        row = self.rowCount()
        self.insertRow(row)
        self._set(row, 0, l.brand.title())
        self._set(row, 1, l.name)
        self._set(row, 2, l.site.title())
        self._set(row, 3, f"{l.price:,.2f} {l.currency}", align_right=True)
        self._set(row, 4, f"{deal.historical_min:,.2f}", align_right=True)
        discount = (
            f"%{deal.discount_pct:.1f}"
            if deal.discount_pct is not None
            else "—"
        )
        self._set(row, 5, discount, align_right=True)
        self._set_open_button(row, 6, l.url)

    # internal
    def _set(self, row: int, col: int, text: str, *, align_right: bool = False) -> None:
        item = QTableWidgetItem(text)
        if align_right:
            item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.setItem(row, col, item)

    def _set_open_button(self, row: int, col: int, url: str) -> None:
        btn = QPushButton("Aç")
        btn.clicked.connect(lambda _=False, u=url: QDesktopServices.openUrl(QUrl(u)))
        self.setCellWidget(row, col, btn)
