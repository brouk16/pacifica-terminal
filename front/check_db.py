import sqlite3
import datetime

print("🔍 Проверяю базу данных scanner_history.db...\n")

try:
    # Подключаемся к нашему файлу
    conn = sqlite3.connect("scanner_history.db")
    cursor = conn.cursor()

    # Спрашиваем: сколько всего строк в таблице?
    cursor.execute("SELECT COUNT(*) FROM heatmap")
    count = cursor.fetchone()[0]

    if count == 0:
        print("🪹 База данных пока ПУСТАЯ. Питон еще не успел закрыть ни одной минуты.")
    else:
        print(f"📦 БИНГО! В базе сохранено: {count} минут(ы) истории стакана.")

        # Берем самую свежую запись, чтобы проверить время
        cursor.execute("SELECT t FROM heatmap ORDER BY t DESC LIMIT 1")
        last_t = cursor.fetchone()[0]

        # Переводим миллисекунды в человеческое время
        readable_time = datetime.datetime.fromtimestamp(last_t / 1000).strftime('%H:%M:%S')
        print(f"⏱️ Время последней сохраненной минуты: {readable_time}")

    conn.close()
except sqlite3.OperationalError:
    print("❌ Ошибка: Файл базы данных или таблица не найдены! Скрипт вообще ничего не создал.")
except Exception as e:
    print(f"⚠️ Какая-то другая ошибка: {e}")