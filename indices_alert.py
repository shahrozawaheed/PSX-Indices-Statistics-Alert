import os
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from zoneinfo import ZoneInfo
import time
import json
import hashlib

PSX_URL = "https://dps.psx.com.pk/trading-panel"
SENT_FILE = "sent_indices_alerts.json"

TARGET_INDICES = ["KSE100", "KSE30", "KMI30"]

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}


# --------------------------------------------------
# Basic checks
# --------------------------------------------------

if not DISCORD_WEBHOOK_URL:
    print("DISCORD_WEBHOOK_URL is not set.")
    raise SystemExit(1)


# --------------------------------------------------
# Pakistan date
# --------------------------------------------------

pakistan_time = datetime.now(ZoneInfo("Asia/Karachi"))
today = pakistan_time.date()
today_string = today.isoformat()


# --------------------------------------------------
# Load duplicate-prevention state
# --------------------------------------------------

if os.path.exists(SENT_FILE):
    try:
        with open(SENT_FILE, "r", encoding="utf-8") as file:
            sent_alerts = set(json.load(file))
    except (json.JSONDecodeError, OSError):
        sent_alerts = set()
else:
    sent_alerts = set()


# --------------------------------------------------
# Fetch PSX Trading Panel
# --------------------------------------------------

response = None

for attempt in range(1, 4):
    try:
        response = requests.get(
            PSX_URL,
            headers=HEADERS,
            timeout=30
        )

        print("Attempt:", attempt)
        print("PSX Response Status:", response.status_code)

        if response.status_code == 200:
            break

    except requests.RequestException as error:
        print("Request error:", error)

    time.sleep(5)


if response is None or response.status_code != 200:
    print("Could not fetch PSX Trading Panel.")
    raise SystemExit(1)


# --------------------------------------------------
# Parse HTML
# --------------------------------------------------

soup = BeautifulSoup(response.text, "html.parser")

indices_section = soup.find(
    "div",
    id="tradingPanelIndices"
)

if not indices_section:
    print("Indices Statistics section not found.")
    raise SystemExit(1)


# --------------------------------------------------
# Extract exact PSX displayed values
# --------------------------------------------------

indices = {}

for symbol in TARGET_INDICES:

    panel = indices_section.find(
        "div",
        class_="tabs__panel",
        attrs={"data-name": symbol}
    )

    if not panel:
        print(f"{symbol} panel not found.")
        raise SystemExit(1)

    tbody = panel.find(
        "tbody",
        class_="tbl__body"
    )

    if not tbody:
        print(f"{symbol} table body not found.")
        raise SystemExit(1)

    row = tbody.find("tr")

    if not row:
        print(f"{symbol} row not found.")
        raise SystemExit(1)

    columns = row.find_all("td")

    if len(columns) < 7:
        print(f"{symbol} does not have 7 columns.")
        raise SystemExit(1)

    indices[symbol] = {
        "name": columns[0].get_text(" ", strip=True),
        "current": columns[1].get_text(" ", strip=True),
        "high": columns[2].get_text(" ", strip=True),
        "low": columns[3].get_text(" ", strip=True),
        "change": columns[4].get_text(" ", strip=True),
        "volume": columns[5].get_text(" ", strip=True),
        "value": columns[6].get_text(" ", strip=True),
    }

    # Make sure PSX returned the expected index
    if indices[symbol]["name"] != symbol:
        print(
            f"Unexpected index name for {symbol}: "
            f"{indices[symbol]['name']}"
        )
        raise SystemExit(1)


# --------------------------------------------------
# Duplicate prevention
# --------------------------------------------------

alert_id = hashlib.sha256(
    f"{today_string}|KSE100|KSE30|KMI30".encode("utf-8")
).hexdigest()

if alert_id in sent_alerts:
    print("Indices alert already sent today.")
    raise SystemExit(0)


# --------------------------------------------------
# Build Discord message
# --------------------------------------------------

message_parts = [
    "📊 PSX INDICES STATISTICS",
    f"Date: {today.strftime('%B %d, %Y')}",
    ""
]

for symbol in TARGET_INDICES:

    data = indices[symbol]

    message_parts.extend([
        symbol,
        f"Current Index: {data['current']}",
        f"High: {data['high']}",
        f"Low: {data['low']}",
        f"Change: {data['change']}",
        f"Volume: {data['volume']}",
        f"Value: {data['value']}",
        ""
    ])

message = "\n".join(message_parts).rstrip()


# --------------------------------------------------
# Print message for testing
# --------------------------------------------------

print("\n========== DISCORD MESSAGE ==========\n")
print(message)
print("\n=====================================\n")


# --------------------------------------------------
# Send to Discord
# --------------------------------------------------

discord_response = requests.post(
    DISCORD_WEBHOOK_URL,
    json={"content": message},
    timeout=30
)

print("Discord Response Status:", discord_response.status_code)

if discord_response.status_code in (200, 204):

    sent_alerts.add(alert_id)

    with open(SENT_FILE, "w", encoding="utf-8") as file:
        json.dump(
            sorted(sent_alerts),
            file,
            indent=2
        )

    print("Indices alert sent successfully.")
    print("Duplicate-prevention state saved.")

else:

    print("Discord error:")
    print(discord_response.text)

    raise SystemExit(1)
