import sqlite3

conn = sqlite3.connect("leads.db")
cursor = conn.cursor()

# cursor.execute("""SELECT 
#     cl.role,
#     cl.content,
#     cl.timestamp
# FROM conversation_logs cl
# JOIN leads l ON cl.session_id = l.session_id
# WHERE l.phone_number = '447710173736'
# ORDER BY cl.timestamp ASC;""")
cursor.execute("select l.mobile, c.id, c.role, c.content from leads l join conversation_logs c on l.session_id = c.session_id")

rows = cursor.fetchall()

for row in rows:
    print(row)

conn.close()