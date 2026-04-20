"""
Gradio Frontend for Smart Query Assistant — Enhanced UI v2
Glassmorphism design · Working memory deletion · Polished layout
"""

import os
import re
from typing import Optional

import gradio as gr
from dotenv import load_dotenv

from text2sql_chatbot import Text2SQLChatbot

load_dotenv()

TARGET_DB_CONN = os.getenv("TARGET_DB_CONNECTION", "postgresql://postgres:password@localhost:5432/testdb")
MEMORY_DB_CONN = os.getenv("MEMORY_DB_CONNECTION", "")
LLM_BASE_URL   = os.getenv("LLM_BASE_URL", "http://localhost:11434")
LLM_MODEL      = os.getenv("LLM_MODEL", "codellama:7b")
DEFAULT_SCHEMA = os.getenv("DEFAULT_SCHEMA", "public")

chatbot         = None
current_user    = None
database_loaded = False


# ══════════════════════════════════════════════════════════════════════
# JavaScript  –  bridges HTML delete-buttons → Gradio Python backend
#
# Why this approach:
#   gr.HTML memory cards can't directly trigger Python callbacks.
#   We bridge via: onclick → set hidden Textbox value → click hidden
#   Button → Python handler fires → memory refreshes.
#   The hidden elements use off-screen positioning (not display:none)
#   so programmatic .click() still fires in all browsers.
# ══════════════════════════════════════════════════════════════════════
PAGE_JS = """
function() {
    window._delMem = function(id) {
        const wrap = document.getElementById('del-id-box');
        if (!wrap) return;
        const ta = wrap.querySelector('textarea') || wrap.querySelector('input');
        if (!ta) return;
        // Use React's native setter so Gradio/React detects the value change
        const setter = Object.getOwnPropertyDescriptor(
            Object.getPrototypeOf(ta), 'value'
        ).set;
        setter.call(ta, String(id));
        ta.dispatchEvent(new Event('input', { bubbles: true }));
        // Let Gradio register state change, then fire the hidden button
        setTimeout(function() {
            const btn = document.querySelector('#del-fire-btn button');
            if (btn) btn.click();
        }, 80);
    };

    window._fillMsg = function(text) {
        const ta = document.querySelector('#msg-input textarea');
        if (!ta) return;
        const setter = Object.getOwnPropertyDescriptor(
            Object.getPrototypeOf(ta), 'value'
        ).set;
        setter.call(ta, text);
        ta.dispatchEvent(new Event('input', { bubbles: true }));
    };
}
"""


# ══════════════════════════════════════════════════════════════════════
# CSS
# ══════════════════════════════════════════════════════════════════════
CSS = """
/* ── Base ──────────────────────────────────────────────────────────── */
.gradio-container {
    font-family: 'Inter', system-ui, -apple-system, sans-serif !important;
    max-width: 1300px !important;
    margin: 0 auto !important;
}

/* ── Layout stability — prevent narrow→wide jump on first render ──── */
/* The login Group is the only visible content before login; without a
   width constraint it shrinks to fit the two small textboxes.  When
   main_ui appears the container jumps wider.  Fix: force ALL children
   of the container to fill available width from the first paint.       */
.gradio-container > * { width: 100% !important; }
.gradio-container > .main { width: 100% !important; }
.gradio-container > .main > * { width: 100% !important; }

/* Chat + Memory columns: claim proportional space immediately         */
.chat-col  { min-width: 0; flex: 5 1 0% !important; }
.mem-col   { min-width: 260px; flex: 2 1 0% !important; }

/* ── Header ─────────────────────────────────────────────────────────── */
.app-header {
    background: linear-gradient(135deg, #4338ca 0%, #7c3aed 50%, #9333ea 100%);
    padding: 1.5rem 2rem;
    border-radius: 16px;
    color: white;
    text-align: center;
    margin-bottom: 0.9rem;
    box-shadow: 0 8px 32px rgba(79,70,229,0.45),
                inset 0 1px 0 rgba(255,255,255,0.18);
    position: relative;
    overflow: hidden;
}
.app-header::before {
    content: '';
    position: absolute; inset: 0;
    background: radial-gradient(ellipse at 20% -10%,
        rgba(255,255,255,0.13) 0%, transparent 60%);
    pointer-events: none;
}
.app-header h1 {
    margin: 0;
    font-size: 1.6rem;
    font-weight: 800;
    letter-spacing: -0.03em;
    position: relative;
}
.app-header p {
    margin: 0.3rem 0 0;
    font-size: 0.84rem;
    opacity: 0.75;
    font-weight: 400;
    letter-spacing: 0.015em;
    position: relative;
}

/* ── Memory panel header ────────────────────────────────────────────── */
.mem-panel-title {
    font-size: 0.93rem;
    font-weight: 700;
    color: #a78bfa;
    margin: 0 0 0.15rem !important;
}
.mem-panel-sub {
    font-size: 0.73rem;
    color: #6b7280;
    margin: 0 0 0.6rem !important;
}

/* ── Memory section labels ──────────────────────────────────────────── */
.mem-section { margin-bottom: 0.75rem; }

.mem-section-label {
    display: inline-flex;
    align-items: center;
    gap: 0.25rem;
    font-size: 0.68rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    padding: 0.18rem 0.55rem;
    border-radius: 5px;
    margin-bottom: 0.35rem;
}
.lbl-pref   { color: #fca5a5; background: rgba(239, 68, 68, 0.13); }
.lbl-term   { color: #6ee7b7; background: rgba( 16,185,129, 0.13); }
.lbl-metric { color: #c4b5fd; background: rgba(139, 92,246, 0.13); }
.lbl-entity { color: #93c5fd; background: rgba( 59,130,246, 0.13); }

/* ── Memory cards ───────────────────────────────────────────────────── */
.mem-card {
    border-radius: 8px;
    padding: 0.5rem 0.65rem;
    margin-bottom: 0.3rem;
    border-left: 3px solid;
    background: rgba(255,255,255,0.035);
    font-size: 0.81rem;
    line-height: 1.5;
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    gap: 0.5rem;
    word-break: break-word;
    transition: background 0.15s ease, transform 0.12s ease;
}
.mem-card:hover {
    background: rgba(255,255,255,0.075);
    transform: translateX(3px);
}
.mem-card span { flex: 1; color: rgba(255,255,255,0.86); }

.mc-pref   { border-left-color: #ef4444; }
.mc-term   { border-left-color: #10b981; }
.mc-metric { border-left-color: #8b5cf6; }
.mc-entity { border-left-color: #3b82f6; }

/* ── Memory delete button ───────────────────────────────────────────── */
.mem-del-btn {
    background: rgba(239,68,68,0.12) !important;
    color: #fca5a5 !important;
    border: 1px solid rgba(239,68,68,0.28) !important;
    padding: 1px 7px !important;
    font-size: 0.7rem !important;
    border-radius: 4px !important;
    cursor: pointer !important;
    flex-shrink: 0;
    line-height: 1.7 !important;
    transition: background 0.15s, border-color 0.15s, color 0.15s !important;
    font-family: inherit !important;
}
.mem-del-btn:hover {
    background: rgba(239,68,68,0.32) !important;
    border-color: rgba(239,68,68,0.55) !important;
    color: #fff !important;
}

.mem-empty {
    text-align: center;
    color: #6b7280;
    padding: 1.8rem 1rem;
    font-size: 0.81rem;
    border: 1px dashed rgba(255,255,255,0.08);
    border-radius: 10px;
    margin-top: 0.4rem;
}
.mem-footer {
    text-align: center;
    font-size: 0.69rem;
    color: #4b5563;
    margin-top: 0.5rem;
    padding-top: 0.4rem;
    border-top: 1px solid rgba(255,255,255,0.05);
}

/* ── Example chips ──────────────────────────────────────────────────── */
.ex-chip {
    display: inline-flex;
    align-items: center;
    background: rgba(109,40,217,0.1);
    border: 1px solid rgba(109,40,217,0.28);
    border-radius: 20px;
    padding: 0.28rem 0.8rem;
    font-size: 0.77rem;
    cursor: pointer;
    transition: all 0.14s ease;
    color: #c4b5fd;
    white-space: nowrap;
    user-select: none;
}
.ex-chip:hover {
    background: rgba(109,40,217,0.22);
    border-color: rgba(109,40,217,0.5);
    transform: translateY(-1px);
    color: #ddd6fe;
}

/* ── Schema docs ────────────────────────────────────────────────────── */
.schema-table {
    border: 1px solid rgba(255,255,255,0.07);
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 1rem;
    background: rgba(255,255,255,0.02);
}
.schema-table-header {
    background: rgba(99,102,241,0.11);
    padding: 0.6rem 1rem;
    font-weight: 600;
    font-size: 0.86rem;
    border-bottom: 1px solid rgba(255,255,255,0.07);
    color: #a5b4fc;
}
.schema-row {
    display: flex;
    justify-content: space-between;
    padding: 0.38rem 1rem;
    border-bottom: 1px solid rgba(255,255,255,0.03);
    font-size: 0.8rem;
    transition: background 0.1s;
}
.schema-row:last-child { border-bottom: none; }
.schema-row:hover { background: rgba(255,255,255,0.03); }
.schema-col  { font-weight: 600; font-family: monospace; color: #c4b5fd; }
.schema-type { opacity: 0.5; font-family: monospace; font-size: 0.74rem; }

/* ── Hidden delete-bridge elements ──────────────────────────────────── */
/* Off-screen (not display:none) so programmatic .click() still fires   */
#del-id-box, #del-fire-btn {
    position: fixed !important;
    top: -9999px !important;
    left: -9999px !important;
    width: 1px !important;
    height: 1px !important;
    overflow: hidden !important;
    opacity: 0 !important;
    pointer-events: none !important;
}
"""


# ══════════════════════════════════════════════════════════════════════
# Backend handlers
# ══════════════════════════════════════════════════════════════════════

def login(username: str, db_connection: Optional[str] = None):
    global chatbot, current_user

    if not username or not username.strip():
        return "❌ Please enter a username", gr.update(visible=False), gr.update(interactive=True)

    db_conn = db_connection.strip() if db_connection and db_connection.strip() else TARGET_DB_CONN
    try:
        chatbot = Text2SQLChatbot(
            target_db_connection=db_conn,
            memory_db_connection=MEMORY_DB_CONN,
            llm_base_url=LLM_BASE_URL,
            llm_model=LLM_MODEL,
            schema_name=DEFAULT_SCHEMA,
        )
        validation = chatbot.validate_setup()
        chatbot.set_user(username)
        current_user = username

        parts = [f"✅ Welcome, **{username}**!"]
        if validation.get('issues'):
            parts.append("⚠️ Issues detected:")
            for issue in validation['issues'][:3]:
                parts.append(f"  • {issue}")
        return "\n".join(parts), gr.update(visible=True), gr.update(interactive=False)
    except Exception as e:
        return f"❌ Login failed: {e}", gr.update(visible=False), gr.update(interactive=True)


def logout():
    global chatbot, current_user, database_loaded
    chatbot = None
    current_user = None
    database_loaded = False
    return (
        "👋 Logged out successfully",
        gr.update(visible=False),
        gr.update(interactive=True),
        [], "", "",
    )


def load_database(schema_name: str) -> str:
    global database_loaded
    if not chatbot:
        return "❌ Please log in first"
    schema_name = (schema_name or DEFAULT_SCHEMA).strip()
    try:
        success, message = chatbot.initialize_database(schema_name)
        database_loaded = success
        if success:
            db_info = chatbot.get_database_info()
            db_name = db_info.get('database_name', '')
            mem_tables = {'memories', 'conversation_summaries', 'recent_messages'}
            tables = ', '.join(t for t in chatbot._table_columns if t not in mem_tables)
            return f"✅ {message}\n📊 Database: **{db_name}** · Tables: {tables}"
        return f"❌ {message}"
    except Exception as e:
        return f"❌ Failed to load database: {e}"


# ══════════════════════════════════════════════════════════════════════
# SQL formatting
# ══════════════════════════════════════════════════════════════════════

def format_sql(sql: str) -> str:
    if not sql:
        return ""
    keywords = [
        'SELECT', 'FROM', 'WHERE', 'AND', 'OR',
        'INNER JOIN', 'LEFT JOIN', 'RIGHT JOIN', 'JOIN',
        'ORDER BY', 'GROUP BY', 'HAVING', 'LIMIT', 'ON',
        'SET', 'VALUES', 'INSERT', 'UPDATE',
    ]
    formatted = sql.strip()
    for kw in keywords:
        formatted = re.sub(
            rf'(?<!^)\s+({kw})\b', rf'\n\1', formatted, flags=re.IGNORECASE
        )
    return formatted.strip()


# ══════════════════════════════════════════════════════════════════════
# Message processing
# ══════════════════════════════════════════════════════════════════════

def process_message(message: str, history: list):
    global database_loaded

    if not message or not message.strip():
        return history, "", "", format_memories()

    if not chatbot:
        history = (history or []) + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": "⚠️ Please log in first."},
        ]
        return history, "", "", ""

    if not database_loaded:
        history = (history or []) + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": "⚠️ Please load a database schema first."},
        ]
        return history, "", "", format_memories()

    try:
        result        = chatbot.process_message(message.strip())
        response      = result.get('response', 'No response generated')
        sql_query     = result.get('sql_query', '')
        memories_used = result.get('memories_used', [])
        new_memories  = result.get('new_memories', [])
        is_pref       = result.get('preference_update', False)

        if result.get('success'):
            if is_pref:
                response += "\n\n✨ _Preference saved to memory_"
            else:
                indicators = []
                if memories_used:
                    indicators.append(f"💡 Applied {len(memories_used)} memory context(s)")
                if new_memories:
                    indicators.append(f"🧠 Learned {len(new_memories)} new fact(s)")
                if indicators:
                    response += "\n\n" + "  •  ".join(indicators)

        history = (history or []) + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": response},
        ]

        # SQL display — plain string for gr.Code
        sql_display = ""
        if sql_query and not is_pref:
            sql_display = format_sql(sql_query)
            exec_time = result.get('execution_time', 0)
            if exec_time:
                sql_display += f"\n\n-- ⏱ {exec_time:.3f}s"
        elif is_pref:
            sql_display = "-- 🎯 Preference stored — no SQL executed"

        return history, "", sql_display, format_memories()

    except Exception as e:
        history = (history or []) + [
            {"role": "user",      "content": message},
            {"role": "assistant", "content": f"❌ Error: {e}"},
        ]
        return history, "", "", format_memories()


# ══════════════════════════════════════════════════════════════════════
# Memory display & deletion
# ══════════════════════════════════════════════════════════════════════

_GARBAGE = frozenset([
    'user filtering preferences', 'custom terminology', 'user preferences',
    'custom metrics', 'filtering preferences', 'terminology', 'preferences',
    'metrics', 'entities', 'entity', 'metric',
])

def _is_garbage(content: str) -> bool:
    s = content.strip()
    if not s or len(s) < 4:
        return True
    if s.endswith(':') and len(s) < 35:
        return True
    if s.rstrip(':').strip().lower() in _GARBAGE:
        return True
    sl = s.lower()
    # Filter auto-generated system entity memories — these are internal metadata,
    # not user preferences, and get re-added automatically so deleting is pointless
    if sl.startswith('database schema') and 'contains tables' in sl:
        return True
    if re.match(r'user frequently queries .+ tables?\.?$', sl):
        return True
    return False


def format_memories() -> str:
    if not chatbot:
        return '<div class="mem-empty">No active session</div>'
    try:
        memories = chatbot.get_user_memories_detailed()
        if not memories:
            return '<div class="mem-empty">No memories yet — start chatting!</div>'

        sections = [
            ("🎯 Preferences", memories.get('preferences',  []), "pref",   "lbl-pref"),
            ("📚 Terminology", memories.get('terminology',  []), "term",   "lbl-term"),
            ("📊 Metrics",     memories.get('metrics',      []), "metric", "lbl-metric"),
            ("🗄️ Entities",    memories.get('entities',     []), "entity", "lbl-entity"),
        ]

        parts = []
        total = 0

        for title, items, kind, lbl_cls in sections:
            # Strip tags and filter garbage entries
            clean = []
            for item in items:
                raw = item.get('clean_content', '') or item.get('content', '')
                for tag in ('[PREFERENCE]', '[TERM]', '[METRIC]', '[ENTITY]'):
                    raw = raw.replace(tag, '')
                content = raw.strip()
                if not _is_garbage(content):
                    clean.append((content, item.get('id', 0)))

            if not clean:
                continue

            total += len(clean)
            parts.append(
                f'<div class="mem-section">'
                f'<div class="mem-section-label {lbl_cls}">{title}</div>'
            )
            for content, mid in clean[:10]:
                safe = content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
                parts.append(
                    f'<div class="mem-card mc-{kind}">'
                    f'  <span>{safe}</span>'
                    f'  <button class="mem-del-btn" onclick="window._delMem({mid})">✕</button>'
                    f'</div>'
                )
            if len(clean) > 10:
                parts.append(
                    f'<div style="font-size:0.71rem;color:#6b7280;padding:0.1rem 0 0.4rem;">'
                    f'+{len(clean)-10} more</div>'
                )
            parts.append('</div>')

        if not parts:
            return '<div class="mem-empty">No memories yet — start chatting!</div>'

        parts.append(f'<div class="mem-footer">Total: {total} memories</div>')
        return ''.join(parts)

    except Exception as e:
        return f'<div class="mem-empty">Error: {e}</div>'


def delete_memory_trigger(memory_id_str: str) -> str:
    """Python handler wired to the hidden delete button."""
    if chatbot and memory_id_str:
        try:
            chatbot.delete_memory(int(memory_id_str.strip()))
        except (ValueError, Exception):
            pass
    return format_memories()


def refresh_memories() -> str:
    return format_memories()


def clear_memory_type(memory_type: str):
    if not chatbot:
        return "❌ No active session", format_memories()
    try:
        memories = chatbot.get_user_memories_detailed()
        targets  = memories.get(memory_type, [])
        if not targets:
            return f"No {memory_type} to clear", format_memories()
        deleted = sum(1 for m in targets if chatbot.delete_memory(m['id']))
        return f"✅ Cleared {deleted} {memory_type}", format_memories()
    except Exception as e:
        return f"❌ Error: {e}", format_memories()


# ══════════════════════════════════════════════════════════════════════
# System info
# ══════════════════════════════════════════════════════════════════════

def test_connections() -> str:
    if not chatbot:
        return "❌ Please log in first"
    try:
        r = chatbot.test_connections()
        lines = ["🔍 **Connection Test**\n"]
        for comp, info in r['tests'].items():
            icon = "✅" if info.get('working') else "❌"
            lines.append(f"{icon} **{comp.upper()}**: {info.get('status', '?')}")
            if 'model' in info:
                lines.append(f"   Model: `{info['model']}`")
            if 'storage_type' in info:
                lines.append(f"   Storage: {info['storage_type']}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error: {e}"


def get_system_info() -> str:
    if not chatbot:
        return "❌ Please log in first"
    try:
        info = chatbot.get_system_summary()
        lines = ["📊 **System Info**\n",
                 f"**User**: {info['user']['current_user'] or 'Not set'}"]
        if info['database']['loaded']:
            lines.append(f"**Schema**: {info['database']['schema']}")
            lines.append(f"**Tables**: {', '.join(info['database'].get('tables', []))}")
        else:
            lines.append("**Database**: Not connected")
        mem = info['memory']
        lines.append(f"**Memories**: {mem['total_memories']}  |  **Messages**: {mem['recent_messages']}")
        lines.append(f"**LLM**: `{info['llm']['model']}` @ {info['llm']['base_url']}")
        return "\n".join(lines)
    except Exception as e:
        return f"❌ Error: {e}"


# ══════════════════════════════════════════════════════════════════════
# Schema docs
# ══════════════════════════════════════════════════════════════════════

def schema_docs_html() -> str:
    return """
<div style="padding:0.5rem 0">
  <p style="margin-bottom:1rem;opacity:0.75;font-size:0.87rem;">
    Connects to an <strong>ecommerce customers &amp; orders database</strong>.
  </p>

  <div class="schema-table">
    <div class="schema-table-header">👤 customers — Ecommerce customer records</div>
    <div class="schema-row"><span class="schema-col">customer_id</span><span class="schema-type">SERIAL PK</span></div>
    <div class="schema-row"><span class="schema-col">name</span><span class="schema-type">VARCHAR — customer name</span></div>
    <div class="schema-row"><span class="schema-col">email</span><span class="schema-type">VARCHAR — unique email</span></div>
    <div class="schema-row"><span class="schema-col">city</span><span class="schema-type">VARCHAR — city</span></div>
    <div class="schema-row"><span class="schema-col">country</span><span class="schema-type">VARCHAR — country</span></div>
    <div class="schema-row"><span class="schema-col">segment</span><span class="schema-type">retail / wholesale</span></div>
    <div class="schema-row"><span class="schema-col">registered_at</span><span class="schema-type">TIMESTAMP — signup date</span></div>
  </div>

  <div class="schema-table">
    <div class="schema-table-header">🛒 orders — Orders linked to customers</div>
    <div class="schema-row"><span class="schema-col">order_id</span><span class="schema-type">SERIAL PK</span></div>
    <div class="schema-row"><span class="schema-col">customer_id</span><span class="schema-type">INT FK → customers</span></div>
    <div class="schema-row"><span class="schema-col">status</span><span class="schema-type">pending / shipped / delivered / cancelled</span></div>
    <div class="schema-row"><span class="schema-col">order_date</span><span class="schema-type">TIMESTAMP — when placed</span></div>
    <div class="schema-row"><span class="schema-col">total_amount</span><span class="schema-type">DECIMAL — order total</span></div>
    <div class="schema-row"><span class="schema-col">payment_method</span><span class="schema-type">credit_card / upi / netbanking / cod</span></div>
  </div>

  <p style="font-size:0.82rem;opacity:0.6;">
    <strong>Key FK:</strong> <code>orders.customer_id → customers.customer_id</code>
  </p>
</div>
"""


# ══════════════════════════════════════════════════════════════════════
# Build UI
# ══════════════════════════════════════════════════════════════════════

def build_interface():
    with gr.Blocks(
        title="Smart Query Assistant",
        theme=gr.themes.Soft(
            primary_hue="violet",
            secondary_hue="purple",
            neutral_hue="slate",
        ),
        css=CSS,
        js=PAGE_JS,
        fill_width=True,
    ) as app:

        # ── Header ────────────────────────────────────────────────────
        gr.HTML("""
        <div class="app-header">
            <h1>🧠 Smart Query Assistant</h1>
            <p>Text2SQL Agent · Long-Term Memory · Preference Learning</p>
        </div>
        """)

        # ── Login row ─────────────────────────────────────────────────
        with gr.Group():
            with gr.Row():
                username_input = gr.Textbox(
                    label="Username", value="demo_user",
                    info="Each user gets isolated memory", scale=3)
                db_conn_input = gr.Textbox(
                    label="Database Connection (optional)",
                    placeholder="postgresql://user:pass@host:port/db",
                    type="password", scale=4)
            with gr.Row():
                login_btn  = gr.Button("🔐 Login",            variant="primary",   scale=2)
                logout_btn = gr.Button("🚪 Logout",           variant="secondary", scale=1)
                test_btn   = gr.Button("🔍 Test Connections", variant="secondary", scale=2)
            login_status = gr.Markdown(value="", elem_id="login-status")

        # ── Main UI (hidden until login) ──────────────────────────────
        with gr.Group(visible=False) as main_ui:

            # Schema / status row
            with gr.Row():
                schema_input = gr.Textbox(
                    label="Schema Name", value="public",
                    info="PostgreSQL schema", scale=2)
                load_btn    = gr.Button("📊 Load Schema", variant="primary",   scale=2)
                sysinfo_btn = gr.Button("ℹ️ System Info", variant="secondary", scale=1)
            db_status = gr.Markdown(value="")

            # ── Chat + Memory ─────────────────────────────────────────
            with gr.Row(equal_height=False):

                # Left: conversation (dominant)
                with gr.Column(scale=5, elem_classes=["chat-col"]):
                    chat_display = gr.Chatbot(
                        label="💬 Conversation", height=430,
                        type="messages", show_copy_button=True)

                # Right: memory bank
                with gr.Column(scale=2, min_width=260, elem_classes=["mem-col"]):
                    gr.HTML(
                        '<p class="mem-panel-title">🧠 Memory Bank</p>'
                        '<p class="mem-panel-sub">What I\'ve learned about your preferences</p>'
                    )
                    with gr.Row():
                        refresh_btn  = gr.Button("🔄",          size="sm", variant="secondary", min_width=44)
                        clr_pref_btn = gr.Button("Clear Prefs", size="sm", variant="secondary")
                        clr_term_btn = gr.Button("Clear Terms", size="sm", variant="secondary")

                    memory_display = gr.HTML(
                        value='<div class="mem-empty">Log in and load a schema to begin</div>')

                    # ── Hidden delete bridge ───────────────────────────
                    # Positioned off-screen (not display:none) so
                    # programmatic .click() fires correctly in all browsers
                    del_id_box   = gr.Textbox(elem_id="del-id-box",   visible=False, value="")
                    del_fire_btn = gr.Button("x", elem_id="del-fire-btn", visible=False)

            # ── Input area ────────────────────────────────────────────
            with gr.Row():
                msg_input = gr.Textbox(
                    label="Your Question or Preference",
                    placeholder="Ask about your data, or set a preference…",
                    elem_id="msg-input",
                    scale=6, lines=1, max_lines=3)
                send_btn = gr.Button("📤 Send", variant="primary", scale=1, min_width=100)

            # Chips row
            with gr.Row():
                clear_btn = gr.Button("🗑️ Clear Chat", variant="secondary", size="sm")
                gr.HTML("""
                <div style="display:flex;align-items:center;gap:0.4rem;flex-wrap:wrap;padding:0.15rem 0;">
                    <span style="font-size:0.74rem;color:#6b7280;flex-shrink:0;">Try:</span>
                    <span class="ex-chip" onclick="window._fillMsg('Show me all delivered orders')">Show delivered orders</span>
                    <span class="ex-chip" onclick="window._fillMsg('I only want to see delivered orders')">Set: only delivered</span>
                    <span class="ex-chip" onclick="window._fillMsg('Show orders over 10000')">Orders over 10000</span>
                    <span class="ex-chip" onclick="window._fillMsg('Define big spenders as customers with total spend over 50000')">Define big spenders</span>
                </div>
                """)

            # ── SQL display ───────────────────────────────────────────
            sql_display = gr.Code(
                label="⚡ Generated SQL",
                language="sql",
                interactive=False,
                value="",
            )

            # ── Accordions ────────────────────────────────────────────
            with gr.Accordion("📋 Database Schema Reference", open=False):
                gr.HTML(schema_docs_html())

            with gr.Accordion("📚 Example Queries & Memory Patterns", open=False):
                gr.HTML("""
                <div style="padding:0.5rem 0;font-size:0.88rem;">
                    <p style="font-weight:700;margin-bottom:0.5rem;">🎯 Setting Preferences</p>
                    <span class="ex-chip">"Only show delivered orders"</span>
                    <span class="ex-chip">"Exclude cancelled orders"</span>
                    <span class="ex-chip">"Always show me customers from India"</span>

                    <p style="font-weight:700;margin:1rem 0 0.5rem;">📖 Defining Terminology</p>
                    <span class="ex-chip">"Big spenders means total spend over 50000"</span>
                    <span class="ex-chip">"Recent means last 30 days"</span>
                    <span class="ex-chip">"High-value orders means total_amount over 10000"</span>

                    <p style="font-weight:700;margin:1rem 0 0.5rem;">🔍 Natural Queries</p>
                    <span class="ex-chip">"Show me top customers by order value"</span>
                    <span class="ex-chip">"Orders by payment method"</span>
                    <span class="ex-chip">"Count orders by status"</span>
                    <span class="ex-chip">"Customers with no orders"</span>
                </div>
                """)

            with gr.Accordion("📖 How It Works", open=False):
                gr.Markdown("""
**1. Login** — Each username gets its own isolated memory space.

**2. Load Schema** — The system introspects your database and learns every table, column, and relationship.

**3. Set Preferences** — Tell the system what you care about. Stored as long-term memories and applied automatically.

**4. Ask Questions** — Natural language → SQL using your actual schema, with preferences and terminology auto-applied.

**5. Memory Learning** — The system learns your patterns (preferred filters, custom terms) and applies them transparently.

**Architecture**: Local LLMs (Ollama) · PostgreSQL + pgvector · Sentence Transformers · Mem0-inspired memory
                """)

        # ── Event wiring ──────────────────────────────────────────────
        login_btn.click(
            login, [username_input, db_conn_input],
            [login_status, main_ui, login_btn])

        logout_btn.click(
            logout,
            outputs=[login_status, main_ui, login_btn, chat_display, sql_display, memory_display])

        load_btn.click(load_database, [schema_input], [db_status])
        sysinfo_btn.click(get_system_info, outputs=[db_status])
        test_btn.click(test_connections, outputs=[login_status])

        send_btn.click(
            process_message, [msg_input, chat_display],
            [chat_display, msg_input, sql_display, memory_display])
        msg_input.submit(
            process_message, [msg_input, chat_display],
            [chat_display, msg_input, sql_display, memory_display])

        clear_btn.click(lambda: ([], "", ""), outputs=[chat_display, msg_input, sql_display])
        refresh_btn.click(refresh_memories, outputs=[memory_display])

        clr_pref_btn.click(
            lambda: clear_memory_type("preferences"), outputs=[db_status, memory_display])
        clr_term_btn.click(
            lambda: clear_memory_type("terminology"), outputs=[db_status, memory_display])

        # Delete bridge: JS writes ID to hidden textbox → hidden button fires → Python deletes
        del_fire_btn.click(
            delete_memory_trigger, inputs=[del_id_box], outputs=[memory_display])

    return app


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

def mask_conn(s: str) -> str:
    if not s or '@' not in s:
        return s[:20] + "..." if len(s) > 20 else s
    try:
        before, after = s.split('@', 1)
        user_part = before.rsplit(':', 1)[0] if ':' in before else before
        return f"{user_part}:***@{after}"
    except Exception:
        return "postgresql://***@***"


if __name__ == "__main__":
    print("=" * 60)
    print("🧠  Smart Query Assistant")
    print("=" * 60)
    print(f"  DB:     {mask_conn(TARGET_DB_CONN)}")
    print(f"  Memory: {'PostgreSQL' if MEMORY_DB_CONN else 'JSON files'}")
    print(f"  LLM:    {LLM_MODEL} @ {LLM_BASE_URL}")
    print(f"  Schema: {DEFAULT_SCHEMA}")
    print("-" * 60)

    app = build_interface()
    app.launch(server_name="127.0.0.1", server_port=7860,
               share=False, show_error=True, quiet=False)