# Geo_Cortex_Assistant - Project Summary

## Overview

Geo_Cortex_Assistant is a FastAPI-based application designed to help geologists and researchers explore and manage geological occurrence data from the MODS (Mineral Occurrence Database System) dataset. It's built following the same architecture pattern as the Tourist_Assistant project but adapted for geological data.

## Key Features

### 1. **User Authentication**
- JWT-based authentication with OAuth2
- User registration and login
- Secure password hashing with bcrypt
- Role-based access control

### 2. **RAG (Retrieval-Augmented Generation) System**
- FAISS vector store for semantic search
- OpenAI LLM integration for intelligent query responses
- Automatic extraction of structured occurrence data from queries
- Context-aware responses based on MODS data

### 3. **Geological Occurrence Management**
- Search and filter MODS occurrences by:
  - Major commodity (Gold, Copper, Zinc, etc.)
  - Administrative region
  - Occurrence type (Metallic, Non Metallic)
- Save occurrences to personal lists
- Manage saved occurrences (CRUD operations)

### 4. **API Endpoints**

#### Authentication
*(Removed — API is public)*

#### Occurrences
- `GET /occurrences/` - Get all saved occurrences
- `GET /occurrences/{id}` - Get specific occurrence
- `POST /occurrences/` - Save new occurrence
- `PUT /occurrences/{id}` - Update occurrence
- `DELETE /occurrences/{id}` - Delete occurrence
- `GET /occurrences/mods/search` - Search MODS database

#### LLM Queries
- `POST /query/` - Direct LLM query
- `POST /query/rag` - RAG query with occurrence extraction

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
- **PostgreSQL** - Relational database (SQLite for dev)
- **FAISS** - Vector similarity search
- **Ollama** - Local LLM + embeddings runtime
- **LangChain** - LLM framework and utilities
- **PostGIS** - Spatial extension (geo queries)
- **Pydantic** - Data validation

## Usage Example

```python
# 1. Query with RAG
POST /query/rag
{
  "query": "Find gold occurrences in Riyadh region with high importance"
}
# Returns AI response + structured occurrence data

# 4. Search occurrences
GET /occurrences/mods/search?commodity=Gold&region=Riyadh Region
# Returns filtered occurrences
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

Geo_Cortex_Assistant successfully adapts the Tourist_Assistant architecture for geological data, providing a powerful tool for exploring and managing mineral occurrence information through natural language queries and structured data management.
