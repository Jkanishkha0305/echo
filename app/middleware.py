from fastapi import Request
from fastapi.responses import RedirectResponse
from .dependencies import get_current_user_from_cookie  # Function to get the current user from cookies

async def auth_middleware(request: Request, call_next):
    """Middleware to automatically redirect non-authenticated users to the /login-singup page."""
    # List of public routes that don't require authentication
    public_routes = ["/login-singup", "/login", "/register", "/auth/login", "/auth/google/callback","/static/img/logo.svg"]

    # If the route is not public, check if the user is authenticated
    if request.url.path not in public_routes:
        user = await get_current_user_from_cookie(request)
        if not user:
            # Redirect to the /login-singup page if the user is not authenticated
            return RedirectResponse(url="/register")
    
    # If the user is authenticated or the route is public, continue processing the request
    return await call_next(request)
