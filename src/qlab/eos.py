from pydantic import BaseModel


class EosCue(BaseModel):
    """Eos lighting cue model."""

    number: float
    label: str | None = None


class EosCueList(BaseModel):
    cues: list[EosCue] = []
