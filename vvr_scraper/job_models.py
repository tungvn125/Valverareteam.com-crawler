from typing import List, Optional, Union, Literal, Annotated
from pydantic import BaseModel, Field, RootModel

class ScrapePayload(BaseModel):
    slug: str
    chapters: Optional[List[int]] = None
    formats: List[str] = Field(default_factory=lambda: ["epub", "pdf", "cinema"])

class RenderPayload(BaseModel):
    manifest_path: str
    output_path: str
    fps: int = 30
    render_format: str = "landscape"
    vfx_scale: int = 100

class ServerPayload(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    opds_password: Optional[str] = None

class ScrapeJob(BaseModel):
    task: Literal["crawl"] = "crawl"
    payload: ScrapePayload

class RenderJob(BaseModel):
    task: Literal["render"] = "render"
    payload: RenderPayload

class ServerJob(BaseModel):
    task: Literal["server"] = "server"
    payload: ServerPayload

class JobManifest(RootModel):
    root: Annotated[Union[ScrapeJob, RenderJob, ServerJob], Field(discriminator="task")]

    @property
    def task(self):
        return self.root.task

    @property
    def payload(self):
        return self.root.payload

    def model_dump_json(self, **kwargs):
        return self.root.model_dump_json(**kwargs)
