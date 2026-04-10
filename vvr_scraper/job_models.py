import json
from typing import Annotated, Literal

from pydantic import BaseModel, Field, RootModel


class ScrapePayload(BaseModel):
    slug: str
    chapters: list[int] | None = None
    from_chapter: int | None = None
    to_chapter: int | None = None
    grouping: int | None = None
    skip_illustrations: bool = False
    output_folder: str | None = None
    formats: list[str] = Field(default_factory=lambda: ["epub", "pdf", "cinema"])


class RenderPayload(BaseModel):
    manifest_path: str
    output_path: str
    fps: int = 30
    render_format: str = "landscape"
    vfx_scale: int = 100


class ServerPayload(BaseModel):
    host: str = "0.0.0.0"  # noqa: S104  — intentional bind to all interfaces for server
    port: int = 8000
    opds_password: str | None = None


class BaseJob(BaseModel):
    alias_id: str | None = None
    batch_id: str | None = None
    depends_on: list[str] | None = None
    priority: int = 0


class ScrapeJob(BaseJob):
    task: Literal["crawl"] = "crawl"
    payload: ScrapePayload


class RenderJob(BaseJob):
    task: Literal["render"] = "render"
    payload: RenderPayload


class ServerJob(BaseJob):
    task: Literal["server"] = "server"
    payload: ServerPayload


JobType = Annotated[ScrapeJob | RenderJob | ServerJob, Field(discriminator="task")]


class JobManifest(RootModel):
    root: JobType | list[JobType]

    @property
    def jobs(self) -> list[JobType]:
        if isinstance(self.root, list):
            return self.root
        return [self.root]

    @property
    def task(self):
        return self.jobs[0].task

    @property
    def payload(self):
        return self.jobs[0].payload

    @property
    def priority(self) -> int:
        return self.jobs[0].priority

    def model_dump_json(self, **kwargs):
        if isinstance(self.root, list):
            return json.dumps([j.model_dump(**kwargs) for j in self.root])
        return self.root.model_dump_json(**kwargs)
