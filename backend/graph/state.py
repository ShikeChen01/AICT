"""
Graph state definition for the AICT backend.
"""

from typing import TypedDict, Annotated, List, Dict, Any
import operator
from langchain_core.messages import BaseMessage

class AgentState(TypedDict):
    """
    State for the Manager-Engineer graph.
    
    Attributes:
        messages: Chat history (append-only).
        next: The next node to execute ("Manager", "Engineer", or END).
        project_id: The ID of the project being worked on.
        current_task: Context for the task currently in focus (if any).
        review_queue: List of PR URLs or IDs waiting for Manager review.
    """
    messages: Annotated[List[BaseMessage], operator.add]
    next: str
    project_id: str
    current_task: Dict[str, Any]
    review_queue: List[str]
