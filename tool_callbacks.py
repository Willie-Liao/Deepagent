"""
Tool Call Callbacks - Display tool usage in terminal

These callbacks print tool calls and results to the terminal for user visibility.
IMPORTANT: These DO NOT add content to the LLM context window - they are purely
for logging/display purposes.
"""

from typing import Any, Dict, List, Optional
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.agents import AgentAction, AgentFinish
from langchain_core.messages import BaseMessage
import json


class CompactToolPrinter(BaseCallbackHandler):
    """
    Compact tool call printer - shows one-line summary by default.
    
    This is always active to show tool usage without cluttering the terminal.
    Tool output is for display only and does NOT affect context window.
    """
    
    def __init__(self, max_preview: int = 60):
        self.max_preview = max_preview
        self._tool_count = 0
        self._current_tool = None
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any
    ) -> None:
        """Called when a tool starts executing."""
        self._tool_count += 1
        self._current_tool = serialized.get("name", "unknown")
        print(f"   🔧 Using: {self._current_tool}...", end="", flush=True)
    
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any
    ) -> None:
        """Called when a tool finishes executing."""
        output_str = str(output)
        preview = output_str[:self.max_preview].replace("\n", " ")
        if len(output_str) > self.max_preview:
            preview += f"... ({len(output_str)} chars)"
        
        # Clear the "..." and print result on same line or next
        print(f"\r   🔧 {self._current_tool} → {preview[:50]}")
    
    def on_tool_error(
        self,
        error: BaseException,
        **kwargs: Any
    ) -> None:
        """Called when a tool errors."""
        print(f"\r   ❌ {self._current_tool} failed: {error}")


class ToolCallPrinter(BaseCallbackHandler):
    """
    Detailed tool call printer - shows full input/output.
    
    Use with --show-tools flag for verbose output.
    This does NOT add to the LLM context window - it's purely for display.
    """
    
    def __init__(self, max_input_length: int = 500, max_output_length: int = 800):
        self.max_input_length = max_input_length
        self.max_output_length = max_output_length
        self._tool_count = 0
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any
    ) -> None:
        """Called when a tool starts executing."""
        self._tool_count += 1
        tool_name = serialized.get("name", "unknown")
        
        # Format input for display
        if len(input_str) > self.max_input_length:
            input_display = input_str[:self.max_input_length] + "... [truncated]"
        else:
            input_display = input_str
        
        print(f"\n🔧 [{self._tool_count}] TOOL CALL: {tool_name}")
        print(f"   Input: {input_display}")
    
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any
    ) -> None:
        """Called when a tool finishes executing."""
        output_str = str(output)
        
        # Format output for display
        if len(output_str) > self.max_output_length:
            output_display = output_str[:self.max_output_length] + f"... [{len(output_str) - self.max_output_length} more chars]"
        else:
            output_display = output_str
        
        print(f"   Result: {output_display}")
        print(f"   ✓ Done")
    
    def on_tool_error(
        self,
        error: BaseException,
        **kwargs: Any
    ) -> None:
        """Called when a tool errors."""
        print(f"   ❌ Error: {error}")


class SubagentCallPrinter(BaseCallbackHandler):
    """
    Prints subagent calls to terminal.
    
    This helps track which subagents are being called and when.
    """
    
    def __init__(self):
        self._subagent_count = 0
    
    def on_chain_start(
        self,
        serialized: Dict[str, Any],
        inputs: Dict[str, Any],
        **kwargs: Any
    ) -> None:
        """Called when a chain/subagent starts."""
        chain_name = serialized.get("name", "unknown")
        
        # Only print for subagents (not the main agent)
        if any(name in chain_name.lower() for name in [
            "criterion-analyzer",
            "prompt-designer", 
            "rubric-generator",
            "standard-validator"
        ]):
            self._subagent_count += 1
            print(f"\n🤖 [{self._subagent_count}] SUBAGENT: {chain_name}")
            # Show the task/prompt briefly
            messages = inputs.get("messages", [])
            if messages:
                last_msg = messages[-1]
                content = last_msg.get("content", "") if isinstance(last_msg, dict) else str(last_msg)
                if len(content) > 100:
                    content = content[:100] + "..."
                print(f"   Task: {content}")
    
    def on_chain_end(
        self,
        outputs: Dict[str, Any],
        **kwargs: Any
    ) -> None:
        """Called when a chain/subagent ends."""
        pass  # Don't print end to avoid clutter


class DebugPrinter(BaseCallbackHandler):
    """
    Comprehensive debug printer showing all agent activity.
    
    This is more verbose and shows LLM calls, tool calls, and subagent calls.
    """
    
    def __init__(self, show_llm_calls: bool = False):
        self.show_llm_calls = show_llm_calls
        self._indent = 0
    
    def _print(self, message: str):
        """Print with indentation."""
        indent = "  " * self._indent
        print(f"{indent}{message}")
    
    def on_llm_start(
        self,
        serialized: Dict[str, Any],
        prompts: List[str],
        **kwargs: Any
    ) -> None:
        """Called when LLM starts (optional - can be noisy)."""
        if self.show_llm_calls:
            model = serialized.get("id", ["unknown"])[-1]
            print(f"\n🧠 LLM Call: {model}")
    
    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        **kwargs: Any
    ) -> None:
        """Called when tool starts."""
        tool_name = serialized.get("name", "unknown")
        self._print(f"🔧 Tool: {tool_name}")
        self._indent += 1
        
        # Pretty print JSON input if possible
        try:
            input_data = json.loads(input_str)
            input_display = json.dumps(input_data, indent=2, ensure_ascii=False)
        except json.JSONDecodeError:
            input_display = input_str[:300]
            if len(input_str) > 300:
                input_display += "..."
        
        for line in input_display.split("\n")[:10]:  # Limit lines
            self._print(f"→ {line}")
        if len(input_display.split("\n")) > 10:
            self._print("→ ...")
    
    def on_tool_end(
        self,
        output: str,
        **kwargs: Any
    ) -> None:
        """Called when tool ends."""
        self._indent -= 1
        output_str = str(output)
        preview = output_str[:200].replace("\n", " ")
        if len(output_str) > 200:
            preview += f"... ({len(output_str)} chars total)"
        self._print(f"✓ Result: {preview}")


# Convenience function for chat.py
def get_tool_callbacks(debug: bool = False, show_tools: bool = False) -> List[BaseCallbackHandler]:
    """
    Get the appropriate callbacks for the agent.
    
    Args:
        debug: If True, use verbose debug printer
        show_tools: If True, show detailed tool output
    
    Returns:
        List of callback handlers
    """
    callbacks = []
    
    if debug:
        callbacks.append(DebugPrinter(show_llm_calls=True))
        callbacks.append(SubagentCallPrinter())
    elif show_tools:
        callbacks.append(ToolCallPrinter())
        callbacks.append(SubagentCallPrinter())
    else:
        # Default: compact tool printer always shows tool usage
        callbacks.append(CompactToolPrinter())
    
    return callbacks
