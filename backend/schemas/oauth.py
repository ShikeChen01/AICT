"""Pydantic schemas for OpenAI OAuth endpoints."""

from pydantic import BaseModel


class OAuthLoginResponse(BaseModel):
    url: str


class OAuthCallbackRequest(BaseModel):
    code: str
    state: str


class OAuthCallbackLoginResponse(BaseModel):
    firebase_custom_token: str


class OAuthCallbackConnectResponse(BaseModel):
    connected: bool


class OAuthCallbackErrorResponse(BaseModel):
    error: str
    message: str


class OAuthStatusResponse(BaseModel):
    connected: bool
    email: str | None = None
    scopes: str | None = None
    valid: bool | None = None
