"""
Script to build FAISS vector store from MODS.csv
Run this script to create the vector store for RAG functionality.
"""
import os
import sys
import pandas as pd
from langchain_community.vectorstores import FAISS
from langchain_core.documents import Document
from dotenv import load_dotenv
from langchain_ollama import OllamaEmbeddings

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

load_dotenv()

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODS_CSV_PATH = os.path.join(BASE_DIR, "MODS.csv")
VECTORSTORE_DIR = os.path.join(BASE_DIR, "app", "vectorstores", "mods_vectorstore")

# Ensure vectorstore directory exists
os.makedirs(VECTORSTORE_DIR, exist_ok=True)


def build_vectorstore():
    """Build FAISS vector store from MODS.csv"""
    print("Loading MODS.csv...")
    
    if not os.path.exists(MODS_CSV_PATH):
        raise FileNotFoundError(f"MODS.csv not found at {MODS_CSV_PATH}")
    
    # Load CSV
    df = pd.read_csv(MODS_CSV_PATH)
    print(f"Loaded {len(df)} rows from MODS.csv")
    
    # Initialize embeddings
    print("Initializing embeddings...")
    embeddings = OllamaEmbeddings(
        model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
        base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"),
    )
    
    # Create documents
    print("Creating documents...")
    documents = []
    
    for idx, row in df.iterrows():
        # Create a comprehensive text representation of each occurrence
        text_parts = []
        
        # Basic information
        if pd.notna(row.get('MODS')):
            text_parts.append(f"MODS ID: {row['MODS']}")
        if pd.notna(row.get('English Name')):
            text_parts.append(f"Name: {row['English Name']}")
        if pd.notna(row.get('Arabic Name')):
            text_parts.append(f"Arabic Name: {row['Arabic Name']}")
        if pd.notna(row.get('Major Commodity')):
            text_parts.append(f"Major Commodity: {row['Major Commodity']}")
        if pd.notna(row.get('Occurrence Type')):
            text_parts.append(f"Type: {row['Occurrence Type']}")
        
        # Location
        location_parts = []
        if pd.notna(row.get('Admin Region')):
            location_parts.append(f"Region: {row['Admin Region']}")
        if pd.notna(row.get('Longitude')) and pd.notna(row.get('Latitude')):
            location_parts.append(f"Coordinates: {row['Latitude']}, {row['Longitude']}")
        if pd.notna(row.get('Quadrangle')):
            location_parts.append(f"Quadrangle: {row['Quadrangle']}")
        if location_parts:
            text_parts.append("Location: " + ", ".join(location_parts))
        
        # Geological information
        geo_parts = []
        if pd.notna(row.get('Geologic Formation')):
            geo_parts.append(f"Formation: {row['Geologic Formation']}")
        if pd.notna(row.get('Geologic Group')):
            geo_parts.append(f"Group: {row['Geologic Group']}")
        if pd.notna(row.get('Host Rocks')):
            geo_parts.append(f"Host Rocks: {row['Host Rocks']}")
        if pd.notna(row.get('Structural Province')):
            geo_parts.append(f"Structural Province: {row['Structural Province']}")
        if geo_parts:
            text_parts.append("Geology: " + "; ".join(geo_parts))
        
        # Exploration
        exp_parts = []
        if pd.notna(row.get('Exploration Status')):
            exp_parts.append(f"Status: {row['Exploration Status']}")
        if pd.notna(row.get('Occurrence Importance')):
            exp_parts.append(f"Importance: {row['Occurrence Importance']}")
        if pd.notna(row.get('Exploration Data')):
            exp_parts.append(f"Data: {row['Exploration Data']}")
        if exp_parts:
            text_parts.append("Exploration: " + "; ".join(exp_parts))
        
        # Additional commodities
        if pd.notna(row.get('Minor Commodities')):
            text_parts.append(f"Minor Commodities: {row['Minor Commodities']}")
        if pd.notna(row.get('Trace Commodities')):
            text_parts.append(f"Trace Commodities: {row['Trace Commodities']}")
        
        # Create document text
        doc_text = "\n".join(text_parts)
        
        # Create metadata
        metadata = {
            'row': idx,
            'mods_id': str(row.get('MODS', '')),
            'english_name': str(row.get('English Name', '')),
            'major_commodity': str(row.get('Major Commodity', '')),
            'occurrence_type': str(row.get('Occurrence Type', '')),
            'admin_region': str(row.get('Admin Region', '')) if pd.notna(row.get('Admin Region')) else '',
            'longitude': float(row.get('Longitude', 0)) if pd.notna(row.get('Longitude')) else 0.0,
            'latitude': float(row.get('Latitude', 0)) if pd.notna(row.get('Latitude')) else 0.0,
        }
        
        documents.append(Document(page_content=doc_text, metadata=metadata))
        
        if (idx + 1) % 100 == 0:
            print(f"Processed {idx + 1} rows...")
    
    print(f"Created {len(documents)} documents")
    
    # Create vector store
    print("Creating FAISS vector store...")
    vectorstore = FAISS.from_documents(documents, embeddings)
    
    # Save vector store
    print(f"Saving vector store to {VECTORSTORE_DIR}...")
    vectorstore.save_local(VECTORSTORE_DIR)
    
    print("Vector store created successfully.")
    print(f"   Location: {VECTORSTORE_DIR}")
    print(f"   Documents: {len(documents)}")


if __name__ == "__main__":
    try:
        build_vectorstore()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
