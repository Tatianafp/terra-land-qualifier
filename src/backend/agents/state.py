"""
State definition for the LangGraph qualification agent.

This module defines the state structure that flows through
the agent's state machine.
"""

from typing import Annotated, Optional, Sequence, Dict, Any

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages
from typing_extensions import TypedDict


class QualificationState(TypedDict):
    """
    State object that flows through the qualification agent graph.
    
    This state is updated as the conversation progresses and data is collected.
    """
    
    # Conversation history
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # Extracted data points
    bairro: Optional[str]
    cidade: Optional[str]
    land_size_m2: Optional[float]
    asking_price: Optional[float]
    legal_status: Optional[str]
    owner_type: Optional[str]  # "corretor" or "proprietario"
    differentials: Optional[str]  # vista mar, frente mar, etc
    
    # Validation flags
    location_validated: bool
    is_qualified: bool

    # Qualification lifecycle
    qualification_status: str  # "in_progress" | "complete"
    qualification_complete: bool
    
    # Final output
    qualification_result: Optional[Dict[str, Any]]
    next_step: Optional[str]
    
    # Metadata
    conversation_id: str
    turn_count: int