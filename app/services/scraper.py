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


async def extract_industry_and_location(user_query: str, user_id: str, chat_id: str, db: Session):
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
        "You're a helpful assistant that extracts lead generation criteria from a user's request. "
        "You must identify the following details from the user's request:\n"
        "1. The industry the user wants to find companies in.\n"
        "2. The location (city or country) where the companies should be located.\n"
        "3. The number of companies the user wants to extract.\n"
        "4. The position titles the user is interested in (e.g., CEO, Founder, Managing Director, President).\n\n"

        "If any of these details are missing, ask the user to provide the missing ones in a natural, conversational and polite way. "
        "Only ask about the missing information. Do not mention internal variable names like 'industry' or 'num_companies'.\n\n"
        
        "Examples of polite prompts:\n"
        "- \"How many companies would you like to extract?\"\n"
        "- \"Could you let me know which roles you're targeting in each company, like CEO, Founder, or Director?\"\n"

        "If the city or country seems misspelled, make your best guess and correct it automatically. "
        "Remember what the user has already shared, and keep collecting information step by step.\n\n"

        "Once you have all the required details, respond ONLY with this JSON:\n\n"
        "{\n"
        "  \"industry\": \"<industry>\",\n"
        "  \"location\": \"<City>\",\n"
        "  \"num_companies\": <number>,\n"
        "  \"position_titles\": [\"<Position Title 1>\", \"<Position Title 2>\", ...]\n"
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

def search_companies(industry, location, pages, per_page,titles,required_count):
    API_KEY = "AT_6a8aV93HhvjIfiBCcqA"
    ORG_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_companies/search"
    PEOPLE_SEARCH_URL = "https://api.apollo.io/api/v1/mixed_people/search"
    ENRICH_URL = "https://api.apollo.io/api/v1/people/match"

    headers = {
        "accept": "application/json",
        "Cache-Control": "no-cache",
        "Content-Type": "application/json",
        "x-api-key": API_KEY
    }

    industry = industry 
    location = location 
    pages = pages 
    per_page = per_page 
    titles = titles 

    def get_insurance_companies(current_page):
            companies = []
            payload = {
                "api_key": API_KEY,
                "q_organization_keyword_tags": [industry],
                "organization_locations": [location],
                "page": current_page,
                "per_page": 100,
            }
            try:
                response = requests.post(ORG_SEARCH_URL, json=payload, headers=headers)
                response.raise_for_status()
                data = response.json()
                

                for org in data.get("organizations", []):
                    domain = (org.get("website_url") or "").replace("http://www.", "").replace("https://www.", "")

                    companies.append({
                        "name": org.get("name", "Not Available"),
                        "domain": domain if domain else "Not Available",
                        "address": org.get("location", "Not Available"),
                        "website": org.get("website_url", "Not Available"),
                        "linkedin": org.get("linkedin_url", "Not Available"),
                        "phone": org.get("phone" "Not Available"),
                        "founded_year": org.get("founded_year", "Not Available"),
                        "logo_url": org.get("logo_url", "Not Available"),
                        "organization_owner": org.get("owned_by_organization", {}).get("name", "Not Available"),
                        "location": location
                    })
            except Exception as e:
                print("❌ Failed to fetch companies:", e)
            time.sleep(1)
            return companies

    def find_ceo(domain, location, titles,per_page_persons):
        payload = {
            "api_key": API_KEY,
            "q_organization_domains_list": [domain],
            "person_titles": titles,
            "contact_email_status": ["verified"],
            "person_locations": [location],
            "page": 1,
            "per_page": per_page_persons
        }
        try:
            response = requests.post(PEOPLE_SEARCH_URL, json=payload, headers=headers)
            response.raise_for_status()
            people = response.json().get("people", [])

            if people:
                person = people[0]
                # Try direct phone (not available here)
                phone = person.get("phone")

                # Fallback to organization's phone
                if not phone:
                    org = person.get("organization", {})
                    phone = org.get("primary_phone", {}).get("number") or org.get("phone")

                return {
                    "first_name": person.get("first_name", ""),
                    "last_name": person.get("last_name", ""),
                    "title": person.get("title", ""),
                    "linkedin_url": person.get("linkedin_url", ""),
                    "photo_url": person.get("photo_url", ""),
                    "email_status": person.get("email_status", ""),
                    "phone": phone or "Not Available",
                    "headline": person.get("headline", ""),
                    "city": person.get("city", ""),
                    "state": person.get("state", ""),
                    "country": person.get("country", ""),
                    "company_name": person.get("organization", {}).get("name", ""),
                    "company_domain": person.get("organization", {}).get("domain", "")
                }
        except Exception as e:
            print(f"❌ Error finding CEO for {domain}: {e}")
        return None

    def enrich_ceo(ceo_info):
        payload = {
            "first_name": ceo_info["first_name"],
            "last_name": ceo_info["last_name"],
            "organization_name": ceo_info["company_name"],
            "domain": ceo_info["company_domain"],
            "linkedin_url": ceo_info.get("linkedin_url", ""),
            "reveal_personal_emails": True

        
        }

        try:
            response = requests.post(ENRICH_URL, json=payload, headers=headers)
            response.raise_for_status()
            person_data = response.json().get("person", {})
        
            if person_data:
                return {
                    "name": f"{ceo_info['first_name']} {ceo_info['last_name']}",
                    "title": ceo_info["title"],
                    "email": person_data.get("email", "Not Available"),
                    "phone": person_data.get("phone", "Not Available"),
                    "linkedin": person_data.get("linkedin_url", ceo_info.get("linkedin_url", "Not Available")),
                    "company": ceo_info["company_name"],
                    "extra": person_data.get("summary", "")
                }
        except Exception as e:
            print(f"⚠️ Enrichment failed for {ceo_info['first_name']} {ceo_info['last_name']}: {e}")
        return None

    print("🔍 Starting to gather CEO contacts...")

    results = []
    processed_domains = set()
    company_id = 1
    contact_id = 1
    i = 0  # Index for companies
    current_page = 1
    companies = get_insurance_companies(current_page)  # Fetch initial batch of companies
    print(f"✅ Retrieved {len(companies)} companies.")

   
    while len(results) < required_count: 
        if i >= len(companies):
            # All companies in current batch processed but not enough results yet
            print("🔁 Fetching more companies as current batch exhausted and required contacts not met...")
            if len(results) >= required_count:
                break
            
            more_companies = get_insurance_companies(current_page)  # Fetch 100 at a time

            if not more_companies:
                print("❌ No more companies available. Exiting.")
                break

            # Filter only new, unprocessed companies
            new_unique_companies = [
                c for c in more_companies
                if c.get("domain") and c.get("domain") != "Not Available" and c.get("domain") not in processed_domains
            ]

            if not new_unique_companies:
                print("⚠️ No new unique companies found in this batch. Trying next page...")
                break

            companies = new_unique_companies  # Only keep new ones
            i = 0  # Reset index to start fresh
            print(f"➕ Added {len(new_unique_companies)} new unique companies.")

        company = companies[i]
        i += 1  # Move to next company for next iteration

        domain = company.get("domain")
        if not domain or domain == "Not Available" or domain in processed_domains:
            continue

        processed_domains.add(domain)
        print(f"\n🏢 Processing Company: {company['name']} - {domain}")

        per_page_persons = len(titles)
        ceo_info = find_ceo(domain, company["location"], titles, per_page_persons)
        contacts = []

        if ceo_info:
            print(f"👤 Found CEO: {ceo_info['title']} {ceo_info['first_name']} {ceo_info['last_name']}")
            phone = ceo_info.get("phone", "Not Available")
            location = f"{ceo_info.get('city', 'Not Available')}, {ceo_info.get('state', 'Not Available')}, {ceo_info.get('country', 'Not Available')}"
            enriched = enrich_ceo(ceo_info)

            if enriched:
                print(f"✅ Enriched Contact: {enriched['email']}, {enriched['phone']}")
                contacts.append({
                    "id": contact_id,
                    "name": enriched["name"],
                    "designation": enriched["title"],
                    "email": enriched["email"],
                    "phone": phone,
                    "address": location,
                    "linkedin": enriched["linkedin"],
                    "additional_info": enriched.get("extra", "")
                })
                contact_id += 1

                results.append({
                    "id": company_id,
                    "name": company.get("name", "Not Available"),
                    "address": company.get("location", "Not Available"),
                    "website": domain,
                    "linkedin": company.get("linkedin", "Not Available"),
                    "phone": company.get("phone", "Not Available"),
                    "founded_year": company.get("founded_year", "Not Available"),
                    "logo_url": company.get("logo_url", "Not Available"),
                    "organization_owner": company.get("organization_owner", "Not Available"),
                    "contacts": contacts
                })
                company_id += 1
                
            else:
                print("❌ Enrichment failed. Skipping company.")
        else:
            print("❌ No CEO found. Skipping enrichment.")
        current_page += 1
        time.sleep(1.5)  # avoid rate-limiting

    print(f"\n📦 Final structured results ready. Total: {len(results)} companies with CEO contacts.")
    return results
