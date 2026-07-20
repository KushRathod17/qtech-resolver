from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:5173"

    # The shared secret every registration must present, handed to the team
    # out of band. This is the PRIMARY gate on both signup paths -- creating a
    # new organization and joining an existing one.
    #
    # EMPTY MEANS REGISTRATION IS CLOSED ENTIRELY. Unset must never read as
    # "no restriction": a blank env var is far more likely to be a
    # misconfiguration (typo in the key, forgotten on a new service) than a
    # deliberate decision to let the whole internet register. Failing closed
    # turns that mistake into a support ticket instead of a data breach.
    INVITE_CODE: str = ""

    # An OPTIONAL extra restriction on top of the invite code, narrowing who may
    # join an existing organization. Comma-separated email domains, e.g.
    # "qtechsoftware.com,bizinso.com".
    #
    # Empty means "no domain restriction" -- which is safe here only because
    # INVITE_CODE above is mandatory and independently blocks registration when
    # unset. This setting is a second filter, never the sole gate.
    ALLOWED_SIGNUP_DOMAINS: str = ""

    # Failed logins allowed from one IP (or against one email) before the door
    # shuts for a while. Login was completely unthrottled: five known accounts on
    # `password123` are brute-forceable in seconds.
    LOGIN_MAX_ATTEMPTS: int = 8
    LOGIN_LOCKOUT_SECONDS: int = 900  # 15 minutes

    # Object storage for ticket attachments and avatars. Leave all four blank
    # to use local disk (the default -- fine for local dev and for a host with
    # a persistent disk). Set all four to point uploads at any S3-compatible
    # bucket instead -- required on a free-tier host, since its filesystem is
    # wiped on every deploy/restart. See app/storage.py.
    S3_ENDPOINT_URL: str = ""
    S3_ACCESS_KEY_ID: str = ""
    S3_SECRET_ACCESS_KEY: str = ""
    S3_BUCKET_NAME: str = ""
    S3_REGION: str = "auto"

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.CORS_ORIGINS.split(",")]

    @property
    def invite_code(self) -> str:
        """Stripped, so a trailing newline pasted into the Render dashboard
        doesn't silently make every correct code fail."""
        return self.INVITE_CODE.strip()

    @property
    def allowed_signup_domains(self) -> list[str]:
        return [
            d.strip().lower().lstrip("@")
            for d in self.ALLOWED_SIGNUP_DOMAINS.split(",")
            if d.strip()
        ]

    class Config:
        env_file = ".env"


settings = Settings()