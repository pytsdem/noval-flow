from __future__ import annotations

from pydantic import BaseModel, Field

from novel_flow.models.schemas import BookBlueprint, BookDocument, PatchInstruction


class ResearchTask(BaseModel):
    query: str = Field(min_length=1)


class CreateBookTask(BaseModel):
    blueprint: BookBlueprint
    source_query: str


class RewriteUnitTask(BaseModel):
    book: BookDocument
    block_id: str
    guidance: str


class PatchBlockTask(BaseModel):
    book: BookDocument
    instruction: PatchInstruction


class ExpandTask(BaseModel):
    book: BookDocument
    block_id: str
    expansion_goal: str


class MasterRunTask(BaseModel):
    query: str = Field(default="都市情感反转", min_length=1)
    style_request: str = ""
