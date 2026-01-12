"""
Example script demonstrating how to use the Geo_Cortex_Assistant API
"""
import requests
import json

# API base URL
BASE_URL = "http://127.0.0.1:8000"

def example_rag_query(query: str):
    """Example: RAG query (public; no auth)"""
    url = f"{BASE_URL}/query/rag"
    data = {"query": query}
    response = requests.post(url, json=data)
    print(f"\nRAG Query: '{query}'")
    print(json.dumps(response.json(), indent=2))
    return response.json()


def example_search_occurrences(commodity: str = None, region: str = None):
    """Example: Search MODS occurrences (public; no auth)"""
    url = f"{BASE_URL}/occurrences/mods/search"
    params = {}
    if commodity:
        params["commodity"] = commodity
    if region:
        params["region"] = region
    
    response = requests.get(url, params=params)
    print(f"\nSearch Occurrences:")
    print(f"Found {len(response.json())} occurrences")
    if response.json():
        print(json.dumps(response.json()[0], indent=2))
    return response.json()


def example_agent(query: str):
    """Example: Agentic endpoint (tools + answer)"""
    url = f"{BASE_URL}/agent/"
    data = {"query": query, "max_steps": 3}
    response = requests.post(url, json=data)
    print(f"\nAgent Query: '{query}'")
    print(json.dumps(response.json(), indent=2))
    return response.json()


if __name__ == "__main__":
    print("=" * 60)
    print("Geo_Cortex_Assistant API Usage Examples")
    print("=" * 60)
    
    # Make sure the API is running before executing these examples
    print("\n⚠️  Make sure the API is running at http://127.0.0.1:8000")
    print("   Start it with: uvicorn app.main:app --reload\n")
    
    # Uncomment to run examples:
    #
    # result = example_rag_query("Find gold occurrences in Riyadh region")
    # occurrences = example_search_occurrences(commodity="Gold", region="Riyadh Region")
    # agent_result = example_agent("Count the top commodities in Makkah region and summarize")
    
    print("\n" + "=" * 60)
    print("Examples ready. Uncomment the code above to run them.")
    print("=" * 60)
