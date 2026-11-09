
from db import get_connection

try:
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT 'Connection successful' FROM dual")
    print(cursor.fetchone()[0])

    cursor.close()
    conn.close()

except Exception as e:
    print("Connection failed:", e)
