# IB MYP PHE Criterion C Prompt Writer

An AI-powered assessment design tool built with [DeepAgents SDK](https://docs.langchain.com/oss/python/deepagents/overview) and [Kimi 2.5](https://www.moonshot.cn/) to help IB MYP Physical and Health Education teachers create high-quality, standards-aligned assessment prompts and rubrics for **Criterion C: Applying and Performing**.

## Features

- 🤖 **Kimi 2.5 Integration**: Uses Moonshot AI's Kimi K2.5 model with non-thinking mode for efficient, structured responses
- 📚 **IB Standards Aligned**: Built on official IB MYP PHE assessment criteria
- 🎯 **Criterion C Focus**: Specialized for "Applying and Performing" assessments
- 📝 **Complete Rubrics**: Generates achievement level descriptors with appropriate command terms
- ✅ **Validation**: Built-in validation to ensure tasks meet Criterion C requirements
- 💾 **Persistent Memory**: Saves generated prompts and rubrics for future reference
- 💾 **Checkpoint Persistence**: SQLite-based checkpointing - resume conversations after restart
- 🔍 **Exa Web Search**: Research latest PE practices, assessment examples, and sports techniques

## Project Structure

```
test_deepagent/
├── agent.py                 # Main agent configuration with subagents
├── tools.py                 # Custom tools for criterion reference loading
├── example_usage.py         # Example usage scripts
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (API keys)
├── README.md               # This file
├── skills/                 # Symlink to IB MYP rubric skill
│   └── myp-rubric-creator/
│       ├── SKILL.md
│       └── references/
│           └── assessment_criteria.md
└── workspace/              # Backend storage (auto-created on first run)
    ├── drafts/             # Ephemeral working files
    ├── memories/           # Persistent memory storage
    └── output/             # Generated prompts and rubrics
```

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Set Up API Key

Edit the `.env` file and add your Moonshot API key:

```bash
MOONSHOT_API_KEY=your_moonshot_api_key_here
```

Get your API key from: https://platform.moonshot.cn/

### 3. Run Examples

```bash
python example_usage.py
```

Follow the menu to try different examples:
- Basketball Dribbling (Year 3)
- Swimming Front Crawl (Year 5)
- Soccer Passing (Year 1)
- Task validation

### 4. Use in Your Code

```python
from agent import create_criterion_c_agent

# Create the agent
agent = create_criterion_c_agent()

# Generate an assessment
result = agent.invoke({
    "messages": [{
        "role": "user",
        "content": "Create a Criterion C assessment for volleyball setting for MYP Year 3"
    }]
})

print(result["messages"][-1].content)
```

## Agent Architecture

The agent uses a multi-subagent workflow:

```
┌─────────────────────────────────────────────────────────────────┐
│                    MAIN ORCHESTRATOR AGENT                       │
│              (Coordinates the workflow with Kimi 2.5)            │
└──────────────────────┬──────────────────────────────────────────┘
                       │ delegates via task()
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
┌──────────────┐ ┌──────────┐ ┌────────────────┐
│  CRITERION   │ │  PROMPT  │ │    RUBRIC      │
│  ANALYZER    │ │ DESIGNER │ │   GENERATOR    │
│              │ │          │ │                │
└──────────────┘ └──────────┘ └────────────────┘
                       │
                       ▼
              ┌────────────────┐
              │    VALIDATOR   │
              │                │
              └────────────────┘
```

### Subagents

1. **Criterion Analyzer**: Analyzes activity context and identifies Criterion C requirements
2. **Prompt Designer**: Creates performance-based assessment tasks
3. **Rubric Generator**: Generates achievement level descriptors
4. **Standard Validator**: Validates alignment with IB standards

### Custom Tools

- `get_criterion_reference(year, criterion)`: Load official IB achievement level descriptors
- `get_year_level_command_terms(year)`: Get command terms for specific year level
- `validate_criterion_c_context(task)`: Validate if task is appropriate for Criterion C
- `search_exa(query, type)`: Search the web using Exa AI for PE research
- `search_exa_structured(query, schema)`: Extract structured data from web search

## Criterion C Requirements

From the IB MYP PHE Guide:

### Assessment Context
- **Must** be assessed in performance/playing situations
- **Cannot** assess replication of movement routines
- **Cannot** assess umpiring/refereeing

### Three Strands

1. **Skills and Techniques**: Accuracy, efficiency, control, coordination, timing, fluency, speed, power
2. **Strategies and Movement Concepts**: Use of space, force, flow, adaptation
3. **Information Processing**: Reading situations, decision-making, responding to feedback

### Command Terms by Year Level

| Year Level | Primary Terms | Secondary Terms |
|------------|---------------|-----------------|
| Year 1 | recall, state, identify, outline | apply, solve, suggest |
| Year 3 | demonstrate, apply, describe | explain, identify, design |
| Year 5 | demonstrate, apply, analyse | evaluate, justify, explain |

## Example Output

The agent generates structured assessments like:

```markdown
# Basketball Dribbling Assessment - Criterion C

**Year Level:** Year 3  
**Criterion:** C - Applying and Performing  
**Maximum Score:** 8

## Task Description
Students will demonstrate control and coordination while dribbling through a defensive 
pressure course. They must perform various techniques (crossover, behind-the-back, 
between-the-legs) while maintaining possession against passive defense.

## Achievement Level Descriptors

| Level | Descriptor |
|:-----:|:-----------|
| **0** | The student does not reach a standard described by any of the descriptors below. |
| **1–2** | The student:<br>i. **recalls** and **applies** skills and techniques with limited success<br>ii. **recalls** and **applies** strategies and movement concepts with limited success<br>iii. **recalls** and **applies** information to perform. |
| **3–4** | ... |
| **5–6** | ... |
| **7–8** | ... |
```

## Configuration

### Model Settings

The agent is configured to use Kimi 2.5 with these settings:

```python
model="kimi-k2.5",
base_url="https://api.moonshot.ai/v1",
thinking={"type": "disabled"},  # Non-thinking mode
max_tokens=32768,
```

### Backend Storage

The agent uses a **three-tier backend**:

```
workspace/                      ← Physical directory on disk
├── drafts/                     ← Ephemeral working files (StateBackend)
├── memories/                   ← Persistent memory (StoreBackend + InMemoryStore)
└── output/                     ← Generated prompts and rubrics (FilesystemBackend)
```

| Path | Backend | Purpose | Persistence |
|------|---------|---------|-------------|
| `/` (default) | FilesystemBackend | Output files, rubrics, prompts | ✅ Saved to disk |
| `/memories/` | StoreBackend | Cross-thread memory, user preferences | ✅ InMemoryStore |
| `/drafts/` | StateBackend | Temporary working files | ❌ Ephemeral |

For production, replace `InMemoryStore` with `PostgresStore`.

### Checkpoint Persistence

Conversations are automatically saved to `checkpoints.sqlite`:

```bash
# First session
python chat.py
> Create a basketball assessment
[chat, exit]

# Restart - resume where you left off
python chat.py
> What was I working on?  # ← Agent remembers!
```

Each conversation uses a `thread_id`. To start fresh, use the `reset` command in chat.

## Troubleshooting

### API Key Issues
```
⚠️  MOONSHOT_API_KEY not set!
```
Solution: Add your API key to the `.env` file.

### Skill Not Found
```
Error: Assessment criteria file not found
```
Solution: Ensure the `skills` symlink points to the correct location.

### Model Connection Errors
```
Error connecting to Moonshot API
```
Solution: 
1. Check your internet connection
2. Verify your API key is valid
3. Check Moonshot API status

## Resources

- [IB MYP Physical and Health Education Guide](https://www.ibo.org/programmes/middle-years-programme/)
- [DeepAgents SDK Documentation](https://docs.langchain.com/oss/python/deepagents/overview)
- [Moonshot AI Documentation](https://platform.moonshot.cn/docs)

## License

MIT License - Feel free to modify and distribute.

## Contributing

Contributions welcome! Areas for improvement:
- Additional sport/activity templates
- Multi-criterion assessment support
- Integration with learning management systems
- Enhanced differentiation options
