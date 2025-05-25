import pandas as pd
import psycopg2

# Railway PostgreSQL credentials
conn = psycopg2.connect(
    dbname="railway",
    user="postgres",
    password="ZWsFoRdyJTKilCpxFEuraYSBNAXPsRww",
    host="trolley.proxy.rlwy.net",
    port="45972"
)

# Your SQL query
query = "SELECT * FROM products_Product;"

# Read into DataFrame
df = pd.read_sql(query, conn)

# Save to CSV
df.to_csv("output.csv", index=False)

print("✅ Data exported successfully!")

conn.close()
