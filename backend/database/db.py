import mysql.connector

try:
    db=mysql.connector.connect(
        host="10.10.14.14",
        user="itdevelopers",
        password="develop@321",
        database="ajaydemo",
        port=3306
    )
    cursor = db.cursor()
    print("Database connected")
except Exception as e:
    print("Database Error:", e)