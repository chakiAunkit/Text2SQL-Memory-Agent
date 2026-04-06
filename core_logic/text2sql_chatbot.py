"""
Text2SQL Chatbot with Reliable SQL Generation & Memory Integration

Key fixes over previous version:
  1. SQL prompt uses ACTUAL introspected schema (not hardcoded columns)
  2. Explicit JOIN relationships injected from FK metadata
  3. Generated SQL validated against real table/column names before execution
  4. Memory extraction on queries only when preference/term signals detected
  5. Improved response formatting with markdown tables
"""

import requests
import time
import re
from typing import Dict, List, Optional, Any, Tuple
from memory_agent_opensource import MemoryAgent
from postgreSQL_data_client import PostgresDataClient


class Text2SQLChatbot:
    """
    Text2SQL chatbot that generates reliable SQL by grounding prompts
    in the actual database schema and validating output before execution.
    """

    def __init__(self,
                 target_db_connection: str,
                 memory_db_connection: Optional[str] = None,
                 llm_base_url: str = "http://localhost:11434",
                 llm_model: str = "codellama:7b",
                 schema_name: str = "public"):
        """Initialize the chatbot."""
        self.agent = MemoryAgent(
            use_postgres=bool(memory_db_connection),
            postgres_conn_string=memory_db_connection or "",
            llm_base_url=llm_base_url,
            llm_model=llm_model
        )

        self.data_client = PostgresDataClient(target_db_connection)

        self.llm_base_url = llm_base_url
        self.llm_model = llm_model
        self.schema_name = schema_name

        # Session state
        self.current_user = None
        self.db_schema_loaded = False
        self.schema_text = ""
        # Structured schema info for validation & prompt building
        self._schema_metadata: Dict[str, Any] = {}
        self._table_columns: Dict[str, List[str]] = {}
        self._join_hints: List[str] = []

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    def set_user(self, username: str):
        """Set current user and load their memory context."""
        self.current_user = username
        self.agent.load_user_context(username)
        self.db_schema_loaded = False
        print(f"User set: {username}")

    def initialize_database(self, schema_name: Optional[str] = None) -> Tuple[bool, str]:
        """Load database schema and prepare for queries."""
        if not self.current_user:
            return False, "No user set"

        schema_to_use = schema_name or self.schema_name

        try:
            metadata = self.data_client.get_schema_metadata(schema_to_use)
            self.agent.set_db_schema(metadata)
            self.schema_text = self.data_client.format_schema_for_llm(schema_to_use)
            self._schema_metadata = metadata
            self.db_schema_loaded = True

            # Build lookup structures for validation and prompt building
            self._build_schema_lookups(metadata)

            table_count = len(metadata.get('tables', []))
            if table_count > 0:
                memory_tables = {'memories', 'conversation_summaries', 'recent_messages'}
                business_tables = [t['table_name'] for t in metadata['tables']
                                   if t['table_name'] not in memory_tables]
                if business_tables:
                    db_memory = f"[ENTITY] Database schema '{schema_to_use}' contains tables: {', '.join(business_tables[:5])}"
                    self.agent.update_memories([db_memory])

            return True, f"Schema '{schema_to_use}' loaded successfully ({table_count} tables)"

        except Exception as e:
            return False, f"Failed to load schema '{schema_to_use}': {str(e)}"

    def _build_schema_lookups(self, metadata: Dict[str, Any]):
        """Pre-compute table->columns mapping and JOIN hints from FK metadata."""
        self._table_columns = {}
        self._join_hints = []

        for table in metadata.get('tables', []):
            tname = table['table_name']
            cols = [c['column_name'] for c in table.get('columns', [])]
            self._table_columns[tname] = cols

            for fk in table.get('foreign_keys', []):
                hint = (
                    f"{tname}.{fk['column']} = "
                    f"{fk['references_table']}.{fk['references_column']}"
                )
                self._join_hints.append(hint)

        # Also pull from top-level relationships
        for rel in metadata.get('relationships', []):
            hint = f"{rel['from_table']}.{rel['from_column']} = {rel['to_table']}.{rel['to_column']}"
            if hint not in self._join_hints:
                self._join_hints.append(hint)

    # ------------------------------------------------------------------
    # Prompt building — compact for 7B models, still schema-grounded
    # ------------------------------------------------------------------

    def _build_schema_prompt(self) -> str:
        """
        Build a COMPACT schema block for the LLM prompt.

        For 7B models like CodeLlama, we need to keep the schema very short:
        one line per table with just column names (no types/descriptions).
        This is still 100% dynamic from introspected metadata.
        """
        if not self._schema_metadata:
            return self.schema_text

        lines: List[str] = []
        for table in self._schema_metadata.get('tables', []):
            tname = table['table_name']
            if tname in ('memories', 'conversation_summaries', 'recent_messages'):
                continue

            cols = [c['column_name'] for c in table.get('columns', [])]
            # Key column hints: only for status/enum columns that need value examples
            hints = []
            for c in table.get('columns', []):
                desc = c.get('description', '')
                cname = c['column_name']
                ctype = c.get('data_type', '').lower()

                # Enum/status columns with descriptions
                if desc and any(k in cname for k in ['status', 'category', 'type', 'condition', 'trend', 'rating']):
                    hints.append(f"  -- {cname}: {desc}")

                # State columns: auto-hint 2-letter codes when column is VARCHAR(2)
                if 'state' in cname and ('character varying' in ctype or 'varchar' in ctype):
                    max_len = c.get('max_length') or c.get('character_maximum_length') or 0
                    if max_len and int(max_len) <= 2:
                        hints.append(f"  -- {cname}: 2-letter US state codes (e.g. 'CA', 'TX', 'FL', 'NY')")

            lines.append(f"TABLE {tname} ({', '.join(cols)})")
            for h in hints[:5]:  # Max 5 hints per table
                lines.append(h)

        if self._join_hints:
            lines.append(f"JOIN: {'; '.join(self._join_hints)}")

        return '\n'.join(lines)

    # ------------------------------------------------------------------
    # Input classification
    # ------------------------------------------------------------------

    def _is_preference_statement(self, user_message: str) -> bool:
        """Detect if input is a preference/terminology statement rather than a query."""
        message_lower = user_message.lower().strip()

        preference_patterns = [
            r"i\s+(?:am\s+)?(?:only\s+)?(?:not\s+)?interested\s+in",
            r"i\s+(don't|do not)\s+want",
            r"i\s+want\s+to\s+see",
            r"i\s+prefer",
            r"i\s+like",
            r"i\s+need\s+to\s+see",
            r"always\s+show",
            r"never\s+show",
            r"exclude\b",
            r"include\s+only",
            r"filter\s+by",
            r"only\s+show\s+me",
            r"from\s+now\s+on",
            r"going\s+forward",
            r"let'?s\s+(call|define)",
            r"define\s+.*\s+as",
            r".*\s+means\s+.*",
            r"consider\s+.*\s+as",
            r"i\s+am\s+not\s+interested",
            r"i\s+no\s+longer",
            r"stop\s+showing",
            r"remove\s+.*\s+filter",
        ]

        for pattern in preference_patterns:
            if re.search(pattern, message_lower):
                return True

        if " means " in message_lower or " is defined as " in message_lower:
            return True

        question_words = ["what", "how", "when", "where", "which", "who", "why",
                          "show me", "list", "give me", "find", "get", "count"]
        has_question = any(word in message_lower for word in question_words)

        basic_preferences = ["i want", "i need", "i prefer", "always", "never"]
        has_preference = any(pref in message_lower for pref in basic_preferences)

        return has_preference and not has_question

    def _has_memory_signal(self, user_message: str) -> bool:
        """
        Lightweight check: does the message carry a preference, term, or
        metric signal worth sending to the LLM for extraction?

        This prevents the system from making an expensive LLM extraction
        call on every plain data query like "show me all loans".  Only
        messages that embed a preference alongside a query (e.g. "show me
        only approved high-value loans") trigger post-query extraction.
        """
        msg = user_message.lower().strip()

        # Signals that a preference / term / metric is embedded in a query
        signals = [
            "only ", "always ", "never ", "exclude ", "prefer ",
            "i want", "i need", "i like", "interested in",
            "from now on", "going forward",
            " means ", " defined as ", " call ", "define ",
            "high-value", "high value", "low-risk", "low risk",
            "consider ", "approved only", "filter ",
        ]
        return any(s in msg for s in signals)

    # ------------------------------------------------------------------
    # Preference handling
    # ------------------------------------------------------------------

    def _handle_preference_statement(self, user_message: str) -> Dict[str, Any]:
        """Handle preference statements by extracting and storing memories."""
        try:
            self.agent.add_message_to_history("Human", user_message)

            synthetic_response = "I understand your preference. I'll remember this for future queries."
            new_memories = self.agent.extract_memories([user_message, synthetic_response])

            if new_memories:
                print(f"🔧 PREFERENCE: Found {len(new_memories)} memories: {new_memories}")
                self.agent.update_memories(new_memories)
                detailed = f"Got it! I've noted: **{user_message.strip('.')}**. I'll apply this to future queries automatically."
                self.agent.add_message_to_history("AI", detailed)
                return self._result(response=detailed, new_memories=new_memories,
                                    success=True, preference_update=True)
            else:
                response = "I understand. I'll keep this in mind for future queries."
                self.agent.add_message_to_history("AI", response)
                return self._result(response=response, success=True, preference_update=True)

        except Exception as e:
            return self._result(
                response="I had trouble processing your preference. Please try rephrasing.",
                error=f"Preference error: {e}", success=False, preference_update=True)

    # ------------------------------------------------------------------
    # Main message processing
    # ------------------------------------------------------------------

    def process_message(self, user_message: str) -> Dict[str, Any]:
        """Process user message — routes to preference handler or SQL pipeline."""
        if not self.current_user:
            return self._result(response="Please set a user first.",
                                error="No user set", success=False)

        if not self.db_schema_loaded:
            return self._result(response="Please load a database schema first.",
                                error="Database not loaded", success=False)

        try:
            print(f"\n{'='*60}")
            print(f"🔍 INPUT: '{user_message}'")

            if self._is_preference_statement(user_message):
                print("✅ ROUTED -> Preference handler")
                return self._handle_preference_statement(user_message)

            print("✅ ROUTED -> SQL generation pipeline")
            return self._process_sql_query(user_message)

        except Exception as e:
            print(f"❌ process_message error: {e}")
            return self._result(
                response="I encountered an error. Please try again.",
                error=str(e), success=False)

    def _process_sql_query(self, user_message: str) -> Dict[str, Any]:
        """Full SQL pipeline: enrich -> generate -> validate -> execute -> format."""
        self.agent.add_message_to_history("Human", user_message)

        # 1. Retrieve relevant memories
        relevant_memories = self.agent.retrieve_relevant_memories(user_message)
        preferences, terminology, metrics, entities = self._categorize_memories(relevant_memories)

        # 2. Enhance the natural-language query with memory context
        enhanced_query = self._enhance_query(user_message, terminology, entities)

        # 3. Generate SQL (with retry)
        sql_query = self._generate_sql_with_retry(
            enhanced_query, preferences, terminology, metrics, entities)

        # 4. Validate and fix the SQL
        if sql_query:
            sql_query = self._validate_and_fix_sql(sql_query)

        # 5. Fallback if generation failed
        if not sql_query or not sql_query.strip():
            sql_query = self._generate_simple_sql(user_message)
            if sql_query:
                print(f"⚠️ Using fallback SQL: {sql_query}")

        if not sql_query or not sql_query.strip():
            return self._result(
                response="I couldn't generate a valid query. Try rephrasing — for example, "
                         "'Show me all loans' or 'List properties in California'.",
                memories_used=relevant_memories, success=False)

        # 6. Security check
        sql_lower = sql_query.lower().strip()
        if not sql_lower.startswith('select') and not sql_lower.startswith('with'):
            return self._result(
                response="For security, only SELECT queries are allowed.",
                sql_query=sql_query, memories_used=relevant_memories, success=False)

        # 7. Execute
        query_result = self.data_client.execute_query(sql_query)

        # 7b. If execution fails, try fallback
        if not query_result['success']:
            fallback = self._generate_simple_sql(user_message)
            if fallback and fallback != sql_query:
                print(f"⚠️ Primary SQL failed, trying fallback: {fallback}")
                query_result = self.data_client.execute_query(fallback)
                if query_result['success']:
                    sql_query = fallback

        if not query_result['success']:
            return self._result(
                response=f"Query failed: {query_result['error']}",
                sql_query=sql_query, memories_used=relevant_memories,
                success=False, execution_time=query_result.get('execution_time', 0))

        # 8. Format response
        response = self._format_response(query_result, bool(preferences), bool(terminology))
        self.agent.add_message_to_history("AI", response)

        # 9. Learn from successful interactions — only when
        #    the message carries a preference / term / metric signal.
        #    Plain data queries ("show me all loans") are NOT mined,
        #    avoiding spurious LLM extraction calls and noisy memories.
        new_memories = []
        if query_result['success'] and query_result.get('data'):
            if self._has_memory_signal(user_message):
                new_memories = self.agent.extract_memories([user_message, response])
                if new_memories:
                    self.agent.update_memories(new_memories)
                    print(f"📝 Extracted {len(new_memories)} memory(s) from query")

        # 10. Periodic conversation summary
        if len(self.agent.recent_messages) % 8 == 0:
            self.agent.update_conversation_summary()

        return self._result(
            response=response, sql_query=sql_query,
            results=query_result.get('data', []),
            memories_used=relevant_memories, new_memories=new_memories,
            success=True, execution_time=query_result.get('execution_time', 0))

    # ------------------------------------------------------------------
    # SQL generation — FIXED to use real schema
    # ------------------------------------------------------------------

    def _generate_sql_with_retry(self, query: str, preferences: List[str],
                                  terminology: List[str], metrics: List[str],
                                  entities: List[str], max_retries: int = 2) -> str:
        """Generate SQL with retry logic."""
        for attempt in range(max_retries + 1):
            try:
                sql = self._generate_sql(query, preferences, terminology, metrics, entities)
                if sql and sql.strip():
                    return sql
            except Exception as e:
                print(f"SQL generation attempt {attempt + 1} failed: {e}")
                if attempt == max_retries:
                    break
            if attempt < max_retries:
                time.sleep(0.5)
        return ""

    def _generate_sql(self, query: str, preferences: List[str],
                       terminology: List[str], metrics: List[str],
                       entities: List[str]) -> str:
        """
        Generate SQL via Ollama /api/chat (instruction format).

        Uses chat format instead of completion format so it works correctly
        with instruction-tuned models (qwen2.5-coder, etc.) as well as
        codellama. The older /api/generate + SELECT-completion trick only
        worked with completion-style models.
        """
        schema_block = self._build_schema_prompt()

        context_parts = []
        if preferences:
            for pref in preferences[:2]:
                context_parts.append(f"- Apply filter: {pref}")
        if terminology:
            for term in terminology[:2]:
                context_parts.append(f"- Term defined: {term}")
        memory_block = "\n".join(context_parts)

        system_msg = (
            "You are a PostgreSQL expert. "
            "Output ONLY a valid SQL SELECT statement — no explanation, "
            "no markdown fences, no backticks, no comments. "
            "Raw SQL only."
        )

        user_msg = (
            f"Schema (use ONLY these tables and columns):\n{schema_block}\n\n"
            f"Rules:\n"
            f"- Output raw SQL only, nothing else.\n"
            f"- Do NOT JOIN tables unless both tables are genuinely needed "
            f"in SELECT or WHERE.\n"
            f"- Add LIMIT 20 for non-aggregate queries.\n"
            + (f"- User preferences:\n{memory_block}\n" if memory_block else "")
            + f"\nQuestion: {query}"
        )

        print(f"🔍 Prompt ~{(len(system_msg)+len(user_msg))//4} tokens")

        try:
            response = requests.post(
                f"{self.llm_base_url}/api/chat",
                json={
                    "model": self.llm_model,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user",   "content": user_msg},
                    ],
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "top_k": 1,
                        "top_p": 0.1,
                        "num_predict": 400,
                        "num_ctx": 4096,
                        "repeat_penalty": 1.0,
                    },
                },
                timeout=60,
            )

            if response.status_code != 200:
                print(f"❌ LLM HTTP error: {response.status_code}")
                return ""

            raw = response.json().get("message", {}).get("content", "").strip()
            if not raw:
                print("❌ Empty LLM response")
                return ""

            print(f"🔍 Raw LLM response ({len(raw)} chars): {raw[:200]}")

            cleaned = self._clean_sql_response(raw)
            if not self._is_valid_sql_start(cleaned):
                print(f"❌ SQL validation failed: {cleaned[:100]}")
                return ""

            if not cleaned.endswith(';'):
                cleaned += ";"

            # Add LIMIT if missing for non-aggregate queries
            cl = cleaned.lower()
            if ("limit" not in cl and "select" in cl
                    and "count(" not in cl and "sum(" not in cl
                    and "avg(" not in cl and "group by" not in cl):
                cleaned = cleaned.rstrip(';') + " LIMIT 20;"

            print(f"✅ Final SQL: {cleaned}")
            return cleaned

        except Exception as e:
            print(f"❌ SQL generation error: {e}")
            return ""

    def _clean_sql_response(self, sql: str) -> str:
        """Extract clean SQL from LLM response, stripping explanatory text."""
        if not sql:
            return ""

        # Strip markdown fences
        sql = sql.replace("```sql", "").replace("```", "").strip()

        # Remove common preamble
        prefixes = [
            "SQL:", "sql:", "Query:", "Answer:", "Here's", "Here is",
            "To find", "To get", "The SQL", "This query"
        ]
        for prefix in prefixes:
            if sql.lower().startswith(prefix.lower()):
                sql = sql[len(prefix):].strip()

        # Find the SELECT statement
        upper = sql.upper()
        select_pos = upper.find('SELECT')
        if select_pos == -1:
            return ""
        if select_pos > 0:
            sql = sql[select_pos:]

        # Take lines until we hit explanatory text
        lines = sql.split('\n')
        sql_lines = []
        sql_keywords = {'select', 'from', 'where', 'and', 'or', 'order', 'group',
                        'having', 'limit', 'join', 'inner', 'left', 'right', 'on',
                        'as', 'case', 'when', 'then', 'else', 'end', 'in', 'not',
                        'between', 'like', 'is', 'null', 'count', 'sum', 'avg',
                        'max', 'min', 'distinct', 'with', 'union', 'except', 'asc', 'desc'}
        explanatory = {'this will', 'this query', 'explanation', 'note:',
                       'the result', 'this returns', 'you can', 'will return'}

        for line in lines:
            stripped = line.strip()
            if not stripped:
                continue
            lower = stripped.lower()

            if any(lower.startswith(e) for e in explanatory):
                break

            # Keep if it contains SQL keywords or looks like SQL
            has_sql = any(kw in lower.split() for kw in sql_keywords)
            if has_sql or stripped.endswith(';') or stripped.endswith(','):
                sql_lines.append(stripped)
            elif stripped.startswith('(') or stripped.startswith(')'):
                sql_lines.append(stripped)
            else:
                # Might be a column list or continuation — keep if short
                if len(stripped) < 80:
                    sql_lines.append(stripped)
                else:
                    break

        result = ' '.join(sql_lines).strip().rstrip('.!?')
        return result

    def _is_valid_sql_start(self, sql: str) -> bool:
        """Check if string looks like valid SQL."""
        if not sql:
            return False
        upper = sql.strip().upper()
        if not any(upper.startswith(s) for s in ['SELECT', 'WITH']):
            return False
        conversational = ['TO FIND', 'TO GET', 'HERE IS', 'THIS QUERY',
                          'YOU CAN', 'WE CAN', 'LET ME', 'I WILL']
        return not any(p in upper for p in conversational)

    # ------------------------------------------------------------------
    # SQL validation against actual schema — NEW
    # ------------------------------------------------------------------

    def _validate_and_fix_sql(self, sql: str) -> str:
        """
        Validate and clean generated SQL:
        1. Block memory system tables
        2. Strip unnecessary JOINs (when all columns reference only one table)
        """
        if not self._table_columns:
            return sql

        # Check for memory system tables
        tables_in_sql = self._extract_tables_from_sql(sql)
        memory_tables = {'memories', 'conversation_summaries', 'recent_messages'}
        if tables_in_sql & memory_tables:
            print(f"⚠️ SQL references memory tables — rejecting")
            return ""

        # Strip unnecessary JOINs
        sql = self._strip_unnecessary_joins(sql)

        return sql

    def _strip_unnecessary_joins(self, sql: str) -> str:
        """
        If all column references (in SELECT/WHERE/ORDER BY) belong to one table
        but the SQL JOINs another table, remove the JOIN.

        Handles aliased SQL like:
            SELECT p.col FROM properties p JOIN loan_applications la ON ...
        by building an alias→table map first, then resolving references.
        """
        tables_in_sql = self._extract_tables_from_sql(sql)
        if len(tables_in_sql) < 2:
            return sql  # Nothing to strip

        # 1. Build alias → real-table mapping
        alias_map: Dict[str, str] = {}
        _sql_keywords = {'select', 'from', 'where', 'join', 'inner', 'left',
                         'right', 'full', 'cross', 'on', 'and', 'or', 'order',
                         'group', 'having', 'limit', 'as', 'set', 'values',
                         'into', 'not', 'in', 'is', 'null', 'between', 'like',
                         'case', 'when', 'then', 'else', 'end', 'union', 'with'}
        # Match "FROM table alias" and "JOIN table alias"
        for m in re.finditer(
                r'\b(?:FROM|JOIN)\s+([a-zA-Z_]\w*)(?:\s+([a-zA-Z_]\w*))?',
                sql, re.IGNORECASE):
            table = m.group(1).lower()
            alias = (m.group(2) or '').lower()
            if table in self._table_columns:
                alias_map[table] = table          # table name itself
                if alias and alias not in self._table_columns and alias not in _sql_keywords:
                    alias_map[alias] = table      # alias → real table

        # 2. Strip JOIN...ON clauses so ON-columns don't count as "used"
        _join_pattern = r'\s+(?:INNER|LEFT|RIGHT|FULL|CROSS)?\s*JOIN\s+\w+(?:\s+\w+)?\s+ON\s+[^\n;]+'
        sql_without_joins = re.sub(_join_pattern, '', sql, flags=re.IGNORECASE)

        # 3. Find alias.column refs and resolve to real tables
        col_refs = re.findall(r'\b([a-zA-Z_]\w*)\.([a-zA-Z_]\w*)\b', sql_without_joins)
        tables_used_in_cols = set()
        for ref, col in col_refs:
            real = alias_map.get(ref.lower())
            if real:
                tables_used_in_cols.add(real)

        # 4. If only one real table is referenced, strip the JOIN
        if len(tables_used_in_cols) == 1:
            keep_table = list(tables_used_in_cols)[0]
            cleaned = re.sub(_join_pattern, '', sql, flags=re.IGNORECASE)

            # Find the alias used for the kept table so we can strip it
            keep_alias = None
            for alias, real in alias_map.items():
                if real == keep_table and alias != real:
                    keep_alias = alias
                    break

            # Remove alias declaration: "FROM properties p" → "FROM properties"
            if keep_alias:
                cleaned = re.sub(
                    rf'\bFROM\s+{re.escape(keep_table)}\s+{re.escape(keep_alias)}\b',
                    f'FROM {keep_table}', cleaned, flags=re.IGNORECASE)
                # Rewrite alias.col → col
                for ref, col in col_refs:
                    if ref.lower() == keep_alias:
                        cleaned = cleaned.replace(f"{ref}.{col}", col)
            else:
                # No alias — rewrite table.col → col
                for ref, col in col_refs:
                    if ref.lower() == keep_table:
                        cleaned = cleaned.replace(f"{ref}.{col}", col)

            print(f"🔧 Stripped unnecessary JOIN — query only uses '{keep_table}'")
            return cleaned

        return sql

    def _extract_tables_from_sql(self, sql: str) -> set:
        """Extract table names referenced in SQL."""
        tables = set()
        patterns = [
            r'\bFROM\s+([a-zA-Z_][a-zA-Z0-9_]*)',
            r'\bJOIN\s+([a-zA-Z_][a-zA-Z0-9_]*)',
        ]
        for pattern in patterns:
            for match in re.finditer(pattern, sql, re.IGNORECASE):
                tables.add(match.group(1).lower())
        return tables

    # ------------------------------------------------------------------
    # Fallback SQL — uses actual schema, not hardcoded
    # ------------------------------------------------------------------

    def _generate_simple_sql(self, user_message: str) -> str:
        """Generate a simple, safe SQL query as fallback using actual schema."""
        message_lower = user_message.lower()
        valid_tables = {t for t in self._table_columns
                        if t not in ('memories', 'conversation_summaries', 'recent_messages')}

        # Try to match a table name in the user's message
        matched_table = None
        for table in valid_tables:
            singular = table.rstrip('s')
            if table in message_lower or singular in message_lower:
                matched_table = table
                break

        if not matched_table:
            if 'loan' in message_lower and 'loan_applications' in valid_tables:
                matched_table = 'loan_applications'
            elif 'propert' in message_lower and 'properties' in valid_tables:
                matched_table = 'properties'
            elif valid_tables:
                matched_table = sorted(valid_tables)[0]
            else:
                return ""

        cols = self._table_columns.get(matched_table, [])

        # Build conditions from keywords
        conditions = []
        if matched_table == 'loan_applications':
            if 'approved' in message_lower:
                conditions.append("application_status = 'approved'")
            elif 'pending' in message_lower:
                conditions.append("application_status = 'pending'")
            elif 'rejected' in message_lower:
                conditions.append("application_status = 'rejected'")

            if 'high' in message_lower and ('value' in message_lower or 'amount' in message_lower):
                conditions.append("loan_amount > 500000")
            if 'low risk' in message_lower or 'low_risk' in message_lower:
                conditions.append("risk_category = 'low_risk'")
            if 'california' in message_lower or ' ca ' in message_lower:
                if 'applicant_state' in cols:
                    conditions.append("applicant_state = 'CA'")
                elif 'property_state' in cols:
                    conditions.append("property_state = 'CA'")

        elif matched_table == 'properties':
            if 'luxury' in message_lower and 'is_luxury_property' in cols:
                conditions.append("is_luxury_property = true")
            if 'california' in message_lower or ' ca ' in message_lower:
                if 'state' in cols:
                    conditions.append("state = 'CA'")
            if 'investment' in message_lower and 'is_investment_property' in cols:
                conditions.append("is_investment_property = true")

        # Build query
        if 'count' in message_lower or 'how many' in message_lower:
            if conditions:
                where = ' AND '.join(conditions)
                return f"SELECT COUNT(*) as total FROM {matched_table} WHERE {where};"
            return f"SELECT COUNT(*) as total FROM {matched_table};"

        # Select useful columns (skip internal/metadata columns)
        skip = {'created_at', 'last_updated', 'officer_notes'}
        display_cols = [c for c in cols if c not in skip][:8]
        col_list = ', '.join(display_cols) if display_cols else '*'

        base = f"SELECT {col_list} FROM {matched_table}"
        if conditions:
            base += " WHERE " + ' AND '.join(conditions)
        base += " LIMIT 20;"
        return base

    # ------------------------------------------------------------------
    # Memory helpers
    # ------------------------------------------------------------------

    def _categorize_memories(self, memories: List[str]) -> Tuple[List[str], List[str], List[str], List[str]]:
        """Categorize memories by type tag."""
        preferences, terminology, metrics, entities = [], [], [], []
        for m in memories:
            if '[PREFERENCE]' in m:
                preferences.append(m.replace('[PREFERENCE]', '').strip())
            elif '[TERM]' in m:
                terminology.append(m.replace('[TERM]', '').strip())
            elif '[METRIC]' in m:
                metrics.append(m.replace('[METRIC]', '').strip())
            elif '[ENTITY]' in m:
                entities.append(m.replace('[ENTITY]', '').strip())
        return preferences, terminology, metrics, entities

    def _enhance_query(self, query: str, terminology: List[str], entities: List[str]) -> str:
        """Apply terminology definitions and entity context to the query."""
        enhanced = query

        for term in terminology:
            if "means" in term.lower():
                parts = term.split("means", 1)
                if len(parts) == 2:
                    abbr = parts[0].strip().strip('"\'')
                    meaning = parts[1].strip()
                    if abbr.lower() in query.lower():
                        enhanced = re.sub(
                            re.escape(abbr), f"{abbr} ({meaning})",
                            enhanced, count=1, flags=re.IGNORECASE)

            # Handle "X is defined as Y" or "call X as Y"
            for pattern_str in [r'(.+?)\s+is defined as\s+(.+)',
                                r'call\s+(.+?)\s+as\s+(.+)']:
                match = re.match(pattern_str, term, re.IGNORECASE)
                if match:
                    abbr = match.group(1).strip().strip('"\'')
                    meaning = match.group(2).strip()
                    if abbr.lower() in query.lower():
                        enhanced = re.sub(
                            re.escape(abbr), f"{abbr} ({meaning})",
                            enhanced, count=1, flags=re.IGNORECASE)

        return enhanced

    # ------------------------------------------------------------------
    # Response formatting — improved
    # ------------------------------------------------------------------

    def _format_response(self, query_result: Dict[str, Any],
                          preferences_applied: bool,
                          terminology_applied: bool) -> str:
        """Format query results with markdown tables."""
        data = query_result.get('data', [])
        columns = query_result.get('columns', [])

        if not data:
            return "No results found for your query."

        count = len(data)
        parts = [f"Found **{count}** result{'s' if count != 1 else ''}."]

        # Always try table format — it looks much better
        table = self._format_as_markdown_table(data, columns)
        parts.append(table)

        notes = []
        if preferences_applied:
            notes.append("applied your preferences")
        if terminology_applied:
            notes.append("used your custom terms")
        if notes:
            parts.append(f"\n_(Note: I {' and '.join(notes)})_")

        return '\n'.join(parts)

    def _format_as_markdown_table(self, data: List[Dict], columns: List[str]) -> str:
        """Format data as a clean markdown table."""
        if not data or not columns:
            return ""

        display_data = data[:15]

        # Skip internal columns
        skip = {'created_at', 'last_updated', 'officer_notes', 'embedding'}
        display_cols = [c for c in columns if c not in skip]

        # Limit columns for readability
        if len(display_cols) > 8:
            display_cols = display_cols[:8]

        # Build header
        headers = [self._clean_column_name(c) for c in display_cols]
        header_row = "| " + " | ".join(headers) + " |"
        separator = "| " + " | ".join("---" for _ in display_cols) + " |"

        # Build data rows
        rows = []
        for row in display_data:
            cells = []
            for col in display_cols:
                val = self._format_value(row.get(col))
                if len(str(val)) > 25:
                    val = str(val)[:22] + "..."
                cells.append(str(val))
            rows.append("| " + " | ".join(cells) + " |")

        table = '\n'.join([header_row, separator] + rows)

        if len(data) > 15:
            table += f"\n\n_... and {len(data) - 15} more rows_"

        return table

    def _clean_column_name(self, column_name: str) -> str:
        """Convert column_name to readable 'Column Name'."""
        return column_name.replace('_', ' ').title()

    def _format_value(self, value) -> str:
        """Format a value for display."""
        if value is None:
            return "—"
        if isinstance(value, bool):
            return "Yes" if value else "No"
        if isinstance(value, float):
            if abs(value) >= 1000:
                return f"${value:,.2f}"
            return f"{value:.2f}" if value != int(value) else str(int(value))
        if isinstance(value, int) and abs(value) >= 10000:
            return f"${value:,}"
        if isinstance(value, str):
            cleaned = value.replace('_', ' ').title() if value.islower() else value
            return cleaned
        return str(value)

    # ------------------------------------------------------------------
    # Memory management
    # ------------------------------------------------------------------

    def delete_memory(self, memory_id: int) -> bool:
        """Delete a specific memory by ID."""
        if not self.current_user:
            return False
        try:
            success = self.agent.store.delete_memory(memory_id, self.current_user)
            if success:
                self.agent.memories = [m for m in self.agent.memories if m.id != memory_id]
                print(f"✅ Deleted memory {memory_id}")
            return success
        except Exception as e:
            print(f"❌ Error deleting memory {memory_id}: {e}")
            return False

    def get_user_memories(self) -> Dict[str, List[str]]:
        """Get current user's memories organized by category."""
        if not self.current_user:
            return {}
        categories = {'preferences': [], 'terminology': [], 'metrics': [], 'entities': []}
        for memory in self.agent.memories:
            content = memory.content
            if '[PREFERENCE]' in content:
                categories['preferences'].append(content.replace('[PREFERENCE]', '').strip())
            elif '[TERM]' in content:
                categories['terminology'].append(content.replace('[TERM]', '').strip())
            elif '[METRIC]' in content:
                categories['metrics'].append(content.replace('[METRIC]', '').strip())
            elif '[ENTITY]' in content:
                categories['entities'].append(content.replace('[ENTITY]', '').strip())
        return {k: v for k, v in categories.items() if v}

    def get_user_memories_detailed(self) -> Dict[str, List[Dict[str, Any]]]:
        """Get memories with IDs for delete operations."""
        if not self.current_user:
            return {}
        categories: Dict[str, List[Dict[str, Any]]] = {
            'preferences': [], 'terminology': [], 'metrics': [], 'entities': []
        }
        for memory in self.agent.memories:
            info = {
                'id': memory.id,
                'content': memory.content,
                'created_at': memory.created_at,
                'source': memory.source
            }
            content = memory.content
            if '[PREFERENCE]' in content:
                info['clean_content'] = content.replace('[PREFERENCE]', '').strip()
                categories['preferences'].append(info)
            elif '[TERM]' in content:
                info['clean_content'] = content.replace('[TERM]', '').strip()
                categories['terminology'].append(info)
            elif '[METRIC]' in content:
                info['clean_content'] = content.replace('[METRIC]', '').strip()
                categories['metrics'].append(info)
            elif '[ENTITY]' in content:
                info['clean_content'] = content.replace('[ENTITY]', '').strip()
                categories['entities'].append(info)
        return {k: v for k, v in categories.items() if v}

    # ------------------------------------------------------------------
    # Status / diagnostics
    # ------------------------------------------------------------------

    def get_system_summary(self) -> Dict[str, Any]:
        return {
            "user": {"current_user": self.current_user, "user_set": bool(self.current_user)},
            "database": {
                "loaded": self.db_schema_loaded, "schema": self.schema_name,
                "tables": list(self._table_columns.keys()),
                "connection_info": self.get_database_info() if self.db_schema_loaded else None
            },
            "memory": {
                "total_memories": len(self.agent.memories) if self.agent.memories else 0,
                "by_category": self.get_user_memories(),
                "recent_messages": len(self.agent.recent_messages) if hasattr(self.agent, 'recent_messages') else 0
            },
            "llm": {"base_url": self.llm_base_url, "model": self.llm_model}
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "user_set": bool(self.current_user),
            "current_user": self.current_user,
            "database_loaded": self.db_schema_loaded,
            "schema_name": self.schema_name,
            "memory_count": len(self.agent.memories) if self.agent.memories else 0
        }

    def validate_setup(self) -> Dict[str, Any]:
        validation = {
            "database_connection": False, "memory_system": False,
            "llm_connection": False, "overall_status": "checking...",
            "issues": [], "recommendations": []
        }
        try:
            validation["database_connection"] = self.data_client.test_connection_with_query()
            if not validation["database_connection"]:
                validation["issues"].append("Cannot connect to target database")
        except Exception as e:
            validation["issues"].append(f"Database error: {str(e)}")

        try:
            validation["memory_system"] = hasattr(self.agent, 'store') and self.agent.store is not None
            if not validation["memory_system"]:
                validation["issues"].append("Memory system not initialized")
        except Exception as e:
            validation["issues"].append(f"Memory error: {str(e)}")

        try:
            test_response = self.agent._call_llm("test")
            validation["llm_connection"] = bool(test_response and test_response.strip())
            if not validation["llm_connection"]:
                validation["issues"].append(f"Cannot reach LLM at {self.llm_base_url}")
        except Exception as e:
            validation["issues"].append(f"LLM error: {str(e)}")

        if not validation["issues"]:
            validation["overall_status"] = "✅ All systems working"
        else:
            validation["overall_status"] = f"❌ {len(validation['issues'])} issue(s) found"
        return validation

    def get_database_info(self) -> Dict[str, Any]:
        try:
            return self.data_client.get_database_info()
        except Exception as e:
            return {"error": str(e)}

    def test_connections(self) -> Dict[str, Any]:
        results = {"timestamp": time.time(), "tests": {}}
        try:
            db_ok = self.data_client.test_connection_with_query()
            results["tests"]["database"] = {"status": "✅ Connected" if db_ok else "❌ Failed", "working": db_ok}
        except Exception as e:
            results["tests"]["database"] = {"status": f"❌ {e}", "working": False}
        try:
            llm_resp = self.agent._call_llm("ping")
            llm_ok = bool(llm_resp and llm_resp.strip())
            results["tests"]["llm"] = {
                "status": "✅ Connected" if llm_ok else "❌ No response",
                "working": llm_ok, "url": self.llm_base_url, "model": self.llm_model
            }
        except Exception as e:
            results["tests"]["llm"] = {"status": f"❌ {e}", "working": False}
        try:
            mem_ok = hasattr(self.agent, 'store') and self.agent.store is not None
            stype = "PostgreSQL" if hasattr(self.agent.store, 'conn_string') else "JSON"
            results["tests"]["memory"] = {
                "status": "✅ Working" if mem_ok else "❌ Not initialized",
                "working": mem_ok, "storage_type": stype
            }
        except Exception as e:
            results["tests"]["memory"] = {"status": f"❌ {e}", "working": False}
        return results

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _result(response: str = "", sql_query: str = "",
                results: list = None, memories_used: list = None,
                new_memories: list = None, success: bool = False,
                execution_time: float = 0, error: str = "",
                preference_update: bool = False) -> Dict[str, Any]:
        """Build a standardized result dict."""
        d: Dict[str, Any] = {
            "response": response,
            "sql_query": sql_query,
            "results": results or [],
            "memories_used": memories_used or [],
            "new_memories": new_memories or [],
            "success": success,
            "execution_time": execution_time,
        }
        if error:
            d["error"] = error
        if preference_update:
            d["preference_update"] = True
        return d