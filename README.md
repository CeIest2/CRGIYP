# 🧠 Autonomous Cypher Agent
### *for Neo4j · Internet Yellow Pages (IYP)*

> Translate natural language into precise, executable Cypher queries —
> autonomously, accurately, and with self-correcting capabilities.

[![Python](https://img.shields.io/badge/Python-3.9%2B-3776AB?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![Neo4j](https://img.shields.io/badge/Neo4j-Graph_DB-008CC1?style=flat-square&logo=neo4j&logoColor=white)](https://neo4j.com)
[![Gemini](https://img.shields.io/badge/Google-Gemini_2.5_Flash-4285F4?style=flat-square&logo=google&logoColor=white)](https://deepmind.google/technologies/gemini/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](./LICENSE)
[![CypherEval](https://img.shields.io/badge/Benchmark-CypherEval-a855f7?style=flat-square)](https://codeberg.org/dimitrios/CypherEval)

---

## 📖 Overview

The **Autonomous Cypher Agent** is an advanced, self-healing pipeline that bridges the gap between natural language and complex Neo4j graph database queries. It was built specifically for the **Internet Yellow Pages (IYP)** knowledge graph — a large-scale graph database mapping AS numbers, IP prefixes, domain names, IXPs, countries, rankings, and their interconnections across the global internet infrastructure.

Unlike standard Text-to-Cypher generators, this agent:

- 🔍 **Grounds every query in a verified schema** (`IYP_doc.md`) to prevent hallucinated nodes, relationships, or properties
- 🧩 **Decomposes complex questions** into sequential sub-tasks using a Plan-and-Solve strategy (inspired by [arXiv:2312.11242](https://arxiv.org/pdf/2312.11242))
- 🧪 **Tests its own queries** against the live database before returning any result
- 🔧 **Auto-corrects errors** based on real Neo4j feedback through a dedicated Investigator agent
- 🔭 **Traces every reasoning step** end-to-end via native Langfuse integration

---

## ✨ Key Features

| Feature | Description |
|---|---|
| 🎯 **Schema-Grounded Generation** | Every query is generated using a strict schema reference (`IYP_doc.md`) — no hallucinated labels, relationships, or property names |
| 🧩 **Plan-and-Solve Decomposition** | Complex multi-hop questions are automatically broken into ordered sub-tasks, with intermediate results passed as context |
| 🔧 **Self-Healing Loop** | Neo4j syntax or logic errors trigger an autonomous Investigator that runs diagnostic mini-queries and produces a factual correction report |
| 🔍 **RAG-Augmented Generation** | A vector database (Neo4j local instance) stores semantically indexed Cypher examples — retrieved at inference time to guide the generator |
| 🔒 **Strict Output Typing** | All LLM outputs are validated through Pydantic schemas with Gemini Structured Outputs — no fragile string parsing |
| 🔭 **Full Observability** | Native Langfuse integration for tracing reasoning steps, LLM calls, token costs, and execution time per agent |
| ⚡ **Parallel Benchmarking** | Multi-threaded benchmark runner and semantic evaluator allow large-scale evaluation runs with real-time score updates |

---

## 🏗️ Multi-Agent Architecture

The system orchestrates five specialized agents in a dynamic loop:

```
┌─────────────────────────────────────────────────────────────┐
│                        USER QUERY                           │
└──────────────────────────┬──────────────────────────────────┘
                           ▼
               ┌───────────────────────┐
               │   Orchestrator Agent  │
               └──────────┬────────────┘
                          │
    ┌─────────────────────▼───────────────────────────────┐
    │  1. 🔍 Pre-Analysis   (Context & expectations)      │
    │  2. 🔍 RAG Retrieval  (Similar past examples)       │
    │  3. 🔀 Decomposition  (Plan-and-Solve)              │
    │  4. 🔄 Autonomous Loop (per sub-question)           │
    │     ├─ a. ⚙️  Generation   → Cypher query           │
    │     ├─ b. 🛢️  Execution    → Live Neo4j             │
    │     ├─ c. ⚖️  Evaluation   → Success / Reject       │
    │     └─ d. 🕵️  Investigation → Diagnostics if failed │
    │  5. 📝 Final Synthesis                              │
    └─────────────────────────────────────────────────────┘
```

### Agent Roles

| Agent | File | Role |
|---|---|---|
| 🔍 **Pre-Analyst** | `agents/pre_analyst.py` | Establishes real-world context, expected output type, plausibility of empty results, and a dense technical translation for RAG search |
| 🔀 **Decomposer** | `agents/decomposer.py` | Decides if the question requires multiple steps; if so, generates an ordered execution plan with typed inter-step outputs |
| ⚙️ **Request Generator** | `agents/request_generator.py` | Drafts the Cypher query based on the IYP schema, RAG context, and all previous failed attempts |
| ⚖️ **Evaluator** | `agents/evaluator.py` | Analyzes the raw Neo4j output to verify it genuinely answers the question; returns a typed verdict with correction hints |
| 🕵️ **Investigator** | `agents/investigator.py` | On failure, generates and executes diagnostic mini-queries to produce a factual report for the next generation attempt |

---

## 📁 Project Structure

```
cypher_agent/
│
├── agents/
│   ├── decomposer.py            # Plan-and-Solve decomposition
│   ├── evaluator.py             # Result validation agent
│   ├── investigator.py          # Diagnostic & correction agent
│   ├── orchestrator.py          # Main loop & routing logic
│   ├── pre_analyst.py           # Context extraction agent
│   └── request_generator.py    # Cypher generation agent
│
├── DataBase/
│   ├── IYP_connector.py         # Secure Neo4j driver (read-only, traced)
│   ├── rag_retriever.py         # Vector search over RAG database
│   └── rag_db/
│       ├── build_rag_dataset.py # Generates annotated Cypher examples (LLM)
│       ├── setup_rag_db.py      # Embeds and indexes examples into Neo4j
│       └── docker-compose.yml   # Local Neo4j instance for RAG
│
├── docs/
│   └── IYP_doc.md               # Master schema reference (nodes, relationships, properties)
│
├── utils/
│   ├── helpers.py               # Formatting & file utilities
│   └── llm_caller.py            # LangChain/Gemini wrapper with Langfuse tracing
│
├── run_benchmark.py             # Parallel benchmark runner (CypherEval)
└── parallel_evaluator.py        # Semantic equivalence evaluator
```

---

## 🧪 Benchmark Results

The agent was evaluated against **[CypherEval](https://codeberg.org/dimitrios/CypherEval)**, a standardized dataset for assessing LLM-to-Cypher generation on the IYP graph. Queries were categorized into six difficulty levels combining technical precision and general phrasing.

The evaluation pipeline runs two independent scores:
- **Agent Success Rate** — whether the agent produced a query that executed successfully and was validated by the Evaluator
- **Semantic Equivalence Rate** — whether the produced query returns the same factual data as the canonical reference solution (LLM-judged)

### Overall Performance (162 queries, Variation-A with RAG from Variation-B)

| Metric | Score |
|---|---|
| **Agent Success Rate** | **84.6%** (137 / 162) |
| **Semantic Equivalence Rate** | **66.1%** (107 / 162) |

### Performance by Difficulty

| Difficulty | Agent Success | Semantic Equivalence |
|---|---|---|
| Easy Technical | 29 / 32 — **90.6%** | 29 / 32 — **90.6%** |
| Easy General | 30 / 32 — **93.8%** | 28 / 32 — **87.5%** |
| Medium Technical | 26 / 32 — **81.3%** | 17 / 32 — **53.1%** |
| Medium General | 31 / 33 — **93.9%** | 17 / 33 — **51.5%** |
| Hard Technical | 10 / 15 — **66.7%** | 8 / 15 — **53.3%** |
| Hard General | 11 / 18 — **61.1%** | 8 / 18 — **44.4%** |

### Key Observations

- **Easy queries** are handled with very high reliability, demonstrating strong schema grounding for direct lookups and single-hop traversals.
- The main **gap between Agent Success and Semantic Equivalence** on medium/hard queries reveals a semantic drift: the agent produces a valid, executable query, but explores a different (plausible but incorrect) graph path than the canonical solution. This is especially visible on queries involving `OpaqueID`, complex multi-hop DNS paths, or ambiguous ranking interpretations.
- **Hard general queries** are the most challenging, as they require the agent to infer the correct graph strategy from vague natural language without explicit node or relationship hints.

---

## 📦 Prerequisites & Installation

**Requirements:**
- Python 3.9+
- A running Neo4j instance with the IYP database
- Google Gemini API Key *(optimized for `gemini-2.5-flash`)*
- Langfuse account *(required for prompt management and tracing)*
- Docker *(optional, for the local RAG Neo4j instance)*

### 1. Clone & Install

```bash
git clone https://github.com/your-org/cypher-agent.git
cd cypher-agent
pip install pydantic neo4j langchain-google-genai langfuse langchain-core python-dotenv
```

### 2. Configure Environment Variables

Create a `.env` file at the project root:

```env
# ── LLM ───────────────────────────────────────────
GOOGLE_API_KEY=AIzaSy...

# ── Target Database (IYP) ─────────────────────────
IYP_URI=neo4j+s://your-iyp-server.com:7687
IYP_USER=your_user
IYP_PASSWORD=your_password

# ── RAG Database (local) ──────────────────────────
RAG_URI=bolt://localhost:7688
RAG_USER=neo4j
RAG_PASSWORD=password

# ── Observability (Langfuse) ──────────────────────
LANGFUSE_SECRET_KEY=sk-lf-...
LANGFUSE_PUBLIC_KEY=pk-lf-...
LANGFUSE_HOST=https://cloud.langfuse.com
```

### 3. (Optional) Start the RAG Database

```bash
cd DataBase/rag_db
docker compose up -d
python setup_rag_db.py
```

---

## 🚀 Usage

### Single Query

```python
import json
from agents.orchestrator import run_autonomous_loop

question = "What is the market share of AS 3215 in France?"

result = run_autonomous_loop(question, use_rag=True)

if result.get("status") == "SUCCESS":
    print("✅ Final Cypher Query:\n", result["cypher"])
    print("\n📊 Results:\n", json.dumps(result["data"], indent=2))
else:
    print(f"❌ Failed after {result['iterations']} attempts.")
```

The `run_autonomous_loop` function drives the **entire pipeline automatically**: Pre-analysis → RAG Retrieval → Decomposition → Generation → Execution → Evaluation → Self-Correction → Synthesis.

| Parameter | Type | Description |
|---|---|---|
| `question` | `str` | Natural language question |
| `max_retries` | `int` | Maximum correction attempts per sub-question (default: 4) |
| `use_rag` | `bool` | Enable RAG retrieval for similar examples (default: False) |
| `session_id` | `str` | Optional Langfuse session identifier |

### Run the Full Benchmark

```bash
python run_benchmark.py
```

This launches a parallel evaluation on `variation-B.csv` with 12 concurrent workers. Progress and scores are printed in real time. Results are saved incrementally to a JSON report.

### Run Semantic Post-Evaluation

```bash
python parallel_evaluator.py
```

Takes an existing benchmark JSON (with generated Cypher queries), executes both generated and canonical queries against the live database in parallel, and uses an LLM judge to determine semantic equivalence.

---

## 🔍 How the RAG System Works

The RAG pipeline enriches query generation with validated examples from a local vector database:

1. **Dataset Building** (`build_rag_dataset.py`): For each entry in a reference CSV, an LLM annotates the canonical Cypher query with an `abstract_intent` (generalized version of the question) and a `methodology` (graph traversal strategy using exact node/relationship labels).

2. **Indexing** (`setup_rag_db.py`): Each annotated example is embedded with `gemini-embedding-001` and stored as a `CypherExample` node in a local Neo4j instance with a cosine vector index.

3. **Retrieval** (`rag_retriever.py`): At inference time, the Pre-Analyst's `technical_translation` is embedded and used to query the vector index for the top-k most similar examples, which are formatted and injected into the Generator and Decomposer prompts.

---

## 📄 License

Distributed under the **MIT License**. See [`LICENSE`](./LICENSE) for details.