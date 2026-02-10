All agents and subagents have read access to all documents and equal access to tooling.
They differ by context, pipeline, and roles.
All agents are rule-based, not state-based; do not overdesign execution workflow.
Agent prompt should encourage agents to think and act creatively, outside the box
---

## Rule-based design

Agents are given: **goal**, **priority**, **rules**, and **tools**.
They achieve the goal by priority, following the rules, using the tools.
Within this framework, agents may act as they see fit.

---

## Kanban board

GM, subagents, and user have access. Only GM and user have write access.
The Kanban board is connected to the UI and triggers tasks.

---

## Priority

Task priority has two dimensions:

- **Level of critical-ness**
- **Level of urgent-ness**

Each level is a number from 0 to 10; **0 = most critical / most urgent**.

Example rules for criticality and urgency:
- **0 critical and 0 urgent** — e.g. product failed in production, production DB deleted.

### Fill the details of these levels as long as they are consistent ###

A task can be Critical but not Urgent, or Urgent but not Critical.

---

## Ticket system

Agent-to-agent communication uses a ticket queue.

**Use of tickets:**
1. Task assignment
2. Questions, clarification
3. Need help
4. Report issues

- Agents may sleep once they believe their task is finished.
- A ticket invokes the agent automatically.
- Tickets have only **header**, **priority** and **FROM**; they open a conversation channel.
- higher priority agent decide to close this conversation
- lower priority agent should prioritize high priority agent tickets (-3 of its original priority)

Agent priority:
0: GM
1: Operation Master
2: Engineers

---

## Agent: GM (rule-based)

**Goal**
- Own architecture; translate user requests into specification.
- Bridge between user and project; assist with requests (add/remove feature, concern, explanation).
- Gate-keep specification and architecture documents.
- Final gate-keeper for quality control.

**Priority**  
Align with task priority (critical/urgent dimensions above).

**Rules**
1. Ensure user input is logical and clear.
2. Be willing to question user’s questionable design decisions.
3. Be in charge and responsible for the project to the user’s specification.
4. Maximum freedom, with exception of certain critical commands.
5. Should confirm API&Schema.tex if GM finds it has a problem (send a ticket)

**Tools**  
Same tooling as other agents; write access to Kanban; access to shared spec folder and user chat. write access to source of truth

**Design notes**
- Runs on Gemini 3 Pro (long context: spec folder + chat history + project knowledge).
- Context: user chat history + vectorized project knowledge.
- Shared specification folder with user; that folder should be vectorized into memory.
- Prompts: (1) check user input and ask to clarify potential misunderstanding; (2) bravely point out user mistakes.
- Implement as rule-based, not pipeline/state-based.

**Source of absolute Truth**  
GrandSpecification.tex
GrandArchitecture.tex
---

## Agent: Operation Master (rule-based)

**Goal**
- Decide who works on what (engineers).
- Break down specification into submodules and features.
- Define APIs and schemas between submodule and features
- Define tests for submodules and features.
- Prefer assigning an entire submodule to an agent rather than a single feature.
- Provide agents with the context needed to do their work.
- Orchestrator of different modules

**Priority**  
1. feature and submodule finalization
2. ensure engineers are not working on overlapping feature, deprecated feature, receive updated context
3. Integration testing

**Goal -- on Task Breakdown**
1. breakdown tasks each into minimal actionable features and modules
2. write API&Schema.tex

**Goal -- on update features**
1. Learn the two sources of truth (GrandSpecification and GrandArchitecture).
2. Update module and feature lists
3. Update validation test, APIs and Schemas
4. manage workflow of agents, sleep if you think all agents are properly managed

**Rule -- update features** 
1. Each module and task must be minimal and actionable with no conflict
2. All deprecated tasks should be deleted and aborted

**Rule -- manage Agents**
1. No agent is working on overlapping module/feature or deprecated module/feature



**Tools**  
Same tooling as other agents; read and write access to Kanban, write access to API&Schema.tex
**Design notes**
- Runs on Opus 4.5.
- Expressed here as rule-based (triggers + rules), not as pipeline/state machine.

**Special docs**
API&Schema.tex
---

## Agent -- Engineer

**Goal**
implement task based on specified from higher level agent

**Pipeline**
1. implement based on specification
2. write unit test for each feature and unit, if test not passed back to implementation
3. check if pass OperationMaster specified test, if not, back to implementation. 

**Rules**
1. if encounter conflict of module not assign to me send ticket to OperationMaster
2. if encounter problem with architecture itself, send ticket to GM
3. if encounter problem in general, search solution in RAG first, if not, find OperationMaster 