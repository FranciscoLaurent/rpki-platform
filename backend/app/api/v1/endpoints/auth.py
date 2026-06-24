"""认证端点：登录、注册、刷新令牌、获取当前用户、修改密码、登出。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_active_user, get_current_user_optional
from app.core.config import settings
from app.core.database import get_db
from app.core.logging import get_logger
from app.models.user import Role, User
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MessageResponse,
    RefreshTokenRequest,
    TokenResponse,
    UserCreate,
    UserResponse,
)
from app.services import audit_service, auth_service

router = APIRouter()
logger = get_logger("auth")


def _get_client_ip(request: Request) -> str | None:
    """从请求中获取客户端 IP（支持代理转发）。"""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


@router.post("/login", response_model=TokenResponse)
async def login(
    request: Request,
    login_data: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """用户登录，返回访问令牌与刷新令牌。"""
    try:
        user = await auth_service.authenticate_user(
            db, login_data.username, login_data.password
        )
    except ValueError as e:
        # 记录登录失败审计
        await audit_service.log_action(
            db,
            user_id=None,
            tenant_id=None,
            action="login_failed",
            resource_type="auth",
            details={"username": login_data.username, "reason": str(e)},
            ip=_get_client_ip(request),
            user_agent=request.headers.get("User-Agent"),
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )

    access_token, expires_in = auth_service.create_user_access_token(user)
    refresh_token = auth_service.create_user_refresh_token(user)

    # 记录登录成功审计
    await audit_service.log_action(
        db,
        user_id=user.id,
        tenant_id=None,
        action="login_success",
        resource_type="auth",
        ip=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )

    logger.info("用户登录成功", user_id=user.id, username=user.username)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        refresh_token=refresh_token,
        must_change_password=user.must_change_password,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    request: RefreshTokenRequest,
    db: AsyncSession = Depends(get_db),
) -> TokenResponse:
    """使用刷新令牌获取新的访问令牌。"""
    try:
        payload = auth_service.verify_token(request.refresh_token)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    user_id_str = payload.get("sub")
    if user_id_str is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新令牌",
        )

    # 查询用户
    stmt = (
        select(User)
        .options(selectinload(User.roles).selectinload(Role.permissions))
        .where(User.id == int(user_id_str))
    )
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已被禁用",
        )

    access_token, expires_in = auth_service.create_user_access_token(user)
    new_refresh_token = auth_service.create_user_refresh_token(user)

    return TokenResponse(
        access_token=access_token,
        token_type="bearer",
        expires_in=expires_in,
        refresh_token=new_refresh_token,
    )


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(
    user_create: UserCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
) -> UserResponse:
    """注册新用户。

    - 开放注册时（``OPEN_REGISTRATION=True``）任何人可注册。
    - 否则需要超级管理员权限。
    """
    if not settings.OPEN_REGISTRATION:
        if current_user is None or not current_user.is_superuser:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="注册功能未开放，请联系管理员",
            )

    try:
        user = await auth_service.register_user(db, user_create)
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    return UserResponse.model_validate(user)


@router.get("/me", response_model=UserResponse)
async def get_me(
    current_user: User = Depends(get_current_active_user),
) -> UserResponse:
    """获取当前登录用户信息。"""
    return UserResponse.model_validate(current_user)


@router.post("/change-password", response_model=MessageResponse)
async def change_password(
    request: Request,
    password_data: ChangePasswordRequest,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """修改当前用户密码。"""
    try:
        await auth_service.change_password(
            db, current_user, password_data.old_password, password_data.new_password
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    # 记录审计日志
    await audit_service.log_action(
        db,
        user_id=current_user.id,
        tenant_id=None,
        action="change_password",
        resource_type="auth",
        ip=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )

    return MessageResponse(message="密码修改成功")


@router.post("/logout", response_model=MessageResponse)
async def logout(
    request: Request,
    current_user: User = Depends(get_current_active_user),
    db: AsyncSession = Depends(get_db),
) -> MessageResponse:
    """用户登出，将当前令牌加入黑名单。

    注意：客户端需在请求头中携带 Bearer token，登出后该 token 即刻失效。
    """
    # 提取原始令牌并加入黑名单
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        auth_service.blacklist_token(token)

    # 记录审计日志
    await audit_service.log_action(
        db,
        user_id=current_user.id,
        tenant_id=None,
        action="logout",
        resource_type="auth",
        ip=_get_client_ip(request),
        user_agent=request.headers.get("User-Agent"),
    )

    logger.info("用户登出", user_id=current_user.id)
    return MessageResponse(message="已登出")
