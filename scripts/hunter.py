#!/usr/bin/env python3
"""
Asosin-Project — M3U8 Stream Hunter
Ищет прямые IPTV-потоки через поисковики и проверяет доступность
"""

import asyncio
import aiohttp
import re
import os
import json
import time
import random
import logging
from datetime import datetime, timezone
from urllib.parse import urlparse, quote_plus
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S"
)
log = logging.getLogger("hunter")

# ─── Конфиг ───────────────────────────────────────────────────────────────────

MAX_WORKERS      = 80          # параллельных проверок
CHECK_TIMEOUT    = 8           # сек на один поток
SEARCH_DELAY     = (2, 5)      # пауза между запросами к поисковику
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64; rv:125.0) Gecko/20100101 Firefox/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_4) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15",
]

# Поисковые запросы — ищем прямые m3u8 ссылки
SEARCH_QUERIES = [
    'inurl:m3u8 "live" stream',
    'inurl:.m3u8 IPTV channel',
    'filetype:m3u8 live television',
    '"index.m3u8" live stream',
    '"chunklist.m3u8" OR "playlist.m3u8" live',
    'inurl:m3u8 "russia" OR "russian" channel',
    'inurl:m3u8 sport live',
    'inurl:m3u8 news live',
    '"hls" "m3u8" live channel stream',
    'inurl:/hls/ ".m3u8" live',
    'inurl:m3u8 music tv live',
    '"master.m3u8" OR "stream.m3u8" live',
    'inurl:m3u8 entertainment channel live',
    '"ts_live" OR "live_ts" m3u8 stream',
    'inurl:m3u8 children kids tv live',
    'IPTV m3u8 free stream link',
    'free live tv m3u8 direct link',
    'm3u8 stream url live television channel',
    '"application/x-mpegURL" live stream',
    'HLS stream url m3u8 television',
]

# Поисковики (только те что можно без API)
SEARCH_ENGINES = {
    "Google": "https://www.google.com/search?q={query}&num=20&hl=ru",
    "DuckDuckGo": "https://html.duckduckgo.com/html/?q={query}",
    "Bing": "https://www.bing.com/search?q={query}&count=20&setlang=ru",
    "Yandex": "https://yandex.ru/search/?text={query}&numdoc=20&lr=213",
    "Ecosia": "https://www.ecosia.org/search?q={query}",
    "Mojeek": "https://www.mojeek.com/search?q={query}",
}

# Regex для вытаскивания m3u8 URL из HTML
M3U8_PATTERN = re.compile(
    r'https?://[^\s\'"<>{}|\\\^`\[\]]+\.m3u8(?:\?[^\s\'"<>{}|\\\^`\[\]]*)?',
    re.IGNORECASE
)

PLAYLIST_FILE = "playlist/asosin.m3u"
KNOWN_FILE    = "playlist/known_streams.json"

# ─── Поиск ────────────────────────────────────────────────────────────────────

def random_headers() -> dict:
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
    }


async def search_engine(session: aiohttp.ClientSession, engine: str, url_tpl: str, query: str) -> set[str]:
    """Одиночный запрос к поисковику, возвращает найденные m3u8 URL"""
    found = set()
    url = url_tpl.format(query=quote_plus(query))
    try:
        async with session.get(url, headers=random_headers(), timeout=aiohttp.ClientTimeout(total=15), ssl=False) as resp:
            if resp.status == 200:
                html = await resp.text(errors="ignore")
                found = set(M3U8_PATTERN.findall(html))
                if found:
                    log.info(f"[{engine}] '{query[:40]}' → {len(found)} потенциальных URL")
    except Exception as e:
        log.debug(f"[{engine}] ошибка: {e}")
    return found


async def run_search(session: aiohttp.ClientSession) -> set[str]:
    """Запускает все поисковые запросы по всем движкам"""
    all_urls: set[str] = set()
    tasks = []
    for query in SEARCH_QUERIES:
        for engine, tpl in SEARCH_ENGINES.items():
            tasks.append(search_engine(session, engine, tpl, query))

    log.info(f"Всего задач поиска: {len(tasks)}")
    # Запускаем пачками по 6 чтобы не банили
    chunk = 6
    for i in range(0, len(tasks), chunk):
        results = await asyncio.gather(*tasks[i:i+chunk], return_exceptions=True)
        for r in results:
            if isinstance(r, set):
                all_urls |= r
        await asyncio.sleep(random.uniform(*SEARCH_DELAY))

    log.info(f"Найдено уникальных m3u8 URL: {len(all_urls)}")
    return all_urls

# ─── Проверка доступности ─────────────────────────────────────────────────────

async def check_stream(session: aiohttp.ClientSession, url: str) -> Optional[dict]:
    """Проверяет что URL реально отдаёт HLS-контент"""
    try:
        async with session.get(
            url,
            headers=random_headers(),
            timeout=aiohttp.ClientTimeout(total=CHECK_TIMEOUT),
            ssl=False,
            allow_redirects=True,
        ) as resp:
            if resp.status not in (200, 206):
                return None

            content_type = resp.headers.get("Content-Type", "")
            # Первые 512 байт
            chunk = await resp.content.read(512)
            text = chunk.decode("utf-8", errors="ignore").strip()

            # Валидный HLS плейлист начинается с #EXTM3U
            is_hls = (
                text.startswith("#EXTM3U") or
                "#EXT-X-" in text or
                "application/x-mpegurl" in content_type.lower() or
                "application/vnd.apple.mpegurl" in content_type.lower()
            )
            if not is_hls:
                return None

            # Вытаскиваем название канала если есть
            name = _guess_name(url)
            return {"url": url, "name": name, "checked_at": datetime.now(timezone.utc).isoformat()}

    except Exception:
        return None


def _guess_name(url: str) -> str:
    """Угадывает имя канала из URL"""
    parsed = urlparse(url)
    host = parsed.hostname or "unknown"
    path = parsed.path.split("/")
    # берём значимую часть пути
    parts = [p for p in path if p and p not in ("hls", "live", "stream", "playlist", "index", "master")]
    label = parts[0] if parts else host.split(".")[0]
    return label.upper().replace("-", " ").replace("_", " ")[:32]


async def check_all(urls: set[str]) -> list[dict]:
    """Проверяет все найденные URL параллельно"""
    sem = asyncio.Semaphore(MAX_WORKERS)
    results = []

    connector = aiohttp.TCPConnector(limit=MAX_WORKERS, ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        async def _check(url):
            async with sem:
                return await check_stream(session, url)

        tasks = [_check(u) for u in urls]
        log.info(f"Проверяем {len(tasks)} потоков...")
        done = await asyncio.gather(*tasks)

    results = [r for r in done if r is not None]
    log.info(f"Рабочих потоков: {len(results)}")
    return results

# ─── Сохранение ───────────────────────────────────────────────────────────────

def load_known() -> dict:
    if os.path.exists(KNOWN_FILE):
        try:
            with open(KNOWN_FILE) as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_known(streams: dict):
    os.makedirs(os.path.dirname(KNOWN_FILE), exist_ok=True)
    with open(KNOWN_FILE, "w") as f:
        json.dump(streams, f, ensure_ascii=False, indent=2)


def write_m3u(streams: dict):
    os.makedirs(os.path.dirname(PLAYLIST_FILE), exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "#EXTM3U",
        f'#PLAYLIST: Asosin-Project — IPTV Auto ({len(streams)} каналов, обновлено {now})',
        "",
    ]
    for url, info in sorted(streams.items(), key=lambda x: x[1].get("name", "")):
        name = info.get("name", "UNKNOWN")
        checked = info.get("checked_at", "")[:10]
        lines.append(f'#EXTINF:-1 tvg-name="{name}" group-title="Asosin",{name} [{checked}]')
        lines.append(url)
        lines.append("")

    with open(PLAYLIST_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    log.info(f"Плейлист сохранён: {PLAYLIST_FILE} ({len(streams)} каналов)")


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main():
    start = time.time()
    log.info("═══ Asosin-Project Hunter запущен ═══")

    known = load_known()
    log.info(f"Известно потоков из базы: {len(known)}")

    # 1. Поиск новых URL
    connector = aiohttp.TCPConnector(ssl=False)
    async with aiohttp.ClientSession(connector=connector) as session:
        found_urls = await run_search(session)

    # Убираем уже проверенные (чтобы не тратить время)
    new_urls = found_urls - set(known.keys())
    log.info(f"Новых URL для проверки: {len(new_urls)}")

    # 2. Проверка новых
    if new_urls:
        live_streams = await check_all(new_urls)
        for s in live_streams:
            known[s["url"]] = {"name": s["name"], "checked_at": s["checked_at"], "fails": 0}

    # 3. Перепроверка старых (могли умереть)
    if known:
        log.info(f"Перепроверяем старые {len(known)} потоков...")
        old_live = await check_all(set(known.keys()))
        old_live_urls = {s["url"] for s in old_live}

        dead = []
        for url in list(known.keys()):
            if url not in old_live_urls:
                known[url]["fails"] = known[url].get("fails", 0) + 1
                if known[url]["fails"] >= 3:
                    dead.append(url)
            else:
                known[url]["fails"] = 0
                known[url]["checked_at"] = datetime.now(timezone.utc).isoformat()

        for url in dead:
            log.info(f"Удаляем мёртвый поток: {url}")
            del known[url]

    # 4. Сохранение
    save_known(known)
    write_m3u(known)

    elapsed = time.time() - start
    log.info(f"═══ Готово за {elapsed:.1f}с | Итого каналов: {len(known)} ═══")


if __name__ == "__main__":
    asyncio.run(main())
