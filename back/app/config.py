import re

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL, make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://spry:spry@localhost:5432/spry"
    cors_origins: str = "http://localhost:5173"
    cognito_issuer: str
    cognito_client_id: str

    @field_validator("cognito_issuer")
    @classmethod
    def trusted_pool_issuer(cls, value: str) -> str:
        # Exact AWS pool URL only: no userinfo, query, fragment, port or arbitrary host.
        pattern = r"https://cognito-idp\.([a-z]{2}(?:-[a-z]+)+-\d)\.amazonaws\.com(?:\.cn)?/\1_[A-Za-z0-9]+"
        if not re.fullmatch(pattern, value):
            raise ValueError("COGNITO_ISSUER must be an exact HTTPS AWS Cognito user-pool issuer URL")
        return value

    @field_validator("cognito_client_id")
    @classmethod
    def public_client_id(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z0-9]{1,128}", value):
            raise ValueError("COGNITO_CLIENT_ID must be a nonempty public Cognito app-client ID")
        return value

    @property
    def sqlalchemy_url(self) -> URL:
        url = make_url(self.database_url)
        if url.drivername == "postgresql":
            url = url.set(drivername="postgresql+psycopg")
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
