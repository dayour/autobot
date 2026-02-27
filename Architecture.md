## Architecture

```
┌─────────────────────────────────────────────┐
│        AG2/Autogen2 Framework               │
├─────────────────────────────────────────────┤
│                                             │
│  LLM Clients Layer                          │
│  ├── OpenAICompletionsClient               │
│  └── CopilotLLMClient  NEW                │
│      ├── Config: CopilotClientConfig        │
│      ├── Manages: Copilot CLI lifecycle    │
│      └── Implements: ModelClient interface  │
│                                             │
│  Agent Layer                                │
│  ├── ConversableAgent                       │
│  ├── AssistantAgent                         │
│  ├── CopilotConversableAgent  NEW         │
│  │   └── Uses: CopilotLLMClient            │
│  └── CopilotAssistantAgent  NEW           │
│      └── Uses: CopilotLLMClient            │
│                                             │
│  Multi-Agent Layer                          │
│  ├── GroupChat  Compatible                │
│  ├── Swarms  Compatible                   │
│  └── [Future: SWE Agent Swarms]            │
│                                             │
└─────────────────────────────────────────────┘
           │
           ├── Copilot CLI (external process)
           │   ├── Model: GPT-5, Claude, etc.
           │   ├── Tools: First-party tools
           │   └── Auth: GitHub Copilot
           │
           └── GitHub Copilot SDK (Python)
               └── Communication: JSON-RPC
```

---

## Key Features

###  Seamless Integration
- No breaking changes to existing AG2 functionality
- Copilot agents work alongside standard agents
- Full compatibility with GroupChat, Swarms, etc.

###  Flexible Configuration
- Dict-based or Config object initialization
- All Copilot CLI options supported
- Environment variable configuration
- Uses Copilot CLI authentication
- GitHub Copilot subscription billing
- No separate LLM API management
- Follows AG2 patterns and conventions
- Comprehensive error handling
- Full test coverage
- Detailed documentation

---



### To Use Copilot Agents:

1. **Install Copilot SDK:**
   ```bash
   pip install github-copilot-sdk
   ```

2. **Install Copilot CLI:**
   - Follow: https://docs.github.com/en/copilot/using-github-copilot/using-github-copilot-in-the-command-line
   - Requires: GitHub Copilot subscription

3. **Authenticate:**
   ```bash
   copilot auth login
   ```

### Current Limitations:
- Requires active Copilot CLI process
- Cannot run in environments without CLI access
- Async-first design (requires `await` for start/stop)

---

### SWE-agent Integration
**Goal:** Enhance existing SWE-agent's autonomous software engineering capabilities in AG2

Tasks:
1. Refine and improve `autobot/swe/` module structure
2. Refine SWE-agent tools to AG2 format
3. Refine environment management capabilities
4. Enhance `SWEAgent` class (Copilot + SWE capabilities)
5. Integrate problem statement system


### SWE Agent Swarms  
**Goal:** Improve and refine multi-agent workflows for software engineering

Tasks:
1. **Code Review Swarm**
   - Reviewer agents (security, performance, style)
   - Coordinator agent
   - Aggregation and reporting

2. **Debugging Swarm**
   - Finder agent (locate bugs)
   - Fixer agent (propose fixes)
   - Validator agent (test fixes)

3. **Testing Swarm**
   - Generator agent (create tests)
   - Runner agent (execute tests)
   - Analyzer agent (analyze results)

4. **Documentation Swarm**
   - Analyzer agent (understand code)
   - Writer agent (generate docs)
   - Reviewer agent (ensure quality)


---

###  Copilot SDK Integration
- **Copilot LLM Client**
  - ModelClient implementation
  - Async/sync bridge
  - Session management
- **Copilot Agents**
  - CopilotConversableAgent
  - CopilotAssistantAgent

###  SWE Agent Integration  
- **SWE Module** (`autobot/swe/`)
  - Tools: bash, edit, search
  - Environment management
  - SWEAgent class

###  SWE Agent Swarms
- **Swarm Manager** 
- **Code Review Swarm**: security, performance, style reviewers
- **Debug Swarm**: finder, fixer, validator
- **Test Swarm**: generator, runner, coverage analyzer

---

## Usage Examples

### SWE Agent
```python
from autobot import SWEAgent

agent = SWEAgent(
    name="swe_agent",
    copilot_config={"model": "gpt-5", "temperature": 0.3},
)
await agent.start()
# Agent ready with bash, edit, search tools
```

### Code Review Swarm
```python
from autobot.swe import create_code_review_swarm, SWESwarmManager

# Create swarm
agents, user = await create_code_review_swarm()
manager = SWESwarmManager()
swarm = await manager.create_swarm("review", agents, user)

# Use swarm for code review
# ... collaborate on code review tasks ...
```

### Debug Swarm
```python
from autobot.swe import create_debug_swarm

# Create debug team
agents, user = await create_debug_swarm()
# bug_finder, bug_fixer, validator
```

---

## Architecture

```
AG2/Autogen2 Framework
│
├─ LLM Clients
│  └─ CopilotLLMClient 
│
├─ Agents
│  ├─ CopilotConversableAgent 
│  ├─ CopilotAssistantAgent 
│  └─ SWEAgent 
│
└─ Swarms
   ├─ Code Review Swarm 
   ├─ Debug Swarm 
   └─ Test Swarm 
```

---

## Ready For

 **Fine Tuning**
 **Integrating development tools**
 **AI Collaboration**
 **Bug Bush**
 **Code Review**

---



