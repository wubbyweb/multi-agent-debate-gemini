import os
import sqlite3
import operator
import argparse
from typing import Annotated, Sequence, TypedDict, Literal

from pydantic import BaseModel, Field
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_xai import ChatXAI


# ==========================================
# 1. State Definition
# ==========================================
class DebateState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], operator.add]
    active_agent: str          # Tracks which agent holds the floor
    debate_rounds: int         # Prevents infinite loops
    consensus_reached: bool    # Boolean flag evaluated by the Coordinator
    final_output: str          # The synthesized final response


# ==========================================
# 2. Structured Output for Coordinator Routing
# ==========================================
class RoutingDecision(BaseModel):
    consensus_reached: bool = Field(
        description="Whether the debate has reached a conclusion or consensus based on the agents' input."
    )
    next_agent: Literal["Harper", "Benjamin", "Lucas", "END"] = Field(
        description="The next agent to speak. Use END if consensus is reached or if the debate should terminate."
    )
    rationale: str = Field(
        description="The reasoning for routing to this specific agent or for determining consensus."
    )
    final_output: str = Field(
        default="", 
        description="The synthesized final response to the user. Only populated if consensus_reached is True."
    )


# ==========================================
# 3. Model Initialization
# ==========================================
# Ensure XAI_API_KEY is available in your environment variables
xai_api_key = os.environ.get("XAI_API_KEY", "YOUR_XAI_API_KEY")

try:
    if xai_api_key == "YOUR_XAI_API_KEY":
        raise ValueError("API key not set.")
    # Initialize the Grok model
    llm = ChatXAI(
        xai_api_key=xai_api_key, 
        model="grok-4-1-fast-reasoning"
    )
    # The Coordinator uses structured output for routing decisions
    routing_llm = llm.with_structured_output(RoutingDecision)
except Exception as e:
    print(f"Warning: ChatXAI initialization failed. Ensure you have the langchain-xai package and XAI_API_KEY set. Error: {e}")
    class MockLLM:
        def invoke(self, messages):
            return AIMessage(content="This is a mocked agent response due to missing API key or library.")
        def with_structured_output(self, model):
            class MockStructured:
                def invoke(self, messages):
                    # Mock routing logic: 1 round to Harper, then consensus
                    if len(messages) < 4:
                        return RoutingDecision(consensus_reached=False, next_agent="Harper", rationale="Need to research.")
                    return RoutingDecision(consensus_reached=True, next_agent="END", rationale="Consensus reached.", final_output="Mock synthesized final response based on research.")
            return MockStructured()
    llm = MockLLM()
    routing_llm = llm.with_structured_output(RoutingDecision)


# ==========================================
# 4. Helper & Node Functions
# ==========================================
def get_recent_messages(messages: Sequence[BaseMessage], max_history: int = 6) -> Sequence[BaseMessage]:
    """Token optimization: keep only the original prompt and the most recent messages."""
    if len(messages) <= max_history + 1:
        return messages
    return [messages[0]] + list(messages[-max_history:])

def coordinator_node(state: DebateState) -> dict:
    """The Coordinator evaluates the state and delegates or concludes."""
    messages = state.get("messages", [])
    recent_messages = get_recent_messages(messages)
    
    system_prompt = SystemMessage(
        content=(
            "You are the Coordinator of a debate among three sub-agents:\n"
            "- Harper (Researcher): Grounds debate with facts.\n"
            "- Benjamin (Logician): Stress-tests logic and code.\n"
            "- Lucas (Creative): Generates out-of-the-box ideas and alternatives.\n\n"
            "Evaluate the current state of the conversation.\n"
            "If arguments are scattered or incomplete, delegate to Harper, Benjamin, or Lucas to gather more information, stress-test logic, or think creatively.\n"
            "If the sub-agents align and the user's request is fully addressed, flip 'consensus_reached' to True and draft the 'final_output'."
        )
    )
    
    # Invoke the LLM with structured output to get routing decision
    decision: RoutingDecision = routing_llm.invoke([system_prompt] + list(recent_messages))
    
    new_state = {
        "active_agent": decision.next_agent,
        "consensus_reached": decision.consensus_reached,
        "final_output": decision.final_output,
        "debate_rounds": state.get("debate_rounds", 0) + 1
    }
    
    if not decision.consensus_reached:
        content = f"Delegating to {decision.next_agent}. Rationale: {decision.rationale}"
        new_state["messages"] = [AIMessage(content=content, name="Coordinator")]
    
    return new_state

def agent_node(state: DebateState, agent_name: str, role_description: str) -> dict:
    """Generic function for sub-agents to respond based on their persona."""
    messages = state.get("messages", [])
    recent_messages = get_recent_messages(messages)
    
    system_prompt = SystemMessage(
        content=(
            f"You are {agent_name}. {role_description}\n"
            "Respond to the current state of the debate, adding your unique perspective."
        )
    )
    
    response = llm.invoke([system_prompt] + list(recent_messages))
    content = f"[{agent_name}]: {response.content}"
    
    return {"messages": [AIMessage(content=content, name=agent_name)]}

def researcher_node(state: DebateState) -> dict:
    return agent_node(state, "Harper", "You are the Researcher. Ground the debate with facts, data, and external context.")

def logician_node(state: DebateState) -> dict:
    return agent_node(state, "Benjamin", "You are the Logician. Stress-test the logic. Evaluate data or prompts for mathematical accuracy, code correctness, or logical fallacies.")

def creative_node(state: DebateState) -> dict:
    return agent_node(state, "Lucas", "You are the Creative. Generate alternative angles, edge cases, and out-of-the-box narrative structures.")


# ==========================================
# 5. Routing Logic
# ==========================================
def route_debate(state: DebateState):
    """Conditional routing based on Coordinator's decision."""
    if state.get("consensus_reached") or state.get("debate_rounds", 0) >= 3:
        return END
    
    agent = state.get("active_agent")
    if agent in ["Harper", "Benjamin", "Lucas"]:
        return agent
    
    # Fallback to end if routing is invalid
    return END


# ==========================================
# 6. Graph Compilation
# ==========================================
# Initialize lightweight persistent memory
db_path = "a2a_memory.sqlite"
conn = sqlite3.connect(db_path, check_same_thread=False)
memory = SqliteSaver(conn)

# Build the Graph
builder = StateGraph(DebateState)

# Add Nodes
builder.add_node("Coordinator", coordinator_node)
builder.add_node("Harper", researcher_node)
builder.add_node("Benjamin", logician_node)
builder.add_node("Lucas", creative_node)

# Set Entry
builder.set_entry_point("Coordinator")

# Sub-agents always report back to the Coordinator
builder.add_edge("Harper", "Coordinator")
builder.add_edge("Benjamin", "Coordinator")
builder.add_edge("Lucas", "Coordinator")

# Coordinator decides who speaks next or ends the graph
builder.add_conditional_edges("Coordinator", route_debate)

# Compile with persistent memory
debate_graph = builder.compile(checkpointer=memory)


# ==========================================
# 7. Execution Entry Point
# ==========================================
def main():
    parser = argparse.ArgumentParser(description="Multi-Agent Debate CLI")
    parser.add_argument("--prompt", type=str, required=True, help="The initial topic or prompt for the debate.")
    parser.add_argument("--session", type=str, default="session_001", help="Session ID for SQLite memory tracking.")
    args = parser.parse_args()

    thread_config = {"configurable": {"thread_id": args.session}}
    
    print(f"Starting Multi-Agent Debate for session '{args.session}'...")
    print(f"Topic: {args.prompt}\n")
    print("-" * 50)
    
    # Configure the initial state
    initial_input = {
        "messages": [HumanMessage(content=args.prompt)],
        "active_agent": "Coordinator",
        "debate_rounds": 0,
        "consensus_reached": False,
        "final_output": ""
    }

    # Stream the graph execution
    for event in debate_graph.stream(initial_input, config=thread_config):
        for node, state_update in event.items():
            print(f"\n>> Output from {node}:")
            
            # Print messages if any were generated
            if "messages" in state_update and state_update["messages"]:
                # AIMessages are wrapped in lists due to operator.add
                msg = state_update["messages"][-1]
                print(msg.content)
            
            # Print final output if consensus reached
            if node == "Coordinator" and state_update.get("consensus_reached"):
                print("\n" + "=" * 50)
                print("🏁 FINAL SYNTHESIS REACHED 🏁")
                print("=" * 50)
                print(state_update.get("final_output", "No output generated."))

if __name__ == "__main__":
    main()