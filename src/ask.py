from groq import Groq

from src.config import get_settings
from src.retrieval import search_documents

DONT_KNOW = "I don't know based on available documents."

MODEL = "openai/gpt-oss-20b"

MAX_DISTANCE = 0.40


def generate_answer_with_citations(question, tenant_id, user_role):
    documents = search_documents(
        question=question,
        tenant_id=tenant_id,
        user_role=user_role,
        limit=5,
    )

    if not documents:
        return {
            "answer": DONT_KNOW,
            "citations": [],
        }

    if documents[0][3] > MAX_DISTANCE:
        return {
            "answer": DONT_KNOW,
            "citations": [],
        }

    context = ""
    citations = []

    for document in documents:
        document_id, content, source, distance = document

        context += f"\nSource: {source}\nContent: {content}\n"

        citations.append(
            {
                "source": source,
                "content": content,
            }
        )

    settings = get_settings()
    client = Groq(api_key=settings.groq_api_key.get_secret_value())

    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {
                "role": "system",
                "content": (
                    "You are a water utility information assistant. "
                    "Answer using only the supplied documents. "
                    "Do not invent facts. "
                    "Cite every factual claim using the exact "
                    "source ID in square brackets, for example "
                    "[areas:62]. "
                    "If the documents do not support the answer,"
                    "reply exactly: " + DONT_KNOW
                ),
            },
            {
                "role": "user",
                "content": (f"Question: {question}\n\nRetrieved documents:\n{context}"),
            },
        ],
        temperature=0,
    )

    answer = response.choices[0].message.content.strip()

    return {
        "answer": answer,
        "citations": citations,
    }


def generate_answer(question, tenant_id, user_role):
    result = generate_answer_with_citations(
        question=question,
        tenant_id=tenant_id,
        user_role=user_role,
    )
    return result["answer"]


if __name__ == "__main__":
    question = "Which water outages are currently active?"

    answer = generate_answer(
        question=question,
        tenant_id="water_company_A",
        user_role="engineer",
    )

    print("\nQuestion:", question)
    print("\nAnswer:", answer)
