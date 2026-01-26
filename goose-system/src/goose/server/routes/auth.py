"""
Server Routes - Authentication

Authentication endpoints:
- User registration
- User login
- User logout
- Token management
- User profile management

Reference: goose-rs/crates/goose-server/src/routes/auth.rs
"""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Query
from pydantic import BaseModel, Field
# Use string for email to avoid email-validator import issues

from .router import ServerRouter
from ...server.user import UserManager, User, Session, UserRole
from ...server.auth import TokenValidator

router = APIRouter()


# Request/Response Models

class RegisterRequest(BaseModel):
    """User registration request"""
    username: str = Field(..., min_length=3, max_length=50, description="Username")
    password: str = Field(..., min_length=6, max_length=100, description="Password")
    email: Optional[str] = Field(default=None, description="Email address")
    role: Optional[str] = Field(default="user", description="User role (admin/user)")


class RegisterResponse(BaseModel):
    """User registration response"""
    success: bool
    message: str
    user_id: Optional[str] = None
    username: Optional[str] = None


class LoginRequest(BaseModel):
    """User login request"""
    username: str = Field(..., description="Username")
    password: str = Field(..., description="Password")
    expire_hours: Optional[int] = Field(default=24, ge=1, le=168, description="Session expiration in hours")


class LoginResponse(BaseModel):
    """User login response"""
    success: bool
    message: str
    session_id: Optional[str] = None
    user: Optional[Dict[str, Any]] = None


class LogoutRequest(BaseModel):
    """User logout request"""
    session_id: str = Field(..., description="Session ID")


class LogoutResponse(BaseModel):
    """User logout response"""
    success: bool
    message: str


class UserProfile(BaseModel):
    """User profile"""
    user_id: str
    username: str
    email: Optional[str] = None
    role: str
    created_at: str
    is_active: bool


class ChangePasswordRequest(BaseModel):
    """Change password request"""
    old_password: str = Field(..., min_length=6, description="Current password")
    new_password: str = Field(..., min_length=6, max_length=100, description="New password")


class UpdateUserRequest(BaseModel):
    """Update user request"""
    email: Optional[str] = Field(default=None, description="Email address")
    is_active: Optional[bool] = Field(default=None, description="Account active status")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="User metadata")


class ErrorResponse(BaseModel):
    """Error response"""
    error: str
    detail: Optional[str] = None


# Helper function to get user manager
async def get_user_manager() -> UserManager:
    return await UserManager.instance()


# Routes

@router.post("/auth/register", response_model=RegisterResponse, status_code=status.HTTP_201_CREATED)
async def register(request: RegisterRequest) -> RegisterResponse:
    """
    Register a new user

    Creates a new user account with the provided credentials.
    """
    user_manager = await get_user_manager()

    # Map role string to UserRole enum
    role = UserRole.USER
    if request.role == "admin":
        role = UserRole.ADMIN

    success, user, error = await user_manager.register_user(
        username=request.username,
        password=request.password,
        email=request.email,
        role=role
    )

    if success:
        return RegisterResponse(
            success=True,
            message="User registered successfully",
            user_id=user.user_id,
            username=user.username
        )

    return RegisterResponse(
        success=False,
        message=error or "Registration failed"
    )


@router.post("/auth/login", response_model=LoginResponse)
async def login(request: LoginRequest) -> LoginResponse:
    """
    User login

    Authenticates user credentials and creates a session.
    """
    user_manager = await get_user_manager()

    success, session, error = await user_manager.login_user(
        username=request.username,
        password=request.password,
        expire_hours=request.expire_hours
    )

    if success and session:
        user = await user_manager.get_user(session.user_id)

        return LoginResponse(
            success=True,
            message="Login successful",
            session_id=session.session_id,
            user={
                "user_id": session.user_id,
                "username": user.username if user else "",
                "role": user.role.value if user else "user",
            }
        )

    return LoginResponse(
        success=False,
        message=error or "Login failed"
    )


@router.post("/auth/logout", response_model=LogoutResponse)
async def logout(request: LogoutRequest) -> LogoutResponse:
    """
    User logout

    Invalidates the user session.
    """
    user_manager = await get_user_manager()

    success = await user_manager.logout_user(request.session_id)

    if success:
        return LogoutResponse(
            success=True,
            message="Logged out successfully"
        )

    return LogoutResponse(
        success=False,
        message="Session not found or already expired"
    )


@router.get("/auth/profile", response_model=UserProfile)
async def get_profile(
    session_id: str = Query(..., description="Session ID")
) -> UserProfile:
    """
    Get user profile from session

    Returns the user information associated with the session.
    """
    user_manager = await get_user_manager()

    user = await user_manager.get_user_from_session(session_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    return UserProfile(
        user_id=user.user_id,
        username=user.username,
        email=user.email,
        role=user.role.value,
        created_at=user.created_at,
        is_active=user.is_active
    )


@router.post("/auth/change_password")
async def change_password(
    request: ChangePasswordRequest,
    session_id: str = Query(..., description="Session ID")
) -> Dict[str, Any]:
    """
    Change user password

    Allows a user to change their password after authentication.
    """
    user_manager = await get_user_manager()

    # Verify session and get user
    user = await user_manager.get_user_from_session(session_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    success, error = await user_manager.change_password(
        user_id=user.user_id,
        old_password=request.old_password,
        new_password=request.new_password
    )

    if success:
        return {
            "success": True,
            "message": "Password changed successfully"
        }

    raise HTTPException(
        status_code=status.HTTP_BAD_REQUEST,
        detail=error or "Failed to change password"
    )


@router.post("/auth/update_profile")
async def update_profile(
    request: UpdateUserRequest,
    session_id: str = Query(..., description="Session ID")
) -> Dict[str, Any]:
    """
    Update user profile

    Updates user information like email and metadata.
    """
    user_manager = await get_user_manager()

    # Verify session and get user
    user = await user_manager.get_user_from_session(session_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    updates = {}
    if request.email is not None:
        updates["email"] = request.email
    if request.is_active is not None:
        updates["is_active"] = request.is_active
    if request.metadata is not None:
        updates["metadata"] = request.metadata

    success, updated_user, error = await user_manager.update_user(
        user_id=user.user_id,
        **updates
    )

    if success:
        return {
            "success": True,
            "message": "Profile updated successfully",
            "user": updated_user.to_dict() if updated_user else None
        }

    raise HTTPException(
        status_code=status.HTTP_BAD_REQUEST,
        detail=error or "Failed to update profile"
    )


@router.get("/auth/users")
async def list_users(
    session_id: str = Query(..., description="Session ID"),
    limit: int = Query(default=50, ge=1, le=100, description="Number of users to return")
) -> list[Dict[str, Any]]:
    """
    List all users (admin only)

    Returns a list of all registered users.
    """
    user_manager = await get_user_manager()

    # Verify session and get user
    user = await user_manager.get_user_from_session(session_id)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_UNAUTHORIZED,
            detail="Invalid or expired session"
        )

    # Check if user is admin
    if user.role != UserRole.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_FORBIDDEN,
            detail="Admin access required"
        )

    users = await user_manager.list_users(limit=limit)

    return [
        {
            "user_id": u.user_id,
            "username": u.username,
            "email": u.email,
            "role": u.role.value,
            "created_at": u.created_at,
            "is_active": u.is_active
        }
        for u in users
    ]


def routes() -> ServerRouter:
    """Create router with all auth routes"""
    return ServerRouter(router)
