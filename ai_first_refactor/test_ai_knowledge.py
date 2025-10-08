"""
Test: Does AI understand "EV + P" in pharmaceutical context?
"""

from openai import OpenAI
import os
from dotenv import load_dotenv

load_dotenv()
client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))

print("="*80)
print("TESTING AI'S PHARMACEUTICAL KNOWLEDGE")
print("="*80)

# Test 1: What is EV + P?
print("\n[TEST 1] Query: 'What is EV + P in oncology?'")
print("-" * 80)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "What is EV + P in oncology? Be specific about the drug names."}
    ],
    temperature=0.3
)

answer = response.choices[0].message.content
print(answer)

# Test 2: If I want combination studies, what keywords should I search for?
print("\n" + "="*80)
print("[TEST 2] Query: 'If I want to find studies about EV + P combination, what keywords should I search for?'")
print("-" * 80)

response2 = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": """I'm searching a conference database for studies about the EV + P combination in bladder cancer.

The database has study titles, authors, and affiliations but no full abstracts yet.

What specific keywords or phrases should I search for to find relevant combination studies?
Give me a list of search terms."""}
    ],
    temperature=0.3
)

answer2 = response2.choices[0].message.content
print(answer2)

print("\n" + "="*80)
