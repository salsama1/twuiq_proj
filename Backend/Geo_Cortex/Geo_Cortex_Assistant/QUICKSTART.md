## Quick Start (5–10 minutes)

This gets the backend running locally and lets you produce a “judge demo” response in Swagger UI.

### Prerequisites

- Python installed
- PostgreSQL + PostGIS installed and running
- Ollama installed (optional but recommended for best summaries)

### 1) Create venv + install

```bash
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### 2) Create `.env`

Create `Geo_Cortex_Assistant/.env`:

```
DATABASE_URL=postgresql+psycopg2://postgres:YOUR_PASSWORD@localhost:5432/geocortex_assistant
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text
PUBLIC_BASE_URL=http://127.0.0.1:8000
```

### 3) Load MODS into PostGIS + build embeddings

```bash
python scripts/load_mods_to_db.py
python scripts/build_vectorstore.py
```

### 4) Run the API

```bash
uvicorn app.main:app --reload --reload-dir "C:\Users\VICTUS\Geo_Cortex\Geo_Cortex_Assistant\app"
```

Open Swagger UI:

- `http://127.0.0.1:8000/docs`

### 5) Judge demo (Swagger)

Use **`POST /agent/workflow`**:

```json
{
  "query": "Run QC summary and top commodities, then generate charts.",
  "max_steps": 8,
  "use_llm": true
}
```

If Ollama is not running, use offline mode:

```json
{
  "query": "Run QC summary and top commodities, then generate charts.",
  "max_steps": 8,
  "use_llm": false
}
```

### Next

- For full setup + optional GDAL/raster support: `SETUP.md`
- For complete system reference: `DOCUMENTATION.md`

### (Optional) Show evaluated accuracy numbers

If you want a defensible accuracy number to quote (golden + holdout, Wilson 95% lower bounds):

```bash
python scripts/report_accuracy_claims.py
```
