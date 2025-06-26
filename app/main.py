from fastapi import FastAPI, Request, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware  # Import SessionMiddleware
import uvicorn
import sqlite3
import os
from .routes import router
from .database import engine, Base
from .dependencies import get_current_user_for_templates, get_current_user_from_cookie

# Create tables
Base.metadata.create_all(bind=engine)

# Check if database exists and add user_id column if necessary
db_path = "scrapper.db"
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if user_id column exists in search_history table
        cursor.execute("PRAGMA table_info(search_history)")
        columns = cursor.fetchall()
        column_names = [column[1] for column in columns]
        
        if 'user_id' not in column_names:
            print("Adding user_id column to search_history table...")
            cursor.execute("ALTER TABLE search_history ADD COLUMN user_id INTEGER")
            conn.commit()
            print("Column added successfully.")
        
        conn.close()
    except Exception as e:
        print(f"Error checking/updating database schema: {e}")

# Initialize FastAPI app
app = FastAPI(title="Scrapper", description="Web scraping application")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

# Setup templates
templates = Jinja2Templates(directory="templates")
# Add SessionMiddleware for session management (required for OAuth2)
app.add_middleware(SessionMiddleware, secret_key="09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7")  # Replace with a secure key
# Middleware for authentication check and redirection
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """Middleware to automatically redirect non-authenticated users."""
    # List of public routes that don't require authentication
    public_routes = ["/login-singup", "/login", "/register", "/auth/login", "/auth/google/callback","/static/img/logo.svg"]
    
    # If the route is not public, check for authentication
    if request.url.path not in public_routes:
        user = await get_current_user_from_cookie(request)
        if not user:
            return RedirectResponse(url="/register")  # Redirect to home if not authenticated

    # Proceed with the request if authenticated or route is public
    response = await call_next(request)
    return response

# Add context processor for templates (optional)
@app.middleware("http")
async def add_user_middleware(request: Request, call_next):
    """Add user info to all templates"""
    response = await call_next(request)
    return response

# Include routers
app.include_router(router)

# Run the application
if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
