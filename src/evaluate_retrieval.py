import json

from retrieval import search_documents

TENANT = "water_company_A"
ROLE = "engineer"
K_VALUES = [1, 3, 5]


def main():
    with open("golden_set.json", encoding="utf-8") as file:
        questions = json.load(file)

    hits = {k: 0 for k in K_VALUES}

    for item in questions:
        question = item["question"]
        expected = item["expected_source"]

        results = search_documents(
            question=question,
            tenant_id=TENANT,
            user_role=ROLE,
            limit=5,
        )

        retrieved_sources = [result[2] for result in results]

        print(f"\nQuestion: {question}")
        print(f"Expected: {expected}")

        for k in K_VALUES:
            found = expected in retrieved_sources[:k]

            if found:
                hits[k] += 1

            print(f"Recall@{k} hit: {found}")

    print("\n========== FINAL RECALL RESULTS ==========")

    total = len(questions)

    for k in K_VALUES:
        recall = hits[k] / total

        print(f"Recall@{k}: {hits[k]}/{total} = {recall:.2%}")


if __name__ == "__main__":
    main()
