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
    # The very first account is always allowed regardless, or a fresh install
    # could never be bootstrapped.
    ALLOWED_SIGNUP_DOMAINS: str = ""

    # Failed logins allowed from one IP (or against one email) before the door
    # shuts for a while. Login was completely unthrottled: five known accounts on
    # `password123` are brute-forceable in seconds.
    LOGIN_MAX_ATTEMPTS: int = 8
    LOGIN_LOCKOUT_SECONDS: int = 900  # 15 minutes

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