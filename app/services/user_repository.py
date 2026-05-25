import uuid

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """
    Email and username are stored as the user typed them but matched
    case-insensitively so the UI can show whatever the user provided.
    """

    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, user_id: str) -> User | None:
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        result = await self._session.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        result = await self._session.execute(
            select(User).where(func.lower(User.username) == username.lower())
        )
        return result.scalar_one_or_none()

    async def get_by_identifier(self, identifier: str) -> User | None:
        """Lookup a user by either email or username, case-insensitive."""
        ident = identifier.lower()
        result = await self._session.execute(
            select(User).where(
                or_(
                    func.lower(User.email) == ident,
                    func.lower(User.username) == ident,
                )
            )
        )
        return result.scalar_one_or_none()

    async def create(self, email: str, username: str, hashed_password: str) -> User:
        user = User(
            id=str(uuid.uuid4()),
            email=email,
            username=username,
            hashed_password=hashed_password,
        )
        self._session.add(user)
        await self._session.commit()
        await self._session.refresh(user)
        return user

    async def exists_by_email(self, email: str) -> bool:
        result = await self._session.execute(
            select(User.id).where(func.lower(User.email) == email.lower())
        )
        return result.scalar_one_or_none() is not None

    async def exists_by_username(self, username: str) -> bool:
        result = await self._session.execute(
            select(User.id).where(func.lower(User.username) == username.lower())
        )
        return result.scalar_one_or_none() is not None
