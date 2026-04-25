"""Tek bir ürünün fiyat geçmişini gösteren basit dialog.

QtCharts yoksa (paketleme/sürüm farkı) düz QWidget üzerinde QPainter ile
çizim yapan bir fallback kullanılır.
"""
from __future__ import annotations

from datetime import datetime
from typing import Sequence

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class _PricePlot(QWidget):
    """QPainter ile çizilmiş minimal çizgi grafik. QtCharts dependency'si yok."""

    PADDING_L = 70
    PADDING_R = 16
    PADDING_T = 16
    PADDING_B = 40

    def __init__(self, points: Sequence[tuple[datetime, float]], parent=None) -> None:
        super().__init__(parent)
        self._points = list(points)
        self.setMinimumSize(560, 320)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect()
        p.fillRect(rect, QColor("#ffffff"))

        if not self._points:
            p.setPen(QColor("#888"))
            p.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Henüz fiyat geçmişi yok")
            return

        x0 = self.PADDING_L
        y0 = self.PADDING_T
        x1 = rect.width() - self.PADDING_R
        y1 = rect.height() - self.PADDING_B

        prices = [pr for _, pr in self._points]
        times = [t for t, _ in self._points]
        pmin, pmax = min(prices), max(prices)
        if pmax == pmin:
            pmax = pmin + 1.0
        # %5 padding fiyat ekseni için
        span = pmax - pmin
        pmin -= span * 0.08
        pmax += span * 0.08

        tmin = times[0].timestamp()
        tmax = times[-1].timestamp()
        if tmax == tmin:
            tmax = tmin + 1

        def to_xy(t: datetime, pr: float) -> QPointF:
            x = x0 + (t.timestamp() - tmin) / (tmax - tmin) * (x1 - x0)
            y = y1 - (pr - pmin) / (pmax - pmin) * (y1 - y0)
            return QPointF(x, y)

        # Eksenler
        axis_pen = QPen(QColor("#888"))
        axis_pen.setWidth(1)
        p.setPen(axis_pen)
        p.drawLine(x0, y1, x1, y1)
        p.drawLine(x0, y0, x0, y1)

        # Y ekseni grid + etiket (5 adım)
        p.setPen(QColor("#444"))
        for i in range(5):
            frac = i / 4
            y = y1 - frac * (y1 - y0)
            val = pmin + frac * (pmax - pmin)
            p.setPen(QColor("#eee"))
            p.drawLine(x0 + 1, int(y), x1, int(y))
            p.setPen(QColor("#444"))
            p.drawText(4, int(y) + 4, f"{val:,.0f} TL")

        # X ekseni: ilk, orta, son tarih
        idxs = [0, len(times) // 2, len(times) - 1]
        for i in idxs:
            t = times[i]
            x = to_xy(t, prices[i]).x()
            p.setPen(QColor("#444"))
            label = t.strftime("%d.%m")
            p.drawText(int(x) - 18, y1 + 18, label)

        # Çizgi
        line_pen = QPen(QColor("#0066cc"))
        line_pen.setWidth(2)
        p.setPen(line_pen)
        prev = None
        for t, pr in self._points:
            cur = to_xy(t, pr)
            if prev is not None:
                p.drawLine(prev, cur)
            prev = cur

        # Noktalar
        p.setPen(QPen(QColor("#0066cc")))
        p.setBrush(QColor("#0066cc"))
        for t, pr in self._points:
            xy = to_xy(t, pr)
            p.drawEllipse(xy, 3, 3)

        # Min/güncel etiket
        cur_t, cur_p = self._points[-1]
        min_idx = prices.index(min(prices))
        min_t, min_p = self._points[min_idx]

        info_y = y0 + 14
        p.setPen(QColor("#0066cc"))
        p.drawText(x0 + 8, info_y, f"Güncel: {cur_p:,.2f} TL ({cur_t.strftime('%d.%m %H:%M')})")
        p.setPen(QColor("#cc3300"))
        p.drawText(x0 + 8, info_y + 16, f"Min: {min_p:,.2f} TL ({min_t.strftime('%d.%m')})")


class PriceChartDialog(QDialog):
    def __init__(
        self,
        title: str,
        points: Sequence[tuple[datetime, float]],
        url: str,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Fiyat Geçmişi")
        self.resize(640, 420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        header = QLabel(title)
        header.setWordWrap(True)
        header.setStyleSheet("font-weight: 600;")
        layout.addWidget(header)

        if points:
            sub = QLabel(
                f"{len(points)} kayıt · "
                f"{points[0][0].strftime('%d.%m.%Y')} → {points[-1][0].strftime('%d.%m.%Y')}"
            )
            sub.setStyleSheet("color: #666;")
            layout.addWidget(sub)
        else:
            sub = QLabel(
                "Henüz fiyat geçmişi yok. Birkaç gün üst üste tarayınca grafik dolacak."
            )
            sub.setStyleSheet("color: #666;")
            sub.setWordWrap(True)
            layout.addWidget(sub)

        plot = _PricePlot(points)
        layout.addWidget(plot, 1)

        # Alt buton barı
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        from PySide6.QtCore import QUrl
        from PySide6.QtGui import QDesktopServices

        open_btn = QPushButton("Ürünü Aç")
        open_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(url)))
        btn_row.addWidget(open_btn)

        close_btn = QPushButton("Kapat")
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)
        layout.addLayout(btn_row)
