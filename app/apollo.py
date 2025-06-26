import requests
import time
import csv

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

def get_insurance_companies(pages=1, per_page=2):
    companies = []
    location = "Los Angeles"
    for page in range(1, pages + 1):
        payload = {
            "api_key": API_KEY,
            "q_organization_keyword_tags": ["Insurance"],
            "organization_locations": [location],
            "page": page,
            "per_page": per_page
        }
        response = requests.post(ORG_SEARCH_URL, json=payload)
        if response.status_code == 200:
            data = response.json()
            for org in data.get("organizations", []):
                companies.append({
                    "name": org["name"],
                    "domain": org.get("website_url", "").replace("http://www.", "").replace("https://www", ""),
                    "linkedin": org.get("linkedin_url", ""),
                    "phone": org.get("primary_phone", {}).get("number", "Not found"),
                    "founded_year": org.get("founded_year", "Not found"),
                    "logo_url": org.get("logo_url", ""),
                    "organization_owner": org.get("owned_by_organization", {}).get("name", "Not found"),
                    "location": location
                })
        else:
            print("❌ Failed to fetch companies:", response.text)
        time.sleep(1)
    return companies


def find_ceo(domain,location):
    payload = {
        "api_key": API_KEY,
        "q_organization_domains_list": [domain],
        "person_titles": ["CEO", "Chief Executive Officer", "Founder", "Managing Director", "President"],
        # "person_seniorities": ["C-Suite"],
        "contact_email_status": ["verified"],
        "person_locations": [location],
        "page": 1,
        "per_page": 1
    }
    response = requests.post(PEOPLE_SEARCH_URL, json=payload)
    print(f"📡 People Search Status: {response.status_code}")
    if response.status_code == 200:
        people = response.json().get("people", [])
        if people:
            person = people[0]
            return {
                "first_name": person["first_name"],
                "last_name": person["last_name"],
                "title": person.get("title", ""),
                "linkedin_url": person.get("linkedin_url", ""),
                "company_name": person["organization"]["name"],
                "company_domain": person["organization"]["domain"]
            }
    return None


def enrich_ceo(ceo_info):
    """Only called when CEO is found"""
    payload = {
        "first_name": ceo_info["first_name"],
        "last_name": ceo_info["last_name"],
        "organization_name": ceo_info["company_name"],
        "domain": ceo_info["company_domain"],
        "linkedin_url": ceo_info.get("linkedin_url", ""),
        "reveal_personal_emails": True,
        "reveal_phone_number": False,  # Set True only if using webhook
        # "webhook_url": "https://your-server.com/apollo-phone-webhook"
    }

    response = requests.post(ENRICH_URL, json=payload, headers=headers)
    print(f"⚙️ Enrich Status: {response.status_code}")

    if response.status_code == 200:
        person_data = response.json().get("person", {})
        if person_data:
            return {
                "name": f"{ceo_info['first_name']} {ceo_info['last_name']}",
                "title": ceo_info["title"],
                "email": person_data.get("email", "Not found"),
                "phone": person_data.get("phone", "Not found"),
                "linkedin": person_data.get("linkedin_url", ceo_info.get("linkedin_url", "Not found")),
                "company": ceo_info["company_name"]
            }
        else:
            print("❗️Enrichment returned 200 but no match was found.")
    else:
        print(f"❌ Failed to enrich: {response.text}")
    return None


def save_to_csv(results, filename="ceo_results.csv"):
    if not results:
        print("No data to save.")
        return

    keys = results[0].keys()
    with open(filename, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=keys)
        writer.writeheader()
        writer.writerows(results)
    print(f"📁 Saved {len(results)} records to {filename}")


def main():
    print("🔍 Getting insurance companies...")
    companies = get_insurance_companies(pages=1, per_page=2)
    print(f"✅ Found {len(companies)} companies.")

    enriched_ceos = []

    for company in companies:
        domain = company["domain"]
        if not domain or domain == "Not found":
            continue

        print(f"\n🏢 {company['name']} ({domain})")

        location = company["location"]
        ceo_info = find_ceo(domain,location)

        if ceo_info:
            print(f"👤 Found {ceo_info['title']}: {ceo_info['first_name']} {ceo_info['last_name']}")
            enriched = enrich_ceo(ceo_info)
            if enriched:
                print(f"✅ Enriched: {enriched['email']}, {enriched['phone']}")
                enriched_ceos.append(enriched)
            else:
                print("⚠️ Enrichment failed or no match.")
        else:
            print("❌ No CEO found. Skipping enrichment.")

        time.sleep(1)  # Avoid rate limiting

    if enriched_ceos:
        save_to_csv(enriched_ceos)
    else:
        print("🚫 No CEOs enriched.")


if __name__ == "__main__":
    main()
