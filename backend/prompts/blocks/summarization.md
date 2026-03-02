Your conversation context is approaching its limit. You have a new user prompt to work on.
Summarize the important context into your working memory using update_memory. The user's
new message gives you direction on what is most relevant to keep. Focus on:
- What task you are working on and its current state
- Key decisions made and why
- What remains to be done
- Any blockers or open questions
- Relevant context from past sessions that relates to the user's new request

After updating your memory, call compact_history to remove past session messages from context.
Past session messages remain accessible via read_history.