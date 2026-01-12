from langchain_core.prompts import PromptTemplate
from app.services.retriever_service import retrieve_context, retrieve_documents
from app.services.llm_service import generate_response
from app.models.schemas import OccurrenceInfo
import pandas as pd
import os

# Load MODS CSV (lazy loading)
MODS_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "MODS.csv")
mods_df = None

def get_mods_df():
    """Lazy load MODS CSV"""
    global mods_df
    if mods_df is None:
        if os.path.exists(MODS_CSV_PATH):
            mods_df = pd.read_csv(MODS_CSV_PATH)
        else:
            raise FileNotFoundError(f"MODS.csv not found at {MODS_CSV_PATH}")
    return mods_df

# Prompt Templates
geological_template = """You are a highly experienced geologist specializing in mineral occurrences and geological data.
Use the following context from the MODS (Mineral Occurrence Database System) to help answer the question.
Provide detailed, accurate information based on the context.

Context:
{context}

Question: {query}

Answer:"""

# Template Map
template_map = {
    "geological": PromptTemplate.from_template(geological_template),
}

def route_prompt(_: str) -> str:
    """Single-source routing (geological MODS vector store)."""
    return "geological"


def handle_query_with_context(query: str) -> str:
    """Handle query with context retrieval"""
    source_key = route_prompt(query)
    context = retrieve_context(source_key, query)
    prompt = template_map[source_key].format(query=query, context=context)
    return generate_response(prompt)


def handle_query(query: str):
    """Handle query and extract structured occurrence data"""
    source_key = route_prompt(query)
    documents = retrieve_documents(source_key, query)
    context = "\n".join(doc.page_content for doc in documents)
    prompt = template_map[source_key].format(query=query, context=context)
    response = generate_response(prompt)

    # Extract structured data from documents
    occurrences = []
    df = get_mods_df()
    for doc in documents:
        md = doc.metadata
        if 'row' in md:
            try:
                row_data = df.iloc[md['row']]
                
                # Build description from available fields
                description_parts = []
                if pd.notna(row_data.get('Major Commodity')):
                    description_parts.append(f"Major Commodity: {row_data['Major Commodity']}")
                if pd.notna(row_data.get('Occurrence Type')):
                    description_parts.append(f"Type: {row_data['Occurrence Type']}")
                if pd.notna(row_data.get('Exploration Status')):
                    description_parts.append(f"Status: {row_data['Exploration Status']}")
                if pd.notna(row_data.get('Admin Region')):
                    description_parts.append(f"Region: {row_data['Admin Region']}")
                
                description = "; ".join(description_parts) if description_parts else None
                
                occurrences.append(OccurrenceInfo(
                    mods_id=str(row_data.get('MODS', '')),
                    english_name=str(row_data.get('English Name', '')),
                    arabic_name=str(row_data.get('Arabic Name', '')) if pd.notna(row_data.get('Arabic Name')) else None,
                    major_commodity=str(row_data.get('Major Commodity', '')),
                    longitude=float(row_data.get('Longitude', 0.0)) if pd.notna(row_data.get('Longitude')) else 0.0,
                    latitude=float(row_data.get('Latitude', 0.0)) if pd.notna(row_data.get('Latitude')) else 0.0,
                    admin_region=str(row_data.get('Admin Region', '')) if pd.notna(row_data.get('Admin Region')) else None,
                    elevation=float(row_data.get('Elevation', 0.0)) if pd.notna(row_data.get('Elevation')) else None,
                    occurrence_type=str(row_data.get('Occurrence Type', '')) if pd.notna(row_data.get('Occurrence Type')) else None,
                    exploration_status=str(row_data.get('Exploration Status', '')) if pd.notna(row_data.get('Exploration Status')) else None,
                    occurrence_importance=str(row_data.get('Occurrence Importance', '')) if pd.notna(row_data.get('Occurrence Importance')) else None,
                    description=description
                ))
            except Exception as e:
                print(f"Error processing row {md.get('row', 'unknown')}: {e}")
                continue

    print(f"🔀 Extracted {len(occurrences)} occurrences")
    return response, occurrences


def rag_retrieve(query: str, k: int = 5):
    """
    RAG retrieval ONLY (no LLM call).
    Returns (context_text, occurrences_from_retrieved_rows).
    """
    source_key = route_prompt(query)
    documents = retrieve_documents(source_key, query)
    # allow caller to limit k even if retriever returns more/less
    documents = documents[:k] if documents else []
    context = "\n".join(doc.page_content for doc in documents)

    occurrences = []
    df = get_mods_df()
    for doc in documents:
        md = doc.metadata
        if 'row' in md:
            try:
                row_data = df.iloc[md['row']]
                description_parts = []
                if pd.notna(row_data.get('Major Commodity')):
                    description_parts.append(f"Major Commodity: {row_data['Major Commodity']}")
                if pd.notna(row_data.get('Occurrence Type')):
                    description_parts.append(f"Type: {row_data['Occurrence Type']}")
                if pd.notna(row_data.get('Exploration Status')):
                    description_parts.append(f"Status: {row_data['Exploration Status']}")
                if pd.notna(row_data.get('Admin Region')):
                    description_parts.append(f"Region: {row_data['Admin Region']}")
                description = "; ".join(description_parts) if description_parts else None

                occurrences.append(OccurrenceInfo(
                    mods_id=str(row_data.get('MODS', '')),
                    english_name=str(row_data.get('English Name', '')),
                    arabic_name=str(row_data.get('Arabic Name', '')) if pd.notna(row_data.get('Arabic Name')) else None,
                    major_commodity=str(row_data.get('Major Commodity', '')),
                    longitude=float(row_data.get('Longitude', 0.0)) if pd.notna(row_data.get('Longitude')) else 0.0,
                    latitude=float(row_data.get('Latitude', 0.0)) if pd.notna(row_data.get('Latitude')) else 0.0,
                    admin_region=str(row_data.get('Admin Region', '')) if pd.notna(row_data.get('Admin Region')) else None,
                    elevation=float(row_data.get('Elevation', 0.0)) if pd.notna(row_data.get('Elevation')) else None,
                    occurrence_type=str(row_data.get('Occurrence Type', '')) if pd.notna(row_data.get('Occurrence Type')) else None,
                    exploration_status=str(row_data.get('Exploration Status', '')) if pd.notna(row_data.get('Exploration Status')) else None,
                    occurrence_importance=str(row_data.get('Occurrence Importance', '')) if pd.notna(row_data.get('Occurrence Importance')) else None,
                    description=description
                ))
            except Exception:
                continue

    return context, occurrences
