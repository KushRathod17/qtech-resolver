from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    CORS_ORIGINS: str = "http://localhost:5173"

    # Who may self-register. Comma-separated email domains, e.g.
    # "qtechsoftware.com,bizinso.com".
    #
    # EMPTY MEANS SELF-REGISTRATION IS CLOSED — that is the safe default, and it
    # is deliberate. Signup used to be wide open: anyone who found the URL got an
    # account and could read every ticket, every client name and every
    # attachment. For a tool holding travel-agency customer data that is a
    # confidentiality breach, not a convenience.
    #
    # This only gates JOINING an existing organization (POST /auth/signup/join).
    # Starting a brand-new organization (POST /auth/signup/organization) is
    # never domain-gated -- there's nothing to protect yet, since the org
    # doesn't exist until that call creates it. That's how a fresh install (or
    # a new customer's workspace) gets bootstrapped.
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
    def allowed_signup_domains(self) -> list[str]:
        return [
            d.strip().lower().lstrip("@")
            for d in self.ALLOWED_SIGNUP_DOMAINS.split(",")
            if d.strip()
        ]

    class Config:
        env_file = ".env"


settings = Settings()