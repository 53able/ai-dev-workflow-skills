-- legacy_price を price に写して、旧列を消す
UPDATE orders SET price = legacy_price WHERE price IS NULL;
ALTER TABLE orders DROP COLUMN legacy_price;
