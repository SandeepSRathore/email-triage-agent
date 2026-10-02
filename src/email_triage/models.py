from dataclasses import dataclass, field


@dataclass(frozen=True)
class Email:
    id: str
    sender: str
    subject: str
    date: str
    body: str
    list_unsubscribe: str | None = None
    label_ids: list[str] = field(default_factory=list)
