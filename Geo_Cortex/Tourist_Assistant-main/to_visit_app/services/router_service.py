# router_service.py

from langchain_core.prompts import PromptTemplate
from langchain_openai import OpenAIEmbeddings
from langchain_community.utils.math import cosine_similarity
from services.retriever_service import retrieve_context
from services.llm_service import generate_response

# 🧠 Templates
Rules_template = """You are a knowledgeable lawyer specializing in tourism laws in Egypt.
Use the following context to help answer the question:
{context}

Question:
{query}"""

restaurant_template = """You are a highly experienced restaurant guide specializing in restaurants.
Use the following context to help answer the question:
{context}

Question:
{query}"""

Tour_template = """You are a highly experienced Tourist expert specializing in Tourism places.
Use the following context to help answer the question:
{context}

Question:
{query}"""

# 🗺️ Template Map
template_map = {
    "rules": PromptTemplate.from_template(Rules_template),
    "restaurant": PromptTemplate.from_template(restaurant_template),
    "tour": PromptTemplate.from_template(Tour_template),
}

# 🧠 Embeddings
embeddings = OpenAIEmbeddings()

# ✨ Routing Labels
routing_labels = [
    "tourism laws in Egypt",
    "restaurant guide",
    "tour guide for interesting places in Egypt"
]
routing_embeddings = embeddings.embed_documents(routing_labels)

# 🔀 Routing logic
def route_prompt(query: str) -> str:
    query_embedding = embeddings.embed_query(query)
    similarity = cosine_similarity([query_embedding], routing_embeddings)[0]
    most_similar_idx = similarity.argmax()
    source_keys = ["rules", "restaurant", "tour"]
    source_key = source_keys[most_similar_idx]
    print(f"🔀 Routed to: {source_key} (score: {similarity[most_similar_idx]:.2f})")
    return source_key

# 🧾 Full handling logic
def handle_query_with_contex(query: str) -> str:
    source_key = route_prompt(query)
    print(source_key)
    context = retrieve_context(source_key, query)
    print(context)
    prompt = template_map[source_key].format(query=query, context=context)
    return generate_response(prompt)

#for new user query request and response schemas
from uuid import uuid4
from services.retriever_service import retrieve_context, retrieve_documents
from models.schemas import PlaceInfo
import pandas as pd

# Load CSV once at the beginning (ideally outside this function)
restaurant_df = pd.read_csv(r"F:\AI_APPS\Tourist_Assistant\to_visit_app\services\cairo_restaurants_cleaned.csv")

def handle_query(query: str):
    source_key = route_prompt(query)
    documents = retrieve_documents(source_key, query)
    context = "\n".join(doc.page_content for doc in documents)
    prompt = template_map[source_key].format(query=query, context=context)
    response = generate_response(prompt)
    #print(f"🔀 Routed to: {source_key}🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀")
    #print(documents)

    # Only extract structured data for restaurant type
    places = []
    if source_key == "restaurant":
        for doc in documents:
            md = doc.metadata
            print(md['row'],'___________________________________________')
            # Find the row in the CSV that matches this UUID
            row_data = restaurant_df.iloc[md['row']]
            print(row_data)
            try:
                places.append(PlaceInfo(
                uuid=row_data["uuid"],
                poi_name=row_data["poi_name"],
                lat=float(row_data["lat"]),
                lng=float(row_data["lng"]),
                reviews_no=float(row_data.get("reviews", 0.0)),
                price_range=row_data.get("price", "N/A"),
                category=row_data.get("category", "restaurant")
            ))

            except:
                continue
            
    
        print(f"🔀 Extracted {(places)}🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀")
    return response, places

def handle_chat(query: str):
    source_key = route_prompt(query)
    documents = retrieve_documents(source_key, query)
    context = "\n".join(doc.page_content for doc in documents)
    prompt = template_map[source_key].format(query=query, context=context)
    response = generate_response(prompt)
    #print(f"🔀 Routed to: {source_key}🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀🔀")
    #print(documents)
    return response
