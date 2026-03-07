-- Schema Creation
CREATE SCHEMA raw;

CREATE TABLE raw.customers (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(100),
    signup_date DATE DEFAULT CURRENT_DATE
);

CREATE TABLE raw.orders (
    id SERIAL PRIMARY KEY,
    customer_id INTEGER REFERENCES raw.customers(id),
    order_date DATE DEFAULT CURRENT_DATE,
    status VARCHAR(20),
    amount NUMERIC(10, 2)
);

-- Seed Data
INSERT INTO raw.customers (name, email) VALUES
('Alice Smith', 'alice@example.com'),
('Bob Jones', 'bob@example.com'),
('Charlie Brown', 'charlie@example.com'),
('Diana Prince', 'diana@example.com'),
('Evan Wright', 'evan@example.com');

INSERT INTO raw.orders (customer_id, order_date, status, amount) VALUES
(1, '2024-01-01', 'completed', 150.00),
(1, '2024-01-15', 'completed', 50.50),
(2, '2024-01-05', 'pending', 1200.00),
(3, '2024-02-01', 'returned', 45.00),
(4, '2024-02-10', 'completed', 300.00),
(5, '2024-02-12', 'cancelled', 0.00),
(1, '2024-03-01', 'completed', 85.00),
(2, '2024-03-05', 'completed', 250.00);
