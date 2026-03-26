import asyncio
import json
import requests
import sqlite3
import websockets
from datetime import datetime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

# ==========================================
# 1. НАСТРОЙКИ И БАЗА ДАННЫХ
# ==========================================
DB_FILE = "liquidations.db"
BASE_REST = "https://api.pacifica.fi/api/v1"
WS_URL = "wss://ws.pacifica.fi/ws"
LIQUIDATION_CAUSES = {"market_liquidation", "backstop_liquidation"}


# Инициализация SQLite базы данных
def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
                   CREATE TABLE IF NOT EXISTS liquidations
                   (
                       id
                       INTEGER
                       PRIMARY
                       KEY
                       AUTOINCREMENT,
                       timestamp
                       TEXT,
                       symbol
                       TEXT,
                       position
                       TEXT,
                       price
                       REAL,
                       amount
                       REAL,
                       total_value
                       REAL,
                       UNIQUE
                   (
                       timestamp,
                       symbol
                   ) -- Защита от дубликатов на уровне БД!
                       )
                   ''')
    conn.commit()
    conn.close()
    print("🗄️ База данных SQLite готова!")


# Сохранение одной ликвидации в БД
def save_to_db(event):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT
                       OR IGNORE INTO liquidations (timestamp, symbol, position, price, amount, total_value)
            VALUES (?, ?, ?, ?, ?, ?)
                       ''', (event['timestamp'], event['symbol'], event['position'], event['price'], event['amount'],
                             event['total_value']))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")


# ==========================================
# 2. FASTAPI СЕРВЕР
# ==========================================
app = FastAPI(title="Pacifica Terminal API")

# Разрешаем фронтенду (React) обращаться к нашему API (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # В рабочей версии тут будет адрес твоего сайта
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Эндпоинт, который будет отдавать данные твоему React-приложению
@app.get("/api/liquidations")
def get_liquidations(limit: int = 5000):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row  # Чтобы получать данные как словари
    cursor = conn.cursor()

    # Берем самые свежие записи из БД
    cursor.execute(
        'SELECT timestamp, symbol, position, price, amount, total_value FROM liquidations ORDER BY timestamp DESC LIMIT ?',
        (limit,))
    rows = cursor.fetchall()
    conn.close()

    # Превращаем строки из БД в обычный JSON
    return [dict(row) for row in rows]


# ==========================================
# 3. ФОНОВЫЙ WEBSOCKET ПАРСЕР
# ==========================================
def fetch_markets() -> list[str]:
    try:
        response = requests.get(f"{BASE_REST}/info", timeout=10)
        symbols = [market["symbol"] for market in response.json()["data"]]
        print(f"✅ Загружено маркетов: {len(symbols)}")
        return symbols
    except:
        return ["BTC", "ETH", "SOL"]


async def ws_listener():
    symbols = fetch_markets()

    while True:
        try:
            print(f"🔄 Подключение к WS: {WS_URL}")
            async with websockets.connect(WS_URL, ping_interval=20) as websocket:
                print(f"📡 Подписка на {len(symbols)} маркетов...")

                for i, ticker in enumerate(symbols):
                    await websocket.send(
                        json.dumps({"method": "subscribe", "params": {"source": "trades", "symbol": ticker}}))
                    if i % 15 == 0: await asyncio.sleep(0.05)

                await websocket.send(json.dumps({"method": "subscribe", "params": {"source": "liquidations"}}))
                print("🚀 РЛС запущен. Данные летят прямо в БД.")

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

                                liq_event = {
                                    "timestamp": datetime.now().isoformat(),
                                    "symbol": symbol,
                                    "position": "Long" if "long" in str(
                                        trade.get('d', trade.get('side', ''))).lower() else "Short",
                                    "price": price,
                                    "amount": amount,
                                    "total_value": round(price * amount, 2)
                                }

                                # Отправляем ликвидацию в базу данных
                                save_to_db(liq_event)
                                print(f"🚨 ЛИКВИДАЦИЯ! {symbol} на ${liq_event['total_value']} -> Сохранено в БД")

        except Exception as e:
            print(f"⚠️ WS Error: {e}. Реконнект через 5 сек...")
            await asyncio.sleep(5)


# ==========================================
# 4. ЗАПУСК ВСЕГО ВМЕСТЕ
# ==========================================
@app.on_event("startup")
async def startup_event():
    init_db()
    # Запускаем парсер как фоновую задачу, чтобы он не мешал API отвечать на запросы
    asyncio.create_task(ws_listener())


if __name__ == "__main__":
    # Запускаем сервер на порту 8000
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)