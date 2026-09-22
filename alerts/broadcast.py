"""
alerts/broadcast.py — NEERKAAVAL Multi-Channel Emergency Broadcast
===================================================================
Channels:
  - Telegram      : Bot API via requests
                    Env vars: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
  - Email         : SMTP (Gmail app-password ready)
                    Env vars: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, ALERT_EMAIL
  - Push (ntfy.sh): Free push notification service — no account needed
                    Topic: controlled via NTFY_TOPIC env var (default: neerkaaval_alerts_demo)
                    Subscribe at: https://ntfy.sh/<NTFY_TOPIC>
                    Install app : Android / iOS — search "ntfy"

If env vars are absent, each channel fires in "demo mode" and returns
a status dict with demo=True instead of raising an exception.
"""

from __future__ import annotations
import os
import smtplib
import logging
import requests
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any

logger = logging.getLogger(__name__)

# ── ntfy.sh topic (override with NTFY_TOPIC env var) ────────────────────────
_NTFY_DEFAULT_TOPIC  = "neerkaaval_alerts_demo"
_NTFY_DEFAULT_SERVER = "https://ntfy.sh"


# ---------------------------------------------------------------------------
# Message template
# ---------------------------------------------------------------------------
def _build_message(node: str, peak_depth: float,
                   lat: float, lon: float, time_str: str = "LIVE") -> str:
    return (
        f"🚨 NEERKAAVAL FLOOD ALERT 🚨\n\n"
        f"📍 Location  : {node}\n"
        f"   Coordinates: {lat:.4f}°N, {lon:.4f}°E\n"
        f"🌊 Peak Depth : {peak_depth:.2f} m  (threshold 1.2 m breached)\n"
        f"⏱  Time       : {time_str}\n\n"
        f"⚠️  Immediate civil action required.\n"
        f"   Smart control is OFFLINE or overridden.\n"
        f"   Deploy emergency pumps at Velachery Main drain.\n\n"
        f"— NEERKAAVAL Digital Twin | IIT Madras / AMC"
    )


# ---------------------------------------------------------------------------
# TELEGRAM
# ---------------------------------------------------------------------------
def send_telegram(
    node: str, peak_depth: float, lat: float, lon: float,
    bot_token: str = "", chat_id: str = "",
) -> Dict[str, Any]:
    """Send flood alert via Telegram Bot API."""
    token = bot_token or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    cid   = chat_id  or os.environ.get("TELEGRAM_CHAT_ID",  "")

    if not token or not cid:
        logger.info("Telegram: demo mode (no token/chat_id configured)")
        return {"channel": "telegram", "success": True, "demo": True,
                "message": "Demo mode — set TELEGRAM_BOT_TOKEN & TELEGRAM_CHAT_ID"}

    msg = _build_message(node, peak_depth, lat, lon)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": cid, "text": msg}, timeout=10)
        r.raise_for_status()
        return {"channel": "telegram", "success": True, "demo": False,
                "status_code": r.status_code}
    except Exception as exc:
        logger.error(f"Telegram alert failed: {exc}")
        return {"channel": "telegram", "success": False, "demo": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# EMAIL
# ---------------------------------------------------------------------------
def send_email(
    node: str, peak_depth: float, lat: float, lon: float,
) -> Dict[str, Any]:
    """Send flood alert via SMTP email."""
    host  = os.environ.get("SMTP_HOST",   "smtp.gmail.com")
    port  = int(os.environ.get("SMTP_PORT", "587"))
    user  = os.environ.get("SMTP_USER",   "")
    pwd   = os.environ.get("SMTP_PASS",   "")
    to    = os.environ.get("ALERT_EMAIL", "")

    if not all([host, user, pwd, to]):
        logger.info("Email: demo mode (SMTP env vars not configured)")
        return {"channel": "email", "success": True, "demo": True,
                "message": "Demo mode — set SMTP_HOST, SMTP_USER, SMTP_PASS, ALERT_EMAIL"}

    body = _build_message(node, peak_depth, lat, lon)
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"🚨 NEERKAAVAL FLOOD ALERT — {node} @ {peak_depth:.2f}m"
    msg["From"]    = user
    msg["To"]      = to
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(host, port) as server:
            server.ehlo()
            server.starttls()
            server.login(user, pwd)
            server.sendmail(user, to, msg.as_string())
        logger.info(f"Email sent to {to}")
        return {"channel": "email", "success": True, "demo": False}
    except Exception as exc:
        logger.error(f"Email alert failed: {exc}")
        return {"channel": "email", "success": False, "demo": False, "error": str(exc)}


# ---------------------------------------------------------------------------
# PUSH NOTIFICATION (ntfy.sh)
# ---------------------------------------------------------------------------
def send_push_alert(
    node: str, peak_depth: float, lat: float, lon: float,
) -> Dict[str, Any]:
    """
    Send a push notification via ntfy.sh.

    Recipients subscribe on the free ntfy app (no account needed):
      Android : https://play.google.com/store/apps/details?id=io.heckel.ntfy
      iOS     : https://apps.apple.com/app/ntfy/id1625396347
      Web     : https://ntfy.sh/<your-topic>

    Required env vars:
      NTFY_TOPIC   — the ntfy.sh topic to publish to (default: neerkaaval_alerts_demo)
      NTFY_SERVER  — override the server (default: https://ntfy.sh)
      NTFY_TOKEN   — bearer token for private/access-controlled topics
    """
    topic  = os.environ.get("NTFY_TOPIC",  _NTFY_DEFAULT_TOPIC)
    server = os.environ.get("NTFY_SERVER", _NTFY_DEFAULT_SERVER)
    token  = os.environ.get("NTFY_TOKEN",  "")

    url = server.rstrip("/") + "/" + topic

    message = (
        f"NEERKAAVAL ALERT: {node} has reached {peak_depth:.2f} m!\n"
        f"Coords: {lat:.4f}°N, {lon:.4f}°E\n"
        f"Threshold breached (>1.2 m). Sluice gate activation recommended."
    )

    headers: Dict[str, str] = {
        "Title":        f"FLOOD ALERT: {node}",   # ASCII-safe (no emoji) — emoji OK in body
        "Priority":     "urgent",
        "Tags":         "warning,droplet,rotating_light",
        "Content-Type": "text/plain; charset=utf-8",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"

    try:
        r = requests.post(url, data=message.encode("utf-8"), headers=headers, timeout=10)
        r.raise_for_status()
        resp = r.json() if r.text.strip().startswith("{") else {}
        logger.info(f"Push alert sent: topic={topic} id={resp.get('id', 'n/a')}")
        return {
            "channel":     "push",
            "success":     True,
            "demo":        False,
            "topic":       topic,
            "url":         url,
            "status_code": r.status_code,
            "message_id":  resp.get("id"),
        }
    except Exception as exc:
        logger.error(f"Push alert failed: {exc}")
        return {"channel": "push", "success": False, "demo": False,
                "topic": topic, "url": url, "error": str(exc)}


# ---------------------------------------------------------------------------
# BROADCAST ALL
# ---------------------------------------------------------------------------
def broadcast_all(
    node: str,
    peak_depth: float,
    lat: float  = 12.98,
    lon: float  = 80.22,
    bot_token: str = "",
    chat_id:   str = "",
) -> Dict[str, Dict[str, Any]]:
    """
    Fire all alert channels concurrently: Telegram, Email, ntfy.sh push.

    Returns a dict keyed by channel name with per-channel status dicts:
      results["telegram"] | results["email"] | results["push"]
    """
    import concurrent.futures

    results: Dict[str, Dict[str, Any]] = {}

    def _tg(): return send_telegram(node, peak_depth, lat, lon, bot_token, chat_id)
    def _em(): return send_email(node, peak_depth, lat, lon)
    def _pu(): return send_push_alert(node, peak_depth, lat, lon)

    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as ex:
        futures = {
            "telegram": ex.submit(_tg),
            "email":    ex.submit(_em),
            "push":     ex.submit(_pu),
        }
        for name, fut in futures.items():
            try:
                results[name] = fut.result(timeout=15)
            except Exception as exc:
                results[name] = {"channel": name, "success": False,
                                 "demo": False, "error": str(exc)}

    return results
