from app.vectorstores.loader import retrievers


def _get_documents(retriever, query: str):
    """
    Compatibility shim across LangChain versions.
    Newer retrievers use `.invoke(query)`; older use `.get_relevant_documents(query)`.
    """
    if hasattr(retriever, "get_relevant_documents"):
        return retriever.get_relevant_documents(query)
    return retriever.invoke(query)


def retrieve_context(source_key: str, query: str) -> str:
    """Retrieve context from vector store"""
    retriever = retrievers[source_key]
    documents = _get_documents(retriever, query)
    return "\n".join(doc.page_content for doc in documents)


def retrieve_documents(source_key: str, query: str):
    """Retrieve documents from vector store"""
    retriever = retrievers[source_key]
    return _get_documents(retriever, query)
