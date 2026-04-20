-- ==============================================================================
-- SMART QUERY ASSISTANT - Complete Database Setup
-- Text2SQL Agent with Long-Term Memory - Production Ready Schema
-- ==============================================================================
--
-- This script creates a complete database environment for the Smart Query Assistant
-- including business data tables and memory system infrastructure.
--
-- Features:
-- ✅ Business data: Customers and orders (ecommerce)
-- ✅ Memory system: User-specific long-term memory storage
-- ✅ Vector embeddings: pgvector support for semantic search
-- ✅ Sample data: Realistic test data for immediate use
-- ✅ Production ready: Proper indexes and constraints
--
-- Usage:
--   psql -h localhost -U postgres -d your_database -f test_db_setup.sql
--
-- Requirements:
--   - PostgreSQL 12+
--   - pgvector extension available
-- ==============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Clean up existing tables (for fresh setup)
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS customers CASCADE;
DROP TABLE IF EXISTS properties CASCADE;
DROP TABLE IF EXISTS loan_applications CASCADE;
DROP TABLE IF EXISTS memories CASCADE;
DROP TABLE IF EXISTS conversation_summaries CASCADE;
DROP TABLE IF EXISTS recent_messages CASCADE;

-- ==============================================================================
-- BUSINESS DATA TABLES
-- Core tables for ecommerce customer & order demonstration
-- ==============================================================================

-- -----------------------------------------------------------------------------
-- CUSTOMERS - Perfect for demonstrating PREFERENCES, ENTITIES and TERMINOLOGY
-- -----------------------------------------------------------------------------
CREATE TABLE customers (
    customer_id   SERIAL PRIMARY KEY,
    name          VARCHAR(100) NOT NULL,
    email         VARCHAR(150) UNIQUE NOT NULL,
    city          VARCHAR(80),
    country       VARCHAR(80),
    segment       VARCHAR(20) NOT NULL CHECK (segment IN ('retail', 'wholesale')),
    registered_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE  customers IS 'Ecommerce customer records with segment and registration date';
COMMENT ON COLUMN customers.segment IS 'Customer segment: retail or wholesale';
COMMENT ON COLUMN customers.registered_at IS 'Timestamp when the customer first registered';

-- -----------------------------------------------------------------------------
-- ORDERS - Perfect for demonstrating METRICS and PREFERENCES
-- -----------------------------------------------------------------------------
CREATE TABLE orders (
    order_id       SERIAL PRIMARY KEY,
    customer_id    INTEGER NOT NULL REFERENCES customers(customer_id),
    status         VARCHAR(20) NOT NULL CHECK (status IN ('pending', 'shipped', 'delivered', 'cancelled')),
    order_date     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    total_amount   DECIMAL(12, 2) NOT NULL,
    payment_method VARCHAR(20) NOT NULL CHECK (payment_method IN ('credit_card', 'upi', 'netbanking', 'cod'))
);

COMMENT ON TABLE  orders IS 'Ecommerce orders linked to customers with status, amount, and payment method';
COMMENT ON COLUMN orders.status IS 'Order lifecycle: pending, shipped, delivered, cancelled';
COMMENT ON COLUMN orders.payment_method IS 'Payment channel: credit_card, upi, netbanking, cod';
COMMENT ON COLUMN orders.total_amount IS 'Final order total in base currency';

-- ==============================================================================
-- MEMORY SYSTEM TABLES
-- Long-term memory infrastructure for personalized AI interactions
-- ==============================================================================

-- -----------------------------------------------------------------------------
-- MEMORIES - Core memory storage with vector embeddings
-- -----------------------------------------------------------------------------
CREATE TABLE memories (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    content TEXT NOT NULL,
    created_at FLOAT NOT NULL,
    source TEXT,
    metadata JSONB DEFAULT '{}'::JSONB,
    embedding VECTOR(384)  -- For sentence-transformers all-MiniLM-L6-v2
);

COMMENT ON TABLE memories IS 'User-specific memories with vector embeddings for semantic search';
COMMENT ON COLUMN memories.user_id IS 'Unique identifier for user isolation';
COMMENT ON COLUMN memories.content IS 'Memory content with category tags: [PREFERENCE], [TERM], [METRIC], [ENTITY]';
COMMENT ON COLUMN memories.embedding IS '384-dimensional vector embedding for similarity search';
COMMENT ON COLUMN memories.metadata IS 'Additional metadata like memory type, confidence, etc.';

-- -----------------------------------------------------------------------------
-- CONVERSATION SUMMARIES - Compressed conversation history
-- -----------------------------------------------------------------------------
CREATE TABLE conversation_summaries (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    summary TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE conversation_summaries IS 'Compressed conversation history for long-term context';

-- -----------------------------------------------------------------------------
-- RECENT MESSAGES - Rolling window of recent interactions
-- -----------------------------------------------------------------------------
CREATE TABLE recent_messages (
    id SERIAL PRIMARY KEY,
    user_id TEXT NOT NULL,
    messages TEXT NOT NULL,  -- Note: 'messages' not 'message' (matches Python code)
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE recent_messages IS 'Recent message history for immediate context (rolling window)';

-- ==============================================================================
-- INDEXES FOR PERFORMANCE
-- ==============================================================================

-- Business Data Indexes
CREATE INDEX idx_customers_segment  ON customers(segment);
CREATE INDEX idx_customers_country  ON customers(country);
CREATE INDEX idx_customers_city     ON customers(city);
CREATE INDEX idx_customers_reg_at   ON customers(registered_at);

CREATE INDEX idx_orders_customer_id ON orders(customer_id);
CREATE INDEX idx_orders_status      ON orders(status);
CREATE INDEX idx_orders_date        ON orders(order_date);
CREATE INDEX idx_orders_amount      ON orders(total_amount);
CREATE INDEX idx_orders_payment     ON orders(payment_method);

-- Memory System Indexes (Critical for Performance)
CREATE INDEX idx_memories_user_id    ON memories(user_id);
CREATE INDEX idx_memories_created_at ON memories(created_at);

-- HNSW Vector Index for Fast Similarity Search
CREATE INDEX memories_embedding_idx ON memories USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

CREATE INDEX idx_summaries_user_id ON conversation_summaries(user_id);
CREATE INDEX idx_summaries_updated ON conversation_summaries(updated_at);

CREATE INDEX idx_messages_user_id ON recent_messages(user_id);
CREATE INDEX idx_messages_created ON recent_messages(created_at);

-- ==============================================================================
-- SAMPLE DATA - Realistic Test Data for Memory Demonstration
-- ==============================================================================

-- -----------------------------------------------------------------------------
-- Sample Customers (~30 rows, diverse cities / countries / segments)
-- -----------------------------------------------------------------------------
INSERT INTO customers (name, email, city, country, segment, registered_at) VALUES
('Aarav Sharma',       'aarav.sharma@example.com',    'Mumbai',        'India',        'retail',    '2024-01-12 09:24:00'),
('Priya Iyer',         'priya.iyer@example.com',      'Bengaluru',     'India',        'retail',    '2024-02-03 14:10:00'),
('Rohan Kapoor',       'rohan.kapoor@example.com',    'Delhi',         'India',        'wholesale', '2024-02-19 11:45:00'),
('Neha Verma',         'neha.verma@example.com',      'Pune',          'India',        'retail',    '2024-03-05 16:30:00'),
('Ishaan Mehta',       'ishaan.mehta@example.com',    'Hyderabad',     'India',        'retail',    '2024-03-22 08:15:00'),
('Ananya Reddy',       'ananya.reddy@example.com',    'Chennai',       'India',        'wholesale', '2024-04-08 13:00:00'),
('Kabir Singh',        'kabir.singh@example.com',     'Kolkata',       'India',        'retail',    '2024-04-27 17:20:00'),
('Meera Nair',         'meera.nair@example.com',      'Kochi',         'India',        'retail',    '2024-05-14 10:05:00'),
('Arjun Patel',        'arjun.patel@example.com',     'Ahmedabad',     'India',        'wholesale', '2024-05-30 12:40:00'),
('Saanvi Joshi',       'saanvi.joshi@example.com',    'Jaipur',        'India',        'retail',    '2024-06-18 15:55:00'),
('Emma Johnson',       'emma.johnson@example.com',    'New York',      'USA',          'retail',    '2024-06-29 09:10:00'),
('Liam Brown',         'liam.brown@example.com',      'Los Angeles',   'USA',          'wholesale', '2024-07-11 18:25:00'),
('Olivia Davis',       'olivia.davis@example.com',    'Chicago',       'USA',          'retail',    '2024-07-25 07:50:00'),
('Noah Wilson',        'noah.wilson@example.com',     'Houston',       'USA',          'retail',    '2024-08-09 14:35:00'),
('Ava Martinez',       'ava.martinez@example.com',    'San Francisco', 'USA',          'wholesale', '2024-08-23 16:15:00'),
('James Taylor',       'james.taylor@example.com',    'London',        'UK',           'retail',    '2024-09-04 11:00:00'),
('Sophia Anderson',    'sophia.anderson@example.com', 'Manchester',    'UK',           'retail',    '2024-09-19 13:45:00'),
('Lucas Thomas',       'lucas.thomas@example.com',    'Birmingham',    'UK',           'wholesale', '2024-10-06 10:30:00'),
('Mia Walker',         'mia.walker@example.com',      'Berlin',        'Germany',      'retail',    '2024-10-22 08:55:00'),
('Ethan Hall',         'ethan.hall@example.com',      'Munich',        'Germany',      'wholesale', '2024-11-07 17:05:00'),
('Isabella Young',     'isabella.young@example.com',  'Paris',         'France',       'retail',    '2024-11-25 19:20:00'),
('Mason King',         'mason.king@example.com',      'Lyon',          'France',       'retail',    '2024-12-10 12:10:00'),
('Charlotte Wright',   'charlotte.wright@example.com','Toronto',       'Canada',       'wholesale', '2024-12-28 15:00:00'),
('Benjamin Scott',     'benjamin.scott@example.com',  'Vancouver',     'Canada',       'retail',    '2025-01-14 09:40:00'),
('Amelia Green',       'amelia.green@example.com',    'Sydney',        'Australia',    'retail',    '2025-02-02 11:25:00'),
('Henry Baker',        'henry.baker@example.com',     'Melbourne',     'Australia',    'wholesale', '2025-02-19 14:50:00'),
('Harper Adams',       'harper.adams@example.com',    'Dubai',         'UAE',          'wholesale', '2025-03-08 16:35:00'),
('Elijah Nelson',      'elijah.nelson@example.com',   'Singapore',     'Singapore',    'retail',    '2025-03-24 08:20:00'),
('Evelyn Carter',      'evelyn.carter@example.com',   'Tokyo',         'Japan',        'retail',    '2025-04-09 10:55:00'),
('Daniel Mitchell',    'daniel.mitchell@example.com', 'Seoul',         'South Korea',  'wholesale', '2025-04-25 13:15:00');

-- -----------------------------------------------------------------------------
-- Sample Orders (~30 rows, mixed statuses / payment methods / spanning 2 years)
-- -----------------------------------------------------------------------------
INSERT INTO orders (customer_id, status, order_date, total_amount, payment_method) VALUES
( 1, 'delivered', '2024-02-10 11:30:00',  2450.00, 'upi'),
( 1, 'delivered', '2024-06-14 15:45:00',  5120.50, 'credit_card'),
( 2, 'shipped',   '2024-03-22 09:15:00',   875.75, 'upi'),
( 2, 'cancelled', '2024-05-07 17:20:00',  3200.00, 'netbanking'),
( 3, 'delivered', '2024-04-12 13:00:00', 68500.00, 'netbanking'),
( 3, 'delivered', '2024-10-18 10:40:00', 54200.00, 'credit_card'),
( 4, 'delivered', '2024-04-29 14:55:00',  1899.00, 'cod'),
( 5, 'pending',   '2024-05-16 08:25:00',   650.00, 'upi'),
( 6, 'delivered', '2024-06-02 16:10:00', 72300.00, 'netbanking'),
( 6, 'shipped',   '2025-01-19 12:30:00', 41800.00, 'credit_card'),
( 7, 'delivered', '2024-07-08 19:00:00',  3450.25, 'credit_card'),
( 8, 'cancelled', '2024-07-21 11:15:00',  1120.00, 'cod'),
( 9, 'delivered', '2024-08-05 15:35:00', 58900.00, 'netbanking'),
(10, 'delivered', '2024-08-29 09:45:00',  2240.50, 'upi'),
(11, 'shipped',   '2024-09-12 13:20:00',  7850.00, 'credit_card'),
(12, 'delivered', '2024-09-27 17:40:00', 95400.00, 'credit_card'),
(13, 'delivered', '2024-10-15 10:05:00',  1675.00, 'credit_card'),
(14, 'pending',   '2024-11-03 14:25:00',  4320.75, 'credit_card'),
(15, 'delivered', '2024-11-20 16:50:00', 83200.00, 'netbanking'),
(16, 'delivered', '2024-12-08 08:35:00',  2980.00, 'credit_card'),
(17, 'cancelled', '2024-12-22 12:00:00',   540.00, 'cod'),
(18, 'delivered', '2025-01-09 15:25:00', 61500.00, 'netbanking'),
(19, 'shipped',   '2025-01-26 18:10:00',  3720.00, 'credit_card'),
(20, 'delivered', '2025-02-14 11:45:00', 47800.00, 'credit_card'),
(21, 'delivered', '2025-03-02 09:00:00',  5210.50, 'credit_card'),
(22, 'delivered', '2025-03-18 13:55:00',  1890.00, 'upi'),
(23, 'shipped',   '2025-04-04 16:20:00', 76200.00, 'netbanking'),
(25, 'delivered', '2025-04-20 10:15:00',  2650.00, 'credit_card'),
(27, 'pending',   '2026-01-07 14:40:00', 52400.00, 'netbanking'),
(29, 'delivered', '2026-02-15 17:05:00',  3980.00, 'upi');

-- ==============================================================================
-- SAMPLE MEMORY DATA - Demonstrates Memory System Functionality
-- ==============================================================================

-- Sample memories for demonstration (these will be created by users naturally)
INSERT INTO memories (user_id, content, created_at, source, metadata) VALUES
('sample_user',  '[PREFERENCE] User only wants to see delivered orders',                                      1709251200.0, 'conversation', '{"type": "preference", "confidence": 0.9}'),
('sample_user',  '[TERM] Big spenders means customers with total order value over 50000',                     1709251300.0, 'conversation', '{"type": "term", "confidence": 0.95}'),
('sample_user',  '[ENTITY] User frequently queries the orders and customers tables',                          1709251400.0, 'conversation', '{"type": "entity", "confidence": 0.8}'),
('sample_user2', '[PREFERENCE] User prefers to see data from India only',                                     1709251500.0, 'conversation', '{"type": "preference", "confidence": 0.85}'),
('sample_user2', '[METRIC] High-value orders are defined as orders with total_amount over 10000',             1709251600.0, 'conversation', '{"type": "metric", "confidence": 0.9}');

-- ==============================================================================
-- VERIFICATION QUERIES - Validate Setup
-- ==============================================================================

-- Display setup summary
SELECT 'DATABASE SETUP COMPLETED SUCCESSFULLY' as status;

SELECT
    'Business Data Summary' as category,
    'Customers: ' || COUNT(*) as details
FROM customers
UNION ALL
SELECT
    'Business Data Summary',
    'Orders: ' || COUNT(*)
FROM orders
UNION ALL
SELECT
    'Memory System Summary',
    'Sample Memories: ' || COUNT(*)
FROM memories
UNION ALL
SELECT
    'System Status',
    'pgvector Extension: ' || CASE WHEN COUNT(*) > 0 THEN 'ENABLED' ELSE 'DISABLED' END
FROM pg_extension WHERE extname = 'vector';

-- Show data distribution for memory learning opportunities
SELECT
    'Order Status Distribution' as metric_type,
    status as value,
    COUNT(*) as count
FROM orders
GROUP BY status
UNION ALL
SELECT
    'Customer Segment Distribution',
    segment,
    COUNT(*)
FROM customers
GROUP BY segment
UNION ALL
SELECT
    'Country Distribution',
    country,
    COUNT(*)
FROM customers
WHERE country IS NOT NULL
GROUP BY country
ORDER BY metric_type, count DESC;

-- Sample queries to test the system
SELECT 'SAMPLE QUERIES TO TEST YOUR SYSTEM:' as instructions;
SELECT '1. Show me all delivered orders' as sample_query
UNION ALL SELECT '2. How many big spenders do we have?'
UNION ALL SELECT '3. Which customers are in India?'
UNION ALL SELECT '4. Show me orders over 50000 with customer details'
UNION ALL SELECT '5. I only want to see delivered orders going forward (sets preference)';

-- Verify all indexes are created
SELECT
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes
WHERE schemaname = 'public'
AND tablename IN ('customers', 'orders', 'memories', 'conversation_summaries', 'recent_messages')
ORDER BY tablename, indexname;

-- Final success message
SELECT
    'SETUP COMPLETE! Your Smart Query Assistant database is ready.' as message
UNION ALL
SELECT (SELECT COUNT(*) FROM customers) || ' customers and ' ||
       (SELECT COUNT(*) FROM orders) || ' orders loaded'
UNION ALL
SELECT 'Memory system initialized with ' || (SELECT COUNT(*) FROM memories) || ' sample memories'
UNION ALL
SELECT 'Start your application and try: "Show me all delivered orders"'
UNION ALL
SELECT 'The system will learn your preferences as you interact with it!';

-- Show table sizes for reference
SELECT
    table_name,
    pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) as size
FROM information_schema.tables
WHERE table_schema = 'public'
AND table_name IN ('customers', 'orders', 'memories', 'conversation_summaries', 'recent_messages')
ORDER BY pg_total_relation_size(quote_ident(table_name)) DESC;
