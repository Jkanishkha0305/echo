from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from typing import List, Optional
from datetime import timedelta
from . import models
from fastapi import Body
from sqlalchemy import desc
from sqlalchemy import func, and_
import re
import json
from .database import get_db
from sqlalchemy.exc import SQLAlchemyError
from .services.scraper import search_companies,extract_industry_and_location
from .services.b2c_leads import search_people,extract_people_and_location
from .auth import authenticate_user, create_access_token
from .dependencies import get_current_user_for_templates
from fastapi import HTTPException
from fastapi.responses import JSONResponse
import logging
from pydantic import BaseModel
from fastapi import HTTPException, Query
from fastapi.security import OAuth2PasswordBearer
import requests
from fastapi.responses import RedirectResponse
from jose import jwt
from datetime import datetime
from .auth import SECRET_KEY, ALGORITHM  # Secret key and algorithm for JWT encoding
import uuid
from uuid import uuid4
from datetime import datetime, timezone
from fastapi.responses import JSONResponse
from datetime import datetime, timezone

import os 
from dotenv import load_dotenv
load_dotenv()
# Initialize router
router = APIRouter()

# Configure logging
# Set up logging configuration
logging.basicConfig(
    level=logging.INFO,  # Set the minimum level of logs to INFO
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Log to console
        logging.FileHandler('app.log')  # Log to file
    ]
)

# Create a logger instance
logger = logging.getLogger(__name__)

# Setup templates 
templates = Jinja2Templates(directory="templates")
# Google OAuth2 Backend (Custom OAuth2 Class)
# OAuth setup with Google credentials


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI = "http://127.0.0.1:8000/auth/google/callback"


@router.get("/auth/login")
async def login_google():
    google_login_url = f"https://accounts.google.com/o/oauth2/auth?response_type=code&client_id={GOOGLE_CLIENT_ID}&redirect_uri={GOOGLE_REDIRECT_URI}&scope=openid%20profile%20email&access_type=offline"
    return RedirectResponse(url=google_login_url)


# Function to generate JWT token
def create_access_token(data: dict, expires_delta: timedelta = timedelta(hours=1)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

@router.get("/auth/google/callback")
async def auth_google(code: str, db: Session = Depends(get_db)):
    # Exchange code for token
    token_res = requests.post(
        "https://oauth2.googleapis.com/token",
        data={
            "code": code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": GOOGLE_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
    )
    token_json = token_res.json()
    access_token = token_json.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Failed to obtain token")

    # Fetch user info
    user_info_res = requests.get(
        "https://www.googleapis.com/oauth2/v1/userinfo",
        headers={"Authorization": f"Bearer {access_token}"}
    )
    user_data = user_info_res.json()
    email = user_data.get("email")
    name = user_data.get("name", "Google User")

    if not email:
        raise HTTPException(status_code=400, detail="Google login failed")

    # Save or update user
    user = db.query(models.User).filter(models.User.email == email).first()
    if user:
        user.name = name
        user.updated_at = datetime.now()
    else:
        user = models.User(name=name, email=email, password="", created_at=datetime.now())
        db.add(user)
    db.commit()

    # JWT
    jwt_token = create_access_token(data={"sub": user.email}, expires_delta=timedelta(days=30))

    # Redirect with cookie
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="access_token",
        value=jwt_token,
        httponly=True,
        max_age=3600 * 24 * 30,
        expires=3600 * 24 * 30,
        secure=True,
        samesite="Lax"
    )
    return response
@router.get("/token")
async def get_token(token: str = Depends(oauth2_scheme)):
    return jwt.decode(token, GOOGLE_CLIENT_SECRET, algorithms=["HS256"])


# Home page is now the search page
@router.get("/", response_class=RedirectResponse)
async def home_redirect(
    db: Session = Depends(get_db),
    user_info = Depends(get_current_user_for_templates)
):
    user_id = user_info["user_id"]

    # Get the latest conversation for this user
    last_chat = (
        db.query(models.ConversationHistory)
        .filter(models.ConversationHistory.user_id == user_id)
        .order_by(desc(models.ConversationHistory.created_at))
        .first()
    )

    # If the last chat exists and is empty, reuse it
    if last_chat and last_chat.content == "":
        chat_id = last_chat.chat_id
        print("Reusing last chat")
    else:
        print("Creating new chat")
       
        chat_id = str(uuid4())
        db.add(models.ConversationHistory(
            user_id=user_id,
            chat_id=chat_id,
            role="assistant",
            content=""
        ))
        db.commit()

    return RedirectResponse(url=f"/c/{chat_id}")

@router.post("/new-chat")
async def create_new_chat(
    db: Session = Depends(get_db),
    user_info = Depends(get_current_user_for_templates)
):
    user_id = user_info["user_id"]
    new_chat_id = str(uuid4())

    db.add(models.ConversationHistory(
        user_id=user_id,
        chat_id=new_chat_id,
        role="assistant",
        content=""
    ))
    db.commit()

    return RedirectResponse(url=f"/c/{new_chat_id}", status_code=303)

@router.get("/c/{chat_id}", response_class=HTMLResponse)
async def chat_by_id(
    chat_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user_info=Depends(get_current_user_for_templates)
):
    user_id = user_info.get("user_id")

    # Check chat exists for this user
    exists = (
        db.query(models.ConversationHistory)
        .filter_by(chat_id=chat_id, user_id=user_id)
        .first()
    )
    if not exists:
        raise HTTPException(status_code=404, detail="Chat not found")

    # ✅ Get all messages for this chat_id
    chat_messages = (
        db.query(models.ConversationHistory)
        .filter_by(chat_id=chat_id, user_id=user_id)
        .order_by(models.ConversationHistory.id.asc())
        .all()
    )

    # ✅ Subquery: latest created_at for each chat_id
    subquery = (
        db.query(
            models.ConversationHistory.chat_id,
            func.max(models.ConversationHistory.created_at).label("latest_created_at")
        )
        .filter(models.ConversationHistory.user_id == user_id)
        .group_by(models.ConversationHistory.chat_id)
        .subquery()
    )

    # ✅ Join with main table to get the latest message per chat_id
    latest_chats = (
        db.query(models.ConversationHistory)
        .join(subquery, and_(
            models.ConversationHistory.chat_id == subquery.c.chat_id,
            models.ConversationHistory.created_at == subquery.c.latest_created_at
        ))
        .order_by(models.ConversationHistory.created_at.desc())
        .all()
    )

    has_content = any(msg.content.strip() for msg in chat_messages)
    def strip_html_tags(text):
        # Remove all HTML tags like <a href="...">, </div>, etc.
        return re.sub(r'<[^>]*>', '', text or "")
    for chat in latest_chats:
        chat.preview_text = strip_html_tags(chat.content)
    return templates.TemplateResponse("index.html", {
        "request": request,
        "chat_id": chat_id,
        "has_content": has_content,
        "chat_messages": chat_messages,
        "chats": latest_chats,  # used in sidebar
        **user_info
    })


@router.get("/login-singup", response_class=HTMLResponse)
async def myhome(
    request: Request,

):
    return templates.TemplateResponse("landing.html", {
        "request": request,
      
    })

@router.get("/inbox", response_class=HTMLResponse)
async def inbox(
    request: Request,
    db: Session = Depends(get_db),
    user_info=Depends(get_current_user_for_templates)
):
    return templates.TemplateResponse("inbox.html", {
        "request": request,
        **user_info
    })


@router.post("/apollo-phone-webhook/")
async def apollo_phone_webhook(request: Request):
    data = await request.json()  # Parse incoming JSON data
    logger.info(f"Received webhook data: {data}")
    # Check if the data contains phone numbers
    phone_numbers = data.get("phone_numbers", [])

    if phone_numbers:
        # If phone numbers are present, extract the first phone number
        phone_number = phone_numbers[0].get("number", "Not Available")
    else:
        phone_number = "Not Available"

    # Process the phone number as needed (e.g., save to a database or log it)
    return {"status": "success", "phone_number": phone_number}

@router.post("/search/{chat_id}")
async def search(
    chat_id: str,
    request: Request,
    message: str = Form(...),
    btoc_mode: Optional[str] = Form(None),  
    db: Session = Depends(get_db),
    user_info=Depends(get_current_user_for_templates)
):
    if btoc_mode == "on":
        print("B2C mode enabled")
        user_id = user_info.get("user_id")

        # Save search query
        try:
            history = models.SearchHistory(query=message)
            if user_id:
                history.user_id = user_id
            db.add(history)
            db.commit()
            db.refresh(history)
        except Exception as e:
            print(f"Error saving search history: {e}")
            db.rollback()
            return JSONResponse(status_code=500, content={
                "message": "Error",
                "reply": "An error occurred while saving your search history."
            })

        # Get ChatGPT response
        chatgpt_response = await extract_people_and_location(message, user_id, chat_id, db)
        try:
            json_response = chatgpt_response if isinstance(chatgpt_response, dict) else json.loads(chatgpt_response)
        except json.JSONDecodeError:
            ai_reply = models.ConversationHistory(
                user_id=user_id,
                chat_id=chat_id,
                role="assistant",
                content=chatgpt_response,
                final_reply=chatgpt_response,
                created_at=datetime.now(timezone.utc)
            )
            db.add(ai_reply)
            db.commit()
            db.refresh(ai_reply)
            return JSONResponse(content={"message": "Success", "reply": chatgpt_response})

        required_fields = ["job_title", "location","num_of_peoples"]
        missing_fields = [f for f in required_fields if f not in json_response]
        if missing_fields:
            return JSONResponse(content={
                "message": "Success",
                "reply": f"Missing information: {', '.join(missing_fields)}. Please update your query."
            })

        job_title = json_response["job_title"]
        location = json_response["location"]
        number_of_peoples = json_response["num_of_peoples"]
    

        peoples_per_page = 100

        # Dynamic input: number of people to fetch
        num_of_peoples = int(number_of_peoples)  # replace with any dynamic value

        # Calculate total number of pages needed
        total_pages = (num_of_peoples + peoples_per_page - 1) // peoples_per_page

        # (Optional) Calculate people per page for uniform distribution
        people_per_page = num_of_peoples // total_pages


        try:
            peoples_found = search_people(
                job_title, location,
                pages=total_pages,
                per_page=people_per_page,
                required_count=num_of_peoples
            )
        except Exception as e:
            print(f"Search error: {e}")
            return JSONResponse(content={
                "message": "Success",
                "reply": "An error occurred during search. Limit is 100 companies."
            })

        for people in peoples_found:
            try:
                # Save company
                db_company = models.Company(
                    name=people.get("company", "Not Available"),
                    address=people.get("location", "Not Available"),
                    search_id=chat_id
                )
                db.add(db_company)
                db.commit()
                db.refresh(db_company)

                # Save contact (linked to this company)
                db_contact = models.Contact(
                    name=people.get("name", "Not Available"),
                    designation=people.get("designation", "Not Available"),
                    email=people.get("email", "Not Available"),
                    phone=people.get("phone", "Not Available"),
                    address=people.get("location", "Not Available"),
                    linkedin=people.get("linkedin", "Not Available"),
                    additional_info=people.get("additional_info", "Not Available"),
                    company_id=db_company.id
                )
                db.add(db_contact)
                db.commit()

            except Exception as e:
                print(f"Error saving company/contact: {e}")
                db.rollback()
                continue


        # ✅ Save a single <a> tag message AFTER all company/contact inserts
        try:
            with_chat_id = models.ConversationHistory(
                user_id=user_id,
                chat_id=chat_id,
                role="assistant",
                content=f'<a href="/contacts/{chat_id}" target="_blank">Click here to view Leads</a>',
                final_reply=chat_id,
                created_at=datetime.now(timezone.utc)
            )
            db.add(with_chat_id)
            db.commit()
            db.refresh(with_chat_id)
        except Exception as e:
            print(f"Error saving assistant reply: {e}")
            db.rollback()

        return JSONResponse(content={
            "message": "Success",
            "chat_id": chat_id,
            "link": f'<a href="/contacts/{chat_id}" target="_blank">Click here to view Leads</a>'
        })

    else:
        print("B2B mode enabled")
        user_id = user_info.get("user_id")

        # Save search query
        try:
            history = models.SearchHistory(query=message)
            if user_id:
                history.user_id = user_id
            db.add(history)
            db.commit()
            db.refresh(history)
        except Exception as e:
            print(f"Error saving search history: {e}")
            db.rollback()
            return JSONResponse(status_code=500, content={
                "message": "Error",
                "reply": "An error occurred while saving your search history."
            })

        # Get ChatGPT response
        chatgpt_response = await extract_industry_and_location(message, user_id, chat_id, db)

        try:
            json_response = chatgpt_response if isinstance(chatgpt_response, dict) else json.loads(chatgpt_response)
        except json.JSONDecodeError:
            ai_reply = models.ConversationHistory(
                user_id=user_id,
                chat_id=chat_id,
                role="assistant",
                content=chatgpt_response,
                final_reply=chatgpt_response,
                created_at=datetime.now(timezone.utc)
            )
            db.add(ai_reply)
            db.commit()
            db.refresh(ai_reply)
            return JSONResponse(content={"message": "Success", "reply": chatgpt_response})

        required_fields = ["industry", "location", "num_companies", "position_titles"]
        missing_fields = [f for f in required_fields if f not in json_response]
        if missing_fields:
            return JSONResponse(content={
                "message": "Success",
                "reply": f"Missing information: {', '.join(missing_fields)}. Please update your query."
            })

        industry = json_response["industry"]
        location = json_response["location"]
        num_companies = json_response["num_companies"]
        position_titles = json_response["position_titles"]

        companies_per_page = 100
        total_pages = (num_companies + companies_per_page - 1) // companies_per_page
        companies_per_page = num_companies // total_pages

        try:
            companies = search_companies(
                industry, location,
                pages=total_pages,
                per_page=companies_per_page,
                titles=position_titles,
                required_count=num_companies
            )
        except Exception as e:
            print(f"Search error: {e}")
            return JSONResponse(content={
                "message": "Success",
                "reply": "An error occurred during search. Limit is 100 companies."
            })

        for company in companies:
            try:
                if isinstance(company, dict):
                    db_company = models.Company(
                        name=company.get("name", "Not Available"),
                        address=company.get("address", "Not Available"),
                        website=company.get("website", "Not Available"),
                        phone=company.get("phone", "Not Available"),
                        linkedin=company.get("linkedin", "Not Available"),
                        founded_year=company.get("founded_year", "Not Available"),
                        logo=company.get("logo_url", "Not Available"),
                        search_id=chat_id
                    )
                    db.add(db_company)
                    db.commit()
                    db.refresh(db_company)

                    for contact in company.get("contacts", []):
                        if isinstance(contact, dict):
                            db_contact = models.Contact(
                                name=contact.get("name", "Not Available"),
                                designation=contact.get("designation", "Not Available"),
                                email=contact.get("email", "Not Available"),
                                phone=contact.get("phone", "Not Available"),
                                address=contact.get("address", "Not Available"),
                                linkedin=contact.get("linkedin", "Not Available"),
                                additional_info=contact.get("additional_info", "Not Available"),
                                company_id=db_company.id
                            )
                            db.add(db_contact)
                    db.commit()
            except Exception as e:
                print(f"Error saving company/contact: {e}")
                db.rollback()
                continue

        # ✅ Save a single <a> tag message AFTER all company/contact inserts
        try:
            with_chat_id = models.ConversationHistory(
                user_id=user_id,
                chat_id=chat_id,
                role="assistant",
                content=f'<a href="/contacts/{chat_id}" target="_blank">Click here to view Leads</a>',
                final_reply=chat_id,
                created_at=datetime.now(timezone.utc)
            )
            db.add(with_chat_id)
            db.commit()
            db.refresh(with_chat_id)
        except Exception as e:
            print(f"Error saving assistant reply: {e}")
            db.rollback()

        return JSONResponse(content={
            "message": "Success",
            "chat_id": chat_id,
            "link": f'<a href="/contacts/{chat_id}" target="_blank">Click here to view Leads</a>'
        })


@router.get("/contacts/{chat_id}", response_class=HTMLResponse)
async def contacts_by_chat_id(
    chat_id: str,
    request: Request,
    db: Session = Depends(get_db),
    user_info=Depends(get_current_user_for_templates)
):
    # Fetch companies associated with the chat_id
    companies = db.query(models.Company).filter(models.Company.search_id == chat_id).all()

    if not companies:
        return templates.TemplateResponse("searchresults.html", {
            "request": request,
            "companies": [],
            "query": f"No leads found for chat ID: {chat_id}",
            **user_info
        })

    # Fetch contacts associated with those companies
    company_ids = [company.id for company in companies]
    contacts = db.query(models.Contact).filter(models.Contact.company_id.in_(company_ids)).all()

    # Group contacts under each company
    company_data = []
    for company in companies:
        company_contacts = [contact.as_dict() for contact in contacts if contact.company_id == company.id]
        company_data.append({
            "name": company.name,
            "address": company.address,
            "website": company.website,
            "phone": company.phone,
            "linkedin": company.linkedin,
            "founded_year": company.founded_year,
            "logo": company.logo,
            "contacts": company_contacts
        })
    
    return templates.TemplateResponse("searchresults.html", {
        "request": request,
        "companies": company_data,
        "query": f"Leads for chat ID: {chat_id}",
        **user_info
    })
 


    
@router.post("/create_list", response_class=JSONResponse)
async def create_list(
    request: Request,
    list_name: str = Form(...),  # Get list name from form data
    db: Session = Depends(get_db)
):
    # Save new list to database
    new_list = models.ListContacts(name=list_name)
    db.add(new_list)

    try:
        db.commit()  # Commit changes to the database
        db.refresh(new_list)  # Refresh the newly added list to get its ID and other fields
    except Exception as e:
        print(f"Error saving list: {e}")
        db.rollback()  # Rollback changes if an error occurs
        return JSONResponse({"status": "error", "message": "Database error"}, status_code=500)

    # Return the status, message, and the newly created list
    return JSONResponse({
        "status": "success",
        "message": f"List '{new_list.name}' created successfully!",
   
    })

@router.get("/get_lists", response_class=JSONResponse)
async def get_lists(db: Session = Depends(get_db)):
    # Retrieve all lists from the database
    lists = db.query(models.ListContacts).all()

    # Return the lists as JSON
    return JSONResponse({
        "status": "success",
        "lists": [{"id": l.id, "name": l.name} for l in lists]
    })



@router.post("/add_to_list", response_class=JSONResponse)
async def add_contact_to_list(
    request: Request,
    list: int = Form(...),
    contact_id: int = Form(...),
    db: Session = Depends(get_db)
):
    try:
        # Log form data received
        form_data = await request.form()
        logger.info(f"Form data received: {dict(form_data)}")
        logger.info(f"Received form data - list_id: {list}, contact_id: {contact_id}")

        # Validate contact_id as integer
        try:
            contact_id = int(contact_id)
        except ValueError:
            raise HTTPException(status_code=400, detail="contact_id must be a valid integer.")

        # Fetch contact from DB
        contact = db.query(models.Contact).filter(models.Contact.id == contact_id).first()
        if not contact:
            logger.error(f"Contact with ID {contact_id} not found.")
            return JSONResponse({"status": "error", "message": "Contact not found."}, status_code=404)

        # Check for duplicate entry in ContactDetail
        existing = db.query(models.ContactDetail).filter_by(
            list_id=list,
            email=contact.email
        ).first()

        if existing:
            logger.info(f"Duplicate contact not added: {contact.email} already in list {list}")
            return JSONResponse({
                "status": "skipped",
                "message": "Contact already exists in the list."
            })

        # Create ContactDetail entry
        contact_detail = models.ContactDetail(
            name=contact.name,
            email=contact.email,
            phone=contact.phone,
            address=contact.address,
            designation=contact.designation,
            additional_info=contact.additional_info,
            list_id=list
        )
        db.add(contact_detail)

        try:
            db.commit()
            db.refresh(contact_detail)
            logger.info(f"Successfully added contact {contact_id} to list {list} with ID {contact_detail.id}")

        except Exception as db_error:
            db.rollback()
            logger.error(f"Database error: {db_error}")
            return JSONResponse({"status": "error", "message": f"Database error: {db_error}"}, status_code=500)

        return JSONResponse({
            "status": "success",
            "message": "Contact added to list successfully!",
            "contact_detail_id": contact_detail.id
        })

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return JSONResponse({"status": "error", "message": f"Unexpected error: {e}"}, status_code=500)

@router.post("/add_all_to_list", response_class=JSONResponse)
async def add_all_to_list(request: Request, db: Session = Depends(get_db)):
    try:
        # Parse JSON body
        body = await request.json()
        logger.info(f"Received JSON: {body}")

        list_id = body.get("list")
        contact_ids = body.get("contact_ids", [])

        # Validate list_id
        if not isinstance(list_id, int):
            raise HTTPException(status_code=400, detail="list_id must be an integer.")

        # Validate contact_ids
        if not isinstance(contact_ids, list) or not all(isinstance(i, int) for i in contact_ids):
            raise HTTPException(status_code=400, detail="contact_ids must be a list of integers.")

        # Fetch contacts from the database
        contacts = db.query(models.Contact).filter(models.Contact.id.in_(contact_ids)).all()

        if len(contacts) != len(contact_ids):
            logger.error("Some contacts were not found.")
            return JSONResponse({"status": "error", "message": "Some contacts not found."}, status_code=404)

        # Fetch the list
        contact_list = db.query(models.ListContacts).get(list_id)
        if not contact_list:
            logger.error(f"List with ID {list_id} not found.")
            return JSONResponse({"status": "error", "message": "List not found."}, status_code=404)

        added_count = 0

        # Add contacts to list only if not already present
        for contact in contacts:
            # Check if this contact is already added to the list
            existing = db.query(models.ContactDetail).filter_by(
                email=contact.email,  # or use contact.id if unique per user
                list_id=list_id
            ).first()

            if existing:
                logger.info(f"Skipping duplicate: {contact.email} already in list {list_id}")
                continue

            contact_detail = models.ContactDetail(
                name=contact.name,
                email=contact.email,
                phone=contact.phone,
                address=contact.address,
                designation=contact.designation,
                additional_info=contact.additional_info,
                list_id=list_id
            )
            db.add(contact_detail)
            added_count += 1

        try:
            db.commit()
            db.refresh(contact_list)
            logger.info(f"{added_count} contacts added to list {list_id}")
        except Exception as db_error:
            db.rollback()
            logger.error(f"Database error: {db_error}")
            return JSONResponse({"status": "error", "message": f"Database error: {db_error}"}, status_code=500)

        return JSONResponse({
            "status": "success",
            "message": f"{added_count} new contacts added to list successfully! Skipped duplicates."
        })

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return JSONResponse({"status": "error", "message": f"Unexpected error: {e}"}, status_code=500)

# Get company details
@router.get("/company/{company_id}", response_class=HTMLResponse)
async def company_details(
    request: Request, 
    company_id: int, 
    db: Session = Depends(get_db),
    user_info = Depends(get_current_user_for_templates)
):
    company = db.query(models.Company).filter(models.Company.id == company_id).first()
    if not company:
        raise HTTPException(status_code=404, detail="Company not found")
    
    contacts = db.query(models.Contact).filter(models.Contact.company_id == company_id).all()
    
    return templates.TemplateResponse(
        "company_details.html", 
        {
            "request": request, 
            "company": company,
            "contacts": contacts,
            **user_info
        }
    )

# Search history
@router.get("/history", response_class=HTMLResponse)
async def history(
    request: Request, 
    db: Session = Depends(get_db),
    user_info = Depends(get_current_user_for_templates)
):
    if user_info.get("user_id"):
        # Show only user's history if logged in
        history = db.query(models.SearchHistory).filter(
            models.SearchHistory.user_id == user_info["user_id"]
        ).order_by(models.SearchHistory.timestamp.desc()).all()
    else:
        # Show all history when not logged in (or limit to recent)
        history = db.query(models.SearchHistory).order_by(
            models.SearchHistory.timestamp.desc()
        ).limit(10).all()
    
    return templates.TemplateResponse(
        "history.html", 
        {
            "request": request, 
            "history": history,
            **user_info
        }
    )

# Contacts page
# Contacts page with robust error handling
@router.get("/searchresults", response_class=HTMLResponse)
async def contacts_page(
    request: Request,
    db: Session = Depends(get_db),
    user_info = Depends(get_current_user_for_templates)
):
    # Check if there are search results in the session
    query = request.query_params.get("q")
    if query:
        # If there's a query parameter, perform the search
        companies = search_companies(query)
        return templates.TemplateResponse("searchresults.html", {
            "request": request,
            "companies": companies,
            "query": query,
            **user_info
        })
    
@router.get("/contact-lists", response_class=HTMLResponse)
async def contact_lists_page(
    request: Request, 
    db: Session = Depends(get_db),
    user_info = Depends(get_current_user_for_templates)
    ):
    """Fetch all contact lists and render the template."""
    contact_lists = db.query(models.ListContacts).all()
    return templates.TemplateResponse("contact-lists.html", {
        "request": request,
        "contact_lists": contact_lists,
        **user_info
    })

@router.get("/contact-lists/{list_id}", response_class=JSONResponse)
async def get_contacts_by_list(list_id: int, db: Session = Depends(get_db)):
    """Fetch contacts linked to a specific list and return as JSON."""
    contact_list = db.query(models.ListContacts).filter(models.ListContacts.id == list_id).first()
    if not contact_list:
        return JSONResponse(content={"error": "List not found"}, status_code=404)

    contacts = db.query(models.ContactDetail).filter(models.ContactDetail.list_id == list_id).limit(10).all()

    return JSONResponse(content={
        "list_id": list_id,
        "list_name": contact_list.name,
        "contacts": [
            {
                "id": contact.id,
                "name": contact.name,
                "designation": contact.designation or "",
                "email": contact.email or "N/A",
                "phone": contact.phone or "N/A",
                "address": contact.address or "N/A",
                "additional_info": contact.additional_info or "N/A"
            }
            for contact in contacts
        ]
    })

@router.get("/contact-lists/{list_id}/more", response_class=JSONResponse)
async def get_more_contacts(request: Request, list_id: int, offset: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    """Fetch more contacts linked to a specific list (for expanding view)."""
    contact_list = db.query(models.ListContacts).filter(models.ListContacts.id == list_id).first()
    contacts = db.query(models.ContactDetail).filter(models.ContactDetail.list_id == list_id).offset(offset).limit(limit).all()
    
    # Check if there are more contacts to load
    total_contacts = db.query(models.ContactDetail).filter(models.ContactDetail.list_id == list_id).count()
    show_more = total_contacts > (offset + len(contacts))
    
    # Return JSON with contacts and show_more flag
    return JSONResponse(content={
        "contacts": [
            {
                "id": contact.id,
                "name": contact.name,
                "designation": contact.designation or "",
                "email": contact.email or "N/A",
                "phone": contact.phone or "N/A",
                "address": contact.address or "N/A",
                "additional_info": contact.additional_info or "N/A"
            }
            for contact in contacts
        ],
        "show_more": show_more
    })  
# Login page
@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    user_info=Depends(get_current_user_for_templates)
):
    if user_info.get("user_logged_in"):
        return RedirectResponse(url="/")  # already logged in
    return templates.TemplateResponse("login.html", {"request": request, **user_info})


# POST: Login Form Submission
@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request,
    db: Session = Depends(get_db),
    email: str = Form(...),
    password: str = Form(...),
    remember_me: bool = Form(False, alias="rememberMe")
):
    user = authenticate_user(db, email, password)
    if not user:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error": "Invalid email or password",
            "user_logged_in": False
        })

    # Generate token
    access_token_expires = timedelta(days=30 if remember_me else 1)
    access_token = create_access_token(data={"sub": user.email}, expires_delta=access_token_expires)

    # Redirect after login
    response = RedirectResponse(url="/", status_code=302)
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        max_age=3600 * 24 * 30 if remember_me else 3600 * 24,
        expires=3600 * 24 * 30 if remember_me else 3600 * 24,
        secure=True,
        samesite="Lax"
    )
    return response

# Registration page
@router.get("/register", response_class=HTMLResponse)
async def register_page(
    request: Request,
    user_info = Depends(get_current_user_for_templates)
):
    # If already logged in, redirect to home
    if user_info.get("user_logged_in"):
        return templates.TemplateResponse("index.html", {
            "request": request,
            **user_info
        })
    
    return templates.TemplateResponse("register.html", {
        "request": request,
        **user_info
    })

# Registration action
@router.post("/register", response_class=HTMLResponse)
async def register(
    request: Request,
    db: Session = Depends(get_db),
    name: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    confirmPassword: str = Form(...),
    termsAgreed: bool = Form(False)
):
    from .auth import register_user, create_access_token
    
    # Validation
    if password != confirmPassword:
        return templates.TemplateResponse(
            "register.html", 
            {
                "request": request,
                "error": "Passwords do not match",
                "name": name,
                "email": email,
                "user_logged_in": False
            }
        )
    
    if not termsAgreed:
        return templates.TemplateResponse(
            "register.html", 
            {
                "request": request,
                "error": "You must agree to the terms of service",
                "name": name,
                "email": email,
                "user_logged_in": False
            }
        )
    
    # Register user
    user = register_user(db, name, email, password)
    if not user:
        return templates.TemplateResponse(
            "register.html", 
            {
                "request": request,
                "error": "Email already registered",
                "name": name,
                "user_logged_in": False
            }
        )
    
    # Create access token
    access_token = create_access_token(data={"sub": user.email})
    
    # Create response
    response = templates.TemplateResponse(
        "index.html", 
        {
            "request": request,
            "user_logged_in": True,
            "user_name": user.name,
            "user_id": user.id
        }
    )
    
    # Set cookie
    response.set_cookie(
        key="access_token",
        value=f"Bearer {access_token}",
        httponly=True,
        max_age=3600 * 24,
    )
    
    return response

# Logout action
@router.get("/logout", response_class=HTMLResponse)
async def logout(request: Request):
    response = templates.TemplateResponse(
        "register.html", 
        {
            "request": request,
            "user_logged_in": False,
            "user_name": None,
            "user_id": None
        }
    )
    
    # Clear the cookie
    response.delete_cookie(key="access_token")
    
    return response

# Email page
@router.get("/email")
async def render_email_page(
    request: Request,
    list_id: int = Query(None),  # Accept the list_id as an optional query parameter
    db: Session = Depends(get_db),
    user_info = Depends(get_current_user_for_templates)  # To get user information for templates
):
    """Render the email page with the selected contact list's information, if provided."""
    
    contact_list = None
    if list_id is not None:
        # Only query the database if list_id is provided
        contact_list = db.query(models.ListContacts).filter(models.ListContacts.id == list_id).first()

    # Return the email page with or without the contact list
    return templates.TemplateResponse("email.html", {
        "request": request,
        "contact_list": contact_list,  # This will be None if no valid list_id is provided
        **user_info,  # Include user-specific information in the context
    })
# Call page
@router.get("/call", response_class=HTMLResponse)
async def call_page(
    request: Request,
    user_info = Depends(get_current_user_for_templates)
):
    return templates.TemplateResponse("call.html", {
        "request": request,
        **user_info
    })

# Settings page
@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    user_info = Depends(get_current_user_for_templates)
):
    return templates.TemplateResponse("settings.html", {
        "request": request,
        **user_info
    })