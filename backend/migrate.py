import json
import sqlite3
import os

# Указываем пути. Судя по твоему скрину, JSON лежит тут:
JSON_FILE = os.path.join("../front", "public", "liquidations.json")
DB_FILE = "liquidations.db"


def migrate_data():
    if not os.path.exists(JSON_FILE):
        print(f"❌ Файл {JSON_FILE} не найден! Проверь путь.")
        return

    # Подключаемся к базе
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    # На всякий случай создаем таблицу, если main.py еще не запускался
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
                   )
                       )
                   ''')

    print(f"📂 Читаем старые данные из {JSON_FILE}...")
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"⏳ Найдено {len(data)} записей. Начинаем перенос в БД...")

    count = 0
    for event in data:
        try:
            # INSERT OR IGNORE спасет нас от дубликатов
            cursor.execute('''
                           INSERT
                           OR IGNORE INTO liquidations (timestamp, symbol, position, price, amount, total_value)
                VALUES (?, ?, ?, ?, ?, ?)
                           ''', (
                               event.get('timestamp'),
                               event.get('symbol'),
                               event.get('position'),
                               event.get('price', 0),
                               event.get('amount', 0),
                               event.get('total_value', 0)
                           ))

            # rowcount показывает, добавилась ли строка (1) или была пропущена как дубликат (0)
            if cursor.rowcount > 0:
                count += 1
        except Exception as e:
            print(f"⚠️ Ошибка с записью {event.get('symbol')}: {e}")

    # Сохраняем изменения и закрываем базу
    conn.commit()
    conn.close()

    print(f"✅ Готово! Успешно перенесено {count} записей в новую базу {DB_FILE}!")


if __name__ == "__main__":
    migrate_data()