"""Kaçırılan günlük taramanın telafisi — karar fonksiyonu."""
from datetime import datetime

from backend.scheduler import is_scan_due

D = datetime(2026, 11, 6)


def at(h, m=0, day=6):
    return D.replace(day=day, hour=h, minute=m)


def test_pc_opened_after_schedule_without_scan_today():
    # 10:00 kaçtı, PC 14:30'da açıldı, son tarama dün → tara
    assert is_scan_due(at(14, 30), "10:00", at(10, 2, day=5))


def test_already_scanned_today():
    assert not is_scan_due(at(14, 30), "10:00", at(10, 3))


def test_manual_scan_after_schedule_counts():
    assert not is_scan_due(at(18), "10:00", at(12, 15))


def test_before_schedule_time_waits():
    # sabah 08:00'de açıldı; dünkü tarama var, saat daha gelmedi
    assert not is_scan_due(at(8), "10:00", at(10, 1, day=5))


def test_scan_earlier_today_before_schedule_does_not_count():
    # 07:00'de elle taranmış; 10:00 hedefi yine de geçerli
    assert is_scan_due(at(11), "10:00", at(7))


def test_empty_db():
    assert is_scan_due(at(11), "10:00", None)
