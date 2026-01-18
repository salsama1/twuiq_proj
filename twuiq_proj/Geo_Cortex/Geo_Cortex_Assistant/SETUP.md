# Setup Guide for Geo_Cortex_Assistant

This guide will help you set up and run the Geo_Cortex_Assistant application.

## Prerequisites

- Python 3.8 or higher
- PostgreSQL database (or SQLite for development)
- Ollama (local LLM runtime)
- MODS.csv file in the project root

## Step 1: Install Dependencies

1. Create a virtual environment:
```bash
python -m venv venv
```

2. Activate the virtual environment:
```bash
# Windows
venv\Scripts\activate

# Linux/Mac
source venv/bin/activate
```

3. Install required packages:
```bash
pip install -r requirements.txt
```

## Step 2: Configure Environment Variables

1. Create a `.env` file in the project root:
```bash
type nul > .env
```

2. Edit `.env` and set the following variables:
```
DATABASE_URL=postgresql+psycopg2://postgres:209810@localhost:5432/geocortex_assistant
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_MODEL=llama3.1
OLLAMA_EMBED_MODEL=nomic-embed-text
```

## Step 3: Set Up Database

### Option A: PostgreSQL (Recommended for Production)

1. Install PostgreSQL if not already installed
2. Create a database:
```sql
CREATE DATABASE geocortex_assistant;
\c geocortex_assistant
CREATE EXTENSION IF NOT EXISTS postgis;
```

3. Update `DATABASE_URL` in `.env` with your PostgreSQL credentials

### Option B: SQLite (For Development)

Update `app/database.py` to use SQLite:
```python
SQLALCHEMY_DATABASE_URL = "sqlite:///./geocortex.db"
```

## Step 4: Load MODS Data

1. Ensure `MODS.csv` is in the project root directory

2. Load MODS data into the database:
```bash
python scripts/load_mods_to_db.py
```

This will populate the `mods_occurrences` table with all geological occurrences from the CSV.

## Step 5: Build Vector Store

Build the FAISS vector store for RAG functionality:
```bash
python scripts/build_vectorstore.py
```

This process may take several minutes depending on the size of MODS.csv. The vector store will be saved in `app/vectorstores/mods_vectorstore/`.

## Step 6: Run the Application

Start the FastAPI server:
```bash
uvicorn app.main:app --reload
```

The API will be available at:
- API: http://127.0.0.1:8000
- Interactive Docs: http://127.0.0.1:8000/docs
- Alternative Docs: http://127.0.0.1:8000/redoc

## Testing the API

### Test RAG Query

Use the `/query/rag` endpoint:
```json
{
  "query": "Find gold occurrences in Riyadh region"
}
```

This will:
- Search the vector store for relevant occurrences
- Generate an AI response
- Return structured occurrence data with coordinates

### Search MODS Occurrences

Use the `/occurrences/mods/search` endpoint with filters:
- `commodity`: Filter by major commodity (e.g., "Gold", "Copper")
- `region`: Filter by admin region (e.g., "Riyadh Region")
- `occurrence_type`: Filter by type (e.g., "Metallic", "Non Metallic")

## Troubleshooting

### Vector Store Not Found
If you get an error about the vector store, run:
```bash
python scripts/build_vectorstore.py
```

### Database Connection Error
- Check that PostgreSQL is running
- Verify DATABASE_URL in `.env`
- Ensure the database exists

### Ollama Errors
- Ensure Ollama is running: `ollama serve`
- Pull the models you configured:
  - `ollama pull llama3.1`
  - `ollama pull nomic-embed-text`

### MODS.csv Not Found
- Ensure MODS.csv is in the project root directory
- Check the file path in error messages

## Project Structure

```
Geo_Cortex_Assistant/
├── app/
│   ├── main.py              # FastAPI application
│   ├── database.py          # Database configuration
│   ├── models/              # Database models and schemas
│   ├── routers/             # API route handlers
│   ├── services/            # Business logic (LLM, RAG)
│   └── vectorstores/        # FAISS vector stores
├── scripts/
│   ├── build_vectorstore.py # Build vector store from CSV
│   └── load_mods_to_db.py   # Load CSV into database
├── MODS.csv                 # Geological occurrence data
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables (create this)
└── README.md               # Project documentation
```

## Next Steps

- Explore the API endpoints in the Swagger UI
- Try different queries to test the RAG functionality
- Integrate with mapping tools for visualization

## Support

For issues or questions, please check the README.md or contact the development team.
