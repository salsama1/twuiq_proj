# Geo_Cortex_Assistant - Project Summary

## Overview

Geo_Cortex_Assistant is a **backend-only geospatial platform** (FastAPI + PostGIS) built for geospatial scientists. It supports:

- **RAG retrieval** over a MODS dataset (FAISS embeddings + deterministic lookups for IDs/names)
- An **agentic workflow layer** that turns natural language into **multi-step geospatial operations**
- **GIS-ready outputs** (GeoJSON/CSV/OGC API Features/MVT tiles) + chart payloads
- **Governance + audit logging** and LLM guardrails (no table dumps)

## Key Features

### 1. **Agentic workflow**
- `POST /agent/workflow`: run tool plans + return summaries, artifacts, charts, and traceability
- `POST /agent/workflow/file`: upload a geospatial file, store AOI + FeatureCollection in session, then run ops

### 2. **RAG (Retrieval-Augmented Generation) System**
- FAISS vector store for semantic search over MODS text
- Deterministic exact lookups for **MODS IDs** and **site names** (improves accuracy)
- Structured `OccurrenceInfo` extraction for retrieved rows

### 3. **Geospatial operations (vector + raster)**
- Vector: intersects/dwithin/buffer/nearest + overlay/union/intersection/difference + dissolve + spatial joins
- QC: duplicates/outliers/summary checks
- Optional raster: upload, tiles, sampling, zonal stats

### 4. **API Endpoints**

#### Primary “demo” endpoints
- `POST /agent/workflow`
- `POST /agent/workflow/file`
- `POST /query/rag` (RAG-only query flow)
- `GET /ogc/collections/mods_occurrences/items` (QGIS-friendly OGC API Features)

## Architecture

### Similarities to Tourist_Assistant

1. **Same FastAPI Structure**
   - Modular router-based architecture
   - Database models with SQLAlchemy
   - Pydantic schemas for validation
   - Service layer for business logic

2. **RAG Implementation**
   - Vector store using FAISS
   - Embedding-based routing
   - Context retrieval and LLM generation
   - Structured data extraction

3. **Authentication System**
   - Same JWT/OAuth2 implementation
   - Similar user management
   - Password hashing with bcrypt

### Adaptations for Geological Data

1. **Data Models**
   - `MODSOccurrence` - Stores geological occurrence data from MODS.csv
   - `SavedOccurrence` - User's saved occurrences (similar to Tovisit)
   - Fields adapted for geological data (commodities, formations, etc.)

2. **RAG Templates**
   - Geological-focused prompts
   - Specialized for mineral occurrence queries
   - Extracts geological metadata

3. **Search Capabilities**
   - Filter by commodity, region, occurrence type
   - Geographic coordinate support
   - Exploration status filtering

## Data Flow

1. **Initialization**
   - Load MODS.csv into database (`load_mods_to_db.py`)
   - Build FAISS vector store (`build_vectorstore.py`)

2. **Query Processing**
   - User submits query via API
   - Query is embedded and routed to vector store
   - Relevant documents retrieved
   - Context passed to LLM
   - Structured occurrence data extracted
   - Response returned with occurrences

3. **Data Management**
   - Users can save interesting occurrences
   - Personal lists for tracking
   - Full CRUD operations

## File Structure

```
Geo_Cortex_Assistant/
├── app/
│   ├── main.py                 # FastAPI application entry point
│   ├── database.py             # Database configuration
│   ├── models/
│   │   ├── dbmodels.py         # SQLAlchemy models
│   │   └── schemas.py           # Pydantic schemas
│   ├── routers/
│   │   ├── auth.py             # Authentication routes
│   │   ├── occurrences.py      # Occurrence management routes
│   │   └── llm.py              # LLM query routes
│   ├── services/
│   │   ├── llm_service.py      # LLM generation
│   │   ├── retriever_service.py # Vector store retrieval
│   │   └── router_service.py   # Query routing and handling
│   └── vectorstores/
│       └── loader.py           # Vector store loader
├── scripts/
│   ├── build_vectorstore.py    # Build FAISS index from CSV
│   ├── load_mods_to_db.py      # Load CSV into database
│   └── example_usage.py        # API usage examples
├── MODS.csv                    # Geological occurrence data
├── requirements.txt            # Python dependencies
├── README.md                   # Project documentation
├── SETUP.md                    # Setup instructions
└── PROJECT_SUMMARY.md          # This file
```

## Technology Stack

- **FastAPI** - Modern Python web framework
- **SQLAlchemy** - ORM for database operations
- **PostgreSQL + PostGIS** - Relational + spatial database
- **FAISS** - Vector similarity search
- **Ollama** - Local LLM + embeddings runtime
- **LangChain** - LLM framework and utilities
- **Pydantic** - Data validation

## Usage Example

```python
# 1. Query with RAG (API)
POST /query/rag
{
  "query": "Find gold occurrences in Riyadh region with high importance"
}
# Returns AI response + structured occurrence data
```

## Next Steps

1. **Frontend Development**
   - Web interface for querying
   - Interactive map visualization
   - User dashboard

2. **Advanced Features**
   - Geographic clustering
   - Statistical analysis
   - Export functionality
   - Advanced filtering

3. **Integration**
   - GIS tools integration
   - External geological databases
   - Reporting features

## Differences from Tourist_Assistant

| Feature | Tourist_Assistant | Geo_Cortex_Assistant |
|---------|------------------|---------------------|
| Data Type | Restaurants, Tourist Places | Geological Occurrences |
| Primary Data | Cairo restaurants CSV | MODS geological data |
| Focus | Tourism recommendations | Geological research |
| Key Fields | Reviews, price, category | Commodity, formation, exploration status |
| Use Case | Tourist planning | Geological exploration |

## Conclusion

Geo_Cortex_Assistant provides a robust backend for geospatial scientists: agentic workflows, high-accuracy RAG retrieval, GIS interoperability, and governed outputs suitable for demos and judge evaluation.
