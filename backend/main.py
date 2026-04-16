import asyncio
import json
import sqlite3
import websockets
import time
import httpx
import requests
import random
from datetime import datetime, timedelta
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# --- НАСТРОЙКИ ---
DB_FILE = "liquidations.db"
BASE_REST = "https://api.pacifica.fi/api/v1"
APP_REST = "https://app.pacifica.fi/api/v1"
WS_URL = "wss://ws.pacifica.fi/ws"
LIQUIDATION_CAUSES = {"market_liquidation", "backstop_liquidation"}

# 🔑 Твой АПИ Ключ
API_KEY = "3SvUyCVAw5EDFJ9NvJGsJn7wU6VcNvCNrzU7w79x8bS27Mr3otSpf9eeX2qFATJBHGi7RE1XxxSicVqzM3oyvCeR"
START_TIME_PACIFICA = 1704067200000

GLOBAL_DATA = {
    "volume_24h": 0,
    "oi": 0,
    "liquidated_24h": 0,
    "volume_all_time": 0,
    "chart_data": [],
    "market_share": [],
    "is_loading_history": False
}


# --- БАЗА ДАННЫХ ---
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS liquidations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, symbol TEXT, position TEXT,
            price REAL, amount REAL, total_value REAL,
            UNIQUE (timestamp, symbol)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_volume (
            timestamp_ms INTEGER PRIMARY KEY,
            volume_usd REAL
        )
    ''')
    conn.commit()
    conn.close()


def save_liquidation_to_db(event):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR IGNORE INTO liquidations (timestamp, symbol, position, price, amount, total_value)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (event['timestamp'], event['symbol'], event['position'], event['price'], event['amount'],
              event['total_value']))
        conn.commit()
        conn.close()
    except Exception:
        pass


def save_volume_to_db(timestamp_ms, volume_usd):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('INSERT OR REPLACE INTO daily_volume (timestamp_ms, volume_usd) VALUES (?, ?)',
                       (timestamp_ms, volume_usd))
        conn.commit()
        conn.close()
    except Exception as e:
        pass


def get_chart_data_from_db():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT timestamp_ms, volume_usd FROM daily_volume ORDER BY timestamp_ms ASC")
        rows = cursor.fetchall()
        conn.close()

        chart_data = []
        vol_all_time = 0
        for r in rows:
            chart_data.append([r[0] / 1000, r[1]])
            vol_all_time += r[1]
        return chart_data, vol_all_time
    except Exception:
        return [], 0


def get_last_db_timestamp():
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(timestamp_ms) FROM daily_volume")
        res = cursor.fetchone()
        conn.close()
        return res[0] if res and res[0] else None
    except Exception:
        return None


# --- УМНЫЙ ПАРСЕР ДАТ (Читает любой формат из БД) ---
def parse_safe_date(ts_val):
    if not ts_val: return None
    ts_str = str(ts_val)
    try:
        if ts_str.replace('.', '', 1).isdigit():
            val = float(ts_str)
            if val > 1e11: val /= 1000  # Если это миллисекунды
            return datetime.fromtimestamp(val)
        return datetime.fromisoformat(ts_str.replace('Z', '+00:00'))
    except:
        return None


# --- КАЛЬКУЛЯТОР СТАТИСТИКИ ЛИКВИДАЦИЙ ---
def calculate_liquidation_stats():
    try:
        conn = sqlite3.connect(DB_FILE)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        # Берем последние 50000 записей (с головой хватит на неделю)
        cursor.execute("SELECT timestamp, total_value, position FROM liquidations ORDER BY id DESC LIMIT 50000")
        rows = cursor.fetchall()
        conn.close()

        now = datetime.now()
        stats = {"1h": 0, "4h": 0, "24h": 0, "7d": 0, "long_24h": 0, "short_24h": 0}

        for r in rows:
            dt = parse_safe_date(r["timestamp"])
            if not dt: continue

            val = float(r["total_value"] or 0)
            pos = str(r["position"]).upper()
            hours_diff = (now - dt).total_seconds() / 3600

            if hours_diff <= 1: stats["1h"] += val
            if hours_diff <= 4: stats["4h"] += val
            if hours_diff <= 24:
                stats["24h"] += val
                if "LONG" in pos: stats["long_24h"] += val
                if "SHORT" in pos: stats["short_24h"] += val
            if hours_diff <= 168: stats["7d"] += val

        return stats
    except Exception as e:
        return {"1h": 0, "4h": 0, "24h": 0, "7d": 0, "long_24h": 0, "short_24h": 0}


# --- FASTAPI ---
app = FastAPI(title="Pacifica Terminal API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"],
                   allow_headers=["*"])


# --- АВТОМАТИЧЕСКИЙ СБОР ИСТОРИИ ---
async def collect_and_save_volume(symbols, start_time, end_time):
    headers = {"Accept": "*/*", "Authorization": f"Bearer {API_KEY}"}
    daily_totals = {}

    async with httpx.AsyncClient() as client:
        for ticker in symbols:
            url = f"{APP_REST}/kline?symbol={ticker}&interval=1d&start_time={start_time}&end_time={end_time}"
            try:
                res = await client.get(url, headers=headers, timeout=15)
                if res.status_code == 200:
                    data = res.json()
                    klines = data.get('data', []) if isinstance(data, dict) else data
                    for candle in klines:
                        try:
                            if isinstance(candle, dict):
                                t = int(candle.get('t', 0))
                                c = float(candle.get('c', 0))
                                v = float(candle.get('v', 0))
                            elif isinstance(candle, list) and len(candle) >= 6:
                                t = int(candle[0])
                                c = float(candle[4])
                                v = float(candle[5])
                            else:
                                continue

                            if t > 0:
                                vol_usd = v * c
                                daily_totals[t] = daily_totals.get(t, 0) + vol_usd
                        except Exception:
                            continue
            except Exception:
                pass
            await asyncio.sleep(4)

    for t, vol in daily_totals.items():
        save_volume_to_db(t, vol)


async def background_sync_task():
    await asyncio.sleep(2)
    GLOBAL_DATA["is_loading_history"] = True
    try:
        headers = {"Accept": "application/json"}
        async with httpx.AsyncClient() as client:
            res_pac = await client.get(f'{BASE_REST}/info/prices', headers=headers, timeout=10)
            symbols = [c.get('symbol') for c in res_pac.json().get('data', []) if c.get('symbol')]

        last_ts = get_last_db_timestamp()
        now_ms = int(time.time() * 1000)

        if not last_ts:
            await collect_and_save_volume(symbols, START_TIME_PACIFICA, now_ms)
        else:
            await collect_and_save_volume(symbols, now_ms - (2 * 24 * 60 * 60 * 1000), now_ms)

        chart, vol_all = get_chart_data_from_db()
        GLOBAL_DATA["chart_data"] = chart
        GLOBAL_DATA["volume_all_time"] = vol_all
    finally:
        GLOBAL_DATA["is_loading_history"] = False


# --- ГЛАВНЫЙ ЭНДПОИНТ ---
@app.get("/api/v1/global-stats")
async def get_global_stats():
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(f'{BASE_REST}/info/prices', timeout=10)
            if res.status_code == 200:
                coins = res.json().get('data', [])
                vol24 = 0;
                oi = 0;
                market_share = []
                for c in coins:
                    v = float(c.get('volume_24h', 0))
                    o = float(c.get('open_interest', 0)) * float(c.get('mark', 0) or 0)
                    vol24 += v;
                    oi += o
                    sym = c.get('symbol', 'UNKNOWN').split('-')[0]
                    market_share.append({"ticker": sym, "rawVolume": v, "rawOi": o})

                GLOBAL_DATA["volume_24h"] = vol24
                GLOBAL_DATA["oi"] = oi
                GLOBAL_DATA["market_share"] = market_share
    except Exception:
        pass

    # 🔥 ТЕПЕРЬ ОН БЕРЕТ ПРАВИЛЬНУЮ СТАТИСТИКУ ЗА 24 ЧАСА ИЗ НАШЕГО КАЛЬКУЛЯТОРА
    try:
        liq_stats = calculate_liquidation_stats()
        GLOBAL_DATA["liquidated_24h"] = liq_stats["24h"]
    except Exception:
        pass

    if not GLOBAL_DATA["chart_data"]:
        chart, vol_all = get_chart_data_from_db()
        GLOBAL_DATA["chart_data"] = chart
        GLOBAL_DATA["volume_all_time"] = vol_all

    return GLOBAL_DATA


# --- 🔥 ИСПРАВЛЕННЫЙ API ЛИКВИДАЦИЙ ---
@app.get("/api/liquidations")
def get_liquidations(limit: int = 50):
    # 1. Достаем 50 последних сделок для таблицы "Live Feed"
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute('SELECT * FROM liquidations ORDER BY id DESC LIMIT ?', (limit,))
    feed = [dict(row) for row in cursor.fetchall()]
    conn.close()

    # 2. Считаем реальную стату за 1H, 4H, 24H, 7D
    stats = calculate_liquidation_stats()

    # Отдаем всё вместе в одном удобном формате
    return {
        "stats": stats,
        "feed": feed
    }


# --- WEBSOCKET И СТАРТ ---
def fetch_markets():
    try:
        response = requests.get(f"{BASE_REST}/info/prices", timeout=10)
        return [m["symbol"] for m in response.json()["data"]]
    except:
        return ["BTC-USD", "ETH-USD"]


async def ws_listener():
    symbols = fetch_markets()
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20) as websocket:
                for i, ticker in enumerate(symbols):
                    await websocket.send(
                        json.dumps({"method": "subscribe", "params": {"source": "trades", "symbol": ticker}}))
                    if i % 15 == 0: await asyncio.sleep(0.05)
                await websocket.send(json.dumps({"method": "subscribe", "params": {"source": "liquidations"}}))

                async for response in websocket:
                    data = json.loads(response)
                    channel = data.get("channel")
                    if channel in ["trades", "liquidations"]:
                        trades = data.get("data", [])
                        if not isinstance(trades, list): trades = [trades]
                        for trade in trades:
                            if trade.get("tc") in LIQUIDATION_CAUSES or channel == "liquidations":
                                price = float(trade.get('p', trade.get('price', 0)))
                                amount = float(trade.get('a', trade.get('amount', 0)))
                                symbol = trade.get('s') or trade.get('symbol')
                                save_liquidation_to_db({
                                    "timestamp": datetime.now().isoformat(),
                                    "symbol": symbol,
                                    "position": "Long" if "long" in str(
                                        trade.get('d', trade.get('side', ''))).lower() else "Short",
                                    "price": price,
                                    "amount": amount,
                                    "total_value": round(price * amount, 2)
                                })
        except Exception:
            await asyncio.sleep(5)


@app.on_event("startup")
async def startup_event():
    init_db()
    asyncio.create_task(ws_listener())
    asyncio.create_task(background_sync_task())


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)