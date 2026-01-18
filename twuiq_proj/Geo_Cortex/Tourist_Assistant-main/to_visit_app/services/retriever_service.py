from vectorstores.loader import retrievers

def retrieve_context(source_key: str, query: str) -> str:
    retriever = retrievers[source_key]
    documents = retriever.get_relevant_documents(query)
    return "\n".join(doc.page_content for doc in documents)

# for user query request and response schemas
def retrieve_documents(source_key: str, query: str):
    retriever = retrievers[source_key]
    return retriever.get_relevant_documents(query)