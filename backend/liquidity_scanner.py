import asyncio
import json
import websockets
import time
import requests
import sqlite3
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# 🔥 ЛОКАЛЬНЫЙ ПУТЬ ДЛЯ БАЗЫ
DB_PATH = "scanner_history.db"

SCANNER_HISTORY = []
MAX_HEATMAP_POINTS = 5000

TIMEFRAMES = ["1m", "5m", "1h", "1d"]
CANDLE_HISTORY = {tf: {} for tf in TIMEFRAMES}
MAX_CANDLES = 3000

WS_URL = "wss://ws.pacifica.fi/ws"


def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS heatmap
                      (t INTEGER PRIMARY KEY, bids TEXT, asks TEXT)''')
    conn.commit()
    conn.close()
    print(f"🗄️ База данных готова (локально): {DB_PATH}")


def load_history_from_db():
    global SCANNER_HISTORY
    try:
        if not os.path.exists(DB_PATH): return
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT t, bids, asks FROM heatmap ORDER BY t DESC LIMIT ?", (MAX_HEATMAP_POINTS,))
        rows = cursor.fetchall()
        SCANNER_HISTORY = [{"t": r[0], "bids": json.loads(r[1]), "asks": json.loads(r[2])} for r in reversed(rows)]
        conn.close()
        print(f"✅ Загружено {len(SCANNER_HISTORY)} минут истории стакана!")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки из БД: {e}")


def save_snapshot_to_db(snapshot):
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO heatmap (t, bids, asks) VALUES (?, ?, ?)",
                       (snapshot["t"], json.dumps(snapshot["bids"]), json.dumps(snapshot["asks"])))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"⚠️ Ошибка сохранения: {e}")


def fetch_pacifica_history(interval="1m", limit=1000):
    try:
        end_time = int(time.time() * 1000)
        interval_ms_map = {"1m": 60000, "5m": 300000, "1h": 3600000, "1d": 86400000}
        ms_per_candle = interval_ms_map.get(interval, 60000)
        start_time = end_time - (limit * ms_per_candle)

        url = f"https://api.pacifica.fi/api/v1/kline?symbol=BTC&interval={interval}&start_time={start_time}&end_time={end_time}&limit={limit}"
        response = requests.get(url)

        if response.status_code == 200:
            data = response.json().get("data", [])
            for kline in data:
                t = int(kline.get("t", 0))
                if t != 0:
                    CANDLE_HISTORY[interval][t] = {
                        "t": t, "o": float(kline.get("o", 0)), "h": float(kline.get("h", 0)),
                        "l": float(kline.get("l", 0)), "c": float(kline.get("c", 0))
                    }
            print(f"✅ История свечей {interval} загружена")
    except Exception as e:
        print(f"⚠️ Ошибка загрузки свечей {interval}: {e}")


async def run_scanner():
    global SCANNER_HISTORY, CANDLE_HISTORY
    while True:
        try:
            print("🌊 Подключаюсь к Pacifica WS...")
            async with websockets.connect(WS_URL) as ws:
                await ws.send(
                    json.dumps({"method": "subscribe", "params": {"source": "book", "symbol": "BTC", "agg_level": 10}}))
                for tf in TIMEFRAMES:
                    await ws.send(json.dumps(
                        {"method": "subscribe", "params": {"source": "candle", "symbol": "BTC", "interval": tf}}))

                async for message in ws:
                    data = json.loads(message)
                    if "error" in data:
                        continue

                    channel = data.get("channel", "")

                    if channel == "book":
                        order_levels = data.get("data", {}).get("l", [[], []])
                        bids = order_levels[0][:300] if len(order_levels) > 0 else []
                        asks = order_levels[1][:300] if len(order_levels) > 1 else []
                        if not bids and not asks: continue

                        current_minute_ts = int(time.time() / 60) * 60000
                        snapshot = {
                            "t": current_minute_ts,
                            "bids": [[float(i['p']), float(i['a'])] for i in bids],
                            "asks": [[float(i['p']), float(i['a'])] for i in asks]
                        }

                        if not SCANNER_HISTORY or current_minute_ts > SCANNER_HISTORY[-1]["t"]:
                            if SCANNER_HISTORY:
                                save_snapshot_to_db(SCANNER_HISTORY[-1])
                                print(f"💾 Минута закрыта. Сохранено в БД (Уровней: {len(bids) + len(asks)})")

                            SCANNER_HISTORY.append(snapshot)
                            if len(SCANNER_HISTORY) > MAX_HEATMAP_POINTS: SCANNER_HISTORY.pop(0)
                        else:
                            SCANNER_HISTORY[-1] = snapshot

                    elif "candle" in channel:
                        c_data = data.get("data", {})
                        tf_id = c_data.get("i")
                        if tf_id in CANDLE_HISTORY:
                            CANDLE_HISTORY[tf_id][c_data["t"]] = c_data

        except Exception as e:
            print(f"🔄 Реконнект через 5 сек... {e}")
            await asyncio.sleep(5)


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("🚀 Запуск ядра ликвидности...")
    init_db()
    load_history_from_db()
    for tf in TIMEFRAMES:
        fetch_pacifica_history(tf, 1000)

    task = asyncio.create_task(run_scanner())
    yield
    task.cancel()


app = FastAPI(title="Liquidity Scanner Engine", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# 🔥 ВОТ ЭТОТ ЭНДПОИНТ ТЫ СЛУЧАЙНО УДАЛИЛ! ОН ОБЯЗАН ТУТ БЫТЬ:
@app.get("/api/scanner/data")
async def get_scanner_data():
    return {
        "heatmap": SCANNER_HISTORY,
        "candles": {tf: list(CANDLE_HISTORY[tf].values()) for tf in TIMEFRAMES}
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8001)