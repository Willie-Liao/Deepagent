"""
Interactive chat with IB MYP PHE Criterion C Prompt Writer Agent.
Shows context window usage percentage and tool calls.

Usage:
    python chat.py                  # Use PostgreSQL checkpoint (default)
    python chat.py --memory         # Use in-memory checkpoint (no persistence)
    python chat.py --show-tools     # Show tool calls in terminal
    python chat.py --debug          # Show all activity (tools + subagents)
"""

import os
import sys
import argparse
import uuid
from contextlib import contextmanager
from pathlib import Path
from dotenv import load_dotenv
from langchain_core.messages import SystemMessage

# Import memory functions
from memory import (
    reflect_and_update_memory,
    load_memory_from_store,
    save_memory_to_store,
    format_memory_for_prompt,
    get_system_prompt_with_memory
)
from agent import (
    create_criterion_c_agent,
    get_kimi_model,
    BASE_SYSTEM_PROMPT
)
from tool_callbacks import get_tool_callbacks

# Load environment variables
load_dotenv()


@contextmanager
def get_agent_context(use_memory=False, fallback_to_memory=True):
    """
    Context manager for agent with PostgreSQL checkpointer.
    
    Usage:
        with get_agent_context(use_memory=False) as (agent, store):
            result = agent.invoke(...)
    
    Args:
        use_memory: If True, always use in-memory mode
        fallback_to_memory: If True and PostgreSQL fails, fall back to in-memory mode
    """
    if use_memory:
        # No checkpointer - in-memory only
        print("💾 Checkpoint: In-memory (no persistence)")
        agent, store = create_criterion_c_agent(checkpointer=None)
        yield agent, store
        return
    
    # Use PostgreSQL (default)
    from langgraph.checkpoint.postgres import PostgresSaver
    db_uri = os.getenv("DATABASE_URL", "postgresql://willieliao@localhost:5432/deepagent_db?sslmode=disable")
    
    try:
        with PostgresSaver.from_conn_string(db_uri) as checkpointer:
            checkpointer.setup()
            print(f"💾 Checkpoint: PostgreSQL ({db_uri.split('@')[-1]})")
            agent, store = create_criterion_c_agent(checkpointer=checkpointer)
            yield agent, store
    except Exception as e:
        if "Connection refused" in str(e) or "could not connect" in str(e).lower():
            if fallback_to_memory:
                print("")
                print("⚠️  PostgreSQL not available - falling back to in-memory mode")
                print("    (Conversations will NOT be saved)")
                print("")
                print("To use PostgreSQL, start it with:")
                print("   open -a Postgres.app")
                print("")
                agent, store = create_criterion_c_agent(checkpointer=None)
                yield agent, store
            else:
                print("")
                print("❌ Error: Cannot connect to PostgreSQL!")
                print("")
                print("PostgreSQL doesn't appear to be running. Options:")
                print("")
                print("1. Start PostgreSQL (Postgres.app):")
                print("   open -a Postgres.app")
                print("   Or:")
                print("   /Applications/Postgres.app/Contents/Versions/18/bin/pg_ctl -D \"$HOME/Library/Application Support/Postgres/var-18\" start")
                print("")
                print("2. Use in-memory mode (no persistence):")
                print("   python chat.py --memory")
                print("")
                sys.exit(1)
        else:
            raise


def get_callbacks(show_tools=False, debug=False):
    """Get callback handlers for tool call display."""
    # Always return callbacks - compact printer shows by default
    return get_tool_callbacks(debug=debug, show_tools=show_tools)


def list_available_checkpoints(use_memory=False):
    """
    List available checkpoints from PostgreSQL.
    
    Returns:
        List of (thread_id, checkpoint_count, last_active) tuples
        where last_active is ISO timestamp string from checkpoint JSON
    """
    if use_memory:
        return []
    
    try:
        import psycopg
        db_uri = os.getenv("DATABASE_URL", "postgresql://willieliao@localhost:5432/deepagent_db?sslmode=disable")
        
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                # Extract timestamp from checkpoint JSON -> ts field
                cur.execute("""
                    SELECT thread_id, COUNT(*) as count, 
                           MAX((checkpoint->>'ts')::timestamptz) as last_active
                    FROM checkpoints
                    GROUP BY thread_id
                    ORDER BY MAX(checkpoint->>'ts') DESC
                    LIMIT 10
                """)
                results = cur.fetchall()
                return [(row[0], row[1], row[2]) for row in results]
    except Exception as e:
        print(f"\n⚠️  Warning: Could not connect to PostgreSQL: {e}")
        print("    Falling back to in-memory mode (no checkpoint persistence)")
        print("    To use PostgreSQL, start it with: open -a Postgres.app")
        print("")
        return []


def get_checkpoint_summary(thread_id, use_memory=False):
    """
    Get a summary of the conversation from checkpoint.
    
    Returns:
        int: Number of messages in checkpoint
    """
    if use_memory:
        return 0
    
    try:
        import psycopg
        db_uri = os.getenv("DATABASE_URL", "postgresql://willieliao@localhost:5432/deepagent_db?sslmode=disable")
        
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*) FROM checkpoints
                    WHERE thread_id = %s
                """, (thread_id,))
                result = cur.fetchone()
                return result[0] if result else 0
    except Exception:
        return 0


def load_messages_from_checkpoint(thread_id, use_memory=False):
    """
    Load conversation messages from checkpoint for accurate token counting.
    
    Returns:
        list: Messages loaded from checkpoint, or empty list if not available
    """
    if use_memory:
        return []
    
    try:
        import psycopg
        from langgraph.checkpoint.serde import jsonplus
        
        db_uri = os.getenv("DATABASE_URL", "postgresql://willieliao@localhost:5432/deepagent_db?sslmode=disable")
        serde = jsonplus.JsonPlusSerializer()
        
        with psycopg.connect(db_uri) as conn:
            with conn.cursor() as cur:
                # Get the latest checkpoint for this thread (order by version, not checkpoint_id)
                cur.execute("""
                    SELECT type, blob 
                    FROM checkpoint_blobs
                    WHERE thread_id = %s AND channel = 'messages'
                    ORDER BY version DESC
                    LIMIT 1
                """, (thread_id,))
                result = cur.fetchone()
                
                if result and result[0] and result[1]:
                    type_str, blob = result
                    # Deserialize using LangGraph's JsonPlusSerializer
                    messages_data = serde.loads_typed((type_str, blob))
                    
                    # Convert LangChain message objects to simple dict format
                    messages = []
                    for msg in messages_data if isinstance(messages_data, list) else []:
                        # Handle LangChain message objects
                        msg_type = type(msg).__name__
                        if msg_type == 'HumanMessage':
                            messages.append({"role": "user", "content": getattr(msg, 'content', '')})
                        elif msg_type == 'AIMessage':
                            messages.append({"role": "assistant", "content": getattr(msg, 'content', '')})
                        # Skip ToolMessage (tool results don't count toward context window)
                    return messages
                return []
    except Exception as e:
        return []


def select_thread_id(use_memory=False):
    """
    Simple checkpoint selection: 3 main options, paginated list view.
    
    Returns:
        tuple: (thread_id, existing_messages)
    """
    if use_memory:
        thread_id = f"chat-{uuid.uuid4().hex[:8]}"
        return thread_id, []
    
    checkpoints = list_available_checkpoints(use_memory=False)
    
    if not checkpoints:
        thread_id = f"chat-{uuid.uuid4().hex[:8]}"
        print(f"\n🆕 New conversation: {thread_id}\n")
        return thread_id, []
    
    while True:
        print("")
        print("=" * 70)
        print("📂 CONVERSATION OPTIONS")
        print("=" * 70)
        print("")
        print("  [1] 🆕  Start fresh (new conversation)")
        print("  [2] 📋  List saved conversations")
        print("  [3] 🗑️   Reset/Clear current thread")
        print("")
        
        choice = input("Choice: ").strip()
        
        if choice == "1":
            thread_id = f"chat-{uuid.uuid4().hex[:8]}"
            print(f"\n🆕 New conversation: {thread_id}\n")
            return thread_id, []
        
        elif choice == "2":
            # Paginated list view
            page = 0
            per_page = 5
            total_pages = (len(checkpoints) + per_page - 1) // per_page
            
            while True:
                print("")
                print("-" * 70)
                print(f"📋 Saved Conversations (Page {page + 1}/{max(1, total_pages)})")
                print("-" * 70)
                
                start = page * per_page
                end = min(start + per_page, len(checkpoints))
                
                for i, (thread_id, count, last_active) in enumerate(checkpoints[start:end], start + 1):
                    # Format timestamp as YY/MM/DD HH:MM:SS
                    if last_active:
                        if isinstance(last_active, str):
                            # Parse ISO format string
                            from datetime import datetime
                            try:
                                dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                                ts_str = dt.strftime("%y/%m/%d %H:%M:%S")
                            except:
                                ts_str = last_active[:19]  # Fallback: first 19 chars (ISO without timezone)
                        else:
                            ts_str = last_active.strftime("%y/%m/%d %H:%M:%S")
                    else:
                        ts_str = "unknown"
                    print(f"  [{i}] {thread_id}")
                    print(f"      {count} checkpoint(s)  |  Last active: {ts_str}")
                
                print("")
                print("Options:")
                if total_pages > 1:
                    if page > 0:
                        print("  [P] ⬆️   Previous page")
                    if page < total_pages - 1:
                        print("  [N] ⬇️   Next page")
                print(f"  [1-{end}] Select conversation")
                print("  [B] ⬅️   Back to main menu")
                print("")
                
                list_choice = input("Choice: ").strip().upper()
                
                if list_choice == "B":
                    break
                elif list_choice == "P" and page > 0:
                    page -= 1
                elif list_choice == "N" and page < total_pages - 1:
                    page += 1
                else:
                    try:
                        idx = int(list_choice) - 1
                        if 0 <= idx < len(checkpoints):
                            thread_id = checkpoints[idx][0]
                            checkpoint_count = get_checkpoint_summary(thread_id)
                            print(f"\n📂 Resuming: {thread_id} ({checkpoint_count} checkpoints)\n")
                            return thread_id, None
                        else:
                            print("   ⚠️ Invalid number")
                    except ValueError:
                        print("   ⚠️ Invalid choice")
        
        elif choice == "3":
            # Delete ALL checkpoints for this deepagent
            if not use_memory:
                try:
                    import psycopg
                    db_uri = os.getenv("DATABASE_URL", "postgresql://willieliao@localhost:5432/deepagent_db?sslmode=disable")
                    with psycopg.connect(db_uri) as conn:
                        with conn.cursor() as cur:
                            cur.execute("DELETE FROM checkpoints")
                            cur.execute("DELETE FROM checkpoint_blobs")
                            cur.execute("DELETE FROM checkpoint_writes")
                            conn.commit()
                    print(f"\n🗑️  All checkpoints cleared.")
                except Exception as e:
                    print(f"\n⚠️  Could not clear checkpoints: {e}")
            thread_id = f"chat-{uuid.uuid4().hex[:8]}"
            print(f"✅ New conversation: {thread_id}\n")
            return thread_id, []
        
        else:
            print("   ⚠️ Please enter 1, 2, or 3")


# Kimi K2.5 context window
MAX_CONTEXT_TOKENS = 250000  # Total context window
WARNING_THRESHOLD = 80  # Show warning at 80%
CRITICAL_THRESHOLD = 95  # Show critical warning at 95%


def estimate_tokens(text):
    """Rough estimation: ~4 characters per token for English/Chinese."""
    return len(text) // 4


def calculate_context_usage(messages):
    """
    Calculate context window usage from input/output tokens.
    
    Input = user messages, Output = assistant messages
    Total = (input + output) / 250K * 100%
    """
    input_chars = sum(len(m.get("content", "")) for m in messages if m.get("role") == "user")
    output_chars = sum(len(m.get("content", "")) for m in messages if m.get("role") == "assistant")
    
    input_tokens = input_chars // 4
    output_tokens = output_chars // 4
    total_tokens = input_tokens + output_tokens
    
    percentage = (total_tokens / MAX_CONTEXT_TOKENS) * 100
    
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
        "percentage": min(percentage, 100)
    }


def get_context_bar(percentage):
    """Get a visual bar showing context usage."""
    filled = int(percentage / 10)
    empty = 10 - filled
    bar = "█" * filled + "░" * empty
    return bar


def get_context_color(percentage):
    """Get color code based on percentage."""
    if percentage < WARNING_THRESHOLD:
        return "\033[92m"  # Green
    elif percentage < CRITICAL_THRESHOLD:
        return "\033[93m"  # Yellow
    else:
        return "\033[91m"  # Red


def print_context_status(messages):
    """Print context window status from current messages."""
    stats = calculate_context_usage(messages)
    bar = get_context_bar(stats["percentage"])
    color = get_context_color(stats["percentage"])
    reset = "\033[0m"
    
    print(f"\n{color}[Context: {bar} {stats['percentage']:.1f}% | In: {stats['input_tokens']:,} | Out: {stats['output_tokens']:,} | Total: {stats['total_tokens']:,}/{MAX_CONTEXT_TOKENS//1000}K]{reset}")
    
    if stats["percentage"] >= CRITICAL_THRESHOLD:
        print(f"{color}⚠️  CRITICAL: Context window nearly full! Consider starting a new chat.{reset}")
    elif stats["percentage"] >= WARNING_THRESHOLD:
        print(f"{color}⚠️  Warning: Context window filling up.{reset}")
    
    return stats["percentage"]


def prepare_messages_with_memory(messages, store, user_id):
    """
    Prepare messages list with memory-injected system message at the start.
    Returns a new list with the system message prepended.
    """
    # Load memory from store
    memory_data = load_memory_from_store(store, user_id)
    memory_content = format_memory_for_prompt(memory_data)
    
    # Build system prompt with memory
    system_prompt = get_system_prompt_with_memory(BASE_SYSTEM_PROMPT, memory_content)
    
    # Create new messages list with system message at start
    # Use LangChain SystemMessage format
    formatted_messages = [{"role": "system", "content": system_prompt}]
    
    # Add conversation messages (skip any existing system messages)
    for msg in messages:
        if msg.get("role") != "system":
            formatted_messages.append(msg)
    
    return formatted_messages


def update_memory_after_turn(messages, response_content, store, user_id):
    """
    Reflect on the conversation and update memory.
    Follows the pattern from memory_store.py's write_memory function.
    """
    try:
        # Get existing memory
        existing_memory = load_memory_from_store(store, user_id)
        
        # Add assistant response to messages for reflection
        full_conversation = messages + [{"role": "assistant", "content": response_content}]
        
        # Reflect and update memory
        model = get_kimi_model()
        new_memory = reflect_and_update_memory(
            full_conversation,
            existing_memory,
            model
        )
        
        # Save to store
        save_memory_to_store(store, user_id, new_memory)
        
        return True
    except Exception as e:
        # Silent fail - memory update should not break the conversation
        if os.getenv("DEBUG"):
            print(f"\n[Memory update error: {e}]")
        return False


def main():
    """Run interactive chat session."""
    
    # Parse arguments
    parser = argparse.ArgumentParser(description="IB MYP PHE Criterion C Prompt Writer Chat")
    parser.add_argument("--memory", action="store_true", help="Use in-memory checkpoint (no persistence)")
    parser.add_argument("--show-tools", action="store_true", help="Show tool calls in terminal")
    parser.add_argument("--debug", action="store_true", help="Show all activity including subagent calls")
    args = parser.parse_args()
    
    # Check for API key
    if not os.getenv("MOONSHOT_API_KEY"):
        print("Error: MOONSHOT_API_KEY not set in .env file")
        print("Get your key from: https://platform.moonshot.cn/")
        return
    
    print("=" * 70)
    print("IB MYP PHE Criterion C Prompt Writer - Interactive Chat")
    print("=" * 70)
    print(f"Model: Kimi K2.5 | Context Window: ~{MAX_CONTEXT_TOKENS//1000}K tokens")
    print("💡 Memory enabled: Agent will learn about you over time")
    print()
    
    # Get callbacks for tool display (compact mode by default)
    callbacks = get_callbacks(show_tools=args.show_tools, debug=args.debug)
    if args.debug:
        print("🔍 Debug mode: Showing all activity")
    elif args.show_tools:
        print("🔍 Tool display: Detailed")
    
    # Ask user for checkpoint selection BEFORE connecting to PostgreSQL
    # This way the dialog always shows even if PostgreSQL is not available
    thread_id, existing_messages = select_thread_id(use_memory=args.memory)
    
    # Run chat with agent context (handles PostgreSQL connection)
    with get_agent_context(use_memory=args.memory) as (agent, store):
        print("✅ Agent ready!\n")
        
        # Conversation history (without system message - added dynamically)
        # Track if this is first turn after resuming from checkpoint
        is_first_turn_after_resume = False
        if existing_messages is None and not args.memory:
            # Continuing from checkpoint - load messages from agent state
            is_first_turn_after_resume = True
            try:
                # Load messages from checkpoint for accurate token counting
                messages = load_messages_from_checkpoint(thread_id, use_memory=args.memory)
                if messages:
                    print(f"📝 Loaded {len(messages)} messages from checkpoint\n")
                else:
                    print("📝 Loaded conversation from checkpoint\n")
            except Exception:
                messages = []
        else:
            messages = existing_messages if existing_messages else []
        
        # Show initial memory status
        memory_data = load_memory_from_store(store, thread_id)
        if memory_data and memory_data.get("memory"):
            print("🧠 Memory loaded:")
            print(f"   {memory_data.get('memory', 'No memory')[:150]}...")
            print()
        else:
            print("🧠 No memory yet. I'll learn about you as we chat!\n")
        
        while True:
            # Show context status before each prompt (from current messages)
            context_pct = print_context_status(messages)
            
            # Get user input
            try:
                user_input = input("> ").strip()
            except (KeyboardInterrupt, EOFError):
                print("\n\nGoodbye!")
                break
            
            # Handle commands
            if user_input.lower() in ["quit", "exit", "q"]:
                print("\nGoodbye!")
                break
            
            if user_input.lower() in ["reset", "r", "clear", "c"]:
                # Delete current thread's checkpoints before resetting
                if not args.memory:
                    try:
                        import psycopg
                        db_uri = os.getenv("DATABASE_URL", "postgresql://willieliao@localhost:5432/deepagent_db?sslmode=disable")
                        with psycopg.connect(db_uri) as conn:
                            with conn.cursor() as cur:
                                cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
                                cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
                                cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
                                conn.commit()
                        print(f"\n🗑️  Deleted checkpoints for: {thread_id}")
                    except Exception as e:
                        print(f"\n⚠️  Could not delete checkpoints: {e}")
                messages = []
                thread_id = f"chat-{uuid.uuid4().hex[:8]}"
                print(f"✅ New conversation started.")
                print(f"   Thread ID: {thread_id}\n")
                continue
            
            if user_input.lower() in ["status", "s"]:
                continue  # Already printed above
            
            if user_input.lower() in ["thread", "t"]:
                print(f"\nCurrent Thread ID: {thread_id}\n")
                continue
            
            if user_input.lower() == "memory":
                # Show current memory
                memory_data = load_memory_from_store(store, thread_id)
                if memory_data and memory_data.get("memory"):
                    print("\n🧠 Current Memory:")
                    print("-" * 50)
                    print(memory_data.get("memory"))
                    print("-" * 50)
                    if memory_data.get("last_updated"):
                        print(f"Last updated: {memory_data.get('last_updated')}")
                else:
                    print("\n🧠 No memory stored yet.")
                print()
                continue
            
            if user_input.lower() in ["list", "l"]:
                checkpoints = list_available_checkpoints(use_memory=args.memory)
                if checkpoints:
                    print("\n📂 Saved conversations:")
                    for i, (tid, count, last_active) in enumerate(checkpoints, 1):
                        # Format timestamp as YY/MM/DD HH:MM:SS
                        if last_active:
                            if isinstance(last_active, str):
                                from datetime import datetime
                                try:
                                    dt = datetime.fromisoformat(last_active.replace('Z', '+00:00'))
                                    ts_str = dt.strftime("%y/%m/%d %H:%M:%S")
                                except:
                                    ts_str = last_active[:19]
                            else:
                                ts_str = last_active.strftime("%y/%m/%d %H:%M:%S")
                        else:
                            ts_str = "unknown"
                        marker = " ← current" if tid == thread_id else ""
                        print(f"  {i}. {tid} ({count} checkpoints, {ts_str}){marker}")
                    print("")
                else:
                    print("\n📂 No saved conversations\n")
                continue
            
            if user_input.lower() in ["delete", "d"]:
                if args.memory:
                    print("\n⚠️ In-memory mode - no checkpoints to delete\n")
                else:
                    try:
                        import psycopg
                        db_uri = os.getenv("DATABASE_URL", "postgresql://willieliao@localhost:5432/deepagent_db?sslmode=disable")
                        with psycopg.connect(db_uri) as conn:
                            with conn.cursor() as cur:
                                cur.execute("DELETE FROM checkpoints WHERE thread_id = %s", (thread_id,))
                                cur.execute("DELETE FROM checkpoint_blobs WHERE thread_id = %s", (thread_id,))
                                cur.execute("DELETE FROM checkpoint_writes WHERE thread_id = %s", (thread_id,))
                                conn.commit()
                        print(f"\n🗑️  Deleted checkpoints for: {thread_id}")
                        messages = []
                        thread_id = f"chat-{uuid.uuid4().hex[:8]}"
                        print(f"🆕 New thread ID: {thread_id}\n")
                    except Exception as e:
                        print(f"\n❌ Error deleting checkpoints: {e}\n")
                continue
            
            if not user_input:
                continue
            
            # Check if context is critically full
            if context_pct >= 100:
                print("\n❌ Context window is FULL!")
                print("Please type 'reset' to clear history and start fresh.\n")
                continue
            
            # Add user message
            messages.append({"role": "user", "content": user_input})
            
            # Prepare messages with memory-injected system prompt
            messages_with_memory = prepare_messages_with_memory(messages, store, thread_id)
            
            # Get agent response
            print("\n🤔 Thinking...")
            try:
                # Build config with callbacks for tool display
                # Tool output is display-only and does NOT count toward context window
                config = {
                    "configurable": {"thread_id": thread_id},
                    "callbacks": callbacks
                }
                
                # First turn after resuming: let checkpointer load conversation history
                # Pass only the new user message, not the full history (which would duplicate checkpoint)
                if is_first_turn_after_resume:
                    # Get just the latest user message
                    latest_message = messages[-1] if messages and messages[-1]["role"] == "user" else None
                    if latest_message:
                        result = agent.invoke({"messages": [latest_message]}, config=config)
                    else:
                        result = agent.invoke({}, config=config)
                    is_first_turn_after_resume = False
                else:
                    result = agent.invoke(
                        {"messages": messages_with_memory},
                        config=config
                    )
                
                # Get the last AI message
                response = result["messages"][-1].content
                
                # Add to history
                messages.append({"role": "assistant", "content": response})
                
                # Print response
                print("\n" + "=" * 70)
                print(response)
                print("=" * 70 + "\n")
                
                # Update memory after successful response
                # This follows the pattern from memory_store.py's write_memory
                memory_updated = update_memory_after_turn(messages, response, store, thread_id)
                if args.debug and memory_updated:
                    print("[🧠 Memory updated]\n")
                
            except Exception as e:
                print(f"\n❌ Error: {e}\n")
                # Remove the failed user message from history
                if messages and messages[-1]["role"] == "user":
                    messages.pop()


if __name__ == "__main__":
    # Enable ANSI colors on Windows
    if sys.platform == "win32":
        os.system("color")
    main()
