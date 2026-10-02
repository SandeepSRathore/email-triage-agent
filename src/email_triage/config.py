"""Load and validate config.toml."""

import tomllib
from pathlib import Path

from pydantic import BaseModel, Field, field_validator


class Category(BaseModel):
    # Restricted charset so labels can be used unquoted in Gmail search queries.
    name: str = Field(pattern=r"^[A-Za-z0-9_-]+$")
    description: str


class Config(BaseModel):
    model: str = "gpt-5.4-mini"
    label_prefix: str = Field(default="Triage", pattern=r"^[A-Za-z0-9_-]+$")
    lookback_days: int = Field(default=2, ge=1)
    max_per_run: int = Field(default=50, ge=1)
    categories: list[Category] = Field(min_length=1)

    @field_validator("categories")
    @classmethod
    def _unique_names(cls, categories: list[Category]) -> list[Category]:
        names = [c.name for c in categories]
        dupes = {n for n in names if names.count(n) > 1}
        if dupes:
            raise ValueError(f"Duplicate category names: {sorted(dupes)}")
        return categories

    @property
    def category_names(self) -> list[str]:
        return [c.name for c in self.categories]

    def label_for(self, category: str) -> str:
        return f"{self.label_prefix}/{category}"

    @property
    def all_labels(self) -> list[str]:
        return [self.label_for(n) for n in self.category_names]


def load_config(path: Path) -> Config:
    with path.open("rb") as f:
        return Config.model_validate(tomllib.load(f))
