"""
tests/test_broadcast.py — NEERKAAVAL Broadcast Alert Test Suite
===============================================================
Tests for alerts/broadcast.py covering:
  - _build_message  : content assertions
  - send_email      : demo mode, SMTP success/failure, MIME body
  - send_push_alert : URL, headers (Priority/Title/Authorization),
                      body content, auth token, error paths
  - send_telegram   : demo mode, URL, payload, failure handling
  - broadcast_all   : all channels present, partial failure isolation,
                      exception capture, kwarg forwarding

Unit tests mock all network/SMTP — no real calls are made.
Live tests are skipped unless BROADCAST_LIVE_TEST=1 is set.

Run unit tests (fast, offline):
    pytest tests/test_broadcast.py -v -m "not live"

Run live integration tests (real HTTP + SMTP):
    $env:BROADCAST_LIVE_TEST=1; pytest tests/test_broadcast.py -v -m live
"""

from __future__ import annotations
import os
import email as email_mod
import smtplib
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from alerts.broadcast import (
    _build_message,
    send_email,
    send_push_alert,
    send_telegram,
    broadcast_all,
)

# ── Shared test constants ─────────────────────────────────────────────────────

NODE  = "Velachery_Main"
DEPTH = 1.85
LAT   = 12.9800
LON   = 80.2200
TOPIC = "neerkaaval_alerts_demo"

LIVE = os.environ.get("BROADCAST_LIVE_TEST", "0") == "1"


# =============================================================================
# _build_message
# =============================================================================

class TestBuildMessage:
    def test_contains_node_name(self):
        assert NODE in _build_message(NODE, DEPTH, LAT, LON)

    def test_contains_formatted_depth(self):
        assert f"{DEPTH:.2f}" in _build_message(NODE, DEPTH, LAT, LON)

    def test_contains_latitude(self):
        assert f"{LAT:.4f}" in _build_message(NODE, DEPTH, LAT, LON)

    def test_contains_longitude(self):
        assert f"{LON:.4f}" in _build_message(NODE, DEPTH, LAT, LON)

    def test_contains_threshold(self):
        assert "1.2" in _build_message(NODE, DEPTH, LAT, LON)

    def test_custom_time_appears(self):
        ts = "2026-09-16 13:00"
        assert ts in _build_message(NODE, DEPTH, LAT, LON, time_str=ts)

    def test_returns_non_empty_string(self):
        msg = _build_message(NODE, DEPTH, LAT, LON)
        assert isinstance(msg, str) and len(msg) > 20


# =============================================================================
# EMAIL
# =============================================================================

class TestSendEmail:
    def test_demo_mode_when_credentials_empty(self):
        env = {"SMTP_HOST": "smtp.example.com", "SMTP_PORT": "587",
               "SMTP_USER": "", "SMTP_PASS": "", "ALERT_EMAIL": ""}
        with patch.dict(os.environ, env, clear=False):
            result = send_email(NODE, DEPTH, LAT, LON)
        assert result["channel"] == "email"
        assert result["demo"]    is True
        assert result["success"] is True

    @patch("smtplib.SMTP")
    def test_sends_successfully(self, mock_smtp_cls):
        mock_server = MagicMock()
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
        mock_smtp_cls.return_value.__exit__  = MagicMock(return_value=False)

        env = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
               "SMTP_USER": "sender@gmail.com", "SMTP_PASS": "apppass",
               "ALERT_EMAIL": "dest@gmail.com"}
        with patch.dict(os.environ, env, clear=False):
            result = send_email(NODE, DEPTH, LAT, LON)

        assert result["channel"] == "email"
        assert result["success"] is True
        assert result["demo"]    is False
        mock_server.sendmail.assert_called_once()

    @patch("smtplib.SMTP")
    def test_returns_failure_on_auth_error(self, mock_smtp_cls):
        mock_smtp_cls.side_effect = smtplib.SMTPAuthenticationError(535, b"Bad credentials")

        env = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
               "SMTP_USER": "bad@gmail.com", "SMTP_PASS": "wrong",
               "ALERT_EMAIL": "dest@gmail.com"}
        with patch.dict(os.environ, env, clear=False):
            result = send_email(NODE, DEPTH, LAT, LON)

        assert result["success"] is False
        assert result["demo"]    is False
        assert "error" in result

    @patch("smtplib.SMTP")
    def test_body_contains_node_and_depth(self, mock_smtp_cls):
        """MIME payload must carry node name and depth after base64 decode."""
        captured = []
        mock_server = MagicMock()
        mock_server.sendmail.side_effect = lambda frm, to, msg: captured.append(msg)
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
        mock_smtp_cls.return_value.__exit__  = MagicMock(return_value=False)

        env = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
               "SMTP_USER": "sender@gmail.com", "SMTP_PASS": "apppass",
               "ALERT_EMAIL": "dest@gmail.com"}
        with patch.dict(os.environ, env, clear=False):
            send_email(NODE, DEPTH, LAT, LON)

        assert len(captured) == 1
        parsed = email_mod.message_from_string(captured[0])
        body = "".join(
            part.get_payload(decode=True).decode("utf-8", errors="ignore")
            for part in parsed.walk()
            if part.get_content_type() == "text/plain"
        )
        assert NODE in body,           "Node name missing from email body"
        assert f"{DEPTH:.2f}" in body, "Depth missing from email body"

    @patch("smtplib.SMTP")
    def test_subject_contains_node(self, mock_smtp_cls):
        """Subject header must include the node name (RFC2047-decoded)."""
        captured = []
        mock_server = MagicMock()
        mock_server.sendmail.side_effect = lambda frm, to, msg: captured.append(msg)
        mock_smtp_cls.return_value.__enter__ = lambda s: mock_server
        mock_smtp_cls.return_value.__exit__  = MagicMock(return_value=False)

        env = {"SMTP_HOST": "smtp.gmail.com", "SMTP_PORT": "587",
               "SMTP_USER": "sender@gmail.com", "SMTP_PASS": "apppass",
               "ALERT_EMAIL": "dest@gmail.com"}
        with patch.dict(os.environ, env, clear=False):
            send_email(NODE, DEPTH, LAT, LON)

        from email.header import decode_header
        parsed = email_mod.message_from_string(captured[0])
        subject = "".join(
            (p.decode(e or "utf-8") if isinstance(p, bytes) else p)
            for p, e in decode_header(parsed["Subject"])
        )
        assert NODE in subject, f"Node not in Subject: {subject}"


# =============================================================================
# PUSH NOTIFICATION (ntfy.sh)  — send_push_alert
# =============================================================================

class TestSendPushAlert:
    @patch("requests.post")
    def test_sends_successfully(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200,
            text='{"id":"abc123","topic":"neerkaaval_alerts_demo"}',
            raise_for_status=MagicMock(),
        )
        result = send_push_alert(NODE, DEPTH, LAT, LON)

        assert result["channel"]     == "push"
        assert result["success"]     is True
        assert result["demo"]        is False
        assert result["status_code"] == 200
        mock_post.assert_called_once()

    @patch("requests.post")
    def test_posts_to_correct_topic_url(self, mock_post):
        """URL must be https://ntfy.sh/<NTFY_TOPIC> by default."""
        mock_post.return_value = MagicMock(
            status_code=200, text="{}", raise_for_status=MagicMock()
        )
        env = {"NTFY_TOPIC": "", "NTFY_SERVER": "https://ntfy.sh", "NTFY_TOKEN": ""}
        with patch.dict(os.environ, env, clear=False):
            os.environ.pop("NTFY_TOPIC", None)
            result = send_push_alert(NODE, DEPTH, LAT, LON)

        call_url = mock_post.call_args.args[0]
        assert call_url == f"https://ntfy.sh/{TOPIC}"
        assert result["topic"] == TOPIC
        assert result["url"]   == f"https://ntfy.sh/{TOPIC}"

    @patch("requests.post")
    def test_priority_is_urgent(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, text="{}", raise_for_status=MagicMock()
        )
        send_push_alert(NODE, DEPTH, LAT, LON)
        headers = mock_post.call_args.kwargs["headers"]
        assert headers.get("Priority") == "urgent"

    @patch("requests.post")
    def test_title_header_contains_node(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, text="{}", raise_for_status=MagicMock()
        )
        send_push_alert(NODE, DEPTH, LAT, LON)
        title = mock_post.call_args.kwargs["headers"].get("Title", "")
        assert NODE in title,             f"Node '{NODE}' not found in Title: '{title}'"
        assert "FLOOD ALERT" in title,    f"'FLOOD ALERT' not found in Title: '{title}'"

    @patch("requests.post")
    def test_body_contains_depth_and_node(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, text="{}", raise_for_status=MagicMock()
        )
        send_push_alert(NODE, DEPTH, LAT, LON)
        raw_body = mock_post.call_args.kwargs["data"].decode("utf-8")
        assert NODE            in raw_body, "Node missing from push body"
        assert f"{DEPTH:.2f}" in raw_body, "Depth missing from push body"

    @patch("requests.post")
    def test_bearer_token_when_ntfy_token_set(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, text="{}", raise_for_status=MagicMock()
        )
        env = {"NTFY_TOPIC": TOPIC, "NTFY_SERVER": "https://ntfy.sh",
               "NTFY_TOKEN": "tk_secret123"}
        with patch.dict(os.environ, env, clear=False):
            send_push_alert(NODE, DEPTH, LAT, LON)

        auth = mock_post.call_args.kwargs["headers"].get("Authorization", "")
        assert auth == "Bearer tk_secret123"

    @patch("requests.post")
    def test_no_auth_header_when_no_token(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, text="{}", raise_for_status=MagicMock()
        )
        env = {"NTFY_TOPIC": TOPIC, "NTFY_SERVER": "https://ntfy.sh", "NTFY_TOKEN": ""}
        with patch.dict(os.environ, env, clear=False):
            send_push_alert(NODE, DEPTH, LAT, LON)

        assert "Authorization" not in mock_post.call_args.kwargs["headers"]

    @patch("requests.post")
    def test_returns_message_id_from_response(self, mock_post):
        mock_response = MagicMock(status_code=200,
                                  text='{"id":"XvNyCDluCDLq","topic":"neerkaaval_alerts_demo"}',
                                  raise_for_status=MagicMock())
        mock_response.json.return_value = {"id": "XvNyCDluCDLq", "topic": TOPIC}
        mock_post.return_value = mock_response

        result = send_push_alert(NODE, DEPTH, LAT, LON)
        assert result["message_id"] == "XvNyCDluCDLq"


    @patch("requests.post")
    def test_returns_failure_on_connection_error(self, mock_post):
        import requests as req_mod
        mock_post.side_effect = req_mod.exceptions.ConnectionError("network down")

        result = send_push_alert(NODE, DEPTH, LAT, LON)
        assert result["channel"] == "push"
        assert result["success"] is False
        assert result["demo"]    is False
        assert "error" in result

    @patch("requests.post")
    def test_custom_server_url(self, mock_post):
        mock_post.return_value = MagicMock(
            status_code=200, text="{}", raise_for_status=MagicMock()
        )
        env = {"NTFY_TOPIC": "alerts", "NTFY_SERVER": "https://my.ntfy.server",
               "NTFY_TOKEN": ""}
        with patch.dict(os.environ, env, clear=False):
            result = send_push_alert(NODE, DEPTH, LAT, LON)

        assert result["url"] == "https://my.ntfy.server/alerts"


# =============================================================================
# TELEGRAM
# =============================================================================

class TestSendTelegram:
    def test_demo_mode_without_token(self):
        env = {"TELEGRAM_BOT_TOKEN": "", "TELEGRAM_CHAT_ID": ""}
        with patch.dict(os.environ, env, clear=False):
            result = send_telegram(NODE, DEPTH, LAT, LON, bot_token="", chat_id="")
        assert result["channel"] == "telegram"
        assert result["demo"]    is True
        assert result["success"] is True

    @patch("requests.post")
    def test_sends_successfully(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())
        result = send_telegram(NODE, DEPTH, LAT, LON,
                               bot_token="FAKE_TOKEN", chat_id="123456789")
        assert result["success"]     is True
        assert result["demo"]        is False
        assert result["status_code"] == 200

    @patch("requests.post")
    def test_posts_to_correct_url(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())
        bot_token = "BOT_XYZ"
        send_telegram(NODE, DEPTH, LAT, LON, bot_token=bot_token, chat_id="999")
        url = mock_post.call_args.args[0]
        assert f"bot{bot_token}/sendMessage" in url

    @patch("requests.post")
    def test_failure_returns_error_dict(self, mock_post):
        import requests as req_mod
        mock_post.side_effect = req_mod.exceptions.ConnectionError("timeout")
        result = send_telegram(NODE, DEPTH, LAT, LON, bot_token="tok", chat_id="999")
        assert result["success"] is False
        assert "error" in result

    @patch("requests.post")
    def test_payload_contains_node_and_depth(self, mock_post):
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=MagicMock())
        send_telegram(NODE, DEPTH, LAT, LON, bot_token="tok", chat_id="999")
        text = mock_post.call_args.kwargs["json"]["text"]
        assert NODE            in text
        assert f"{DEPTH:.2f}" in text


# =============================================================================
# BROADCAST_ALL
# =============================================================================

class TestBroadcastAll:
    @patch("alerts.broadcast.send_push_alert")
    @patch("alerts.broadcast.send_email")
    @patch("alerts.broadcast.send_telegram")
    def test_returns_all_three_channels(self, mock_tg, mock_em, mock_pu):
        mock_tg.return_value = {"channel": "telegram", "success": True,  "demo": True}
        mock_em.return_value = {"channel": "email",    "success": True,  "demo": False}
        mock_pu.return_value = {"channel": "push",     "success": True,  "demo": False}

        results = broadcast_all(NODE, DEPTH, LAT, LON)
        assert set(results.keys()) == {"telegram", "email", "push"}

    @patch("alerts.broadcast.send_push_alert")
    @patch("alerts.broadcast.send_email")
    @patch("alerts.broadcast.send_telegram")
    def test_partial_failure_doesnt_stop_others(self, mock_tg, mock_em, mock_pu):
        mock_tg.return_value = {"channel": "telegram", "success": False, "demo": False}
        mock_em.return_value = {"channel": "email",    "success": True,  "demo": False}
        mock_pu.return_value = {"channel": "push",     "success": True,  "demo": False}

        results = broadcast_all(NODE, DEPTH, LAT, LON)
        assert results["email"]["success"]    is True
        assert results["push"]["success"]     is True
        assert results["telegram"]["success"] is False

    @patch("alerts.broadcast.send_push_alert")
    @patch("alerts.broadcast.send_email")
    @patch("alerts.broadcast.send_telegram")
    def test_channel_exception_captured(self, mock_tg, mock_em, mock_pu):
        """Unhandled exception inside a channel must not propagate to caller."""
        mock_tg.side_effect = RuntimeError("unexpected crash")
        mock_em.return_value = {"channel": "email", "success": True, "demo": False}
        mock_pu.return_value = {"channel": "push",  "success": True, "demo": False}

        results = broadcast_all(NODE, DEPTH, LAT, LON)
        assert "telegram" in results
        assert results["telegram"]["success"] is False

    @patch("alerts.broadcast.send_push_alert")
    @patch("alerts.broadcast.send_email")
    @patch("alerts.broadcast.send_telegram")
    def test_passes_bot_token_and_chat_id(self, mock_tg, mock_em, mock_pu):
        mock_tg.return_value = {"channel": "telegram", "success": True, "demo": False}
        mock_em.return_value = {"channel": "email",    "success": True, "demo": False}
        mock_pu.return_value = {"channel": "push",     "success": True, "demo": False}

        broadcast_all(NODE, DEPTH, LAT, LON, bot_token="TK123", chat_id="CID456")
        mock_tg.assert_called_once_with(NODE, DEPTH, LAT, LON, "TK123", "CID456")

    @patch("alerts.broadcast.send_push_alert")
    @patch("alerts.broadcast.send_email")
    @patch("alerts.broadcast.send_telegram")
    def test_default_coordinates(self, mock_tg, mock_em, mock_pu):
        mock_tg.return_value = {"channel": "telegram", "success": True, "demo": True}
        mock_em.return_value = {"channel": "email",    "success": True, "demo": True}
        mock_pu.return_value = {"channel": "push",     "success": True, "demo": True}

        broadcast_all(NODE, DEPTH)          # lat/lon omitted
        _, args, _ = mock_em.mock_calls[0]
        assert args[2] == 12.98             # default lat
        assert args[3] == 80.22             # default lon


# =============================================================================
# LIVE / INTEGRATION TESTS   (skipped unless BROADCAST_LIVE_TEST=1)
# =============================================================================

@pytest.mark.live
@pytest.mark.skipif(not LIVE, reason="Set BROADCAST_LIVE_TEST=1 to run live tests")
class TestLiveIntegration:
    """
    Real network calls — run with:
        $env:BROADCAST_LIVE_TEST=1; pytest tests/test_broadcast.py -v -m live

    Expected outcomes with current credentials:
      - Email: SUCCESS (Gmail SMTP + app-password)
      - Push:  SUCCESS (public ntfy.sh topic, no auth)
      - Telegram: DEMO (no bot token in env)
    """

    def test_live_email(self):
        result = send_email(NODE, DEPTH, LAT, LON)
        print(f"\nEmail → {result}")
        assert result["channel"] == "email"
        assert result["success"] is True, f"Email failed: {result.get('error')}"

    def test_live_push(self):
        """
        Sends a real push to the topic configured in NTFY_TOPIC env var.
        Open the ntfy app and subscribe to that topic to verify receipt.
        """
        result = send_push_alert(NODE, DEPTH, LAT, LON)
        print(f"\nPush → {result}")
        assert result["channel"]     == "push"
        assert result["success"]     is True, f"Push failed: {result.get('error')}"
        assert result["status_code"] == 200
        print(f"  Check: https://ntfy.sh/{result['topic']}")

    def test_live_telegram_demo(self):
        """Without TELEGRAM_BOT_TOKEN set, must return demo — not an error."""
        result = send_telegram(NODE, DEPTH, LAT, LON)
        print(f"\nTelegram → {result}")
        assert result["channel"] == "telegram"
        assert result["demo"]    is True

    def test_live_broadcast_all(self):
        results = broadcast_all(NODE, DEPTH, LAT, LON)
        print("\n── broadcast_all results ──")
        for ch, r in results.items():
            icon = "✅" if r["success"] else "❌"
            demo = " [DEMO]" if r.get("demo") else ""
            err  = f"  ⚠ {r['error']}" if "error" in r else ""
            print(f"  {icon} {ch}{demo}{err}")

        assert set(results.keys()) == {"telegram", "email", "push"}
        assert results["email"]["success"] is True, \
            f"Email live send failed: {results['email'].get('error')}"
        assert results["push"]["success"]  is True, \
            f"Push live send failed: {results['push'].get('error')}"
