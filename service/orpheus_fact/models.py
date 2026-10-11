"""Small immutable wire contracts for the Fact boundary."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FactRef(StrictModel):
    fact_id: str = Field(pattern=r"^fact-[0-9a-f]{32}$")
    version: int = Field(ge=1)


class Source(StrictModel):
    citation: str = Field(min_length=1, max_length=4000)
    locator: str = Field(min_length=1, max_length=4000)
    excerpt: str = Field(default="", max_length=100000)


class Artifact(StrictModel):
    name: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9._-]{0,199}$")
    kind: Literal["script", "report", "data", "certificate"]
    content: str = Field(min_length=1, max_length=2000000)

    @field_validator("content")
    @classmethod
    def text_only(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("artifact must be UTF-8 text")
        return value


class Candidate(StrictModel):
    title: str = Field(min_length=1, max_length=300)
    statement: str = Field(min_length=1, max_length=100000)
    assumptions: str = Field(max_length=100000)
    proof: str = Field(min_length=1, max_length=500000)
    sources: tuple[Source, ...] = ()
    dependencies: tuple[FactRef, ...] = ()
    artifacts: tuple[Artifact, ...] = ()
    revises: FactRef | None = None

    @field_validator("title", "statement", "proof")
    @classmethod
    def nonblank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("blank mathematical content")
        return value

    @model_validator(mode="after")
    def unique_dependencies(self):
        refs = [(r.fact_id, r.version) for r in self.dependencies]
        if len(set(refs)) != len(refs):
            raise ValueError("duplicate dependency")
        if self.revises and any(r.fact_id == self.revises.fact_id for r in self.dependencies):
            raise ValueError("revision must not depend on its own fact lineage")
        names = [artifact.name.casefold() for artifact in self.artifacts]
        if len(set(names)) != len(names):
            raise ValueError("duplicate artifact name")
        return self

    def canonical(self) -> str:
        body = self.model_dump(mode="json")
        # Preserve every pre-artifact candidate digest.
        if not self.artifacts:
            body.pop("artifacts", None)
        return json.dumps(body, sort_keys=True,
                          ensure_ascii=False, separators=(",", ":"))

    def digest(self) -> str:
        return hashlib.sha256(self.canonical().encode("utf-8")).hexdigest()


class Finding(StrictModel):
    location: str = Field(min_length=1, max_length=1000)
    issue: str = Field(min_length=1, max_length=10000)


class Review(StrictModel):
    candidate_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    rule_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    verdict: Literal["PASS", "REJECT", "INCONCLUSIVE"]
    summary: str = Field(min_length=1, max_length=10000)
    errors: tuple[Finding, ...] = ()
    gaps: tuple[Finding, ...] = ()
    references_checked: tuple[str, ...] = ()
    report_markdown: str = Field(min_length=1, max_length=200000)
    repair_hints: str = Field(max_length=20000)

    @model_validator(mode="after")
    def coherent_verdict(self):
        if self.verdict == "PASS" and (self.errors or self.gaps):
            raise ValueError("PASS contradicts errors or gaps")
        if self.verdict != "PASS" and not self.repair_hints.strip():
            raise ValueError("non-PASS requires explanation or repair hints")
        if not self.summary.strip() or not self.report_markdown.strip():
            raise ValueError("review must contain readable explanation")
        return self
