import psycopg2

# Your database connection details
DATABASE_URL = "postgresql://barterex_user:ORdt0qCDzsPf5jDFgQNFQeAZRQrro7nq@dpg-d2rjiujipnbc73d2pskg-a.oregon-postgres.render.com/barterex"

try:
    # Connect to the database
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    
    # Clear the alembic_version table
    cursor.execute("DELETE FROM alembic_version;")
    conn.commit()
    
    print("✅ Migration table cleared successfully!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    
finally:
    if conn:
        cursor.close()
        conn.close()
        print("Database connection closed.")