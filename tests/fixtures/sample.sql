CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE orders (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) REFERENCES users(id),
    total DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE FUNCTION get_user_orders(p_user_id VARCHAR(36))
RETURNS TABLE AS $$
    SELECT * FROM orders WHERE user_id = p_user_id;
$$ LANGUAGE SQL;

SELECT * FROM users WHERE id = '123';
INSERT INTO users (id, name) VALUES ('1', 'Alice');
