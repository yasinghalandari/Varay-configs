hereimport os
import re
import asyncio
from pathlib import Path
from urllib.parse import quote
from telethon import TelegramClient

CHANNEL = os.environ.get("TG_CHANNEL", "@Spotify_Porteghali")
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]

NAME = os.environ.get("CFG_NAME", "یاسین")
NAME_ENC = quote(NAME, safe="")

STATE_DIR = Path("state")
STATE_DIR.mkdir(parents=True, exist_ok=True)
LAST_ID_FILE = STATE_DIR / "last_id.txt"

OUT_FILE = Path("config.txt")

SCHEMES = r"(?:vmess|vless|trojan|ss|ssr|hysteria|hysteria2|tuic)://"
CFG_RE = re.compile(rf"{SCHEMES}\S+", re.IGNORECASE)

def load_last_id() -> int:
    if LAST_ID_FILE.exists():
        try:
            return int(LAST_ID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            return 0
    return 0

def save_last_id(last_id: int) -> None:
    LAST_ID_FILE.write_text(str(last_id), encoding="utf-8")

def read_existing() -> set[str]:
    if OUT_FILE.exists():
        lines = [l.strip() for l in OUT_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()]
        return {l for l in lines if l}
    return set()

def write_all(configs: list[str]) -> None:
    OUT_FILE.write_text("\n".join(configs) + ("\n" if configs else ""), encoding="utf-8")

def rename_label(url: str) -> str:
    if "#" in url:
        base = url.split("#", 1)[0]
        return f"{base}#{NAME_ENC}"
    return f"{url}#{NAME_ENC}"

async def main():
    session_name = "session/telethon"
    client = TelegramClient(session_name, API_ID, API_HASH)
    await client.start()

    last_id = load_last_id()
    existing = read_existing()

    new_configs = set()
    max_seen_id = last_id

    async for msg in client.iter_messages(CHANNEL, limit=500):
        if msg.id is None:
            continue
        if msg.id <= last_id:
            break

        max_seen_id = max(max_seen_id, msg.id)

        text = msg.message or ""
        for it in CFG_RE.finditer(text):
            new_configs.add(rename_label(it.group(0).strip()))

    if not new_configs:
        print("No new configs found.")
        if max_seen_id > last_id:
            save_last_id(max_seen_id)
        await client.disconnect()
        return

    combined = list(existing.union(new_configs))
    combined.sort()

    write_all(combined)
    save_last_id(max_seen_id)

    print(f"Added {len(new_configs)} new configs. Total: {len(combined)}")
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(main())
