import sqlite3

# Connect to your database
conn = sqlite3.connect("attendance.db")
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(students)")
for row in cursor.fetchall():
    print(row)

# Show all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
print("Tables:", cursor.fetchall())

# Show all users
cursor.execute("SELECT * FROM users;")
print("Users:", cursor.fetchall())

# Show all marks
cursor.execute("SELECT * FROM marks;")
print("Marks:", cursor.fetchall())

# Show all attendance
cursor.execute("SELECT * FROM attendance;")
print("Attendance:", cursor.fetchall())

conn.close()
