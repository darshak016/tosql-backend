import os
import sqlite3
from datetime import datetime, timedelta
import random

def seed_ecommerce_db(db_path: str = None):
    if db_path is None:
        db_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(db_dir, "ecommerce.db")

    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Drop existing tables if re-seeding
    cursor.executescript("""
        DROP TABLE IF EXISTS order_items;
        DROP TABLE IF EXISTS orders;
        DROP TABLE IF EXISTS products;
        DROP TABLE IF EXISTS customers;
    """)

    # Create tables
    cursor.executescript("""
        CREATE TABLE customers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            country TEXT NOT NULL,
            city TEXT NOT NULL,
            signup_date DATE NOT NULL
        );

        CREATE TABLE products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            price REAL NOT NULL,
            stock_quantity INTEGER NOT NULL,
            rating REAL DEFAULT 4.5
        );

        CREATE TABLE orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            order_date DATE NOT NULL,
            total_amount REAL NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('completed', 'pending', 'cancelled', 'shipped')),
            FOREIGN KEY (customer_id) REFERENCES customers (id)
        );

        CREATE TABLE order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            unit_price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders (id),
            FOREIGN KEY (product_id) REFERENCES products (id)
        );
    """)

    # Seed Customers
    customers_data = [
        ("Alice Johnson", "alice@example.com", "USA", "New York", "2023-01-15"),
        ("Bob Smith", "bob@example.com", "USA", "San Francisco", "2023-02-20"),
        ("Carlos Gomez", "carlos@example.com", "Mexico", "Mexico City", "2023-03-10"),
        ("Diana Prince", "diana@example.com", "UK", "London", "2023-04-05"),
        ("Elena Rossi", "elena@example.com", "Italy", "Milan", "2023-05-12"),
        ("Fiona Gallagher", "fiona@example.com", "Canada", "Toronto", "2023-06-18"),
        ("George Miller", "george@example.com", "Australia", "Sydney", "2023-07-22"),
        ("Hannah Schmidt", "hannah@example.com", "Germany", "Berlin", "2023-08-01"),
        ("Ivan Petrov", "ivan@example.com", "Estonia", "Tallinn", "2023-09-14"),
        ("Jin Woo", "jin@example.com", "South Korea", "Seoul", "2023-10-30"),
        ("Kavita Rao", "kavita@example.com", "India", "Bangalore", "2023-11-11"),
        ("Liam O'Connor", "liam@example.com", "Ireland", "Dublin", "2023-12-05")
    ]
    cursor.executemany(
        "INSERT INTO customers (name, email, country, city, signup_date) VALUES (?, ?, ?, ?, ?)",
        customers_data
    )

    # Seed Products
    products_data = [
        ("Ultra Wireless Noise-Cancelling Headphones", "Electronics", 299.99, 45, 4.8),
        ("Mechanical RGB Gaming Keyboard", "Electronics", 129.50, 80, 4.6),
        ("Ergonomic Mesh Office Chair", "Furniture", 249.00, 15, 4.7),
        ("Adjustable Standing Desk", "Furniture", 499.00, 8, 4.9),
        ("Ceramic Pour-Over Coffee Dripper", "Kitchen", 34.99, 120, 4.4),
        ("Stainless Steel Thermal Water Bottle", "Kitchen", 24.50, 200, 4.5),
        ("Organic Cotton Crewneck T-Shirt", "Apparel", 29.00, 350, 4.3),
        ("Water-Resistant Commuter Backpack", "Apparel", 89.99, 60, 4.7),
        ("Smart 4K Ultra HD Streaming Box", "Electronics", 69.99, 110, 4.2),
        ("Cast Iron Pre-Seasoned Skillet", "Kitchen", 42.00, 95, 4.8)
    ]
    cursor.executemany(
        "INSERT INTO products (name, category, price, stock_quantity, rating) VALUES (?, ?, ?, ?, ?)",
        products_data
    )

    # Seed Orders & Order Items
    statuses = ['completed', 'completed', 'completed', 'pending', 'shipped', 'cancelled']
    start_date = datetime(2023, 6, 1)
    
    order_id = 1
    orders_rows = []
    items_rows = []

    random.seed(42) # Deterministic data for consistent testing

    for _ in range(50):
        cust_id = random.randint(1, len(customers_data))
        days_offset = random.randint(0, 365)
        ord_date = (start_date + timedelta(days=days_offset)).strftime("%Y-%m-%d")
        status = random.choice(statuses)

        # 1 to 4 items per order
        num_items = random.randint(1, 4)
        selected_prods = random.sample(range(1, len(products_data) + 1), num_items)
        
        order_total = 0.0
        order_items_temp = []
        for prod_id in selected_prods:
            prod_price = products_data[prod_id - 1][2]
            qty = random.randint(1, 3)
            subtotal = prod_price * qty
            order_total += subtotal
            order_items_temp.append((order_id, prod_id, qty, prod_price))

        orders_rows.append((cust_id, ord_date, round(order_total, 2), status))
        items_rows.extend(order_items_temp)
        order_id += 1

    cursor.executemany(
        "INSERT INTO orders (customer_id, order_date, total_amount, status) VALUES (?, ?, ?, ?)",
        orders_rows
    )
    cursor.executemany(
        "INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES (?, ?, ?, ?)",
        items_rows
    )

    conn.commit()
    conn.close()
    return db_path

if __name__ == "__main__":
    path = seed_ecommerce_db()
    print(f"Sample database seeded successfully at {path}")
