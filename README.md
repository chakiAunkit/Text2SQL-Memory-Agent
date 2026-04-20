# 🧠 Text2SQL Agent with Long-Term Memory

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14+-336791.svg)](https://www.postgresql.org/)
[![Ollama](https://img.shields.io/badge/Ollama-Local_LLM-brightgreen.svg)](https://ollama.ai/)

A production-ready Text-to-SQL system with **persistent long-term memory** that learns 
and remembers user preferences, terminology, and context across sessions. Built entirely 
with open-source components, runs fully locally on your own hardware, and designed with 
real-world multi-user scenarios in mind.
---

## 🌟 Key Features

### 🎯 Long-Term Memory Architecture (Mem0-Inspired)
- **User Preferences**: Automatically applies filters and criteria learned from past conversations
- **Custom Terminology**: Remembers domain-specific terms and their database mappings
- **Metric Definitions**: Stores calculation methods and aggregation formulas
- **Entity Recognition**: Tracks frequently accessed tables, columns, and relationships


### 🔒 Production Grade
- **Multi-User Memory Isolation**: Complete memory separation per user — no cross-contamination
- **PostgreSQL + pgvector**: Production-grade vector similarity search with HNSW indexing
- **Local LLM Deployment**: Privacy-first with Ollama framework (qwen2.5-coder, CodeLlama, Qwen)
- **Modular Architecture**: Swap data sources without changing memory logic

### 💡 Reliable Query Generation
- **Schema-Grounded Prompts**: SQL is generated against the actual introspected schema — never hardcoded
- **SQL Validation**: Generated queries are validated against real table/column names before execution
- **Unnecessary JOIN Stripping**: Automatically removes JOINs when only one table is needed
- **Intelligent Fallback**: If the LLM fails, a schema-aware fallback generates valid SQL
- **Preference Detection**: Distinguishes between data queries and memory updates
- **Chat API Format**: Uses Ollama `/api/chat` — compatible with all instruction-tuned models

---

## 📋 Table of Contents

- [Why Open-Source & Local-First?](#-why-open-source--local-first)
- [How Does the System Work?](#-how-does-the-system-work)
- [Architecture](#-architecture)
- [How the Mem0 Memory System Works](#-how-the-mem0-memory-system-works)
- [Prompt Engineering](#-prompt-engineering)
- [Quick Start](#-quick-start)
- [Configuration](#-configuration)
- [Usage](#-usage)
- [Project Structure](#-project-structure)
- [API Reference](#-api-reference)
- [Development](#-development)
- [Troubleshooting](#-troubleshooting)
- [Future Work](#-future-work)
- [License](#-license)

---

## 🔓 Why Open-Source & Local-First?

This project was designed from the ground up with one core constraint: **everything must run on your own hardware, with zero external API dependencies.**

Most Text-to-SQL systems with memory rely on OpenAI embeddings, managed vector databases (Pinecone, Weaviate), or cloud-hosted LLMs. This creates three problems:

- **Privacy**: Your queries, preferences, and schema details leave your network
- **Cost**: API calls accumulate quickly at scale
- **Vendor lock-in**: Changing providers requires rewriting significant portions of the stack

This project replaces every proprietary component with a fully open-source, locally-runnable equivalent:

| Role | Cloud / Proprietary | This Project |
|------|--------------------|----|
| LLM for SQL generation | OpenAI GPT-4 | Ollama (qwen2.5-coder, CodeLlama, Qwen) |
| LLM for memory extraction | OpenAI GPT-3.5 | Same local Ollama instance |
| Text embeddings | OpenAI text-embedding-ada | `sentence-transformers` (all-MiniLM-L6-v2) |
| Vector database | Pinecone / Weaviate | PostgreSQL + `pgvector` extension |
| Business data store | Any cloud DB | PostgreSQL |
| Web interface | Proprietary SaaS | Gradio (self-hosted) |

The result is a system that achieves comparable personalisation quality to cloud-based solutions while keeping all data, preferences, and queries entirely within your own infrastructure.

---

## 🖥️ How Does the System Work?

A walkthrough of the UI and the key interactions a user has with the system.

---
### Step 1 — Login and Isolated Memory Spaces

![Login](docs/images/Login.png)
*(Login panel — username "Aunkit" entered, optional database connection field, Login / Logout / Test Connections buttons visible under the Smart Query Assistant header)*

The entry point to the system. A user enters their username — each username gets a completely isolated memory space, so one user's preferences never leak into another's queries. The optional Database Connection field lets users point the system at any PostgreSQL instance; if left blank, the connection from `.env` is used. The **Test Connections** button validates the database, LLM (Ollama), and memory store in one click so setup issues surface immediately.

---

### Step 2 — Teaching the System a Preference

![Preference](docs/images/Preference.png)
*(Preference capture — user says "Always show me customers from India", system confirms and saves. Memory Bank on the right shows the new preference `country = 'India'` under PREFERENCES. SQL panel at the bottom shows "Preference stored — no SQL executed".)*

This is the memory system's core UX moment. When the user states a preference, the system:
- Detects it as a preference statement (not a data query) via the regex classifier
- Extracts the structured fact using the LLM extraction prompt
- Stores it to the Memory Bank tagged `[PREFERENCE]`
- Confirms in chat with ✨ *Preference saved to memory*
- Shows `-- Preference stored — no SQL executed` in the SQL panel so it's clear no query ran

The Memory Bank on the right updates in real time — here showing `country = 'India'` under PREFERENCES.

---

### Step 3 — Defining Custom Terminology

![Terminology](docs/images/Terminology.png)
*(Terminology capture — user says "High value order means total amount over 10000", system confirms and saves under TERMINOLOGY. Memory Bank shows `High value order means total amount over 10000` in the green TERMINOLOGY section.)*

Beyond preferences, users can teach the system their **own vocabulary**. Phrases like `X means Y` or `Define X as Y` are extracted as `[TERM]` memories and stored separately from preferences. Terminology is looked up semantically at query time, so when a user later asks *"Show me high-value orders"*, the system knows exactly which column and threshold to use — no need to re-specify the definition every session.

The Memory Bank visually separates PREFERENCES (red border, filters) from TERMINOLOGY (green border, definitions) so the user can see at a glance what the system has learned about them.

---


### Step 4 — Querying with Preferences and Terminology Applied

![Example Query](docs/images/Example.png)
*(Query "Show me customers who have a high order value" — results table shows 5 rows of wholesale customers from India (Rohan Kapoor, Ananya Reddy, …). Generated SQL panel shows a JOIN across `customers` and `orders` with `WHERE c.country = 'India' AND o.total_amount > 10000`. Execution time 0.030s.)*

This is where the stored memories pay off. The user asks a natural-language question that mentions neither "India" nor "10000", yet the generated SQL automatically includes both:
- `WHERE c.country = 'India'` — applied from the stored `[PREFERENCE]`
- `AND o.total_amount > 10000` — resolved from the stored `[TERM]` definition of "high value order"

The system also correctly **preserves the JOIN** between `customers` and `orders` because the WHERE clause references columns from both tables. The unnecessary-JOIN stripper is smart enough to keep the JOIN when it's actually load-bearing, and drop it when it isn't. The results render directly in chat, and the syntax-highlighted SQL is displayed alongside for full transparency and debuggability.

---

## 🏗️ Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Gradio Web Interface                      │
│     (Dark Theme, Memory Bank, SQL Syntax Highlighting)       │
└──────────────────────┬──────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────┐
│                 Text2SQL Chatbot Engine                      │
│  (Preference Detection → Schema-Grounded SQL → Validation)  │
└──────┬────────────────────────────┬─────────────────────────┘
       │                            │
       ▼                            ▼
┌──────────────────┐      ┌────────────────────────┐
│  Memory Agent    │      │   PostgreSQL Client    │
│  (Mem0-inspired) │      │  (Schema Introspection │
│                  │      │   + Query Execution)   │
└────────┬─────────┘      └────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  PostgreSQL + pgvector           │
│  - memories (HNSW vector index)  │
│  - conversation_summaries        │
│  - recent_messages               │
└──────────────────────────────────┘
         │
         ▼
┌──────────────────────────────────┐
│  Ollama (Local LLM)              │
│  - qwen2.5-coder / CodeLlama     │
│  - sentence-transformers         │
│    (all-MiniLM-L6-v2)            │
└──────────────────────────────────┘
```

### Core Components

| Component | File | Responsibility |
|-----------|------|----------------|
| **Memory Agent** | `memory_agent_opensource.py` | Mem0-inspired extraction, storage, retrieval. Vector similarity search with user isolation. |
| **Text2SQL Chatbot** | `text2sql_chatbot.py` | Query classification, schema-grounded SQL generation, validation, JOIN stripping, fallback. |
| **PostgreSQL Client** | `postgreSQL_data_client.py` | Schema introspection, FK discovery, query execution, metadata caching. |
| **Gradio Frontend** | `gradio_frontend.py` | Web UI with chat, memory bank, SQL syntax highlighting, working memory deletion. |

### SQL Generation Pipeline (Detailed)

Every user message flows through a strict, ordered pipeline in `text2sql_chatbot.py`:

```
User Input
    │
    ├──► Is this a preference/definition statement?
    │         │
    │         └──► YES: extract_memories() → update_memories() → confirm to user
    │
    └──► NO — SQL pipeline:
              │
              ▼
         [1] retrieve_relevant_memories(query)
              Semantic search against the user's memory store
              │
              ▼
         [2] _categorize_memories()
              Split retrieved memories into: preferences, terminology, metrics, entities
              │
              ▼
         [3] _enhance_query()
              Substitute user-defined terms into the natural language query
              │
              ▼
         [4] _generate_sql_with_retry()  ──► _generate_sql()
              Build schema prompt + memory context block
              Send to Ollama /api/chat
              Parse and clean raw LLM output
              │
              ▼
         [5] _validate_and_fix_sql()
              Block queries targeting memory tables
              Strip unnecessary JOINs (scan column refs after removing ON clauses)
              Verify all column names exist in introspected schema
              │
              ▼
         [6] _generate_simple_sql()  [fallback if step 4–5 fail]
              Schema-aware rule-based SQL generation
              │
              ▼
         [7] data_client.execute_query()
              Execute against PostgreSQL
              Retry with fallback SQL if execution fails
              │
              ▼
         [8] _format_response()
              Render results as markdown table
              Append "(preferences applied)" note when relevant
              │
              ▼
         [9] extract_memories() → update_memories()
              Learn from successful interactions
```

### Memory Storage Schema

Three tables enforce strict user isolation — every row is scoped to a `user_id`:

```sql
-- Core memory store with vector embeddings
CREATE TABLE memories (
    id          SERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,          -- isolation boundary
    content     TEXT NOT NULL,          -- "[PREFERENCE] only delivered orders"
    created_at  FLOAT NOT NULL,
    source      TEXT,                   -- "conversation" | "initialization"
    metadata    JSONB DEFAULT '{}',     -- {"type": "preference"}
    embedding   VECTOR(384)             -- all-MiniLM-L6-v2 embedding
);

-- HNSW index: fast approximate nearest-neighbour search
CREATE INDEX ON memories USING hnsw (embedding vector_cosine_ops);
-- Per-user scan efficiency
CREATE INDEX ON memories (user_id);

-- Compressed long-term conversation context
CREATE TABLE conversation_summaries (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    summary    TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Rolling window of recent messages (last 20 per user)
CREATE TABLE recent_messages (
    id         SERIAL PRIMARY KEY,
    user_id    TEXT NOT NULL,
    messages   TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 🧠 How the Mem0 Memory System Works

The memory architecture is directly inspired by the [Mem0 research paper](https://mem0.ai/research), which proposes a two-phase approach to agent memory management. This project implements that architecture from scratch using entirely open-source, locally-run components.

### Why Traditional Text2SQL Systems Fail at Memory

Most Text-to-SQL tools treat every session as a blank slate. Users are forced to re-specify their preferences ("only show delivered orders"), re-define their terminology ("big spenders means total spend over 50000"), and re-establish context at the start of every conversation. This is the **cognitive load problem** — the AI assistant should be learning, but isn't.

### The Two-Phase Mem0 Architecture

#### Phase 1 — Memory Extraction

When a user sends a message, the LLM analyses **only the user's message** to extract structured facts. The AI response is intentionally excluded — it's often a table of SQL results, and column names would be extracted as fake memories.

The extraction prompt instructs the model to tag facts into four categories:

```
[PREFERENCE]  An explicit filter the user wants applied to all future queries
              e.g. "[PREFERENCE] User only wants to see delivered orders"

[TERM]        A custom term and its precise database mapping
              e.g. "[TERM] 'big spenders' means customers with total order value over 50000"

[METRIC]      A user-defined calculation or KPI
              e.g. "[METRIC] 'average order value' = SUM(total_amount) / COUNT(*)"

[ENTITY]      Frequently accessed tables, columns, or relationships
              e.g. "[ENTITY] User frequently queries the orders and customers tables"
```

If there is nothing meaningful to extract, the model outputs exactly `NONE` — a hard gate that prevents noise from accumulating in the memory store.

#### Phase 2 — Memory Update (ADD / UPDATE / DELETE / NOOP)

Each extracted fact is compared against the user's existing memories using cosine similarity. The system then classifies the operation:

```
New fact embedding
       │
       ▼
 Find top-3 similar existing memories (pgvector cosine search)
       │
       ├── No similar memory found
       │       └──► ADD  (insert as new memory)
       │
       ├── Similarity > 0.95
       │       └──► NOOP  (fact is redundant, discard)
       │
       └── Similarity 0.70 – 0.95
               │
               └──► LLM judgement:
                       "DELETE" ──► new fact contradicts existing → replace old
                       "UPDATE" ──► new fact enhances existing → update content
                       "NOOP"   ──► effectively the same → discard
```

This layered approach means the memory store stays accurate over time — contradictions are resolved, redundancies are filtered, and new information is correctly integrated.

### Memory Retrieval at Query Time

When a user asks a question, the query is embedded and compared against their entire memory store. The top-k most semantically relevant memories are retrieved and injected into the SQL generation prompt as context:

```python
# Cosine similarity search — user-isolated
SELECT content, (1 - (embedding <=> query_embedding)) AS similarity
FROM memories
WHERE user_id = 'analyst_1'
ORDER BY embedding <=> query_embedding
LIMIT 5;
```

Only memories that are actually relevant to the current question surface — not the entire history.

### Memory Categories in Practice

```
User: "I only want to see delivered orders"
→ Stored: [PREFERENCE] User only wants to see delivered orders

User: "Big spenders means customers with total spend over 50000"
→ Stored: [TERM] big spenders = customers with total order value over 50000

User: "Show me top big spenders"
→ [PREFERENCE] and [TERM] memories retrieved via semantic search
→ SQL generated with filters and terminology pre-applied
→ Response includes "(Note: preferences applied)"
```

---

## ✍️ Prompt Engineering

Prompt design is a first-class concern in this system. Because the target models are 7B-parameter local models (not GPT-4), prompts must be compact, unambiguous, and structured to reliably produce parseable output. Every prompt in the system was designed with this constraint in mind.

### SQL Generation Prompt

The SQL prompt uses the **Ollama `/api/chat` endpoint** with a split system + user message structure. Earlier versions used `/api/generate` with a SQL completion trick, but instruction-tuned models (qwen2.5-coder, Qwen, etc.) behave fundamentally differently in completion mode vs chat mode — the chat format was essential for reliable output.

**System message** — sets the model's strict output contract:
```
You are a PostgreSQL expert.
Output ONLY a valid SQL SELECT statement — no explanation,
no markdown fences, no backticks, no comments.
Raw SQL only.
```

**User message** — injects schema + memory context + question:
```
Schema (use ONLY these tables and columns):
TABLE customers (customer_id, name, email, city, country, segment, registered_at)
TABLE orders (order_id, customer_id, status, order_date, total_amount, payment_method)
  -- status: 'pending', 'shipped', 'delivered', 'cancelled'
  -- segment: 'retail', 'wholesale'
JOIN: orders.customer_id = customers.customer_id

Rules:
- Output raw SQL only, nothing else.
- Do NOT JOIN tables unless both are genuinely needed in SELECT or WHERE.
- Add LIMIT 20 for non-aggregate queries.
- User preferences:
  - Apply filter: [PREFERENCE] only show delivered orders
  - Term defined: [TERM] big spenders = customers with total order value over 50000

Question: Show me all big spenders
```

#### Why the Schema Block is Compact

Full schema blocks (with data types, nullability, descriptions, indexes) can easily exceed 2,000 tokens for a moderate schema. At 4,096 token context windows, that leaves little room for the question, memories, and SQL output. The schema block is deliberately compressed to **one line per table** — table name, all column names — with value hints only for status/enum columns that the model needs to know about to write correct WHERE clauses.

#### Decoding Parameters — Set for Determinism

SQL generation uses near-zero temperature to minimise hallucination:

```python
"options": {
    "temperature": 0.0,   # Fully deterministic output
    "top_k": 1,           # Greedy decoding
    "top_p": 0.1,         # Narrow nucleus
    "num_predict": 400,   # Enough for a complex SQL query
    "num_ctx": 4096,      # Full context window
    "repeat_penalty": 1.0 # No repeat suppression — SQL has repeated keywords
}
```

Memory extraction uses a slightly higher temperature (0.1) because the task benefits from minor paraphrase variation when generalising facts.

### Memory Extraction Prompt

The extraction prompt uses a strict output format to make parsing reliable without regex:

```
You extract user preferences and custom terminology from a single user message
for a Text-to-SQL system. Output ONLY facts that represent an explicit user
preference, a custom term definition, or a custom metric definition.
Do NOT extract facts that are just column names, table names, or SQL results.

Format each fact on its own line as:
[PREFERENCE] <explicit filter the user wants applied to all future queries>
[TERM] <custom term and its definition>
[METRIC] <custom calculation or KPI definition>

If there is nothing to extract, output exactly: NONE

User message: {user_msg}

Facts (or NONE):
```

Output is parsed line by line — only lines containing a valid tag (`[PREFERENCE]`, `[TERM]`, `[METRIC]`, `[ENTITY]`) with meaningful content (>5 chars after the tag) are accepted. A maximum of 2 facts per extraction call prevents the model from over-extracting on long messages.

### Memory Operation Classification Prompt

When a new fact has 0.70–0.95 cosine similarity with an existing memory, the LLM is asked to classify the relationship. The prompt is intentionally minimal to prevent the model from overthinking:

```
Compare these two pieces of information:
Existing: {existing_content}
New: {new_fact}

Respond with exactly one word:
- DELETE if the new information contradicts the existing one and should replace the old
- UPDATE if the new information enhances the old
- NOOP if they say the same thing

Decision:
```

The response is `.strip().upper()` and validated against the three allowed values — any other output defaults to `NOOP` (conservative).

### Preference Detection

Before reaching the LLM, every user message is classified by a regex-based preference detector. This avoids wasting LLM calls on messages that are clearly data queries, and correctly routes preference statements before they reach the SQL pipeline. Patterns include:

```python
r"i\s+(?:am\s+)?(?:only\s+)?interested\s+in",
r"i\s+(don't|do not)\s+want",
r"always\s+show", r"never\s+show",
r"define\s+.*\s+as", r".*\s+means\s+.*",
r"from\s+now\s+on", r"going\s+forward",
```

A secondary gate prevents false positives: if the message also contains question words (`what`, `show me`, `list`, `count`, etc.), it is routed to the SQL pipeline even if a preference pattern matches.

---

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- PostgreSQL 14+ with `pgvector` extension
- Ollama for local LLM deployment

### 1. Clone the Repository

```bash
git clone https://github.com/Aunkit/text2sql-memory.git
cd text2sql-memory
```

### 2. Install Dependencies

**Using uv (recommended)**
```bash
uv pip install -e .
```

**Using Conda**
```bash
chmod +x setup_conda.sh
./setup_conda.sh
conda activate text2sql-memory
```

**Using pip**
```bash
pip install -e .
```

### 3. Setup PostgreSQL

```bash
# Install pgvector extension
sudo apt-get install postgresql-14-pgvector  # Ubuntu/Debian
# or
brew install pgvector  # macOS

# Create database and load sample schema + data
createdb testdb
psql -d testdb -f test_db_setup.sql
```

### 4. Install and Start Ollama

```bash
# Install Ollama
curl -fsSL https://ollama.ai/install.sh | sh

# Pull the recommended model
ollama pull gsxr/one:latest   # qwen2.5-coder:7b — best SQL quality

# Start the server (keep this terminal open)
ollama serve
```

### 5. Configure Environment

Create a `.env` file in the project root:

```env
TARGET_DB_CONNECTION=postgresql://postgres:password@localhost:5432/testdb
MEMORY_DB_CONNECTION=postgresql://postgres:password@localhost:5432/testdb
LLM_BASE_URL=http://localhost:11434
LLM_MODEL=gsxr/one:latest
DEFAULT_SCHEMA=public
```

> If `MEMORY_DB_CONNECTION` is empty, the system uses JSON file storage for memories (good for development).

### 6. Run

```bash
python gradio_frontend.py
```

Open `http://localhost:7860` in your browser.

---

## ⚙️ Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `TARGET_DB_CONNECTION` | PostgreSQL connection string for business data | `postgresql://postgres:password@localhost:5432/testdb` |
| `MEMORY_DB_CONNECTION` | PostgreSQL connection for memory storage (empty = JSON files) | `""` |
| `LLM_BASE_URL` | Ollama API endpoint | `http://localhost:11434` |
| `LLM_MODEL` | LLM model name | `gsxr/one:latest` |
| `DEFAULT_SCHEMA` | Default PostgreSQL schema to load | `public` |

### Supported LLM Models

All models are called via Ollama's `/api/chat` endpoint, which works with any instruction-tuned model.

| Model | Speed | SQL Quality | Notes |
|-------|-------|-------------|-------|
| `gsxr/one:latest` | ⚡ Fast | Excellent | **Recommended** — qwen2.5-coder:7b |
| `qwen2.5-coder:7b` | ⚡ Fast | Excellent | Same model via official tag |
| `codellama:7b` | ⚡ Fast | Good | Solid alternative |
| `qwen2.5:3b` | ⚡⚡ Very fast | Moderate | For low-memory machines |
| `qwen3:4b` | ⚡ Fast | Good | Good balance of speed and quality |

---

## 💻 Usage

### Workflow

1. **Login** — enter a username (each user gets isolated memory)
2. **Load Schema** — the system introspects your database automatically
3. **Set Preferences** — teach the system what you care about
4. **Ask Questions** — natural language queries with automatic preference application
5. **Review Memory** — see what the system has learned in the Memory Bank panel

### Example Session

```
User: "I only want to see delivered orders"
→ ✅ Preference saved to memory

User: "Show me all orders"
→ SELECT order_id, customer_id, status, order_date, total_amount, payment_method
  FROM orders
  WHERE status = 'delivered'               ← auto-applied preference
  LIMIT 20;

User: "Define big spenders as customers with total spend over 50000"
→ ✅ Terminology saved to memory

User: "Show me customers from India"
→ SELECT customer_id, name, email, city, country, segment
  FROM customers                           ← no unnecessary JOIN
  WHERE country = 'India'
  LIMIT 20;
```

### Programmatic Usage

```python
from text2sql_chatbot import Text2SQLChatbot

# Initialize
chatbot = Text2SQLChatbot(
    target_db_connection="postgresql://user:pass@localhost/testdb",
    memory_db_connection="postgresql://user:pass@localhost/memorydb",
    llm_base_url="http://localhost:11434",
    llm_model="gsxr/one:latest"
)

# Set user and load database
chatbot.set_user("analyst_1")
success, msg = chatbot.initialize_database("public")

# Process a query
result = chatbot.process_message("Show me all delivered orders")

print(result['sql_query'])       # Generated SQL
print(result['results'])         # Query results
print(result['memories_used'])   # Applied memories
print(result['new_memories'])    # Newly learned facts
print(result['success'])         # True/False
```

---

## 📁 Project Structure

```
text2sql-memory/
│
├── memory_agent_opensource.py     # Mem0-inspired memory system
│                                  # Memory, PostgresMemoryStore,
│                                  # JSONMemoryStore, MemoryAgent
│
├── text2sql_chatbot.py            # Main chatbot orchestrator
│                                  # Text2SQLChatbot (schema-grounded
│                                  # SQL generation + validation)
│
├── postgreSQL_data_client.py      # Database connector
│                                  # PostgresDataClient (introspection,
│                                  # FK discovery, query execution)
│
├── gradio_frontend.py             # Web interface
│                                  # Gradio Blocks app with chat,
│                                  # memory bank, SQL display
│
├── test_db_setup.sql              # Sample DB schema + realistic data
├── detailed_test_setup.py         # Component integration tests
├── main.py                        # CLI entry point
├── pyproject.toml                 # Project metadata & dependencies
├── setup_conda.sh                 # Conda environment setup script
├── uv.lock                        # Dependency lock file
└── .gitignore
```

---

## 📚 API Reference

### Text2SQLChatbot

```python
chatbot = Text2SQLChatbot(
    target_db_connection: str,           # PostgreSQL connection for business data
    memory_db_connection: str = "",      # PostgreSQL connection for memories (empty = JSON)
    llm_base_url: str = "http://localhost:11434",
    llm_model: str = "gsxr/one:latest",
    schema_name: str = "public"
)
```

| Method | Description | Returns |
|--------|-------------|---------|
| `set_user(username)` | Set active user, load their memory context | `None` |
| `initialize_database(schema_name)` | Introspect schema, build lookups | `(bool, str)` |
| `process_message(user_message)` | Route to preference handler or SQL pipeline | `Dict` |
| `get_user_memories()` | Get memories organised by category | `Dict[str, List[str]]` |
| `get_user_memories_detailed()` | Get memories with IDs for deletion | `Dict[str, List[Dict]]` |
| `delete_memory(memory_id)` | Delete a specific memory | `bool` |
| `validate_setup()` | Test all connections (DB, LLM, memory) | `Dict` |
| `test_connections()` | Detailed connection test results | `Dict` |

### MemoryAgent

```python
agent = MemoryAgent(
    use_postgres: bool = False,
    postgres_conn_string: str = "",
    llm_base_url: str = "http://localhost:11434",
    llm_model: str = "gsxr/one:latest"
)
```

| Method | Description | Returns |
|--------|-------------|---------|
| `load_user_context(user_id)` | Load all memories/context for a user | `None` |
| `extract_memories(message_pair)` | Extract facts from user message | `List[str]` |
| `update_memories(candidate_facts)` | Run Mem0 update pipeline (ADD/UPDATE/DELETE/NOOP) | `None` |
| `retrieve_relevant_memories(query)` | Semantic search for relevant memories | `List[str]` |
| `add_message_to_history(role, content)` | Add to recent message window | `None` |
| `update_conversation_summary()` | Compress conversation history | `None` |

---

## 🧪 Development

### Running Tests

```bash
# Component integration test
python detailed_test_setup.py

# Run with pytest
pytest --cov=. --cov-report=html
```

### Code Quality

```bash
black .       # Format
isort .       # Sort imports
flake8 .      # Lint
mypy .        # Type check
```

### Development Install

```bash
uv pip install -e ".[dev,test]"
pre-commit install
```

---

## 🔧 Troubleshooting

### Ollama Connection Failed

```bash
curl http://localhost:11434/api/tags    # Check if Ollama is running
ollama serve                            # Start the server
ollama list                             # Check downloaded models
ollama pull gsxr/one:latest             # Download recommended model
```

### Empty LLM Responses

The system uses Ollama's `/api/chat` endpoint which works with all instruction-tuned models. If you still see `❌ Empty LLM response`:

```bash
# Verify the model is available
ollama list

# Test the chat endpoint directly
curl http://localhost:11434/api/chat -d '{
  "model": "gsxr/one:latest",
  "messages": [{"role": "user", "content": "Say hello"}],
  "stream": false
}'
```

The system includes a schema-aware SQL fallback that fires automatically if the LLM fails.

### PostgreSQL / pgvector Issues

```bash
psql -h localhost -U postgres -d testdb                    # Test connection
psql -d testdb -c "CREATE EXTENSION IF NOT EXISTS vector;" # Enable pgvector
psql -d testdb -c "\dt"                                    # List tables
```

### Memory Not Persisting

```bash
# PostgreSQL memory storage
psql -d testdb -c "SELECT COUNT(*) FROM memories;"

# JSON file storage (development mode)
ls memory_data/<username>/
```

### Preference Not Being Detected

Phrases like "I am only interested in..." or "I prefer..." are automatically routed to the preference handler. If a preference is being executed as a SQL query instead, check the server logs for `ROUTED ->`. Supported patterns include:

- `I am (only) interested in ...`
- `I prefer / I want to see ...`
- `Always show / Never show ...`
- `Define X as ...` / `X means ...`
- `Let's call X as ...`

---

## 🔭 Future Work

### 🔀 User-Selectable LLM Models

The single most impactful planned feature is exposing model selection directly in the Gradio UI. Currently the model is set once via the `LLM_MODEL` environment variable. The plan is to:

- Add a model dropdown to the login/configuration panel that lists all models currently available in the local Ollama instance (fetched live from `/api/tags`)
- Allow switching models mid-session without restarting
- Display per-model capability notes (e.g. context window size, SQL specialisation) to help users make an informed choice
- Persist the user's preferred model as part of their memory profile so it is automatically selected on next login

This would make it trivial to compare how different models perform on the same schema and queries — a useful evaluation tool in itself.

### Other Planned Improvements

- **Connection pooling**: Replace per-operation `psycopg2.connect()` calls with `SimpleConnectionPool` for better throughput under concurrent users
- **Memory quality gating**: Add a confidence threshold to memory extraction — only store memories from queries that returned non-empty results, reducing noise from failed or ambiguous queries
- **Cross-session memory summarisation**: Periodically compress old memories into higher-level summaries (e.g. "User consistently works with order analytics") to keep the memory store lean over many sessions
- **Schema change detection**: Detect when a table or column referenced in a stored memory no longer exists in the current schema, and flag or remove stale memories automatically
- **Additional data connectors**: Pluggable client implementations for Snowflake, Databricks, MySQL, and SQL Server — the `PostgresDataClient` interface is already designed to be swapped out without touching the memory layer

---

## 📄 License

This project is licensed under the MIT License.

---

## 🙏 Acknowledgments

- **[Mem0](https://mem0.ai/research)**: Inspiration for the two-phase memory architecture
- **[Ollama](https://ollama.ai/)**: Local LLM deployment framework
- **[pgvector](https://github.com/pgvector/pgvector)**: Vector similarity search in PostgreSQL
- **[Gradio](https://gradio.app/)**: Web interface framework
- **[sentence-transformers](https://www.sbert.net/)**: Text embedding models

---

**⭐ Star this repo if you find it useful!**
