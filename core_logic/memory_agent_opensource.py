import os
import json
import time
import numpy as np
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime
from sentence_transformers import SentenceTransformer
import requests
import psycopg2
import psycopg2.extras

class Memory:
    """
    Intelligent Memory Unit for Text2SQL Personalization
    
    A structured container that captures and preserves user-specific knowledge 
    for Text2SQL systems. Each Memory represents a single piece of learned 
    information that helps personalize database interactions across sessions.
    
    Core Attributes:
        - id: Unique database identifier for persistence and updates
        - content: The actual knowledge stored (e.g., "User prefers active customers only")
        - created_at: Timestamp for memory aging and relevance tracking
        - source: Origin context (conversation, initialization, import)
        - metadata: Structured tags for memory categorization and retrieval
        - embedding: Vector representation enabling semantic similarity search
    
    Memory Types (via metadata):
        • PREFERENCE: User's filtering and display preferences
        • TERM: Custom terminology and abbreviations  
        • METRIC: User-defined calculations and KPIs
        • ENTITY: Frequently referenced database objects
    """
    def __init__(self, id: Optional[int] = None, content: str = "", created_at: float = 0,
                 source: str = "", metadata: Optional[Dict] = None, embedding: Optional[List[float]] = None):
        self.id = id
        self.content = content
        self.created_at = created_at or time.time()
        self.source = source
        self.metadata = metadata if metadata is not None else {}
        self.embedding = embedding if embedding is not None else []


class PostgresMemoryStore:
    """
    PostgreSQL-based memory storage with pgvector for similarity search.
    
    Why PostgreSQL + pgvector?
    - pgvector allows us to store embeddings as native vector types
    - Enables fast similarity searches using indexes
    - User isolation through user_id field
    - Production-ready with ACID guarantees
    """

    def __init__(self, connection_string: str):
        self.conn_string = connection_string
        self.embedding_dim = 384 # Default dimension for all-MiniLm-L6-v2 embeddings
        self._init_db()

    def _init_db(self):
        """
        Initialize database tables for memory storage.
        
        We create three tables:
        1. memories: Stores actual memory content with embeddings
        2. conversation_summaries: Compressed conversation history
        3. recent_messages: Last N messages for immediate context
        """
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor()

            # Enable pgvector extension
            cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
            conn.commit()

            # Create memories table with user isolation
            cursor.execute(f"""
                CREATE TABLE IF NOT EXISTS memories (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at FLOAT NOT NULL,
                    source TEXT,
                    metadata JSONB DEFAULT '{{}}'::JSONB,
                    embedding VECTOR(384)
                );
            """)

            # Create HNSW index for fast similarity search
            # HNSW = Hierarchical Navigable Small World - efficient for high-dimensional vectors
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS memories_embedding_idx
                ON memories USING hnsw (embedding vector_cosine_ops);
                """)
            
            # Index on user_id for efficient filtering
            cursor.execute("CREATE INDEX IF NOT EXISTS memories_user_id_idx on memories(user_id);")

            # Conversation summaries table
            cursor.execute("""
                    CREATE TABLE IF NOT EXISTS conversation_summaries (
                           id SERIAL PRIMARY KEY,
                           user_id TEXT NOT NULL,
                           summary TEXT NOT NULL,
                           updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                           """)
            cursor.execute("CREATE INDEX IF NOT EXISTS summaries_user_id_idx ON conversation_summaries(user_id);")

            # Recent messages table
            cursor.execute("""
                    CREATE TABLE IF NOT EXISTS recent_messages (
                           id SERIAL PRIMARY KEY,
                           user_id TEXT NOT NULL,
                           messages TEXT NOT NULL,
                           created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                           """)
            cursor.execute("CREATE INDEX IF NOT EXISTS messages_user_id_idx ON recent_messages(user_id);")

            conn.commit()
            cursor.close()
            conn.close()

            print("PostgreSQL database initialized with pgvector.")

        except ImportError:
            print("PostgreSQL drivers are not installed. Install with: pip install psycopg2-binary")
            raise
        except Exception as e:
            print(f"Error initializing PostgreSQL database: {e}")
            raise

    def load_memories(self, user_id: str) -> List[Memory]:
        """Load all memories for a specific user."""
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Only load memories for the specific user
            cursor.execute(
                "SELECT id, content, created_at, source, metadata, embedding FROM memories WHERE user_id = %s ORDER BY created_at DESC;",
                (user_id,)
            )
            rows = cursor.fetchall()

            memories = []
            for row in rows:
                memory = Memory(
                    id=row['id'],
                    content=row['content'],
                    created_at=row['created_at'],
                    source=row['source'],
                    metadata=row['metadata'] or {},
                    embedding=list(row['embedding']) if row['embedding'] is not None else []
                )
                memories.append(memory)

            cursor.close()
            conn.close()

            return memories
        except Exception as e:
            print(f"Error loading memories: {e}")
            return []
        
    def save_memory(self, memory: Memory, user_id: str) -> int:
        """Save a memory for a specific user."""
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor()

            # Ensure embedding is properly formatted
            embedding_to_save = None
            if memory.embedding:
                embedding_str = '[' + ','.join(map(str, memory.embedding)) + ']'
                embedding_to_save = embedding_str

            if memory.id is None:
                # Insert new memory
                cursor.execute("""
                    INSERT INTO memories (user_id, content, created_at, source, metadata, embedding)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    RETURNING id;
                """, (user_id, memory.content, memory.created_at, memory.source,
                      json.dumps(memory.metadata), embedding_to_save)
                )
                
                result = cursor.fetchone()
                if result is not None:
                    memory.id = result[0]
                else:
                    print("Failed to get ID for new memory")
                    return -1
            else:
                # Update existing memory
                cursor.execute(
                    """UPDATE memories SET content = %s, created_at = %s, source = %s, metadata = %s, embedding = %s::vector WHERE id = %s AND user_id = %s;""",
                    (memory.content, memory.created_at, memory.source,
                     json.dumps(memory.metadata), memory.embedding, memory.id, user_id)
                )
            
            conn.commit()
            cursor.close()
            conn.close()

            return memory.id if memory.id is not None else -1
        except Exception as e:
            print(f"Error saving memory: {e}")
            return -1
    
    def delete_memory(self, memory_id: int, user_id: str) -> bool:
        """Delete a memory, ensuring it belongs to the specificied user."""
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor()

            cursor.execute("DELETE FROM memories WHERE id = %s AND user_id = %s", (memory_id, user_id))
            deleted_rows = cursor.rowcount
            conn.commit()
            cursor.close()
            conn.close()

            return deleted_rows > 0
        except Exception as e:
            print(f"Error deleting memory: {e}")
            return False
        
    def find_similar_memories(self, embedding: List[float], user_id: str, top_k: int = 5) -> List[Tuple[Memory, float]]:
        """
        Find memories similar to the given embedding using pgvector.
        
        This uses cosine similarity: <=> operator in pgvector
        Returns memories with their similarity scores (0-1, higher is better)
        """
        try:
            if not embedding:
                return []
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            embedding_str = '[' + ','.join(map(str, embedding)) + ']'

            # pgvector's <=> operator computes cosine distance
            # We convert to similarity by subtracting from 1
            cursor.execute("""
            SELECT id, content, created_at, source, metadata, embedding,
                   (1 - (embedding <=> %s::vector)) AS similarity
            FROM memories
            WHERE user_id = %s AND embedding IS NOT NULL
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
            """, (embedding_str, user_id, embedding_str, top_k))

            rows = cursor.fetchall()

            results = []
            for row in rows:
                memory = Memory(
                    id=row['id'],
                    content=row['content'],
                    created_at=row['created_at'],
                    source=row['source'],
                    metadata=row['metadata'] or {},
                    embedding=list(row['embedding']) if row['embedding'] else []
                )
                similarity = float(row['similarity']) if row['similarity'] is not None else 0.0
                results.append((memory, similarity))

            cursor.close()
            conn.close()

            return results
        except Exception as e:
            print(f"Error finding similar memories: {e}")
            return []
        
    def get_conversation_summary(self, user_id: str) -> str:
        """Get the latest conversation summary for a user"""
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor()

            cursor.execute("SELECT summary FROM conversation_summaries WHERE user_id = %s ORDER BY updated_at DESC LIMIT 1", (user_id,))
            row = cursor.fetchone()

            cursor.close()
            conn.close()

            return row[0] if row else ""
        except Exception as e:
            print(f"Error getting conversation summary: {e}")
            return ""
        
    def save_conversation_summary(self, summary: str, user_id: str) -> bool:
        """Save a conversation summary for a user."""
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor()

            cursor.execute("INSERT INTO conversation_summaries (user_id, summary) VALUES (%s, %s)", (user_id, summary))

            conn.commit()
            cursor.close()
            conn.close()

            return True
        except Exception as e:
            print(f"Error saving conversation summary: {e}")
            return False
        
    def get_recent_messages(self, user_id: str, limit: int = 10) -> List[str]:
        """Get the most recent messages for a user."""
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor()

            cursor.execute("SELECT messages FROM recent_messages WHERE user_id = %s ORDER BY created_at DESC LIMIT %s", (user_id, limit))
            rows = cursor.fetchall()

            cursor.close()
            conn.close()

            return [row[0] for row in rows]
        except Exception as e:
            print(f"Error getting recent messages: {e}")
            return []
    
    def save_message(self, message: str, user_id: str) -> bool:
        """Save a message to recent history."""
        try:
            conn = psycopg2.connect(self.conn_string)
            cursor = conn.cursor()

            cursor.execute("INSERT INTO recent_messages (user_id, messages) VALUES (%s, %s)", (user_id, message))

            # Optional: Clean up old messages to keep table size manageable
            cursor.execute("""
                DELETE FROM recent_messages 
                WHERE user_id = %s AND id NOT IN (
                    SELECT id FROM recent_messages 
                    WHERE user_id = %s 
                    ORDER BY created_at DESC 
                    LIMIT 20
                )
            """, (user_id, user_id))

            conn.commit()
            cursor.close()
            conn.close()

            return True
        except Exception as e:
            print(f"Error saving message: {e}")
            return False

class JSONMemoryStore:
    """
    JSON-based memory storage for development/testing.
    
    This is a simpler alternative to PostgreSQL that stores everything in JSON files.
    Good for:
    - Local development
    - Testing
    - Small-scale deployments
    
    Limitations:
    - No concurrent access handling
    - Slower similarity search (has to load all memories)
    - No built-in user isolation (we handle it in code)
    """
    def __init__(self, base_dir: str = "memory_data"):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _get_user_file(self, user_id: str, file_type: str) -> str:
        """Get the file path for a user's data."""
        user_dir = os.path.join(self.base_dir, user_id)
        os.makedirs(user_dir, exist_ok=True)
        return os.path.join(user_dir, f"{file_type}.json")

    def load_memories(self, user_id: str) -> List[Memory]:
        """Load memories from JSON file."""
        file_path = self._get_user_file(user_id, "memories")
        
        try:
            if not os.path.exists(file_path):
                return []
                
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                
            memories = []
            for item in data:
                memory = Memory(
                    id=item.get("id"),
                    content=item["content"],
                    created_at=item["created_at"],
                    source=item.get("source", ""),
                    metadata=item.get("metadata", {}),
                    embedding=item.get("embedding", [])
                )
                memories.append(memory)
                
            return memories
        except Exception as e:
            print(f"Error loading memories from JSON: {e}")
            return []

    def save_memory(self, memory: Memory, user_id: str) -> int:
        """Save a memory to JSON file."""
        memories = self.load_memories(user_id)
        
        if memory.id is None:
            # Generate new ID
            max_id = max([m.id for m in memories if m.id is not None], default=0)
            memory.id = max_id + 1
            memories.append(memory)
        else:
            # Update existing
            for i, m in enumerate(memories):
                if m.id == memory.id:
                    memories[i] = memory
                    break
        
        # Save to file
        data = []
        for mem in memories:
            data.append({
                "id": mem.id,
                "content": mem.content,
                "created_at": mem.created_at,
                "source": mem.source,
                "metadata": mem.metadata,
                "embedding": mem.embedding
            })
        
        file_path = self._get_user_file(user_id, "memories")
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        
        return memory.id

    def delete_memory(self, memory_id: int, user_id: str) -> bool:
        """Delete a memory from JSON file."""
        memories = self.load_memories(user_id)
        original_count = len(memories)
        memories = [m for m in memories if m.id != memory_id]

        if len(memories) == original_count:
            return False
        
        # Save updated list
        data = []
        for mem in memories:
            data.append({
                "id": mem.id,
                "content": mem.content,
                "created_at": mem.created_at,
                "source": mem.source,
                "metadata": mem.metadata,
                "embedding": mem.embedding
            })
        
        file_path = self._get_user_file(user_id, "memories")
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=2)
        
        return True
    
    def find_similar_memories(self, embedding: List[float], user_id: str, top_k: int = 5) -> List[Tuple[Memory, float]]:
        """
        Find similar memories using cosine similarity.
        
        Since we don't have pgvector in JSON mode, we calculate similarity manually.
        This is slower but works for development.
        """
        if not embedding:
            return []
        
        memories = self.load_memories(user_id)
        
        similarities = []
        for memory in memories:
            if memory.embedding:
                # Calculate cosine similarity
                try:
                    norm1 = np.linalg.norm(embedding)
                    norm2 = np.linalg.norm(memory.embedding)
                
                    if norm1 > 0 and norm2 > 0:
                        similarity = np.dot(embedding, memory.embedding) / (norm1 * norm2)
                    else:
                        similarity = 0.0
                    
                    similarities.append((memory, similarity))
                except Exception as e:
                    print(f"Error calculating similarity for nmemory {memory.id}: {e}")
                    continue
        
        # Sort by similarity (highest first)
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        return similarities[:top_k]

    def get_conversation_summary(self, user_id: str) -> str:
        """Get conversation summary from JSON."""
        file_path = self._get_user_file(user_id, "summaries")
        
        try:
            if not os.path.exists(file_path):
                return ""
                
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            if data:
                # Return the latest summary
                return data[-1]["summary"]
            return ""
        except Exception as e:
            print(f"Error getting conversation summary: {e}")
            return ""

    def save_conversation_summary(self, summary: str, user_id: str) -> bool:
        """Save conversation summary to JSON."""
        file_path = self._get_user_file(user_id, "summaries")
        
        try:
            summaries = []
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    summaries = json.load(f)
            
            summaries.append({
                "summary": summary,
                "timestamp": time.time()
            })
            
            with open(file_path, 'w') as f:
                json.dump(summaries, f, indent=2)
                
            return True
        except Exception as e:
            print(f"Error saving conversation summary: {e}")
            return False

    def get_recent_messages(self, user_id: str, limit: int = 10) -> List[str]:
        """Get recent messages from JSON."""
        file_path = self._get_user_file(user_id, "messages")
        
        try:
            if not os.path.exists(file_path):
                return []
                
            with open(file_path, 'r') as f:
                messages = json.load(f)
            
            # Return the most recent messages
            return [msg["message"] for msg in messages[-limit:]]
        except Exception as e:
            print(f"Error getting recent messages: {e}")
            return []
    
    def save_message(self, message: str, user_id: str) -> bool:
        """Save message to JSON."""
        file_path = self._get_user_file(user_id, "messages")
        
        try:
            messages = []
            if os.path.exists(file_path):
                with open(file_path, 'r') as f:
                    messages = json.load(f)
            
            messages.append({
                "message": message,
                "timestamp": time.time()
            })
            
            # Keep only last 20 messages
            messages = messages[-20:]
            
            with open(file_path, 'w') as f:
                json.dump(messages, f, indent=2)
                
            return True
        except Exception as e:
            print(f"Error saving message: {e}")
            return False


class MemoryAgent:
    """
    The core memory agent inspired by Mem0 architecture.
    
    This agent orchestrates:
    1. Memory extraction from conversations
    2. Memory storage and retrieval
    3. Memory updates (add, update, delete operations)
    4. Context management (summaries, recent messages)
    
    Key concepts:
    - User isolation: Each user has their own memory space
    - Semantic search: Find relevant memories using embeddings
    - Memory categories: Preferences, terminology, metrics, entities
    """

    def __init__(self, use_postgres: bool = False, postgres_conn_string: str = "", llm_base_url: str = "http://localhost:11434", llm_model: str = "codellama:7b"):
        """
        Initialize the memory agent.
        
        Args:
            use_postgres: Whether to use PostgreSQL (True) or JSON (False)
            postgres_conn_string: PostgreSQL connection string
            llm_base_url: Base URL for LLM API (default: Ollama)
            llm_model: Model name to use for LLM operations
        """
        # Initialize storage backend
        if use_postgres and postgres_conn_string:
            try:
                self.store = PostgresMemoryStore(postgres_conn_string)
                print("Using PostgreSQL for memory storage.")
            except ImportError:
                print("PostgreSQL drivers not installed. Falling back to JSON storage.")
                self.store = JSONMemoryStore()
        else:
            self.store = JSONMemoryStore()
            print("Using JSON for memory storage.")

        # Initialize embedding model
        # all-MiniLm-L6-v2 is a good balance of speed and quality
        try:
            self.embedder = SentenceTransformer('all-MiniLm-L6-v2')
            print("Loaded embedding model: all-MiniLM-L6-v2")
        except Exception as e:
            print(f"Error loading embedding model: {e}")
            self.embedder = None

        # LLM configuration
        self.llm_base_url = llm_base_url
        self.llm_model = llm_model

        # User context
        self.current_user_id = None
        self.memories = []
        self.conversation_summary = ""
        self.recent_messages = []
        self.max_recent_messages = 10  # Limit for recent messages

        # Database schema
        self.db_schema = None

    def load_user_context(self, user_id: str):
        """
        Load all context for a specific user.
        
        This is called when switching users or starting a new session.
        Loads:
        - All memories for the user
        - Conversation summary
        - Recent message history
        """
        self.current_user_id = user_id
        self.memories = self.store.load_memories(user_id)
        self.conversation_summary = self.store.get_conversation_summary(user_id)
        self.recent_messages = self.store.get_recent_messages(user_id, self.max_recent_messages)

        print(f"Loaded {len(self.memories)} memories for user {user_id}.")

    def _create_embedding(self, text: str) -> List[float]:
        """
        Create embedding for text using sentence-transformers.
        
        Embeddings are dense vector representations that capture semantic meaning.
        Similar texts will have similar embeddings (high cosine similarity).
        """
        if not self.embedder:
            print("Embedding model not available")
            return [0.0] * 384
        try:
            # encode() returns a numpy array, convert to list for storage
            embedding = self.embedder.encode(text)
            return embedding.tolist()
        except Exception as e:
            print(f"Error creating embedding: {e}")
            return [0.0] * 384
        
    def _call_llm(self, prompt: str) -> str:
        """
        Call the local LLM via Ollama /api/chat.

        Uses chat format so it works with instruction-tuned models
        (qwen2.5-coder, qwen3, etc.) as well as codellama.
        The old /api/generate endpoint returned empty responses for
        instruction-tuned models which expect a chat turn structure.
        """
        try:
            response = requests.post(
                f"{self.llm_base_url}/api/chat",
                json={
                    "model": self.llm_model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 200,
                        "num_ctx": 4096,
                    },
                },
                timeout=60,
            )

            if response.status_code == 200:
                result = response.json().get("message", {}).get("content", "").strip()
                if result:
                    return result
                print("LLM returned empty response")
                return ""
            else:
                print(f"LLM API error: {response.status_code}: {response.text[:200]}")
                return ""

        except requests.exceptions.Timeout:
            print("LLM request timed out after 60 seconds")
            return ""
        except requests.exceptions.ConnectionError:
            print(f"Cannot connect to LLM at {self.llm_base_url}. Is Ollama running?")
            return ""
        except Exception as e:
            print(f"Error calling LLM: {e}")
            return ""

    def extract_memories(self, message_pair: List[str]) -> List[str]:
        """
        Extract user preferences and terminology from a conversation turn.

        Only the USER message is analysed — the AI response is often a SQL
        results table whose column names would be extracted as fake memories.
        """
        user_msg = message_pair[0].strip() if message_pair else ""
        if not user_msg:
            return []

        prompt = (
            "You extract user preferences and custom terminology from a single user message "
            "for a Text-to-SQL system. Output ONLY facts that represent an explicit user "
            "preference, a custom term definition, or a custom metric definition. "
            "Do NOT extract facts that are just column names, table names, or SQL results.\n\n"
            "Format each fact on its own line as:\n"
            "[PREFERENCE] <explicit filter the user wants applied to all future queries>\n"
            "[TERM] <custom term and its definition>\n"
            "[METRIC] <custom calculation or KPI definition>\n\n"
            "If there is nothing to extract, output exactly: NONE\n\n"
            f"User message: {user_msg}\n\n"
            "Facts (or NONE):"
        )

        response = self._call_llm(prompt)

        if not response or response.strip().upper() == "NONE":
            return []

        memories = []
        for line in response.strip().split('\n'):
            line = line.strip()
            if not line:
                continue
            if any(tag in line for tag in ("[PREFERENCE]", "[TERM]", "[METRIC]", "[ENTITY]")):
                # Minimum quality bar: must have actual content after the tag
                tag_end = line.index(']') + 1
                content = line[tag_end:].strip()
                if len(content) > 5:
                    memories.append(line)

        return memories[:2]
    
    def update_memories(self, candidate_facts: List[str]):
        """
        Update the memory database with new facts.
        
        This is the "update phase" of the Mem0 architecture.
        For each candidate fact, we:
        1. Create an embedding
        2. Find similar existing memories
        3. Decide on operation: ADD, UPDATE, DELETE, or NOOP
        4. Execute the operation
        """

        if not self.current_user_id:
            print(" No user context loaded.")
            return

        for fact in candidate_facts:
            # Create embedding for the new fact
            embedding = self._create_embedding(fact)

            # Find similar existing memories
            similar_memories = self._find_similar_memories(embedding, top_k=3)

            # Determine operation
            operation = self._determine_operation(fact, similar_memories)

            if operation == "ADD":
                # Create new memory
                memory = Memory(
                    content=fact,
                    created_at=time.time(),
                    source="conversation",
                    embedding=embedding
                )

                # Extract memory type from tag
                if '[PREFERENCE]' in fact:
                    memory.metadata['type'] = 'preference'
                elif '[TERM]' in fact:
                    memory.metadata['type'] = 'term'
                elif '[METRIC]' in fact:
                    memory.metadata['type'] = 'metric'
                elif '[ENTITY]' in fact:
                    memory.metadata['type'] = 'entity'

                memory_id = self.store.save_memory(memory, self.current_user_id)
                if memory_id > 0:
                    memory.id = memory_id
                    self.memories.append(memory)
                    print(f"+ Added memory: {fact}")
            
            elif operation == "UPDATE" and similar_memories:
                # Update existing memory
                memory_to_update = similar_memories[0][0]
                memory_to_update.content = fact
                memory_to_update.embedding = embedding
                self.store.save_memory(memory_to_update, self.current_user_id)
                print(f"* Updated memory: {fact}")
            
            elif operation == "DELETE" and similar_memories:
                # Delete contradictory memory
                memory_to_delete = similar_memories[0][0]
                if memory_to_delete.id:
                    self.store.delete_memory(memory_to_delete.id, self.current_user_id)
                    self.memories = [m for m in self.memories if m.id != memory_to_delete.id]
                    print(f"- Deleted memory: {memory_to_delete.content}")
    
    def _find_similar_memories(self, query_embedding: List[float], top_k: int = 5) -> List[Tuple[Memory, float]]:
        """Find memories similar to the query embedding."""
        if self.current_user_id:
            return self.store.find_similar_memories(query_embedding, self.current_user_id, top_k)
        return []
    
    def _determine_operation(self, new_fact: str, similar_memories: List[Tuple[Memory, float]]) -> str:
        """
        Determine what operation to perform with a new fact.
        
        Operations:
        - ADD: No similar memory exists
        - UPDATE: Similar memory exists and new fact enhances it
        - DELETE: New fact contradicts existing memory
        - NOOP: New fact is redundant
        """
        if not similar_memories:
            return "ADD"
        
        # Check similarity threshold
        top_similarity = similar_memories[0][1]

        if top_similarity > 0.95:
            # Very similar, consider it redundant
            return "NOOP"
        
        if top_similarity > 0.7:
            # Similar enough to need LLM judgement
            existing_content = similar_memories[0][0].content

            prompt = f"""Compare these two pieces of information:
Existing: {existing_content}
New: {new_fact}

Respond with exactly one word:
- DELETE if the new information contradicts the existing one and should replace the old
- UPDATE if the new information enhances the old
- NOOP if they say the same thing

Decision:"""
            
            response = self._call_llm(prompt).strip().upper()

            if response in ["DELETE", "UPDATE", "NOOP"]:
                return response
            return "NOOP"
        
        return "ADD"  # Not similar enough, treat as new fact
    
    def retrieve_relevant_memories(self, query: str, top_k: int = 5) -> List[str]:
        """
        Retrieve memories relevant to a query.
        
        This is used when processing a new user question to provide context.
        """
        if not self.current_user_id:
            return []
        
        query_embedding = self._create_embedding(query)
        similar_memories = self._find_similar_memories(query_embedding, top_k=top_k)

        return [memory.content for memory,_ in similar_memories]
    
    def update_conversation_summary(self):
        """
        Periodically update the conversation summary.
        
        This compressed representation helps maintain long-term context
        without keeping all messages.
        """
        if not self.current_user_id or not self.recent_messages:
            return
        
        prompt = f"""Summarize the key points from this database query conversation:
Focus on:
- What data the user is interested in
- Any patterns in their queries
- Important context for future interactions

Current summary: {self.conversation_summary}

Recent messages: {chr(10).join(self.recent_messages[-10:])}

Updated summary (2-3 sentences):"""
        new_summary = self._call_llm(prompt).strip()

        if new_summary:
            self.conversation_summary = new_summary
            self.store.save_conversation_summary(new_summary, self.current_user_id)

    def add_message_to_history(self, role: str, content: str):
        """
        Add a message to recent history.
        
        Maintains a rolling window of recent messages for immediate context.
        """
        if not self.current_user_id:
            return
        message = f"{role}: {content}"
        self.recent_messages.append(message)
        self.store.save_message(message, self.current_user_id)

        # Keep only recent messages in memory
        if len(self.recent_messages) > self.max_recent_messages:
            self.recent_messages = self.recent_messages[-self.max_recent_messages:]
    
    def set_db_schema(self, schema: Dict):
        """Store database schema information for SQL generation"""
        self.db_schema = schema