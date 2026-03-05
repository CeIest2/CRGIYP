# 🧠 Neo4j Autonomous Cypher Agent

> *Translate natural language into precise Cypher queries — autonomously, accurately, and with memory.*

---

## Overview

The **Neo4j Autonomous Cypher Agent** is an advanced, self-correcting pipeline that bridges the gap between human language and graph database queries. Built on a **Plan-and-Solve architecture**, it dynamically explores live schemas, heals its own errors, and accumulates knowledge through an episodic memory graph.

Powered by **Google Gemini** and a **Dual-Database Architecture**, the agent keeps your target data environment strictly separated from its cognitive memory layer.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🎯 **Zero-Hallucination Generation** | Explores the live remote Neo4j schema before writing a single line of Cypher |
| 🔧 **Self-Healing Execution** | Catches Neo4j engine errors and auto-corrects iteratively — no user intervention |
| 🧩 **Episodic Graph Memory** | Stores successful queries in a local RAG database; learns from past successes |
| 🗺️ **Plan-and-Solve Routing** | Decomposes complex questions into manageable, sequential sub-queries |
| 🔒 **Strict Output Typing** | Pydantic + Gemini Structured Outputs for robust, fully typed data pipelines |
| 🔭 **Full Observability** | Langfuse integration for tracing, token cost monitoring, and debug loops |

---

## 🏗️ System Architecture

The agent enforces a strict **Dual-Database separation**:

```
┌─────────────────────────────────────────────────────┐
│                    USER QUERY                       │
└───────────────────────┬─────────────────────────────┘
                        ▼
          ┌─────────────────────────┐
          │    Orchestrator         │
          │      main.py            │
          └──────┬──────────────────┘
                 │
    ┌────────────▼────────────────────────────────┐
    │            6-Step Pipeline                  │
    │                                             │
    │  1. 🔍 Retrospector  ──► Local Memory DB    │
    │  2. 📋 Planner       ──► Gemini LLM         │
    │  3. 🗺️  Explorer      ──► Remote Target DB  │
    │  4. ⚙️  Translator    ──► Gemini + Remote DB │
    │  5. ✍️  Writer        ──► Gemini LLM         │
    │  6. 💾 Archivist     ──► Local Memory DB    │
    └─────────────────────────────────────────────┘

  📡 Remote Target DB (IYP)        🧠 Local Memory DB (RAG)
  ─────────────────────────        ──────────────────────────
  • Read-only                      • Read / Write
  • Schema exploration             • Episodic memory
  • Data extraction                • Vector embeddings
```

---

## 🔄 The 6-Step Pipeline

### 1 · 🔍 Memory Retrieval *(The Retrospector)*
Queries the Local Memory DB for semantically similar past questions. If a match is found, previously successful Cypher queries and schema context are loaded directly — skipping redundant work.

### 2 · 📋 Planning *(The Planner)*
Uses Gemini to decompose the user's natural language input into logical, ordered sub-steps.

### 3 · 🗺️ Schema Exploration *(The Explorer)*
Queries the Remote Target DB metadata to validate that all required entities and relationships exist. Gracefully aborts if a concept is not found — preventing hallucinated queries.

### 4 · ⚙️ Generation & Execution *(The Translator & Tester)*
Generates Cypher using Gemini, runs it against the Remote Target DB, catches errors, and **iteratively refines** the code until it succeeds or exhausts retries.

### 5 · ✍️ Synthesis *(The Writer)*
Takes the original user question and the `extracted_data`, then uses Gemini to produce a human-readable `interpretation` — turning raw graph records into a clear, natural language answer.

### 6 · 💾 Memorization *(The Archivist)*
Returns the complete `FinalAnswer` to the caller and silently commits the successful reasoning steps, Cypher queries, and interpretation into the Local Memory DB for future retrieval.

---

## 📦 Prerequisites & Installation

### Requirements

- **Python** 3.9+
- **Remote Neo4j instance** — target database (read-only access)
- **Local Neo4j instance** — agent memory database (read/write)
- **Google Gemini API Key**
- **Langfuse account** *(optional but recommended)*

### Install

```bash
git clone https://github.com/your-org/cypher-agent.git
cd cypher-agent
pip install pydantic neo4j google-genai langfuse
```

### Configure Environment Variables

Create a `.env` file at the project root:

```env
# ── LLM ──────────────────────────────────────────
GOOGLE_API_KEY=AIzaSy...

# ── Target Database (Remote / Read-Only) ─────────
IYP_NEO4J_URI=neo4j+s://remote-server.com:7687
IYP_NEO4J_USER=read_only_user
IYP_NEO4J_PASSWORD=your_remote_password

# ── Agent Memory Database (Local / Read-Write) ───
RAG_NEO4J_URI=bolt://localhost:7687
RAG_NEO4J_USER=neo4j
RAG_NEO4J_PASSWORD=your_local_password

# ── Observability ─────────────────────────────────
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

---

## 📁 Project Structure

```
cypher_agent/
│
├── core/                       # Application core
│   ├── models.py               # Pydantic schemas (strict typing)
│   ├── llm.py                  # Gemini client configuration
│   └── neo4j_clients.py        # Remote (IYP) + Local (RAG) DB connections
│
├── pipeline/                   # Plan-and-Solve workflow
│   ├── 1_retriever.py          # Checks Local Memory DB
│   ├── 2_planner.py            # Decomposes questions (Gemini)
│   ├── 3_explorer.py           # Validates schema on Remote Target DB
│   ├── 4_generator.py          # Writes & fixes Cypher (Gemini + Remote DB)
│   ├── 5_writer.py             # Synthesizes natural language interpretation (Gemini)
│   └── 6_memorizer.py          # Saves success paths to Local Memory DB
│
└── main.py                     # Orchestrator — maps the pipeline
```

---

## 🚀 Usage

```python
from cypher_agent.main import process_natural_language_query

question = "What is the average broadband speed in Northern Europe?"
response = process_natural_language_query(question)

if response.status == "SUCCESS":
    print("Raw data:", response.extracted_data)
    print("Answer:", response.interpretation)
else:
    print("Agent could not find the data:", response.interpretation)
```

---

## 📤 Input / Output Specification

**Input:** A single natural language query *(context-independent)*

**Output:** A structured JSON object matching the `FinalAnswer` Pydantic model. It provides the execution status, the raw extracted data, the exact Cypher queries used, and a human-readable interpretation.

```json
{
  "status": "SUCCESS",
  "queries": [
    "MATCH (c:Country {region: 'Asia'})-[:HAS_SCORE]->(s:CyberSecurityIndex) RETURN c.name, s.score ORDER BY s.score DESC LIMIT 2"
  ],
  "extracted_data": [
    { "c.name": "Singapore", "s.score": 98.5 },
    { "c.name": "Japan",     "s.score": 97.2 }
  ],
  "interpretation": "The top-performing Asian countries in cybersecurity are Singapore (98.5) and Japan (97.2)."
}
```

**Possible statuses:**

| Status | Meaning |
|---|---|
| `SUCCESS` | Data extracted and interpreted successfully |
| `SCHEMA_NOT_FOUND` | Requested concept doesn't exist in the target DB |
| `EXECUTION_FAILED` | Query failed after all auto-correction attempts |
| `MEMORY_HIT` | Answered instantly from episodic memory |

---

## 🔭 Observability with Langfuse

When Langfuse credentials are configured, every agent run is fully traced:

- **Execution steps** — see exactly which pipeline stage ran
- **Gemini reasoning** — inspect prompts, completions, and chain-of-thought
- **Token costs** — track usage per query and over time
- **Auto-correction loops** — debug failed Cypher generation attempts

---

## 📄 License

Distributed under the MIT License. See `LICENSE` for details.