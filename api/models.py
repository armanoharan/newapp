"""Pydantic models for the three CRM constructs: Companies, Contacts and Deals."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, EmailStr, Field


class DealStage(str, Enum):
    prospecting = "prospecting"
    qualification = "qualification"
    proposal = "proposal"
    negotiation = "negotiation"
    closed_won = "closed_won"
    closed_lost = "closed_lost"


# --------------------------------------------------------------------------- #
# Companies
# --------------------------------------------------------------------------- #
class CompanyBase(BaseModel):
    name: str = Field(..., min_length=1)
    domain: str
    industry: str
    employees: int = Field(..., ge=1)
    annual_revenue_usd: int = Field(..., ge=0)
    hq_city: str
    country: str
    description: str = ""


class CompanyCreate(CompanyBase):
    pass


class CompanyUpdate(BaseModel):
    name: str | None = None
    domain: str | None = None
    industry: str | None = None
    employees: int | None = Field(None, ge=1)
    annual_revenue_usd: int | None = Field(None, ge=0)
    hq_city: str | None = None
    country: str | None = None
    description: str | None = None


class Company(CompanyBase):
    id: int


# --------------------------------------------------------------------------- #
# Contacts
# --------------------------------------------------------------------------- #
class ContactBase(BaseModel):
    first_name: str = Field(..., min_length=1)
    last_name: str = Field(..., min_length=1)
    email: EmailStr
    phone: str = ""
    title: str
    company_id: int


class ContactCreate(ContactBase):
    pass


class ContactUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    title: str | None = None
    company_id: int | None = None


class Contact(ContactBase):
    id: int


# --------------------------------------------------------------------------- #
# Deals
# --------------------------------------------------------------------------- #
class DealBase(BaseModel):
    name: str = Field(..., min_length=1)
    company_id: int
    contact_id: int | None = None
    amount_usd: int = Field(..., ge=0)
    stage: DealStage = DealStage.prospecting
    probability: int = Field(10, ge=0, le=100)
    close_date: date
    owner: str
    product: str


class DealCreate(DealBase):
    pass


class DealUpdate(BaseModel):
    name: str | None = None
    company_id: int | None = None
    contact_id: int | None = None
    amount_usd: int | None = Field(None, ge=0)
    stage: DealStage | None = None
    probability: int | None = Field(None, ge=0, le=100)
    close_date: date | None = None
    owner: str | None = None
    product: str | None = None


class Deal(DealBase):
    id: int


class PipelineStage(BaseModel):
    stage: DealStage
    count: int
    total_amount_usd: int
    weighted_amount_usd: int


class PipelineSummary(BaseModel):
    total_deals: int
    open_pipeline_usd: int
    weighted_pipeline_usd: int
    won_usd: int
    stages: list[PipelineStage]
