-- ==============================================================================
-- SMART QUERY ASSISTANT - Complete Database Setup
-- Text2SQL Agent with Long-Term Memory - Production Ready Schema
-- ==============================================================================
-- 
-- This script creates a complete database environment for the Smart Query Assistant
-- including business data tables and memory system infrastructure.
--
-- Features:
-- ✅ Business data: Loan applications and property records
-- ✅ Memory system: User-specific long-term memory storage  
-- ✅ Vector embeddings: pgvector support for semantic search
-- ✅ Sample data: Realistic test data for immediate use
-- ✅ Production ready: Proper indexes and constraints
--
-- Usage:
--   psql -h localhost -U postgres -d your_database -f complete_database_setup.sql
--
-- Requirements:
--   - PostgreSQL 12+ 
--   - pgvector extension available
-- ==============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS vector;

-- Clean up existing tables (for fresh setup)
DROP TABLE IF EXISTS properties CASCADE;
DROP TABLE IF EXISTS loan_applications CASCADE;
DROP TABLE IF EXISTS memories CASCADE;
DROP TABLE IF EXISTS conversation_summaries CASCADE;
DROP TABLE IF EXISTS recent_messages CASCADE;

-- ==============================================================================
-- BUSINESS DATA TABLES
-- Core tables for loan and property management demonstration
-- ==============================================================================

-- -----------------------------------------------------------------------------
-- LOAN APPLICATIONS - Perfect for demonstrating PREFERENCES and TERMINOLOGY
-- -----------------------------------------------------------------------------
CREATE TABLE loan_applications (
    loan_id SERIAL PRIMARY KEY,
    applicant_name VARCHAR(100) NOT NULL,
    email VARCHAR(100),
    phone VARCHAR(20),
    
    -- Financial Details (great for METRICS memory)
    loan_amount DECIMAL(12,2) NOT NULL,
    interest_rate DECIMAL(5,3) NOT NULL,
    loan_term_months INTEGER NOT NULL,
    credit_score INTEGER NOT NULL CHECK (credit_score >= 300 AND credit_score <= 850),
    annual_income DECIMAL(12,2) NOT NULL,
    debt_to_income_ratio DECIMAL(5,3),
    
    -- Status and Approval (perfect for PREFERENCES memory)
    application_status VARCHAR(20) DEFAULT 'pending' CHECK (application_status IN 
        ('pending', 'under_review', 'approved', 'rejected', 'withdrawn')),
    approval_date DATE,
    
    -- Risk Assessment (great for TERMINOLOGY memory)
    risk_category VARCHAR(20) CHECK (risk_category IN 
        ('low_risk', 'moderate_risk', 'high_risk', 'very_high_risk')),
    
    -- Geographic Data (useful for regional preferences)
    applicant_state VARCHAR(2),
    applicant_city VARCHAR(50),
    property_state VARCHAR(2),
    property_city VARCHAR(50),
    
    -- Loan Purpose and Type
    loan_purpose VARCHAR(30) CHECK (loan_purpose IN 
        ('home_purchase', 'refinance', 'home_improvement', 'investment_property', 'commercial')),
    loan_type VARCHAR(20) CHECK (loan_type IN 
        ('conventional', 'fha', 'va', 'usda', 'jumbo')),
    
    -- Timestamps
    application_date DATE DEFAULT CURRENT_DATE,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    
    -- Loan Officer Assignment
    assigned_officer VARCHAR(50),
    officer_notes TEXT
);

-- Add table and column comments for better AI understanding
COMMENT ON TABLE loan_applications IS 'Loan application records with approval status, risk assessment, and financial details';
COMMENT ON COLUMN loan_applications.application_status IS 'Current status: pending, under_review, approved, rejected, withdrawn';
COMMENT ON COLUMN loan_applications.risk_category IS 'Risk assessment: low_risk, moderate_risk, high_risk, very_high_risk';
COMMENT ON COLUMN loan_applications.credit_score IS 'FICO credit score (300-850 range)';
COMMENT ON COLUMN loan_applications.debt_to_income_ratio IS 'Monthly debt payments divided by monthly gross income';
COMMENT ON COLUMN loan_applications.loan_purpose IS 'Purpose: home_purchase, refinance, home_improvement, investment_property, commercial';

-- -----------------------------------------------------------------------------
-- PROPERTIES - Perfect for demonstrating METRICS and ENTITIES
-- -----------------------------------------------------------------------------
CREATE TABLE properties (
    property_id SERIAL PRIMARY KEY,
    loan_id INTEGER REFERENCES loan_applications(loan_id),
    
    -- Property Details
    property_address VARCHAR(200) NOT NULL,
    city VARCHAR(50) NOT NULL,
    state VARCHAR(2) NOT NULL,
    zip_code VARCHAR(10),
    
    -- Property Characteristics (great for TERMINOLOGY memory)
    property_type VARCHAR(30) CHECK (property_type IN 
        ('single_family', 'condo', 'townhouse', 'multi_family', 'commercial', 'land')),
    property_condition VARCHAR(20) CHECK (property_condition IN 
        ('excellent', 'good', 'fair', 'needs_repair', 'poor')),
    
    -- Financial Metrics (perfect for METRICS memory)
    appraised_value DECIMAL(12,2) NOT NULL,
    purchase_price DECIMAL(12,2),
    down_payment DECIMAL(12,2),
    loan_to_value_ratio DECIMAL(5,3),
    
    -- Property Specifications
    bedrooms INTEGER,
    bathrooms DECIMAL(3,1),
    square_feet INTEGER,
    lot_size_acres DECIMAL(8,3),
    year_built INTEGER,
    
    -- Market Information
    neighborhood_rating VARCHAR(10) CHECK (neighborhood_rating IN 
        ('A+', 'A', 'B+', 'B', 'C+', 'C', 'D')),
    market_trend VARCHAR(20) CHECK (market_trend IN 
        ('appreciating', 'stable', 'declining')),
    
    -- Additional Flags (useful for preferences)
    is_primary_residence BOOLEAN DEFAULT TRUE,
    is_investment_property BOOLEAN DEFAULT FALSE,
    is_luxury_property BOOLEAN DEFAULT FALSE,
    
    -- Timestamps
    listing_date DATE,
    appraisal_date DATE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE properties IS 'Property details linked to loan applications with valuations and characteristics';
COMMENT ON COLUMN properties.loan_to_value_ratio IS 'Loan amount divided by appraised property value';
COMMENT ON COLUMN properties.property_condition IS 'Physical condition: excellent, good, fair, needs_repair, poor';
COMMENT ON COLUMN properties.neighborhood_rating IS 'Neighborhood quality rating from A+ (best) to D (worst)';
COMMENT ON COLUMN properties.is_luxury_property IS 'Flag for high-end properties (typically >$1M or top 10% in area)';

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
CREATE INDEX idx_loans_status ON loan_applications(application_status);
CREATE INDEX idx_loans_risk ON loan_applications(risk_category);
CREATE INDEX idx_loans_state ON loan_applications(property_state);
CREATE INDEX idx_loans_amount ON loan_applications(loan_amount);
CREATE INDEX idx_loans_credit_score ON loan_applications(credit_score);
CREATE INDEX idx_loans_officer ON loan_applications(assigned_officer);
CREATE INDEX idx_loans_purpose ON loan_applications(loan_purpose);
CREATE INDEX idx_loans_date ON loan_applications(application_date);

-- Properties Indexes
CREATE INDEX idx_properties_loan_id ON properties(loan_id);
CREATE INDEX idx_properties_state ON properties(state);
CREATE INDEX idx_properties_type ON properties(property_type);
CREATE INDEX idx_properties_value ON properties(appraised_value);
CREATE INDEX idx_properties_luxury ON properties(is_luxury_property);
CREATE INDEX idx_properties_investment ON properties(is_investment_property);

-- Memory System Indexes (Critical for Performance)
CREATE INDEX idx_memories_user_id ON memories(user_id);
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
-- Sample Loan Applications with Diverse Scenarios
-- -----------------------------------------------------------------------------
INSERT INTO loan_applications (
    applicant_name, email, phone, loan_amount, interest_rate, loan_term_months,
    credit_score, annual_income, debt_to_income_ratio, application_status,
    approval_date, risk_category, applicant_state, applicant_city,
    property_state, property_city, loan_purpose, loan_type,
    application_date, assigned_officer, officer_notes
) VALUES
-- HIGH-VALUE APPROVED LOANS (California)
('Sarah Johnson', 'sarah.j@email.com', '555-0201', 875000.00, 6.250, 360, 780, 185000.00, 0.28, 'approved', '2024-02-15', 'low_risk', 'CA', 'San Francisco', 'CA', 'San Francisco', 'home_purchase', 'jumbo', '2024-01-20', 'Mike Chen', 'Excellent credit, strong income'),
('David Kim', 'david.kim@email.com', '555-0202', 650000.00, 6.125, 360, 750, 145000.00, 0.32, 'approved', '2024-02-20', 'low_risk', 'CA', 'Los Angeles', 'CA', 'Los Angeles', 'home_purchase', 'conventional', '2024-01-25', 'Lisa Wong', 'Tech professional, stable employment'),

-- MODERATE RISK PENDING APPLICATIONS
('Jennifer Martinez', 'jen.martinez@email.com', '555-0203', 420000.00, 6.500, 360, 680, 75000.00, 0.38, 'under_review', NULL, 'moderate_risk', 'TX', 'Austin', 'TX', 'Austin', 'home_purchase', 'conventional', '2024-03-01', 'Robert Davis', 'Needs additional income verification'),
('Michael Brown', 'mike.brown@email.com', '555-0204', 285000.00, 6.875, 360, 640, 52000.00, 0.42, 'pending', NULL, 'moderate_risk', 'FL', 'Miami', 'FL', 'Miami', 'refinance', 'fha', '2024-03-05', 'Angela Rodriguez', 'First-time homebuyer program'),

-- HIGH RISK / REJECTED APPLICATIONS
('Thomas Wilson', 'tom.wilson@email.com', '555-0205', 350000.00, 7.250, 360, 580, 48000.00, 0.48, 'rejected', NULL, 'high_risk', 'NY', 'Buffalo', 'NY', 'Buffalo', 'home_purchase', 'fha', '2024-02-28', 'Sarah Johnson', 'DTI ratio too high, insufficient income'),

-- INVESTMENT PROPERTIES
('Rachel Green', 'rachel.green@email.com', '555-0206', 520000.00, 7.000, 360, 720, 125000.00, 0.35, 'approved', '2024-03-10', 'moderate_risk', 'WA', 'Seattle', 'WA', 'Seattle', 'investment_property', 'conventional', '2024-02-18', 'James Liu', 'Investment property, requires 25% down'),

-- REFINANCING CASES
('Kevin Adams', 'kevin.adams@email.com', '555-0207', 380000.00, 5.875, 360, 760, 95000.00, 0.29, 'approved', '2024-03-08', 'low_risk', 'CO', 'Denver', 'CO', 'Denver', 'refinance', 'conventional', '2024-02-22', 'Patricia Kim', 'Cash-out refinance for home improvements'),

-- COMMERCIAL LOANS
('Global Properties LLC', 'contact@globalprops.com', '555-0208', 1250000.00, 7.500, 300, 700, 350000.00, 0.40, 'under_review', NULL, 'moderate_risk', 'IL', 'Chicago', 'IL', 'Chicago', 'commercial', 'conventional', '2024-03-12', 'Steven Zhang', 'Office building acquisition'),

-- LUXURY PROPERTIES
('Elizabeth Windsor', 'e.windsor@email.com', '555-0209', 1800000.00, 6.000, 360, 800, 425000.00, 0.25, 'approved', '2024-03-15', 'low_risk', 'CA', 'Beverly Hills', 'CA', 'Beverly Hills', 'home_purchase', 'jumbo', '2024-02-25', 'Alexander Smith', 'Ultra-high net worth client'),

-- RURAL/USDA LOANS
('Mary Thompson', 'mary.thompson@email.com', '555-0210', 195000.00, 6.250, 360, 690, 42000.00, 0.36, 'approved', '2024-03-18', 'moderate_risk', 'IA', 'Cedar Rapids', 'IA', 'Cedar Rapids', 'home_purchase', 'usda', '2024-03-01', 'Daniel Brown', 'USDA rural development loan'),

-- VETERAN LOANS
('John Rodriguez', 'john.rodriguez@email.com', '555-0211', 310000.00, 5.750, 360, 710, 68000.00, 0.33, 'approved', '2024-03-20', 'low_risk', 'NC', 'Fort Bragg', 'NC', 'Fayetteville', 'home_purchase', 'va', '2024-03-03', 'Michelle Garcia', 'VA loan, military veteran, no down payment required'),

-- ADDITIONAL DIVERSE SCENARIOS
('Amanda Chen', 'amanda.chen@tech.com', '555-0212', 720000.00, 6.375, 360, 795, 168000.00, 0.31, 'approved', '2024-03-22', 'low_risk', 'WA', 'Bellevue', 'WA', 'Bellevue', 'home_purchase', 'conventional', '2024-03-05', 'Mike Chen', 'Software engineer, excellent profile'),
('Carlos Santos', 'carlos.santos@email.com', '555-0213', 445000.00, 6.625, 360, 685, 78000.00, 0.39, 'under_review', NULL, 'moderate_risk', 'AZ', 'Phoenix', 'AZ', 'Phoenix', 'home_purchase', 'conventional', '2024-03-10', 'Robert Davis', 'Self-employed, needs additional documentation'),
('Lisa Park', 'lisa.park@email.com', '555-0214', 892000.00, 6.125, 360, 773, 195000.00, 0.27, 'approved', '2024-03-25', 'low_risk', 'CA', 'San Jose', 'CA', 'San Jose', 'home_purchase', 'jumbo', '2024-03-08', 'Lisa Wong', 'Tech executive, premium client'),
('Robert Taylor', 'robert.taylor@email.com', '555-0215', 265000.00, 7.125, 360, 625, 55000.00, 0.44, 'rejected', NULL, 'high_risk', 'OH', 'Cleveland', 'OH', 'Cleveland', 'home_purchase', 'fha', '2024-03-12', 'Angela Rodriguez', 'Credit issues, high DTI ratio'),
('Investor Group Alpha', 'contact@investoralpha.com', '555-0216', 1450000.00, 7.750, 300, 680, 425000.00, 0.38, 'approved', '2024-03-28', 'moderate_risk', 'FL', 'Miami', 'FL', 'Miami', 'investment_property', 'conventional', '2024-03-15', 'James Liu', 'Commercial real estate investment');

-- -----------------------------------------------------------------------------
-- Sample Properties Linked to Loans
-- -----------------------------------------------------------------------------
INSERT INTO properties (
    loan_id, property_address, city, state, zip_code, property_type, property_condition,
    appraised_value, purchase_price, down_payment, loan_to_value_ratio,
    bedrooms, bathrooms, square_feet, lot_size_acres, year_built,
    neighborhood_rating, market_trend, is_primary_residence, is_investment_property,
    is_luxury_property, listing_date, appraisal_date
) VALUES
-- High-value California properties
(1, '123 Pacific Heights Ave', 'San Francisco', 'CA', '94109', 'single_family', 'excellent', 1250000.00, 1200000.00, 325000.00, 0.70, 4, 3.5, 2800, 0.15, 1995, 'A+', 'appreciating', TRUE, FALSE, TRUE, '2024-01-15', '2024-02-10'),
(2, '456 Beverly Glen Blvd', 'Los Angeles', 'CA', '90210', 'single_family', 'good', 950000.00, 925000.00, 275000.00, 0.68, 3, 2.5, 2200, 0.12, 1988, 'A', 'stable', TRUE, FALSE, TRUE, '2024-01-20', '2024-02-15'),

-- Moderate value properties
(3, '789 Music Lane', 'Austin', 'TX', '78701', 'condo', 'excellent', 485000.00, 465000.00, 45000.00, 0.87, 2, 2.0, 1400, 0.00, 2010, 'B+', 'appreciating', TRUE, FALSE, FALSE, '2024-02-25', '2024-03-05'),
(4, '321 Ocean Drive', 'Miami', 'FL', '33139', 'condo', 'good', 325000.00, 315000.00, 30000.00, 0.88, 2, 2.0, 1200, 0.00, 2005, 'B', 'stable', TRUE, FALSE, FALSE, '2024-02-28', '2024-03-08'),

-- Investment properties
(6, '555 Tech Hub Way', 'Seattle', 'WA', '98101', 'townhouse', 'good', 625000.00, 600000.00, 150000.00, 0.83, 3, 2.5, 1800, 0.05, 2012, 'A', 'appreciating', FALSE, TRUE, FALSE, '2024-02-10', '2024-02-20'),

-- Refinance property
(7, '888 Mountain View Dr', 'Denver', 'CO', '80202', 'single_family', 'excellent', 550000.00, NULL, NULL, 0.69, 4, 3.0, 2400, 0.20, 1998, 'B+', 'stable', TRUE, FALSE, FALSE, NULL, '2024-02-25'),

-- Commercial property
(8, '1000 Business Center Blvd', 'Chicago', 'IL', '60601', 'commercial', 'good', 1850000.00, 1750000.00, 600000.00, 0.68, 0, 6.0, 15000, 0.50, 1985, 'A', 'stable', FALSE, TRUE, FALSE, '2024-03-01', '2024-03-15'),

-- Ultra-luxury property
(9, '777 Rodeo Drive', 'Beverly Hills', 'CA', '90210', 'single_family', 'excellent', 2500000.00, 2400000.00, 700000.00, 0.72, 6, 5.5, 4500, 0.25, 2001, 'A+', 'appreciating', TRUE, FALSE, TRUE, '2024-02-20', '2024-03-10'),

-- Rural property
(10, '999 Country Road', 'Cedar Rapids', 'IA', '52404', 'single_family', 'good', 225000.00, 210000.00, 0.00, 0.87, 3, 2.0, 1600, 2.50, 1985, 'C+', 'stable', TRUE, FALSE, FALSE, '2024-02-25', '2024-03-12'),

-- VA loan property
(11, '444 Military Housing St', 'Fayetteville', 'NC', '28301', 'single_family', 'good', 285000.00, 275000.00, 0.00, 1.09, 3, 2.5, 1750, 0.18, 1992, 'B', 'stable', TRUE, FALSE, FALSE, '2024-02-28', '2024-03-18'),

-- Additional diverse properties
(12, '567 Innovation Drive', 'Bellevue', 'WA', '98004', 'single_family', 'excellent', 825000.00, 800000.00, 152000.00, 0.87, 4, 3.5, 2650, 0.18, 2005, 'A', 'appreciating', TRUE, FALSE, TRUE, '2024-03-02', '2024-03-20'),
(13, '890 Desert Vista', 'Phoenix', 'AZ', '85016', 'single_family', 'good', 510000.00, 485000.00, 40000.00, 0.87, 3, 2.5, 2100, 0.25, 2008, 'B+', 'stable', TRUE, FALSE, FALSE, '2024-03-07', '2024-03-18'),
(14, '123 Silicon Valley Blvd', 'San Jose', 'CA', '95110', 'single_family', 'excellent', 1150000.00, 1100000.00, 258000.00, 0.77, 5, 4.0, 3200, 0.22, 2010, 'A+', 'appreciating', TRUE, FALSE, TRUE, '2024-03-05', '2024-03-22'),
(15, '2500 Investment Plaza', 'Miami', 'FL', '33131', 'commercial', 'excellent', 1850000.00, 1750000.00, 395000.00, 0.78, 0, 8.0, 25000, 1.20, 1995, 'A', 'appreciating', FALSE, TRUE, TRUE, '2024-03-12', '2024-03-25');

-- ==============================================================================
-- SAMPLE MEMORY DATA - Demonstrates Memory System Functionality
-- ==============================================================================

-- Sample memories for demonstration (these will be created by users naturally)
INSERT INTO memories (user_id, content, created_at, source, metadata) VALUES
('demo_user', '[PREFERENCE] User is only interested in approved loans', 1709251200.0, 'conversation', '{"type": "preference", "confidence": 0.9}'),
('demo_user', '[TERM] High-value loans means loan amount over $500,000', 1709251300.0, 'conversation', '{"type": "term", "confidence": 0.95}'),
('demo_user', '[ENTITY] User frequently queries loan_applications and properties tables', 1709251400.0, 'conversation', '{"type": "entity", "confidence": 0.8}'),
('analyst_user', '[PREFERENCE] User prefers to see data from California only', 1709251500.0, 'conversation', '{"type": "preference", "confidence": 0.85}'),
('analyst_user', '[METRIC] Luxury properties are defined as properties with appraised_value > $1,000,000', 1709251600.0, 'conversation', '{"type": "metric", "confidence": 0.9}');

-- ==============================================================================
-- VERIFICATION QUERIES - Validate Setup
-- ==============================================================================

-- Display setup summary
SELECT 'DATABASE SETUP COMPLETED SUCCESSFULLY' as status;

SELECT 
    'Business Data Summary' as category,
    'Loan Applications: ' || COUNT(*) as details
FROM loan_applications
UNION ALL
SELECT 
    'Business Data Summary',
    'Properties: ' || COUNT(*)
FROM properties
UNION ALL
SELECT 
    'Memory System Summary',
    'Sample Memories: ' || COUNT(*)
FROM memories
UNION ALL
SELECT 
    'System Status',
    'pgvector Extension: ' || CASE WHEN COUNT(*) > 0 THEN 'ENABLED ✅' ELSE 'DISABLED ❌' END
FROM pg_extension WHERE extname = 'vector';

-- Show data distribution for memory learning opportunities
SELECT 
    'Approval Status Distribution' as metric_type,
    application_status as value,
    COUNT(*) as count
FROM loan_applications
GROUP BY application_status
UNION ALL
SELECT 
    'Risk Distribution',
    risk_category,
    COUNT(*)
FROM loan_applications
WHERE risk_category IS NOT NULL
GROUP BY risk_category
UNION ALL
SELECT 
    'State Distribution',
    property_state,
    COUNT(*)
FROM loan_applications
WHERE property_state IS NOT NULL
GROUP BY property_state
ORDER BY metric_type, count DESC;

-- Sample queries to test the system
SELECT 'SAMPLE QUERIES TO TEST YOUR SYSTEM:' as instructions;
SELECT '1. Show me all approved loans' as sample_query
UNION ALL SELECT '2. How many high-value loans do we have?' 
UNION ALL SELECT '3. What properties are in California?'
UNION ALL SELECT '4. Show me luxury properties with loans'
UNION ALL SELECT '5. I only want to see approved loans going forward (sets preference)';

-- Verify all indexes are created
SELECT 
    schemaname,
    tablename,
    indexname,
    indexdef
FROM pg_indexes 
WHERE schemaname = 'public' 
AND tablename IN ('loan_applications', 'properties', 'memories', 'conversation_summaries', 'recent_messages')
ORDER BY tablename, indexname;

-- Final success message
SELECT 
    '🎉 SETUP COMPLETE! Your Smart Query Assistant database is ready.' as message
UNION ALL
SELECT '📊 ' || (SELECT COUNT(*) FROM loan_applications) || ' loan applications and ' || 
       (SELECT COUNT(*) FROM properties) || ' properties loaded'
UNION ALL  
SELECT '🧠 Memory system initialized with ' || (SELECT COUNT(*) FROM memories) || ' sample memories'
UNION ALL
SELECT '🚀 Start your application and try: "Show me all approved loans"'
UNION ALL
SELECT '💡 The system will learn your preferences as you interact with it!';

-- Show table sizes for reference
SELECT 
    table_name,
    pg_size_pretty(pg_total_relation_size(quote_ident(table_name))) as size
FROM information_schema.tables 
WHERE table_schema = 'public'
AND table_name IN ('loan_applications', 'properties', 'memories', 'conversation_summaries', 'recent_messages')
ORDER BY pg_total_relation_size(quote_ident(table_name)) DESC;