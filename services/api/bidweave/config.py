# SPDX-FileCopyrightText: 2026 BidWeave contributors
# SPDX-License-Identifier: Apache-2.0
# Apache-2.0 licensed configuration; no warranty.
from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str = "postgresql+psycopg://bidweave:bidweave@localhost:5432/bidweave"
    keycloak_issuer: str = "http://localhost:8091/realms/bidweave"
    keycloak_jwks_url: str | None = None
    keycloak_audience: str = "bidweave-api"
    s3_endpoint: str = "http://localhost:8333"
    s3_bucket: str = "bidweave"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    clamav_host: str = "localhost"
    clamav_port: int = 3310
    flowable_url: str = "http://localhost:8080/process-api"
    flowable_user: str = ""
    flowable_password: str = ""
    nats_url: str = "nats://localhost:4222"
    ted_endpoint: str = "https://publications.europa.eu/webapi/rdf/sparql"
    storage_backend: str = "s3"
    local_storage_path: str = "/tmp/bidweave-objects"
    max_upload_bytes: int = 25 * 1024 * 1024
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", env_prefix="")


@lru_cache
def get_settings() -> Settings:
    return Settings()
