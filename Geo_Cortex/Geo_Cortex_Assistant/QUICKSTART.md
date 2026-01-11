# Quick Start Guide

Get Geo_Cortex_Assistant up and running in 5 minutes!

## Prerequisites Check

- [ ] Python 3.8+ installed
- [ ] PostgreSQL installed (or use SQLite for testing)
- [ ] Ollama installed and running
- [ ] MODS.csv file in project root

## Quick Setup

### 1. Install Dependencies (2 minutes)

```bash
# Create virtual environment
python -m venv venv

# Activate (Windows)
venv\Scripts\activate

# Activate (Linux/Mac)
source venv/bin/activate

# Install packages
pip install -r requirements.txt
```

### 2. Configure Environment (1 minute)

Create `.env` file:
```bash
DATABASE_URL=postgresql+psycopg2://postgres:209810@localhost:5432/geocortex_assistant
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text
```

### 3. Initialize Database (1 minute)

```bash
python scripts/load_mods_to_db.py
```

### 4. Build Vector Store (2-5 minutes)

```bash
python scripts/build_vectorstore.py
```

### 5. Start Server

```bash
uvicorn app.main:app --reload
```

## Test It Out

1. Open http://127.0.0.1:8000/docs
2. Try a query at `/query/rag`:
   ```json
   {
     "query": "Find gold occurrences in Saudi Arabia"
   }
   ```

## Common Issues

**"MODS.csv not found"**
- Make sure MODS.csv is in the project root

**"Vector store not found"**
- Run: `python scripts/build_vectorstore.py`

**"Database connection error"**
- Check PostgreSQL is running
- Or switch to SQLite in `app/database.py`

**"Ollama error"**
- Ensure Ollama is running: `ollama serve`
- Ensure models exist: `ollama pull llama3.1` and `ollama pull nomic-embed-text`

## Next Steps

- Read SETUP.md for detailed instructions
- Check PROJECT_SUMMARY.md for architecture overview
- Explore example_usage.py for API examples

Happy exploring! 🗺️
