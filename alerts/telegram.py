import requests

def send_flood_alert(token, chat_id, node, depth, time="LIVE"):
    message = (
        f"🚨 *NEERKAAVAL FLOOD ALERT* 🚨\n\n"
        f"📍 *Location:* {node}\n"
        f"🌊 *Depth:* {depth:.2f} meters\n"
        f"⏱️ *Time:* {time}\n\n"
        f"Immediate action required. Smart control offline."
    )
    
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "Markdown"}
    
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Failed to send Telegram alert: {e}")