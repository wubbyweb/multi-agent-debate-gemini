# Multi-Agent Debate Architecture

This repository implements a Multi-Agent Debate System utilizing LangGraph, LangChain, and xAI's `grok-4-1-fast-reasoning` model. The system is designed to simulate a comprehensive discussion among three specialized AI sub-agents managed by a central Coordinator to thoroughly address complex queries.

## 🧠 System Architecture

- **Orchestration Framework:** LangGraph (using `StateGraph`)
- **Inference Engine:** xAI API (`grok-4-1-fast-reasoning` via `langchain-xai`)
- **State Persistence (Memory):** SQLite (via LangGraph's `SqliteSaver`)
- **Language:** Python 3.10+

## 👥 Agent Roles

1. **Coordinator:** The central router. Evaluates the user's prompt and the current state of the debate. It delegates tasks to sub-agents if arguments are incomplete. When the sub-agents reach alignment, the Coordinator flags `consensus_reached` as `True` and synthesizes the final output.
2. **Harper (Researcher):** Grounds the debate with empirical facts, data, and external context.
3. **Benjamin (Logician):** Stress-tests logic. Evaluates Harper's data or user's prompt for mathematical accuracy, code correctness, or logical fallacies.
4. **Lucas (Creative):** Generates alternative angles, edge cases, and lateral narrative structures.

## 📂 Project Structure

- `main.py`: The entry point and core implementation of the A2A (Agent-to-Agent) protocol using LangGraph.
- `requirements.txt`: Project dependencies.
- `a2a_memory.sqlite`: An automatically generated lightweight SQLite database for persistent memory across sessions.
- `requirements.md`: The original technical specification.

## ⚙️ Setup Instructions

### 1. Prerequisites

Ensure you have Python 3.10 or higher installed.

### 2. Install Dependencies

You can install the required packages using `pip`:

```bash
pip install -r requirements.txt
```

### 3. Environment Variables

The system relies on the xAI API for inference. You must export your API key before running the application.

```bash
export XAI_API_KEY="your_actual_xai_api_key_here"
```

*Note: If the `XAI_API_KEY` is not set, the application will fallback to a mocked execution for demonstration purposes.*

## 🚀 Running the Debate

You can run the debate using the CLI provided in `main.py`. The script accepts a topic or prompt and an optional session ID for memory tracking.

### Basic Usage

```bash
python main.py --prompt "Design an optimal microservices architecture for a high-frequency trading platform."
```

### Advanced Usage with Persistent Memory

The graph supports checkpointer memory via SQLite. You can resume previous sessions or track specific debates using the `--session` flag.

```bash
python main.py --prompt "What are the security implications of this architecture?" --session "trading_arch_001"
```

## 🛠️ Key Implementation Details

1. **State Definition:** The graph relies on a strongly typed `DebateState` dictionary to pass context (`messages`), track the current speaker (`active_agent`), prevent infinite loops (`debate_rounds`), and determine when execution ends (`consensus_reached`).
2. **Conditional Routing:** The Coordinator acts as a conditional router that forces the model to return a structured Pydantic object (`RoutingDecision`), ensuring deterministic graph navigation.
3. **Token Optimization:** A rolling history window (`get_recent_messages`) ensures that the `messages` array doesn't overwhelm the token limit or context window during multi-round debates.