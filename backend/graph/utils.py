"""
Utility functions for the graph module.
"""

from typing import Any, Union


def extract_text_content(content: Union[str, list, Any]) -> str:
    """
    Safely extract text from message content.
    
    LLM responses can have content as:
    - str: plain text
    - list: multi-part content like [{"type": "text", "text": "..."}]
    - other: fallback to empty string
    
    Args:
        content: Message content, can be string, list of parts, or other
        
    Returns:
        Extracted text as a single string
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        text_parts = []
        for part in content:
            if isinstance(part, str):
                text_parts.append(part)
            elif isinstance(part, dict) and part.get("type") == "text":
                text_parts.append(part.get("text", ""))
        return " ".join(text_parts)
    return ""
