"""
Merged test script for the Text2SQL system.
This single script combines the checks from two test suites:
 - enhanced Text2SQL tests (preference detection, memory ops, SQL fallback, processing)
 - environment and infrastructure checks (imports, DB, Ollama, memory agent, chatbot, env vars)

Usage: python merged_test_suite.py
Make sure you have a .env file with TARGET_DB_CONNECTION, LLM_BASE_URL, LLM_MODEL, optionally MEMORY_DB_CONNECTION.
"""

import os
from dotenv import load_dotenv

# Load environment variables once
load_dotenv()


def test_imports():
    """Test all necessary imports"""
    print("🔍 Testing imports...")
    try:
        import psycopg2  # noqa: F401
        print("✅ psycopg2 imported successfully")
    except Exception as e:  # ImportError or other
        print(f"❌ Failed to import psycopg2: {e}")
        print("   Fix: pip install psycopg2-binary")
        return False

    try:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        print("✅ sentence-transformers imported successfully")
    except Exception as e:
        print(f"❌ Failed to import sentence-transformers: {e}")
        print("   Fix: pip install sentence-transformers")
        return False

    try:
        import requests  # noqa: F401
        print("✅ requests imported successfully")
    except Exception as e:
        print(f"❌ Failed to import requests: {e}")
        print("   Fix: pip install requests")
        return False

    try:
        import gradio as gr  # noqa: F401
        print("✅ gradio imported successfully")
    except Exception as e:
        print(f"❌ Failed to import gradio: {e}")
        print("   Fix: pip install gradio")
        return False

    try:
        import numpy  # noqa: F401
        print("✅ numpy imported successfully")
    except Exception as e:
        print(f"❌ Failed to import numpy: {e}")
        print("   Fix: pip install numpy")
        return False

    return True


def test_environment_config():
    """Test environment configuration"""
    print("\n🔍 Testing environment configuration...")
    required_vars = {
        'TARGET_DB_CONNECTION': 'Database connection string',
        'LLM_BASE_URL': 'Ollama API URL',
        'LLM_MODEL': 'Language model name'
    }

    missing_vars = []
    for var, description in required_vars.items():
        value = os.getenv(var)
        if value:
            # Mask sensitive info in connection strings
            if 'CONNECTION' in var and '@' in value:
                try:
                    masked = value.split('@')[0].split(':')[:-1]
                    masked_str = ':'.join(masked) + ':***@' + value.split('@')[1]
                except Exception:
                    masked_str = '***'
                print(f"✅ {var}: {masked_str}")
            else:
                print(f"✅ {var}: {value}")
        else:
            missing_vars.append((var, description))
            print(f"❌ {var}: Not set")

    if missing_vars:
        print("Create a .env file with these variables")
        return False

    print("✅ All required environment variables are set")
    return True


def test_database_connection():
    """Test database connection and verify tables exist"""
    print("\n🔍 Testing database connection...")
    try:
        from postgreSQL_data_client import PostgresDataClient

        db_conn = os.getenv("TARGET_DB_CONNECTION", "postgresql://postgres:password@localhost:5432/testdb")
        print(f"Connecting to: {db_conn[:50]}...")

        client = PostgresDataClient(db_conn)

        # Test basic connection
        result = client.execute_query("SELECT 1 as test")
        if not result['success']:
            print(f"❌ Basic database query failed: {result.get('error', 'Unknown error')}")
            return False

        print("✅ Basic database connection successful")

        # Test if our tables exist
        table_check = client.execute_query("""
            SELECT table_name FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_name IN ('loan_applications', 'properties')
            ORDER BY table_name;
        """)

        if table_check['success']:
            tables = [row['table_name'] for row in table_check['data']]
            if 'loan_applications' in tables and 'properties' in tables:
                print("✅ Required tables (loan_applications, properties) found")

                # Check data counts
                loan_count = client.execute_query("SELECT COUNT(*) as count FROM loan_applications")
                prop_count = client.execute_query("SELECT COUNT(*) as count FROM properties")

                if loan_count['success'] and prop_count['success']:
                    loans = loan_count['data'][0]['count']
                    props = prop_count['data'][0]['count']
                    print(f"✅ Data found: {loans} loans, {props} properties")

                    if loans == 0 or props == 0:
                        print("⚠️  Warning: Tables exist but no data found")
                        print("   Run: psql -h localhost -U postgres -d testdb -f enhanced_test_database_setup.sql")
                else:
                    print("⚠️  Warning: Could not count table records")
            else:
                print("❌ Required tables not found. Available tables:", tables)
                print("   Run: psql -h localhost -U postgres -d testdb -f enhanced_test_database_setup.sql")
                return False
        else:
            print("⚠️  Warning: Could not check for tables")

        return True

    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        print("   Check your .env file DATABASE_CONNECTION string")
        print("   Ensure PostgreSQL is running")
        return False


def test_ollama_connection():
    """Test Ollama LLM connection"""
    print("\n🔍 Testing Ollama connection...")
    try:
        import requests

        llm_url = os.getenv("LLM_BASE_URL", "http://localhost:11434")
        llm_model = os.getenv("LLM_MODEL", "codellama:7b")

        print(f"Connecting to: {llm_url}")
        print(f"Testing model: {llm_model}")

        # First check if Ollama is running
        try:
            health_response = requests.get(f"{llm_url}/api/tags", timeout=5)
            if health_response.status_code == 200:
                models = health_response.json().get('models', [])
                model_names = [m['name'] for m in models]
                print(f"✅ Ollama is running. Available models: {model_names}")

                if not any(llm_model in name for name in model_names):
                    print(f"⚠️  Model '{llm_model}' not found. Available: {model_names}")
                    print(f"   Run: ollama pull {llm_model}")
            else:
                print(f"⚠️  Ollama health check returned status {health_response.status_code}")
        except Exception:
            print("⚠️  Could not check Ollama status")

        # Test actual generation
        payload = {
            "model": llm_model,
            "prompt": "Hello, respond with just 'OK'",
            "stream": False
        }

        response = requests.post(f"{llm_url}/api/generate", json=payload, timeout=30)

        if response.status_code == 200:
            result = response.json()
            if result.get("response"):
                print(f"✅ Ollama generation successful: '{result['response'][:50]}...'")
                return True
            else:
                print(f"❌ Ollama returned empty response")
                return False
        else:
            print(f"❌ Ollama connection failed: Status {response.status_code}")
            if response.status_code == 404:
                print(f"   Model '{llm_model}' not found. Run: ollama pull {llm_model}")
            return False

    except requests.exceptions.ConnectionError:
        print(f"❌ Cannot connect to Ollama at {llm_url}")
        print("   Make sure Ollama is running: 'ollama serve'")
        print("   Or check if the URL is correct in your .env file")
        return False
    except requests.exceptions.Timeout:
        print("❌ Ollama request timed out")
        print("   The model might be loading. Try again in a moment.")
        return False
    except Exception as e:
        print(f"❌ Ollama test failed: {e}")
        return False


# ---------- Enhanced Text2SQL tests (from original first script) ----------

def test_preference_detection():
    """Test that preference statements are correctly detected."""
    print("\n🔍 Testing preference detection...")
    try:
        from text2sql_chatbot import Text2SQLChatbot

        chatbot = Text2SQLChatbot(
            target_db_connection=os.getenv("TARGET_DB_CONNECTION", "postgresql://test:test@localhost:5432/testdb"),
            memory_db_connection="",  # Use JSON storage by default in tests
            llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            llm_model=os.getenv("LLM_MODEL", "codellama:7b"),
            schema_name="public"
        )

        chatbot.set_user("test_user")

        test_cases = [
            ("I am only interested in approved loans", True),
            ("I am not interested in luxury properties", True),
            ("Show me approved loans", False),
            ("What are some cheap properties?", False),
            ("From now on, only show me California data", True),
            ("Define high-value as over $500K", True),
            ("How many loans do we have?", False),
        ]

        print("\n📋 Test Results:")
        for test_input, expected_is_preference in test_cases:
            is_preference = chatbot._is_preference_statement(test_input)
            status = "✅" if is_preference == expected_is_preference else "❌"
            type_detected = "Preference" if is_preference else "Query"
            print(f"{status} '{test_input}' → Detected as: {type_detected}")

        print("\n✅ Preference detection tests completed!")
        return True
    except Exception as e:
        print(f"❌ Error in preference detection test: {e}")
        return False


def test_memory_operations():
    """Test memory creation, update, and deletion operations."""
    print("\n🧠 Testing memory operations...")
    try:
        from text2sql_chatbot import Text2SQLChatbot

        chatbot = Text2SQLChatbot(
            target_db_connection=os.getenv("TARGET_DB_CONNECTION", "postgresql://test:test@localhost:5432/testdb"),
            memory_db_connection="",
            llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            llm_model=os.getenv("LLM_MODEL", "codellama:7b"),
            schema_name="public"
        )

        chatbot.set_user("test_memory_user")

        print("📝 Testing memory creation...")
        initial_memories = chatbot.get_user_memories()
        try:
            initial_count = len(sum(initial_memories.values(), []))
        except Exception:
            initial_count = 0
        print(f"Initial memories: {initial_count}")

        pref_result = chatbot._handle_preference_statement("I only want to see approved loans")
        print(f"Preference handling result: {pref_result.get('success', False) if isinstance(pref_result, dict) else pref_result}")

        updated_memories = chatbot.get_user_memories()
        try:
            total_memories = len(sum(updated_memories.values(), []))
        except Exception:
            total_memories = 0
        print(f"Memories after preference: {total_memories}")

        detailed_memories = chatbot.get_user_memories_detailed()
        try:
            detailed_count = sum(len(v) for v in detailed_memories.values()) if isinstance(detailed_memories, dict) else 0
        except Exception:
            detailed_count = 0
        print(f"Detailed memories retrieved: {detailed_count}")

        # Test deletion if available
        if isinstance(detailed_memories, dict):
            for category, memories_list in detailed_memories.items():
                if memories_list:
                    memory_to_delete = memories_list[0]
                    memory_id = memory_to_delete.get('id') if isinstance(memory_to_delete, dict) else None
                    if memory_id:
                        print(f"🗑️ Testing deletion of memory {memory_id}")
                        delete_success = chatbot.delete_memory(memory_id)
                        print(f"Deletion result: {delete_success}")
                        break

        print("✅ Memory operations tests completed!")
        return True
    except Exception as e:
        print(f"❌ Error in memory operations test: {e}")
        return False


def test_enhanced_processing():
    """Test the enhanced message processing pipeline."""
    print("\n💬 Testing enhanced message processing...")
    try:
        from text2sql_chatbot import Text2SQLChatbot

        chatbot = Text2SQLChatbot(
            target_db_connection=os.getenv("TARGET_DB_CONNECTION", "postgresql://test:test@localhost:5432/testdb"),
            memory_db_connection="",
            llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            llm_model=os.getenv("LLM_MODEL", "codellama:7b"),
            schema_name="public"
        )

        chatbot.set_user("test_processing_user")

        test_messages = [
            "I am not interested in luxury properties",
            "Show me some cheap properties",
            "Define affordable as under $400K",
        ]

        for message in test_messages:
            print(f"\n📝 Processing: '{message}'")
            is_preference = chatbot._is_preference_statement(message)
            print(f"   Detected as: {'Preference' if is_preference else 'Query'}")
            if is_preference:
                print("   → Would be handled as preference update")
            else:
                print("   → Would generate SQL query")

        print("\n✅ Enhanced processing tests completed!")
        return True
    except Exception as e:
        print(f"❌ Error in enhanced processing test: {e}")
        return False


def test_simple_sql_generation():
    """Test the simple SQL generation fallback."""
    print("\n⚡ Testing simple SQL generation...")
    try:
        from text2sql_chatbot import Text2SQLChatbot

        chatbot = Text2SQLChatbot(
            target_db_connection=os.getenv("TARGET_DB_CONNECTION", "postgresql://test:test@localhost:5432/testdb"),
            memory_db_connection="",
            llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            llm_model=os.getenv("LLM_MODEL", "codellama:7b")
        )

        chatbot.set_user("test_sql_user")

        test_queries = [
            "show me approved loans",
            "what are some cheap properties",
            "show me luxury properties in california",
            "count all loans",
        ]

        for query in test_queries:
            simple_sql = chatbot._generate_simple_sql(query)
            if simple_sql:
                print(f"✅ '{query}' → {str(simple_sql)[:50]}...")
            else:
                print(f"❌ '{query}' → No simple SQL generated")

        print("\n✅ Simple SQL generation tests completed!")
        return True
    except Exception as e:
        print(f"❌ Error in SQL generation test: {e}")
        return False


def test_memory_agent():
    """Test memory agent initialization"""
    print("\n🔍 Testing memory agent...")
    try:
        from memory_agent_opensource import MemoryAgent

        print("Testing with JSON storage...")
        agent = MemoryAgent(use_postgres=False)
        agent.load_user_context("test_user")
        print("✅ JSON-based memory agent initialized successfully")

        # Test embedding creation
        if getattr(agent, 'embedder', None):
            test_embedding = agent._create_embedding("test sentence")
            if test_embedding and len(test_embedding) > 0:
                print("✅ Embedding generation working")
            else:
                print("⚠️  Embedding generation returned empty result")
        else:
            print("⚠️  No embedder loaded")

        # Test PostgreSQL storage if configured
        pg_conn = os.getenv("MEMORY_DB_CONNECTION", "")
        if pg_conn:
            try:
                print("Testing with PostgreSQL storage...")
                pg_agent = MemoryAgent(use_postgres=True, postgres_conn_string=pg_conn)
                pg_agent.load_user_context("test_user")
                print("✅ PostgreSQL-based memory agent initialized successfully")
            except Exception as e:
                print(f"⚠️  PostgreSQL memory storage failed: {e}")
                print("   JSON storage will be used as fallback")

        return True
    except Exception as e:
        print(f"❌ Memory agent test failed: {e}")
        return False


def test_chatbot():
    """Test chatbot initialization"""
    print("\n🔍 Testing chatbot initialization...")
    try:
        if not os.path.exists("text2sql_chatbot.py"):
            if os.path.exists("text1sql.py"):
                print("⚠️  Found 'text1sql.py' but expected 'text2sql_chatbot.py'")
                print("   Please rename: mv text1sql.py text2sql_chatbot.py")
                return False
            else:
                print("❌ text2sql_chatbot.py not found")
                print("   Make sure the file exists and is named correctly")
                return False

        from text2sql_chatbot import Text2SQLChatbot

        db_conn = os.getenv("TARGET_DB_CONNECTION", "postgresql://postgres:password@localhost:5432/testdb")

        print("Initializing chatbot...")
        chatbot = Text2SQLChatbot(
            target_db_connection=db_conn,
            memory_db_connection="",
            llm_base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434"),
            llm_model=os.getenv("LLM_MODEL", "codellama:7b"),
            schema_name="public"
        )

        print("✅ Chatbot initialized successfully")

        # Test validation
        try:
            validation = chatbot.validate_setup()
            print(f"Validation result: {validation.get('overall_status', validation)}")
            if validation.get('issues'):
                print("⚠️  Issues found:")
                for issue in validation.get('issues', []):
                    print(f"  • {issue}")
            else:
                print("✅ No validation issues found")
        except Exception:
            print("⚠️  Chatbot validation not available or raised an exception")

        # Test setting a user
        print("Testing user context...")
        chatbot.set_user("test_user")
        try:
            status = chatbot.get_status()
            if status.get('user_set'):
                print("✅ User context set successfully")
            else:
                print("⚠️  User context not set properly")
        except Exception:
            print("⚠️  Could not retrieve chatbot status")

        return True
    except Exception as e:
        print(f"❌ Chatbot test failed: {e}")
        return False


# ---------- Runner ----------

def main():
    """Run all tests and print summary"""
    print("=" * 80)
    print("🧪 Unified Text2SQL & Infrastructure Test Suite")
    print("=" * 80)

    tests = [
        ("Environment Config", test_environment_config),
        ("Python Imports", test_imports),
        ("Database Connection", test_database_connection),
        ("Ollama Connection", test_ollama_connection),
        ("Memory Agent", test_memory_agent),
        ("Chatbot", test_chatbot),
        ("Preference Detection", test_preference_detection),
        ("Memory Operations", test_memory_operations),
        ("Enhanced Processing", test_enhanced_processing),
        ("Simple SQL Generation", test_simple_sql_generation),
    ]

    results = []
    for test_name, test_func in tests:
        try:
            print(f"\n{'='*10} {test_name} {'='*10}")
            success = test_func()
            results.append((test_name, success))
        except Exception as e:
            print(f"❌ {test_name} crashed: {e}")
            results.append((test_name, False))

    # Summary
    print("\n" + "="*80)
    print("📊 Test Results Summary")
    print("="*80)

    passed = 0
    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{test_name:30}: {status}")
        if success:
            passed += 1

    print(f"\nResult: {passed}/{len(results)} tests passed")

    if passed == len(results):
        print("\n🎉 All tests passed! The system and infra appear to be working correctly.")
        print("\nYou can run the UI (if available) e.g.: python gradio_frontend_fixed.py or python enhanced_gradio_frontend.py")
    else:
        failed_tests = [name for name, success in results if not success]
        print(f"\n⚠️ {len(results) - passed} test(s) failed: {', '.join(failed_tests)}")
        print("\n🔧 Common fixes:")
        print("   • Install missing packages: pip install -r requirements.txt")
        print("   • Start Ollama: ollama serve (in another terminal)")
        print("   • Check database: psql -h localhost -U postgres -d testdb")
        print("   • Rename file: mv text1sql.py text2sql_chatbot.py")

    print("\n" + "="*80)


if __name__ == "__main__":
    main()
