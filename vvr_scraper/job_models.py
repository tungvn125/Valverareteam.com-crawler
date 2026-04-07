from typing import List, Optional, Union, Literal, Annotated
from pydantic import BaseModel, Field

class ScrapePayload(BaseModel):
    slug: str
    chapters: Optional[List[int]] = None
    formats: List[str] = Field(default_factory=lambda: ["epub", "pdf", "cinema"])

class ServerPayload(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    opds_password: Optional[str] = None

class ScrapeJob(BaseModel):
    task: Literal["scrape"] = "scrape"
    payload: ScrapePayload

class ServerJob(BaseModel):
    task: Literal["server"] = "server"
    payload: ServerPayload

JobManifest = Annotated[Union[ScrapeJob, ServerJob], Field(discriminator="task")]
