import os
import re
import asyncio
from pathlib import Path
from urllib.parse import quote, urlsplit

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

# --- تنظیمات تست TCP ---
TCP_TIMEOUT_SEC = float(os.environ.get("TCP_TIMEOUT_SEC", "1.5"))
TCP_CONCURRENCY = int(os.environ.get("TCP_CONCURRENCY", "80"))

def load_last_id() -> int:
    if LAST_ID_FILE.exists():
        try:
            return int(LAST_ID_FILE.read_text(encoding="utf-8").strip())
        except Exception:
            return 0
    return 0

def save_last_id(last_id: int) -> None:
    LAST_ID_FILE.write_text(str(last_id), encoding="utf-8")

def read_existing_preserve_order() -> list[str]:
    """فایل قبلی رو می‌خونه (همون ترتیبی که هست)."""
    if OUT_FILE.exists():
        lines = [l.strip() for l in OUT_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()]
        return [l for l in lines if l]
    return []

def rename_label(url: str) -> str:
    if "#" in url:
        base = url.split("#", 1)[0]
        return f"{base}#{NAME_ENC}"
    return f"{url}#{NAME_ENC}"

def parse_host_port(url: str):
    """
    برای vless/trojan/ss/... که ساختار user@host:port دارن معمولاً جواب می‌ده.
    vmess:// base64 است و اینجا host/port قابل استخراج نیست -> از تست حذف می‌شود.
    """
    try:
        sp = urlsplit(url)
        # urlsplit برای scheme://netloc کار می‌کند. netloc ممکنه userinfo@host:port باشد.
        netloc = sp.netloc
        if not netloc:
            return None

        # حذف userinfo
        if "@" in netloc:
            netloc = netloc.split("@", 1)[1]

        # IPv6 با [] هم ممکنه
        if netloc.startswith("["):
            host = netloc.split("]")[0].strip("[]")
            rest = netloc.split("]")[1]
            port = int(rest.lstrip(":")) if rest.startswith("]:") or rest.startswith(":") else None
        else:
            if ":" not in netloc:
                return None
            host, port_s = netloc.rsplit(":", 1)
            port = int(port_s)

        if not host or not port:
            return None
        return host, port
    except Exception:
        return None

async def tcp_check(host: str, port: int, timeout: float) -> bool:
    try:
        fut = asyncio.open_connection(host, port)
        reader, writer = await asyncio.wait_for(fut, timeout=timeout)
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass
        return True
    except Exception:
        return False

async def filter_by_tcp(configs: list[str]) -> list[str]:
    """
    فقط کانفیگ‌هایی که host/port قابل استخراج دارن و TCP connect می‌شن رو نگه می‌داره.
    vmess:// چون host/portش base64ه، اینجا تست نمی‌خوره و حذف میشه.
    """
    sem = asyncio.Semaphore(TCP_CONCURRENCY)

    async def one(cfg: str):
        hp = parse_host_port(cfg)
        if not hp:
            return None  # تست‌پذیر نیست
        host, port = hp
        async with sem:
            ok = await tcp_check(host, port, TCP_TIMEOUT_SEC)
        return cfg if ok else None

    results = await asyncio.gather(*(one(c) for c in configs))
    return [r for r in results if r]

async def main():
    session_name = "session/telethon"
    client = TelegramClient(session_name, API_ID, API_HASH)
    await client.start()

    last_id = load_last_id()
    existing_list = read_existing_preserve_order()
    existing_set = set(existing_list)

    # اینجا “جدیدترین‌ها” رو نگه می‌داریم (به ترتیب زمان از جدید به قدیم)
    new_list = []
    max_seen_id = last_id

    async for msg in client.iter_messages(CHANNEL, limit=500):
        if msg.id is None:
            continue
        if msg.id <= last_id:
            break

        max_seen_id = max(max_seen_id, msg.id)
        text = msg.message or ""

        for it in CFG_RE.finditer(text):
            found = rename_label(it.group(0).strip())
            if found not in existing_set:
                # چون iter_messages از جدید به قدیم میاد، این ترتیب حفظ میشه
                new_list.append(found)
                existing_set.add(found)

    await client.disconnect()

    if max_seen_id > last_id:
        save_last_id(max_seen_id)

    if not new_list:
        print("No new configs found.")
        return

    # فقط کانفیگ‌های جدید رو تست می‌کنیم (سریع‌تر)
    tested_new = await filter_by_tcp(new_list)

    if not tested_new:
        print("New configs found, but none passed TCP check.")
        return

    # خروجی: جدیدها اول، بعد قبلی‌ها (بدون تکرار)
    # (قبلی‌ها همون ترتیبی که قبلاً بوده می‌مونه)
    final = tested_new + [c for c in existing_list if c not in set(tested_new)]

    OUT_FILE.write_text("\n".join(final) + "\n", encoding="utf-8")
    print(f"New: {len(new_list)} | Passed TCP: {len(tested_new)} | Total: {len(final)}")

if __name__ == "__main__":
    asyncio.run(main())
