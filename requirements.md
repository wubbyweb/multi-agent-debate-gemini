# Technical Specification: Multi-Agent Debate Architecture

## 1. System Architecture & Tech Stack
* **Orchestration Framework:** LangGraph (using `StateGraph`).
* **Inference Engine:** xAI API (`grok-4-1-fast-reasoning` via `langchain-xai`).
* **State Persistence (Memory):** SQLite (via LangGraph's `SqliteSaver`).
* **Language:** Python 3.10+

## 2. Core State Definition
The graph requires a robust state dictionary to pass context, track the debate history, and determine when consensus is reached.

```python
from typing import Annotated, Sequence, TypedDict
from langchain_core.messages import BaseMessage
import operator

class DebateState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    active_agent: str          # Tracks which agent holds the floor
    debate_rounds: int         # Prevents infinite loops
    consensus_reached: bool    # Boolean flag evaluated by the Coordinator
    final_output: str          # The synthesized final response
```

## 3. Agent Roles & System Prompts
Each agent is a node in the LangGraph. They all utilize `grok-4-1-fast-reasoning` but are constrained by strict system prompts to maintain their personas.

* **Coordinator (Grok Node):** * **Role:** Evaluates the current state of the debate. If arguments are scattered, it delegates to Harper, Benjamin, or Lucas. If the sub-agents align, it flips `consensus_reached` to `True` and drafts the `final_output`.
* **Researcher (Harper Node):** * **Role:** Grounds the debate. You can equip this node with LangChain tools (e.g., Tavily or a web scraper) to pull external data.
* **Logician (Benjamin Node):** * **Role:** Stress-tests the logic. Evaluates Harper's data or the user's prompt for mathematical accuracy, code correctness, or logical fallacies.
* **Creative (Lucas Node):** * **Role:** Generates alternative angles, edge cases, and narrative structures. 

## 4. Memory Management (SQLite)
To persist memory across sessions, we utilize LangGraph's SQLite checkpointer. 

```python
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

# Initialize lightweight persistent memory
db_path = "a2a_memory.sqlite"
conn = sqlite3.connect(db_path, check_same_thread=False)
memory = SqliteSaver(conn)
```

## 5. Graph Orchestration (The A2A Protocol)
The execution flow relies on conditional routing. The Coordinator acts as the central router, evaluating the input and passing execution to the sub-agents, who then pass their findings back to the Coordinator for review.

```python
from langgraph.graph import StateGraph, END
from langchain_xai import ChatXAI

llm = ChatXAI(
    xai_api_key="YOUR_XAI_API_KEY", 
    model="grok-4-1-fast-reasoning"
)

# 1. Define Node Functions
def coordinator_node(state: DebateState):
    # LLM call to evaluate messages. 
    # Returns updated state with next active_agent or final_output.
    pass

def researcher_node(state: DebateState):
    # Tool-enabled LLM call for fact-finding.
    pass

def logician_node(state: DebateState):
    # LLM call strictly for logical/code validation.
    pass

def creative_node(state: DebateState):
    # LLM call for lateral thinking.
    pass

# 2. Define Routing Logic
def route_debate(state: DebateState):
    if state.get("consensus_reached") or state.get("debate_rounds", 0) >= 3:
        return END
    
    # Route to the agent chosen by the Coordinator
    return state["active_agent"]

# 3. Build the Graph
builder = StateGraph(DebateState)

builder.add_node("Coordinator", coordinator_node)
builder.add_node("Harper", researcher_node)
builder.add_node("Benjamin", logician_node)
builder.add_node("Lucas", creative_node)

builder.set_entry_point("Coordinator")

# Sub-agents always report back to the Coordinator
builder.add_edge("Harper", "Coordinator")
builder.add_edge("Benjamin", "Coordinator")
builder.add_edge("Lucas", "Coordinator")

# Coordinator decides who speaks next or ends the graph
builder.add_conditional_edges("Coordinator", route_debate)

# Compile with persistent memory
debate_graph = builder.compile(checkpointer=memory)
```

## 6. Execution and Invocation
To trigger the A2A protocol, you invoke the graph with a specific thread ID. The SQLite checkpointer handles the rest.

```python
thread_config = {"configurable": {"thread_id": "session_001"}}
initial_input = {
    "messages": [("user", "Design an optimal microservices architecture for a high-frequency trading platform.")],
    "active_agent": "Coordinator",
    "debate_rounds": 0,
    "consensus_reached": False
}

# Stream the debate process in real-time
for event in debate_graph.stream(initial_input, config=thread_config):
    for node, state_update in event.items():
        print(f"--- Output from {node} ---")
        print(state_update)
```

## 7. Key Considerations for Implementation
* **Token Optimization:** Because four agents are communicating, context windows fill up quickly. Implement a mechanism within the `coordinator_node` to summarize the `messages` array before passing it back to the sub-agents to keep inference costs down.
* **Structured Outputs:** To ensure the Coordinator properly updates the `active_agent` and `consensus_reached` flags, force the model to return a structured Pydantic object (using `.with_structured_output()`) during the routing phase.