"""Bildirim kanalı — tetiklenen fiyat alarmları için.

Birincil bildirim uygulama içidir (frontend tetiklenen alarmları gösterir).
Ek olarak, ortam değişkenleri ayarlıysa e-posta da gönderir; ayarlı değilse
sessizce yalnızca loglar (gizli bilgi commit'lemeye gerek kalmaz).

Gerekli env (hepsi opsiyonel, e-posta için hepsi gerekli):
    CDT_SMTP_HOST, CDT_SMTP_PORT, CDT_SMTP_USER, CDT_SMTP_PASS, CDT_ALERT_TO
"""
from __future__ import annotations

import logging
import os
import smtplib
from email.message import EmailMessage

log = logging.getLogger(__name__)


def _email_configured() -> bool:
    return all(
        os.environ.get(k)
        for k in ("CDT_SMTP_HOST", "CDT_SMTP_PORT", "CDT_SMTP_USER", "CDT_SMTP_PASS", "CDT_ALERT_TO")
    )


def notify_triggered(alerts: list[dict]) -> None:
    """Tetiklenen alarmlar için bildirim. E-posta ayarlıysa gönderir."""
    if not alerts:
        return
    lines = [
        f"- {a.get('product_url')}: hedef {a.get('target_price')} TL, "
        f"güncel {a.get('triggered_price')} TL"
        for a in alerts
    ]
    body = "Fiyat alarmı tetiklendi:\n" + "\n".join(lines)
    log.info("Alarm bildirimi: %d alarm tetiklendi", len(alerts))

    if not _email_configured():
        return
    try:
        msg = EmailMessage()
        msg["Subject"] = f"Coffee Deal Tracker — {len(alerts)} fiyat alarmı"
        msg["From"] = os.environ["CDT_SMTP_USER"]
        msg["To"] = os.environ["CDT_ALERT_TO"]
        msg.set_content(body)
        with smtplib.SMTP(os.environ["CDT_SMTP_HOST"], int(os.environ["CDT_SMTP_PORT"])) as s:
            s.starttls()
            s.login(os.environ["CDT_SMTP_USER"], os.environ["CDT_SMTP_PASS"])
            s.send_message(msg)
        log.info("Alarm e-postası gönderildi")
    except Exception:
        log.exception("Alarm e-postası gönderilemedi")
