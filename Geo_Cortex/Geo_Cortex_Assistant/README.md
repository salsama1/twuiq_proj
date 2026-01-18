# 🗺️ Geo_Cortex_Assistant

**Geo_Cortex_Assistant** is an intelligent, API-driven virtual assistant built using **FastAPI**, designed to help geologists and researchers explore mineral occurrences and geological data from the MODS (Mineral Occurrence Database System) dataset.

---

## 🌟 Features

- 🌐 Public API (no login/auth)
- 📍 Search MODS geological occurrences (including PostGIS geo queries)
- 🧠 Agentic RAG: answers + runs small data processes (counts/filters/nearby)
- 🗺️ Map Visualization for geological occurrences
- 📦 Modular FastAPI design for scalable deployment
- 🔍 Advanced search and filtering of geological data

---

## 🚀 Tech Stack

- **FastAPI** – Web API framework
- **PostgreSQL + PostGIS / SQLAlchemy** – Database + geo queries
- **Ollama (local models)** – LLM + embeddings
- **FAISS** – Vector store for RAG
- **Pydeck / Kepler.gl** – Interactive geospatial map rendering

---

## 📡 API Endpoints

### 📍 Occurrence Endpoints

| Method | Endpoint                          | Description                |
|--------|-----------------------------------|----------------------------|
| GET    | `/occurrences/mods/search`        | Filter/search MODS rows    |
| GET    | `/occurrences/mods/{id}`          | Fetch MODS row by DB id    |

---

### 🧠 RAG / Agent Endpoints

| Method | Endpoint        | Description                  |
|--------|-----------------|------------------------------|
| POST   | `/query/`       | RAG answer + occurrences      |
| POST   | `/query/rag`    | Same as `/query/`             |
| POST   | `/agent/`       | Agentic: can run tools first  |

---

## 📥 Setup & Installation

### 1. Clone the Repo
```bash
cd Geo_Cortex_Assistant
```

### 2. Create Virtual Environment

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Set Environment Variables

Create a `.env` file:
```
DATABASE_URL=postgresql+psycopg2://postgres:209810@localhost:5432/geocortex_assistant
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text
```

### 5. Initialize Database

```bash
python scripts/load_mods_to_db.py
```

### 6. Build Vector Store (FAISS)

```bash
python scripts/build_vectorstore.py
```

### 7. Run the API

```bash
uvicorn app.main:app --reload
```

> Visit `http://127.0.0.1:8000/docs` for Swagger UI
>
> If you built the frontend (`frontend/`) and have `frontend/dist` present in this repo,
> the same FastAPI server will also serve the web UI at `http://127.0.0.1:8000/`.

---

## 🧠 RAG & LLM Integration

* `POST /query/` and `POST /query/rag`: FAISS retrieval + Ollama LLM answer.
* `POST /agent/`: An agent loop that can run small tools (search/count/nearby) before answering.

---

## 🗺️ Map Visualization

* `GET /map`: Returns a map-compatible JSON for rendering geological occurrences on an interactive map.

---

## 📁 Folder Structure

```
Geo_Cortex_Assistant/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── database.py
│   ├── models/
│   │   ├── __init__.py
│   │   ├── dbmodels.py
│   │   └── schemas.py
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── occurrences.py
│   │   ├── llm.py
│   │   └── agent.py
│   ├── services/
│   │   ├── __init__.py
│   │   ├── agent_service.py
│   │   ├── llm_service.py
│   │   ├── retriever_service.py
│   │   └── router_service.py
│   └── vectorstores/
│       ├── __init__.py
│       └── loader.py
├── scripts/
│   └── build_vectorstore.py
├── templates/
├── static/
├── MODS.csv
├── requirements.txt
└── README.md
```

---

## 📜 License

Copyright (c) 2025

All rights reserved.

---

## 📬 Contact

For inquiries, please contact the development team.
