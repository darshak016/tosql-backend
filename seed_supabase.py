import sys
import os
from sqlalchemy import create_engine, text

def seed_supabase(db_url: str):
    print(f"[*] Connecting to Supabase at: {db_url.split('@')[-1] if '@' in db_url else db_url}...")
    
    # Ensure postgresql:// protocol
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    seed_file = os.path.join(os.path.dirname(__file__), "supabase_seed.sql")
    if not os.path.exists(seed_file):
        print(f"[!] Error: {seed_file} not found.")
        sys.exit(1)

    with open(seed_file, "r", encoding="utf-8") as f:
        sql_script = f.read()

    try:
        engine = create_engine(db_url)
        with engine.connect() as conn:
            # Execute statements
            print("[*] Executing database schema creation and data seeding...")
            statements = [s.strip() for s in sql_script.split(";") if s.strip()]
            for stmt in statements:
                conn.execute(text(stmt))
            conn.commit()
            print("[+] Successfully seeded Supabase with customers, products, orders, and order_items!")
            
            # Verify row counts
            for tbl in ["customers", "products", "orders", "order_items"]:
                count = conn.execute(text(f'SELECT COUNT(*) FROM "{tbl}"')).scalar()
                print(f"    - Table '{tbl}': {count} rows")
            
            print("\n[+] Done! Now open your toSQL app, click 'Connect Database', paste your URI, and query away!")

    except Exception as e:
        print(f"[!] Failed to seed Supabase: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python seed_supabase.py \"postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres\"")
        sys.exit(1)
    
    supabase_url = sys.argv[1]
    seed_supabase(supabase_url)
