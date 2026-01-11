from langchain_openai import OpenAIEmbeddings
from langchain_community.vectorstores import FAISS
embeddings = OpenAIEmbeddings()

pdf_vectorstore = FAISS.load_local(
    r"F:\AI_APPS\Tourist_Assistant\to_visit_app\vectorstores\Rules_final_vectorstore", embeddings, allow_dangerous_deserialization=True
)
csv_vectorstore = FAISS.load_local(
    r"F:\AI_APPS\Tourist_Assistant\To_visit_app\vectorstores\faiss_index", embeddings, allow_dangerous_deserialization=True
)
places_vectorstore = FAISS.load_local(
    r"F:\AI_APPS\Tourist_Assistant\to_visit_app\vectorstores\brochure_final_vectorstore", embeddings, allow_dangerous_deserialization=True
)


retrievers = {
    "rules": pdf_vectorstore.as_retriever(search_kwargs={"k": 4}),
    "restaurant": csv_vectorstore.as_retriever(search_kwargs={"k": 4}),
    "tour": places_vectorstore.as_retriever(search_kwargs={"k": 4}),
}
