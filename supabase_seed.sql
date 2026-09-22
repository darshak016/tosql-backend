-- ============================================================
-- Supabase / PostgreSQL E-Commerce Schema & Sample Data Seed
-- You can copy and paste this script into your Supabase SQL Editor
-- ============================================================

-- Drop tables if re-seeding
DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS customers CASCADE;

-- 1. Customers Table
CREATE TABLE customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(150) NOT NULL UNIQUE,
    country VARCHAR(60) NOT NULL,
    city VARCHAR(60) NOT NULL,
    signup_date DATE NOT NULL DEFAULT CURRENT_DATE
);

-- 2. Products Table
CREATE TABLE products (
    id SERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    category VARCHAR(60) NOT NULL,
    price NUMERIC(10, 2) NOT NULL,
    stock_quantity INTEGER NOT NULL,
    rating NUMERIC(3, 1) DEFAULT 4.5
);

-- 3. Orders Table
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER NOT NULL REFERENCES customers(id) ON DELETE CASCADE,
    order_date DATE NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL,
    status VARCHAR(30) NOT NULL CHECK(status IN ('completed', 'pending', 'cancelled', 'shipped'))
);

-- 4. Order Items Table
CREATE TABLE order_items (
    id SERIAL PRIMARY KEY,
    order_id INTEGER NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
    product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
    quantity INTEGER NOT NULL,
    unit_price NUMERIC(10, 2) NOT NULL
);

-- Seed Customers
INSERT INTO customers (name, email, country, city, signup_date) VALUES
('Alice Johnson', 'alice@example.com', 'USA', 'New York', '2023-01-15'),
('Bob Smith', 'bob@example.com', 'USA', 'San Francisco', '2023-02-20'),
('Carlos Gomez', 'carlos@example.com', 'Mexico', 'Mexico City', '2023-03-10'),
('Diana Prince', 'diana@example.com', 'UK', 'London', '2023-04-05'),
('Elena Rossi', 'elena@example.com', 'Italy', 'Milan', '2023-05-12'),
('Fiona Gallagher', 'fiona@example.com', 'Canada', 'Toronto', '2023-06-18'),
('George Miller', 'george@example.com', 'Australia', 'Sydney', '2023-07-22'),
('Hannah Schmidt', 'hannah@example.com', 'Germany', 'Berlin', '2023-08-01'),
('Ivan Petrov', 'ivan@example.com', 'Estonia', 'Tallinn', '2023-09-14'),
('Jin Woo', 'jin@example.com', 'South Korea', 'Seoul', '2023-10-30'),
('Kavita Rao', 'kavita@example.com', 'India', 'Bangalore', '2023-11-11'),
('Liam O''Connor', 'liam@example.com', 'Ireland', 'Dublin', '2023-12-05');

-- Seed Products
INSERT INTO products (name, category, price, stock_quantity, rating) VALUES
('Ultra Wireless Noise-Cancelling Headphones', 'Electronics', 299.99, 45, 4.8),
('Mechanical RGB Gaming Keyboard', 'Electronics', 129.50, 80, 4.6),
('Ergonomic Mesh Office Chair', 'Furniture', 249.00, 15, 4.7),
('Adjustable Standing Desk', 'Furniture', 499.00, 8, 4.9),
('Ceramic Pour-Over Coffee Dripper', 'Kitchen', 34.99, 120, 4.4),
('Stainless Steel Thermal Water Bottle', 'Kitchen', 24.50, 200, 4.5),
('Organic Cotton Crewneck T-Shirt', 'Apparel', 29.00, 350, 4.3),
('Water-Resistant Commuter Backpack', 'Apparel', 89.99, 60, 4.7),
('Smart 4K Ultra HD Streaming Box', 'Electronics', 69.99, 110, 4.2),
('Cast Iron Pre-Seasoned Skillet', 'Kitchen', 42.00, 95, 4.8);

-- Seed Orders
INSERT INTO orders (customer_id, order_date, total_amount, status) VALUES
(1, '2023-07-15', 599.98, 'completed'),
(2, '2023-08-02', 129.50, 'completed'),
(3, '2023-08-19', 748.00, 'completed'),
(4, '2023-09-05', 499.00, 'completed'),
(1, '2023-09-22', 59.49, 'completed'),
(5, '2023-10-10', 299.99, 'completed'),
(6, '2023-10-28', 114.49, 'shipped'),
(7, '2023-11-04', 378.50, 'completed'),
(8, '2023-11-18', 249.00, 'pending'),
(9, '2023-12-01', 89.99, 'completed'),
(10, '2023-12-14', 42.00, 'completed'),
(11, '2024-01-08', 299.99, 'completed'),
(12, '2024-01-20', 129.50, 'completed'),
(2, '2024-02-05', 499.00, 'completed'),
(3, '2024-02-18', 34.99, 'cancelled');

-- Seed Order Items
INSERT INTO order_items (order_id, product_id, quantity, unit_price) VALUES
(1, 1, 2, 299.99),
(2, 2, 1, 129.50),
(3, 3, 1, 249.00),
(3, 4, 1, 499.00),
(4, 4, 1, 499.00),
(5, 5, 1, 34.99),
(5, 6, 1, 24.50),
(6, 1, 1, 299.99),
(7, 8, 1, 89.99),
(7, 6, 1, 24.50),
(8, 2, 1, 129.50),
(8, 3, 1, 249.00),
(9, 3, 1, 249.00),
(10, 8, 1, 89.99),
(11, 10, 1, 42.00),
(12, 1, 1, 299.99),
(13, 2, 1, 129.50),
(14, 4, 1, 499.00),
(15, 5, 1, 34.99);
