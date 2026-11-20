from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings
from sqlalchemy import URL


class Settings(BaseSettings):
    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str
    postgres_host: str
    postgres_port: int = 5432

    # JWT の署名の鍵。短いと総当たりで当てられるため、32文字以上だけ受け付ける。
    jwt_secret_key: SecretStr = Field(min_length=32)

    # Google Books の API キー（api.md 4-2）。なければ起動を止める
    google_books_api_key: SecretStr = Field(min_length=1)

    # OpenAI（api.md 2-7）。使うモデルはコードに書かず、料金を見て .env で切り替える
    openai_api_key: SecretStr = Field(min_length=1)
    openai_model: str = Field(min_length=1)
    # 考える量を指定できるモデル（推論モデル）のときだけ書く（minimal・low など）。空なら送らない
    openai_reasoning_effort: str | None = None

    @field_validator("openai_reasoning_effort", mode="before")
    @classmethod
    def empty_is_none(cls, value: str | None) -> str | None:
        return value or None

    @property
    def database_url(self) -> URL:
        return URL.create(
            drivername="postgresql+psycopg",
            username=self.postgres_user,
            password=self.postgres_password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        )


settings = Settings()
