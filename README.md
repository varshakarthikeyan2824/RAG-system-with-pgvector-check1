# Water Utility RAG System

## 1. Project Overview

A Retrieval-Augmented Generation (RAG) application that answers questions about water outages, affected areas and crew activities.

The system uses PostgreSQL with pgvector for semantic search, Ollama for embeddings and Groq for LLM-based answer generation.

It supports role-based access control, source citations and fallback responses for unsupported questions.

## 2. Technology Stack

- Python
- PostgreSQL 17
- pgvector
- Docker
- Ollama – nomic-embed-text (768 dimensions)
- Groq API – openai/gpt-oss-20b
- psycopg and httpx

## 3. Project Structure

```text
water-utility-rag/
├── data/
│   ├── areas.csv
│   ├── crews.csv
│   └── outage_reports.csv
├── src/
│   ├── ask.py
│   ├── embed_documents.py
│   ├── evaluate_retrieval.py
│   └── retrieval.py
├── documents.sql
├── golden_set.json
├── populate_documents.sql
├── schema.sql
├── README.md
├── pyproject.toml
└── uv.lock
```

## 4. Dataset

| Dataset | Records |
|---|---:|
| Outage reports | 60 |
| Areas | 80 |
| Crews | 140 |
| Total | 280 |

## 5. System Architecture

1. Load CSV data into PostgreSQL.
2. Convert records into searchable documents.
3. Store tenant and role permissions.
4. Generate embeddings using Ollama.
5. Store vectors using pgvector.
6. Retrieve relevant documents using semantic similarity.
7. Generate answers using Groq.
8. Return answers with source citations.

## 6. Role-Based Access Control

| Role | Outages | Areas | Crew records |
|---|---|---|---|
| Admin | Yes | Yes | Yes |
| Engineer | Yes | Yes | Yes |
| Customer | Yes | Yes | No |

Retrieval filters documents by tenant ID and allowed roles.

## 7. Answer Generation

The system uses Groq with the `openai/gpt-oss-20b` model.

Features:
- Answers based on retrieved documents.
- Source citations.
- No unsupported factual claims.
- Fallback response when information is unavailable.

Fallback:

`I don't know based on available documents.`

## 8. Retrieval Evaluation

A golden dataset containing 10 questions was used.

| Metric | Result |
|---|---:|
| Recall@1 | 10/10 (100%) |
| Recall@3 | 10/10 (100%) |
| Recall@5 | 10/10 (100%) |

All 10 expected source documents were retrieved within the top 1, 3 and 5 results.

## 9. Testing

- Customer cannot access crew documents.
- Engineer can access crew documents.
- Unsupported questions return the fallback response.
- Generated answers include source citations.
- Retrieval evaluation achieved 100% Recall@1, Recall@3 and Recall@5.

## 10. Setup

Install dependencies:

```bash
uv sync
```

Start PostgreSQL and pgvector using Docker. Load the database schema and CSV data using the provided SQL files.

Ensure Ollama is running with `nomic-embed-text` available.

Set your Groq API key:

```bash
export GROQ_API_KEY="your_groq_api_key"
```

Never commit API keys or passwords to GitHub.

## 11. Run the Project

Generate embeddings:

```bash
uv run python src/embed_documents.py
```

Test retrieval:

```bash
uv run python src/retrieval.py
```

Generate an answer:

```bash
uv run python src/ask.py
```

Evaluate retrieval:

```bash
uv run python src/evaluate_retrieval.py
```

## 12. Conclusion

This project demonstrates a RAG pipeline with semantic retrieval, vector storage, role-based access control, source citations, unsupported-question handling and retrieval evaluation.
