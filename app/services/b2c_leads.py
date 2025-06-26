import time
import random
from typing import List, Dict, Any
from openai import AsyncOpenAI
import requests
import os
from ..models import ConversationHistory
from sqlalchemy.orm import Session
from fastapi import Request
from dotenv import load_dotenv
from fastapi import HTTPException
from datetime import datetime, timezone
from sqlalchemy import desc
from ..log_process import UserLog

load_dotenv()



client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))  # Or use client = OpenAI() if key is in environment

def create_or_update_log(
    db: Session,
    user_id: str,
    chat_id: str,
    message: str,
    total_companies: int = None,
    processed_companies: int = None,
    left_companies: int = None,
):
    message = message.strip()
    if not message:
        return

    # Fetch the latest log entry for this user/chat
    last_log = (
        db.query(UserLog)
        .filter_by(user_id=user_id, chat_id=chat_id)
        .order_by(desc(UserLog.created_at))
        .first()
    )

    # Avoid logging duplicates
    if last_log and last_log.message.strip() == message:
        return

    # Create new log
    new_log = UserLog(
        user_id=user_id,
        chat_id=chat_id,
        message=message,
        created_at=datetime.utcnow(),
        total_companies=total_companies,
        processed_companies=processed_companies,
        left_companies=left_companies,
    )
    db.add(new_log)
    db.commit()


async def extract_people_and_location(user_query: str, user_id: str, chat_id: str, db: Session):
    # Step 1: Save user message with chat_id
    db.add(ConversationHistory(
        user_id=user_id,
        chat_id=chat_id,
        role="user",
        content=user_query,
        created_at=datetime.now(timezone.utc)
    ))
    db.commit()

    # Step 1: Get the latest entry that has <a href= in content
    latest_link_row = db.query(ConversationHistory) \
        .filter_by(user_id=user_id, chat_id=chat_id) \
        .filter(ConversationHistory.content.contains('<a href=')) \
        .order_by(desc(ConversationHistory.created_at)) \
        .first()

    # Step 2: If such a row is found, get messages after it
    if latest_link_row:
        messages_db = db.query(ConversationHistory) \
            .filter_by(user_id=user_id, chat_id=chat_id) \
            .filter(ConversationHistory.created_at > latest_link_row.created_at) \
            .order_by(ConversationHistory.created_at) \
            .all()
    else:
        # If no <a href= found, return all messages
        messages_db = db.query(ConversationHistory) \
            .filter_by(user_id=user_id, chat_id=chat_id) \
            .order_by(ConversationHistory.created_at) \
            .all()

    print(messages_db)
    # Step 3: Build messages for ChatGPT
    system_prompt = (
    "You're a helpful assistant for generating B2C leads.\n\n"

    "Your job is to extract **three key details** from the user's message:\n"
    "1. The correct job title of the professionals to search (e.g., 'OBGYN', 'Dermatologist').\n"
    "2. The location to search in (city or country).\n"
    "3. The number of people the user wants to find.\n\n"

    "✅ If the job title is vague, descriptive, or too long (e.g., 'Heart Doctor', 'Skin Specialist', 'Expert ENT physician'), refine it to the **exact title** commonly used. For example:\n"
    "- 'OBGYN physicians' → 'OBGYN'\n"
    "- 'Eye Specialist Doctor' → 'Ophthalmologist'\n"
    "- 'Skin Specialist' → 'Dermatologist'\n"
    "- 'Brain Surgeon Doctor' → 'Neurosurgeon'\n"


    "✅ If there are **spelling mistakes** in the job title or location, correct them automatically **without informing the user**.\n"
    "✅ Speak naturally. Do not mention that a correction has been made.\n"

    "❌ Never expose or mention internal variable names like 'job_title', 'location', or 'num_of_peoples'.\n"

    "❓ If **any required information is missing**, ask the user in a polite and friendly tone — but only ask for one missing detail at a time. Examples:\n"
    "- \"What job titles are you targeting? \"\n"
    "- \"Which city or country should I search in for these professionals?\"\n"
    "- \"How many people would you like to find?\"\n\n"
    "Once you have all three details, respond ONLY with a JSON block like this:\n\n"
    
    "📦 Internally, once all three details are available, store or pass them in this JSON structure (but do not display it to the user):\n"
    "{\n"
    "  \"job_title\": \"<Refined Job Title>\",\n"
    "  \"location\": \"<City or Country>\",\n"
    "  \"num_of_peoples\": \"<Number>\"\n"
    "}\n\n"

    "If any detail is missing, ask the user politely in a natural, conversational way — never include variables or JSON in your response."
)



    messages = [{"role": "system", "content": system_prompt}]
    for msg in messages_db:
        messages.append({"role": msg.role, "content": msg.content})

    # Step 4: Call ChatGPT
    response = await client.chat.completions.create(
        model="gpt-4",
        messages=messages,
        temperature=0.2
    )
    assistant_reply = response.choices[0].message.content


    # Step 6: (Optional) Detect if JSON is complete
    # You can still track completeness and maybe update a status in a separate table

    return assistant_reply


# def search_companies(industry: str, location: str) -> List[Dict[str, Any]]:

def search_people(job_title, location, pages, per_page, required_count):
    API_KEY = "AT_6a8aV93HhvjIfiBCcqA"
    PEOPLE_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/search"
    ENRICH_URL = "https://api.apollo.io/api/v1/people/match"

    headers = {
        "accept": "application/json",
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }

    def find_people(page_number):
        payload = {
            "api_key": API_KEY,
            "person_titles": [job_title],
            "contact_email_status": ["verified"],
            "person_locations": [location],
            "page": page_number,
            "per_page": per_page
        }
        try:
            response = requests.post(PEOPLE_SEARCH_URL, json=payload, headers=headers)
            response.raise_for_status()
            return response.json().get("people", [])
        except Exception as e:
            print(f"❌ Error finding people on page {page_number}: {e}")
            return []

    def enrich_person(person):
        org = person.get("organization", {})
        payload = {
            "first_name": person.get("first_name", ""),
            "last_name": person.get("last_name", ""),
            "organization_name": org.get("name", ""),
            "domain": org.get("domain", ""),
            "linkedin_url": person.get("linkedin_url", ""),
            "reveal_personal_emails": True
        }
        try:
            response = requests.post(ENRICH_URL, json=payload, headers=headers)
            response.raise_for_status()
            enriched = response.json().get("person", {})
            return {
                "name": f"{person.get('first_name')} {person.get('last_name')}",
                "title": person.get("title", ""),
                "email": enriched.get("email", "Not Available"),
                "phone": enriched.get("phone", "Not Available"),
                "linkedin": enriched.get("linkedin_url", person.get("linkedin_url", "Not Available")),
                "company": org.get("name", ""),
                "location": f"{person.get('city', '')}, {person.get('state', '')}, {person.get('country', '')}",
                "photo_url": person.get("photo_url", ""),
                "headline": person.get("headline", ""),
                "extra": enriched.get("summary", "")
            }
        except Exception as e:
            print(f"⚠️ Enrichment failed for {person.get('first_name')} {person.get('last_name')}: {e}")
            return None

    print("🔍 Starting to gather people contacts...")
    results = []
    current_page = 1

    while len(results) < required_count:
        people_batch = find_people(current_page)
        
        if not people_batch:
            print(f"⚠️ No more people found on page {current_page}. Stopping early.")
            break

        print(f"📄 Found {len(people_batch)} people on page {current_page}.")

        for person in people_batch:
            if len(results) >= required_count:
                break

            enriched = enrich_person(person)
            if enriched:
                print(f"✅ Enriched: {enriched['name']} - {enriched['email']}")
                results.append(enriched)
            else:
                print(f"❌ Skipped due to enrichment failure: {person.get('first_name')}")

        current_page += 1
        time.sleep(1.5)  # avoid rate-limiting

    print(f"\n📦 Final structured results ready. Total: {len(results)} contacts.")
    return results