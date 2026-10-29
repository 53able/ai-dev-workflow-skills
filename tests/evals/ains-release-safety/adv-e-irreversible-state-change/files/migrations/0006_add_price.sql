ALTER TABLE orders ADD COLUMN price INTEGER;
UPDATE orders SET price = legacy_price WHERE id <= 2;
