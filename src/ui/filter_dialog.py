"""Filtre & ayar penceresi.

Kullanıcı buradan markaları (popüler liste + serbest metin), ürün türlerini,
indirim penceresini ve otomatik başlatma seçeneklerini ayarlar. 'Kaydet'
yeni bir AppConfig döndürür; ana pencere bunu config.json'a yazar.
"""
from __future__ import annotations

import dataclasses

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.core import autostart
from src.core.config import PRODUCT_TYPES, AppConfig

# Popüler / yaygın kahve markaları (anahtar = küçük harf eşleşme,
# etiket = ekranda görünen ad). Kullanıcının config'inde olup burada
# olmayan markalar "Diğer markalar" kutusuna düşer.
POPULAR_BRANDS: list[tuple[str, str]] = [
    ("lavazza", "Lavazza"),
    ("illy", "Illy"),
    ("meinl", "Meinl (Julius Meinl)"),
    ("tchibo", "Tchibo"),
    ("segafredo", "Segafredo"),
    ("dallmayr", "Dallmayr"),
    ("starbucks", "Starbucks"),
    ("kicking horse", "Kicking Horse"),
    ("mehmet efendi", "Mehmet Efendi"),
    ("kahve dünyası", "Kahve Dünyası"),
    ("nescafe", "Nescafé"),
    ("jacobs", "Jacobs"),
    ("mokarabia", "Mokarabia"),
    ("kimbo", "Kimbo"),
    ("melitta", "Melitta"),
    ("probador", "Probador"),
    ("cafemarkt", "Cafemarkt"),
    ("espressolab", "Espressolab"),
    ("whirl", "Whirl"),
]


class FilterDialog(QDialog):
    def __init__(self, config: AppConfig, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Filtreler ve Ayarlar")
        self.resize(560, 640)
        self._config = config

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        # --- Markalar ---------------------------------------------------------
        selected_brands = {b.strip().lower() for b in config.brands}
        popular_keys = {key for key, _ in POPULAR_BRANDS}

        brand_group = QGroupBox("Markalar")
        brand_outer = QVBoxLayout(brand_group)
        brand_hint = QLabel("Aranacak markaları seç. Listede olmayanları aşağıya virgülle ekle.")
        brand_hint.setStyleSheet("color: #666;")
        brand_hint.setWordWrap(True)
        brand_outer.addWidget(brand_hint)

        # Kutucuklar scroll içinde (uzun liste pencereyi taşırmasın)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setMaximumHeight(200)
        grid_host = QWidget()
        grid = QGridLayout(grid_host)
        grid.setContentsMargins(4, 4, 4, 4)
        self._brand_boxes: dict[str, QCheckBox] = {}
        for i, (key, label) in enumerate(POPULAR_BRANDS):
            cb = QCheckBox(label)
            cb.setChecked(key in selected_brands)
            self._brand_boxes[key] = cb
            grid.addWidget(cb, i // 2, i % 2)
        scroll.setWidget(grid_host)
        brand_outer.addWidget(scroll)

        custom_brands = sorted(selected_brands - popular_keys)
        custom_row = QHBoxLayout()
        custom_row.addWidget(QLabel("Diğer markalar:"))
        self._custom_brands = QLineEdit(", ".join(custom_brands))
        self._custom_brands.setPlaceholderText("ör. arabica, mokarabia, ...")
        custom_row.addWidget(self._custom_brands, 1)
        brand_outer.addLayout(custom_row)
        root.addWidget(brand_group)

        # --- Ürün türleri -----------------------------------------------------
        type_group = QGroupBox("Ürün Türleri")
        type_layout = QGridLayout(type_group)
        selected_types = {t.strip().lower() for t in config.product_types}
        self._type_boxes: dict[str, QCheckBox] = {}
        for i, (key, label) in enumerate(PRODUCT_TYPES.items()):
            cb = QCheckBox(label)
            cb.setChecked(key in selected_types)
            self._type_boxes[key] = cb
            type_layout.addWidget(cb, i // 3, i % 3)
        root.addWidget(type_group)

        # --- İndirim penceresi ------------------------------------------------
        window_group = QGroupBox("İndirim Penceresi")
        window_layout = QHBoxLayout(window_group)
        window_layout.addWidget(QLabel("Son"))
        self._history_days = QSpinBox()
        self._history_days.setRange(1, 365)
        self._history_days.setValue(config.history_days)
        self._history_days.setSuffix(" gün")
        window_layout.addWidget(self._history_days)
        window_layout.addWidget(
            QLabel("içindeki en düşüğün altına inen ürünler fırsat sayılır.")
        )
        window_layout.addStretch(1)
        root.addWidget(window_group)

        # --- Otomatik başlatma ------------------------------------------------
        auto_group = QGroupBox("Otomatik Başlatma")
        auto_layout = QVBoxLayout(auto_group)
        self._start_with_windows = QCheckBox(
            "Windows oturum açılışında uygulamayı otomatik başlat"
        )
        # Kayıt defteri tek doğru kaynak — başlangıç durumunu oradan oku.
        self._start_with_windows.setChecked(autostart.is_enabled())
        self._auto_scan = QCheckBox("Uygulama her açıldığında otomatik tarama yap")
        self._auto_scan.setChecked(config.auto_scan_on_launch)
        auto_layout.addWidget(self._start_with_windows)
        auto_layout.addWidget(self._auto_scan)
        note = QLabel(
            "Not: Windows ile başlatıldığında uygulama her zaman bir tarama yapar; "
            "ikinci seçenek elle açtığınızda da taramayı tetikler."
        )
        note.setStyleSheet("color: #666;")
        note.setWordWrap(True)
        auto_layout.addWidget(note)
        root.addWidget(auto_group)

        # --- Butonlar ---------------------------------------------------------
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("Kaydet")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("İptal")
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

    # ------------------------------------------------------------------
    def _collect_brands(self) -> list[str]:
        brands: list[str] = []
        for key, cb in self._brand_boxes.items():
            if cb.isChecked():
                brands.append(key)
        for raw in self._custom_brands.text().split(","):
            b = raw.strip().lower()
            if b and b not in brands:
                brands.append(b)
        return brands

    def _collect_types(self) -> list[str]:
        return [key for key, cb in self._type_boxes.items() if cb.isChecked()]

    def _on_accept(self) -> None:
        brands = self._collect_brands()
        types = self._collect_types()
        if not brands:
            QMessageBox.warning(
                self, "Eksik seçim", "En az bir marka seçmelisiniz."
            )
            return
        if not types:
            QMessageBox.warning(
                self, "Eksik seçim", "En az bir ürün türü seçmelisiniz."
            )
            return
        self.accept()

    def result_config(self) -> AppConfig:
        """Pencereyi 'Kaydet' ile kapatan kullanıcının seçimlerini yansıtan
        yeni AppConfig. (Sadece accept sonrası çağrılmalı.)"""
        return dataclasses.replace(
            self._config,
            brands=self._collect_brands(),
            product_types=self._collect_types(),
            history_days=self._history_days.value(),
            start_with_windows=self._start_with_windows.isChecked(),
            auto_scan_on_launch=self._auto_scan.isChecked(),
        )

    def autostart_enabled(self) -> bool:
        return self._start_with_windows.isChecked()
