"""
Simple IB MYP PHE Agent
Built with DeepAgents SDK and Kimi 2.5
Only uses pre-built filesystem tools.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langgraph.store.memory import InMemoryStore
try:
    from langgraph.checkpoint.postgres import PostgresSaver
    POSTGRES_AVAILABLE = True
except ImportError:
    POSTGRES_AVAILABLE = False
    PostgresSaver = None
from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, FilesystemBackend

# Import memory functions
from memory import (
    get_memory_namespace,
    MEMORY_KEY,
    format_memory_for_prompt,
    load_memory_from_store,
    get_system_prompt_with_memory
)

# Import tools including memory tools
from tools import (
    read_memory,
    update_memory,
    clear_memory,
    set_memory_store,
    read_docx
)

load_dotenv()


def get_kimi_model():
    """Configure and return Kimi 2.5 model with thinking disabled."""
    api_key = os.getenv("MOONSHOT_API_KEY")
    if not api_key:
        raise ValueError("MOONSHOT_API_KEY not found. Please set it in your .env file.")
    
    return ChatOpenAI(
        model="kimi-k2.5",
        base_url="https://api.moonshot.cn/v1",
        api_key=api_key,
        max_tokens=32768,
        extra_body={"thinking": {"type": "disabled"}}
    )


# Workspace directories
WORKSPACE_ROOT = Path(__file__).parent / "workspace"
MEMORY_DIR = WORKSPACE_ROOT / "memories"
for dir_path in [WORKSPACE_ROOT, MEMORY_DIR]:
    dir_path.mkdir(parents=True, exist_ok=True)


# Base system prompt without memory (memory will be injected dynamically)
BASE_SYSTEM_PROMPT = """You are a helpful assistant with filesystem access.

## Available Tools
- read_file(path, offset, limit): Read file contents
- write_file(file_path, content): Create new files
- edit_file(file_path, old_string, new_string): Edit existing files
- ls(path): List directory contents
- glob(pattern): Find files by pattern
- grep(pattern): Search file contents
- read_docx(path): Read Microsoft Word (.docx) files

## Tool Usage Rules
1. When user asks to read/view/show a file → CALL read_file IMMEDIATELY
2. When user asks to write/save/create a file → CALL write_file IMMEDIATELY  
3. When user asks to edit/modify/change a file → CALL edit_file IMMEDIATELY
4. DO NOT say "I will read..." or "I would write..." → JUST CALL THE TOOL
5. DO NOT describe what you would do → DO IT

## Examples
User: "Read /memories/test.txt"
You: [Call read_file(path="/memories/test.txt")]

User: "Save hello to /memories/hello.txt"
You: [Call write_file(file_path="/memories/hello.txt", content="hello")]

User: "What files are in /?"
You: [Call ls(path="/")]"""


def create_backend(runtime):
    """Create composite backend with filesystem access."""
    return CompositeBackend(
        default=FilesystemBackend(
            root_dir=str(WORKSPACE_ROOT),
            virtual_mode=True
        ),
        routes={
            "/memories/": FilesystemBackend(
                root_dir=str(MEMORY_DIR),
                virtual_mode=True
            ),
            "/drafts/": StateBackend(runtime),
        }
    )


def create_criterion_c_agent(checkpointer=None):
    """Create simple agent with only filesystem tools."""
    store = InMemoryStore()
    
    if checkpointer is None:
        print(f"💾 Checkpoint: In-memory (no persistence)")
    else:
        print(f"💾 Checkpoint: {type(checkpointer).__name__}")
    
    print(f"📁 Workspace: {WORKSPACE_ROOT.absolute()}")
    
    model = get_kimi_model()
    
    # Set the memory store for tools
    set_memory_store(store)
    
    agent = create_deep_agent(
        model=model,
        name="simple-agent",
        
        system_prompt=BASE_SYSTEM_PROMPT,
        
        tools=[
            read_memory,    # Tool to read current user memory
            update_memory,  # Tool to add specific facts to memory
            clear_memory,   # Tool to clear all memory
            read_docx,      # Tool to read .docx files
        ],
        subagents=[],  # No subagents
        backend=create_backend,
        store=store,
        checkpointer=checkpointer,
    )
    
    # Return both agent and store so chat.py can access memory
    return agent, store


def get_agent_with_memory(agent, store, user_id: str):
    """
    Get system prompt with user memory injected.
    Returns the full system prompt including memory.
    """
    memory_data = load_memory_from_store(store, user_id)
    memory_content = format_memory_for_prompt(memory_data)
    return get_system_prompt_with_memory(BASE_SYSTEM_PROMPT, memory_content)


if __name__ == "__main__":
    print("Initializing Simple Agent...")
    
    if not os.getenv("MOONSHOT_API_KEY"):
        print("⚠️  MOONSHOT_API_KEY not set!")
        exit(1)
    
    agent, store = create_criterion_c_agent()
    print("✅ Agent ready!")
