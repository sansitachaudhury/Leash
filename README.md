# Leash

> **A behavioral security layer that detects and blocks dangerous AI-agent actions before they happen.**

---

## 1. The Problem

AI agents can now access powerful tools such as:

- Emails
- Databases
- Files
- Payment systems
- Admin tools

If an attacker uses prompt injection through a poisoned document or tool output the AI may perform dangerous actions without realizing it.

Existing prompt level defenses are not always enough.

### The Missing Layer

We need runtime security that monitors what the AI actually does and can stop unsafe actions before they execute.

---

## 2. Our Solution — Leash

Leash sits between the AI agent and the tools it calls.

Before an action is executed, Leash checks:

### ① Semantic Check
Does the action match the user's original task?

### ② Behavior Check
Does the action look unusual for this session?

### ③ Sensitivity Check
How dangerous is the requested tool?

These signals are combined into a **0–100 risk score**.

| Risk Score | Decision |
|---|---|
| **70+** | 🔴 BLOCK |
| **45–69** | 🟡 FLAG FOR REVIEW |
| **< 45** | 🟢 ALLOW |

The decision happens before the tool action causes a side effect.

---

## 3. How It Works

```
AI Agent
   ↓
Proposed Tool Action
   ↓
┌─────────────────────┐
│       LEASH         │
│                     │
│ Semantic Check      │
│ Behavior Check      │
│ Tool Sensitivity    │
│ Risk Score          │
│ Explanation         │
└─────────────────────┘
   ↓
ALLOW / REVIEW / BLOCK
```

---

## 4. What Makes Leash Different?

Instead of asking:

**"Is this prompt safe?"**

Leash will ask:

**"Is this action safe?"**

Even if an attacker successfully manipulates the AI, Leash can still detect that the resulting behavior is abnormal or dangerous.

### Key Advantage

**Leash protects the agent's actions at runtime rather than relying only on prompt level protection.**

---

## 5. AI/ML Behind Leash

Leash uses three major signals:

- **MiniLM embeddings** → detect whether the action has drifted away from the original task
- **Isolation Forest** → detect unusual behavior
- **SHAP** → explain why an action was considered risky

### Risk Score

```
Risk Score =
    40% Semantic Drift
  + 35% Behavioral Anomaly
  + 25% Tool Sensitivity
```

This allows multiple weak warning signals to combine into a strong security decision.

---

## 6. Demo Scenarios

### Scenario 1 — Malicious Document

A poisoned invoice contains hidden instructions.

The agent reads the document and attempts to call:

```
transfer_funds($48,000)
```

The action is considered dangerous and outside the intended task.

**→ Leash blocks the action.**

---

### Scenario 2 — Malicious Tool Output

A database record contains a fake administrative instruction.

The agent reads the record and attempts:

```
grant_access()
```

The behavior is detected as suspicious.

**→ Leash blocks the action.**

After the block, the agent can continue with its original task through legitimate actions.

---

## 7. Technology Stack

| Component | Technology |
|---|---|
| AI Agent | Groq + LLaMA 3.3 70B |
| Backend | FastAPI |
| Anomaly Detection | scikit-learn Isolation Forest |
| Semantic Analysis | Sentence Transformers / MiniLM |
| Explainability | SHAP |
| Real-Time Communication | WebSocket |
| Dashboard | HTML / JavaScript + Chart.js |

---

## 8. Dashboard

The demo dashboard provides:

- **Live risk timeline** — tracks risk scores for agent actions
- **Session log** — shows proposed, allowed and blocked actions
- **Incident reports** — explains why actions were flagged
- **Real-time statistics** — Allow / Review / Block counts

---

## 9. Why Leash Matters

AI agents are moving from simply **generating information** to **taking actions**.

They can interact with:

- Financial systems
- Databases
- Files
- Emails
- Administrative tools

Therefore, AI security cannot stop at the prompt.

We need a security layer that monitors agent behavior in real time and can intervene before an unsafe action happens.

---

## 10. Future Scope

- Plug-and-play SDK for LangChain, CrewAI and AutoGen
- Train models on real production agent traces
- Persistent incident monitoring with PostgreSQL / Redis
- Slack / PagerDuty security alerts
- Fine-tuned semantic drift detection
- Multi-agent attack detection
- Browser-based agent monitoring

---
