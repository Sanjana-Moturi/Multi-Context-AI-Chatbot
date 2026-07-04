import mysql.connector

try:
    db=mysql.connector.connect(
        host="host",
        user="user",
        password="password",
        database="database",
        port=port
    )
    cursor = db.cursor()
    print("Database connected")
except Exception as e:
    print("Database Error:", e)
