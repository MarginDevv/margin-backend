"""Authentication & registration service."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.restaurant import Restaurant
from app.models.subscription import Subscription, SubscriptionPlan, SubscriptionStatus
from app.models.user import User
from app.models.user_restaurant_role import Role, UserRestaurantRole
from app.repositories.user_repo import UserRepository
from app.schemas.auth import RegisterRequest, TokenPair


class AuthService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def register(self, data: RegisterRequest) -> tuple[User, Restaurant, TokenPair]:
        email = data.email.lower()
        if await self.users.get_by_email(email):
            raise ConflictError("User with this email already exists")

        user = User(
            email=email,
            password_hash=hash_password(data.password),
            full_name=data.full_name,
            phone=data.phone,
        )
        self.session.add(user)
        await self.session.flush()

        restaurant = Restaurant(name=data.restaurant_name)
        self.session.add(restaurant)
        await self.session.flush()

        self.session.add(
            UserRestaurantRole(
                user_id=user.id, restaurant_id=restaurant.id, role=Role.OWNER
            )
        )
        self.session.add(
            Subscription(
                restaurant_id=restaurant.id,
                plan=SubscriptionPlan.FREE_TRIAL,
                status=SubscriptionStatus.TRIAL,
            )
        )
        await self.session.flush()

        tokens = self._issue_tokens(user)
        await self.session.commit()
        return user, restaurant, tokens

    async def login(self, email: str, password: str) -> tuple[User, TokenPair]:
        user = await self.users.get_by_email(email.lower())
        if not user or not verify_password(password, user.password_hash):
            raise AuthenticationError("Invalid email or password")
        if not user.is_active:
            raise AuthenticationError("User is inactive")
        return user, self._issue_tokens(user)

    async def refresh(self, refresh_token: str) -> TokenPair:
        try:
            payload = decode_token(refresh_token)
        except ValueError as exc:
            raise AuthenticationError(str(exc)) from exc
        if payload.get("type") != "refresh":
            raise AuthenticationError("Not a refresh token")
        user_id = payload.get("sub")
        if not user_id:
            raise AuthenticationError("Token missing subject")
        import uuid

        user = await self.users.get(uuid.UUID(user_id))
        if not user or not user.is_active:
            raise AuthenticationError("User not found or inactive")
        return self._issue_tokens(user)

    @staticmethod
    def _issue_tokens(user: User) -> TokenPair:
        return TokenPair(
            access_token=create_access_token(
                str(user.id),
                extra_claims={"email": user.email, "is_superuser": user.is_superuser},
            ),
            refresh_token=create_refresh_token(str(user.id)),
        )
