"""
Short-term memory management for DeepAgent.
Follows the langgraph_memory pattern from memory_store.py.
"""

from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime
from langchain_core.messages import SystemMessage
from langchain_openai import ChatOpenAI


class UserMemory(BaseModel):
    """User information extracted from conversations"""
    facts: list[str] = Field(
        default_factory=list,
        description="Key facts about the user (name, role, preferences, etc.)"
    )
    context: list[str] = Field(
        default_factory=list, 
        description="Context from recent conversations"
    )
    last_updated: Optional[str] = Field(
        default=None,
        description="ISO timestamp of last update"
    )


# Memory namespace follows langgraph pattern: ("memory", user_id)
MEMORY_NAMESPACE = "memory"
MEMORY_KEY = "user_memory"


def get_memory_namespace(user_id: str) -> tuple:
    """Get the namespace tuple for a user's memory."""
    return (MEMORY_NAMESPACE, user_id)


# Chatbot instruction - same pattern as memory_store.py
MODEL_SYSTEM_MESSAGE = """You are a helpful assistant with filesystem access.

## Available Tools
- read_file(path, offset, limit): Read file contents
- write_file(file_path, content): Create new files
- edit_file(file_path, old_string, new_string): Edit existing files
- ls(path): List directory contents
- glob(pattern): Find files by pattern
- grep(pattern): Search file contents

## Tool Usage Rules
1. When user asks to read/view/show a file → CALL read_file IMMEDIATELY
2. When user asks to write/save/create a file → CALL write_file IMMEDIATELY  
3. When user asks to edit/modify/change a file → CALL edit_file IMMEDIATELY
4. DO NOT say "I will read..." or "I would write..." → JUST CALL THE TOOL
5. DO NOT describe what you would do → DO IT

## User Memory
{memory}

Use this memory to personalize your responses. If memory is empty, learn about the user through conversation."""


# Create new memory from the chat history - same pattern as memory_store.py
CREATE_MEMORY_INSTRUCTION = """You are collecting information about the user to personalize your responses.

CURRENT USER INFORMATION:
{memory}

INSTRUCTIONS:
1. Review the chat history below carefully
2. Identify new information about the user, such as:
   - Personal details (name, role, school)
   - Preferences (sports they teach, year levels they work with)
   - Assessment needs and patterns
   - Past work or context from previous conversations
3. Merge any new information with existing memory
4. Format the memory as a clear, bulleted list
5. If new information conflicts with existing memory, keep the most recent version

Remember: Only include factual information directly stated by the user. Do not make assumptions or inferences.

Based on the chat history below, please update the user information:"""


def format_memory_for_prompt(memory_dict: dict) -> str:
    """Format memory dict for injection into system prompt."""
    if not memory_dict or not memory_dict.get("memory"):
        return "No memory yet. This is a new conversation."
    return memory_dict.get("memory", "")


def reflect_and_update_memory(
    messages: list,
    existing_memory: dict,
    model: ChatOpenAI
) -> dict:
    """
    Reflect on conversation and update memory.
    Follows the same pattern as memory_store.py's write_memory function.
    """
    # Extract existing memory content
    if existing_memory and existing_memory.get("memory"):
        existing_memory_content = existing_memory.get("memory")
    else:
        existing_memory_content = "No existing memory found."
    
    # Format the memory in the system prompt for reflection
    system_msg = CREATE_MEMORY_INSTRUCTION.format(memory=existing_memory_content)
    
    # Convert messages to format expected by model
    from langchain_core.messages import HumanMessage, AIMessage
    formatted_messages = []
    for m in messages:
        role = m.get("role", "")
        content = m.get("content", "")
        if role == "user":
            formatted_messages.append(HumanMessage(content=content))
        elif role == "assistant":
            formatted_messages.append(AIMessage(content=content))
    
    # Call LLM to reflect and generate new memory
    response = model.invoke([SystemMessage(content=system_msg)] + formatted_messages)
    
    # Return updated memory dict
    return {
        "memory": response.content,
        "last_updated": datetime.now().isoformat()
    }


def get_system_prompt_with_memory(base_prompt: str, memory_content: str) -> str:
    """Inject memory into system prompt."""
    memory_section = f"\n\n## User Memory\n{memory_content}\n\nUse this memory to personalize your responses."
    return base_prompt + memory_section


def load_memory_from_store(store, user_id: str) -> dict:
    """Load user memory from the store."""
    namespace = get_memory_namespace(user_id)
    existing = store.get(namespace, MEMORY_KEY)
    if existing and existing.value:
        return existing.value
    return {}


def save_memory_to_store(store, user_id: str, memory_data: dict):
    """Save user memory to the store."""
    namespace = get_memory_namespace(user_id)
    store.put(namespace, MEMORY_KEY, memory_data)
