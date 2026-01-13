from langchain_core.prompts import PromptTemplate
from app.services.retriever_service import retrieve_context, retrieve_documents
from app.services.llm_service import generate_response
from app.models.schemas import OccurrenceInfo
import pandas as pd
import os
import re
from typing import Any, Optional

# Load MODS CSV (lazy loading)
MODS_CSV_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "MODS.csv")
mods_df = None


def _safe_float(v: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Robust float parsing for messy CSV fields (e.g., '' instead of NaN).
    """
    if v is None:
        return default
    try:
        if isinstance(v, str):
            s = v.strip()
            if s == "":
                return default
            return float(s)
        if pd.isna(v):
            return default
        return float(v)
    except Exception:
        return default

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
                
                occurrences.append(
                    OccurrenceInfo(
                        mods_id=str(row_data.get("MODS", "")),
                        english_name=str(row_data.get("English Name", "")),
                        arabic_name=str(row_data.get("Arabic Name", "")) if pd.notna(row_data.get("Arabic Name")) else None,
                        major_commodity=str(row_data.get("Major Commodity", "")),
                        longitude=_safe_float(row_data.get("Longitude"), default=0.0) or 0.0,
                        latitude=_safe_float(row_data.get("Latitude"), default=0.0) or 0.0,
                        admin_region=str(row_data.get("Admin Region", "")) if pd.notna(row_data.get("Admin Region")) else None,
                        elevation=_safe_float(row_data.get("Elevation"), default=None),
                        occurrence_type=str(row_data.get("Occurrence Type", "")) if pd.notna(row_data.get("Occurrence Type")) else None,
                        exploration_status=str(row_data.get("Exploration Status", "")) if pd.notna(row_data.get("Exploration Status")) else None,
                        occurrence_importance=str(row_data.get("Occurrence Importance", "")) if pd.notna(row_data.get("Occurrence Importance")) else None,
                        description=description,
                    )
                )
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
    # Guardrail: if the user provides an explicit MODS id, do an exact lookup.
    # This dramatically improves retrieval accuracy without "overfitting" (it's an identifier lookup).
    q = (query or "").strip()
    m = re.search(r"\bmods\s*0*(\d+)\b", q, flags=re.IGNORECASE)
    if m:
        try:
            df = get_mods_df()
            target_num = int(m.group(1))
            mods_nums = (
                df["MODS"]
                .astype(str)
                .str.extract(r"(\d+)", expand=False)
                .fillna("")
                .apply(lambda x: int(x) if str(x).isdigit() else -1)
            )
            hits = df.index[mods_nums == target_num].tolist()
            if hits:
                idx = int(hits[0])
                row_data = df.iloc[idx]
                context = "\n".join(
                    [
                        f"MODS ID: {row_data.get('MODS')}",
                        f"Name: {row_data.get('English Name')}",
                        f"Arabic Name: {row_data.get('Arabic Name')}" if pd.notna(row_data.get("Arabic Name")) else "",
                        f"Major Commodity: {row_data.get('Major Commodity')}",
                        f"Type: {row_data.get('Occurrence Type')}" if pd.notna(row_data.get("Occurrence Type")) else "",
                        f"Region: {row_data.get('Admin Region')}" if pd.notna(row_data.get("Admin Region")) else "",
                    ]
                ).strip()

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

                occ = OccurrenceInfo(
                    mods_id=str(row_data.get('MODS', '')),
                    english_name=str(row_data.get('English Name', '')),
                    arabic_name=str(row_data.get('Arabic Name', '')) if pd.notna(row_data.get('Arabic Name')) else None,
                    major_commodity=str(row_data.get('Major Commodity', '')),
                    longitude=_safe_float(row_data.get("Longitude"), default=0.0) or 0.0,
                    latitude=_safe_float(row_data.get("Latitude"), default=0.0) or 0.0,
                    admin_region=str(row_data.get('Admin Region', '')) if pd.notna(row_data.get('Admin Region')) else None,
                    elevation=_safe_float(row_data.get("Elevation"), default=None),
                    occurrence_type=str(row_data.get('Occurrence Type', '')) if pd.notna(row_data.get('Occurrence Type')) else None,
                    exploration_status=str(row_data.get('Exploration Status', '')) if pd.notna(row_data.get('Exploration Status')) else None,
                    occurrence_importance=str(row_data.get('Occurrence Importance', '')) if pd.notna(row_data.get('Occurrence Importance')) else None,
                    description=description,
                )
                return context, [occ]
        except Exception:
            pass

    # If the query strongly references a specific English Name, do an exact name lookup.
    # This improves accuracy for common user queries like:
    # - "Tell me about <site name>"
    # - "Give me details on <site name>"
    # - "What is <site name>?"
    try:
        df = get_mods_df()
        phrase = None
        # Common query templates
        # IMPORTANT: order matters. Some templates contain a trailing "what is ..." clause
        # (e.g., "Where is <name> located and what is the major commodity?"). We must
        # capture the <name> first to avoid extracting "the major commodity" as a phrase.
        mname = re.search(r"^\s*where\s+is\s+(.+?)\s+located\b", q, flags=re.IGNORECASE)
        if mname:
            phrase = mname.group(1)
        mname = re.search(r"\babout\s+(.+)$", q, flags=re.IGNORECASE)
        if mname:
            phrase = mname.group(1)
        if phrase is None:
            mname = re.search(r"\b(details\s+on|detail\s+on)\s+(.+)$", q, flags=re.IGNORECASE)
            if mname:
                phrase = mname.group(2)
        if phrase is None:
            mname = re.search(r"\bwhat\s+is\s+(.+)$", q, flags=re.IGNORECASE)
            if mname:
                candidate = (mname.group(1) or "").strip()
                # Ignore generic trailing clauses that aren't site names
                if not re.search(r"\b(major\s+commodity|commodity|admin\s+region|region|location)\b", candidate, flags=re.IGNORECASE):
                    phrase = candidate
        if phrase is None:
            mname = re.search(r"\bsummarize\s+(.+)$", q, flags=re.IGNORECASE)
            if mname:
                phrase = mname.group(1)
        if phrase is None:
            mname = re.search(r"\b(short\s+)?description\s+of\s+(.+)$", q, flags=re.IGNORECASE)
            if mname:
                phrase = mname.group(2)
        if phrase is None:
            # If query is short, treat it as a name lookup attempt
            s = q.strip()
            if 3 <= len(s) <= 120 and not re.search(r"\b(region|commodity|commodities|qc|duplicates|outliers|bbox|nearest|buffer|intersect|dwithin)\b", s, flags=re.IGNORECASE):
                phrase = s

        if phrase is not None:
            phrase = phrase.strip().strip(".").strip("?").strip("!").strip()
            if phrase:
                def _norm(s: str) -> str:
                    s = (s or "").upper()
                    s = re.sub(r"[^A-Z0-9]+", " ", s)
                    s = re.sub(r"\s+", " ", s).strip()
                    return s

                phrase_u = phrase.upper()
                phrase_n = _norm(phrase)

                col = df["English Name"].astype(str)
                col_u = col.str.strip().str.upper()
                col_n = col_u.apply(_norm)

                # exact (raw) match first
                hits = df.index[col_u == phrase_u].tolist()
                if not hits and phrase_n:
                    # exact (normalized) match
                    hits = df.index[col_n == phrase_n].tolist()
                if not hits:
                    # contains (raw), then contains (normalized)
                    hits = df.index[col_u.str.contains(re.escape(phrase_u), na=False)].tolist()
                if not hits and phrase_n:
                    hits = df.index[col_n.str.contains(re.escape(phrase_n), na=False)].tolist()
                if hits:
                    # Build context from top matches (cap to k)
                    occurrences = []
                    contexts = []
                    for idx in hits[:k]:
                        row_data = df.iloc[int(idx)]
                        contexts.append(
                            "\n".join(
                                [
                                    f"MODS ID: {row_data.get('MODS')}",
                                    f"Name: {row_data.get('English Name')}",
                                    f"Major Commodity: {row_data.get('Major Commodity')}",
                                    f"Type: {row_data.get('Occurrence Type')}" if pd.notna(row_data.get("Occurrence Type")) else "",
                                    f"Region: {row_data.get('Admin Region')}" if pd.notna(row_data.get("Admin Region")) else "",
                                ]
                            ).strip()
                        )
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
                        occurrences.append(
                            OccurrenceInfo(
                                mods_id=str(row_data.get('MODS', '')),
                                english_name=str(row_data.get('English Name', '')),
                                arabic_name=str(row_data.get('Arabic Name', '')) if pd.notna(row_data.get('Arabic Name')) else None,
                                major_commodity=str(row_data.get('Major Commodity', '')),
                                longitude=_safe_float(row_data.get("Longitude"), default=0.0) or 0.0,
                                latitude=_safe_float(row_data.get("Latitude"), default=0.0) or 0.0,
                                admin_region=str(row_data.get('Admin Region', '')) if pd.notna(row_data.get('Admin Region')) else None,
                                elevation=_safe_float(row_data.get("Elevation"), default=None),
                                occurrence_type=str(row_data.get('Occurrence Type', '')) if pd.notna(row_data.get('Occurrence Type')) else None,
                                exploration_status=str(row_data.get('Exploration Status', '')) if pd.notna(row_data.get('Exploration Status')) else None,
                                occurrence_importance=str(row_data.get('Occurrence Importance', '')) if pd.notna(row_data.get('Occurrence Importance')) else None,
                                description=description,
                            )
                        )
                    return "\n\n".join([c for c in contexts if c]), occurrences
    except Exception:
        pass

    source_key = route_prompt(query)
    documents = retrieve_documents(source_key, query) or []

    # Re-rank documents using cheap lexical signals (improves top-k quality).
    ql = q.lower()
    q_tokens = {t for t in re.split(r"[^a-z0-9]+", ql) if len(t) >= 3}
    q_mods = None
    m2 = re.search(r"\bmods\s*0*(\d+)\b", ql)
    if m2:
        q_mods = f"mods {m2.group(1)}"

    scored = []
    for i, doc in enumerate(documents):
        md = getattr(doc, "metadata", {}) or {}
        score = 0.0
        try:
            mods_id = str(md.get("mods_id") or "").lower()
            name = str(md.get("english_name") or "").lower()
        except Exception:
            mods_id = ""
            name = ""
        if q_mods and q_mods in mods_id:
            score += 1000.0
        # token overlap with english name
        if name and q_tokens:
            for t in q_tokens:
                if t in name:
                    score += 2.0
        scored.append((score, i, doc))

    scored.sort(key=lambda x: (-x[0], x[1]))
    documents = [d for (_s, _i, d) in scored[: max(25, k)]]
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
