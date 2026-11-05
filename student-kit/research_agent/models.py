from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Decision(StrictModel):
    say: str
    feeling: str
    intent: str
    status: Literal["continue", "finished", "gave_up"]
    evidence: list[str]
    uncertainty: list[str]
    product_selected: bool


class Action(StrictModel):
    kind: Literal["click", "type", "select", "scroll", "back", "wait", "none"]
    element_id: int | None
    text: str
    direction: Literal["up", "down", "none"]


class Limits(StrictModel):
    max_steps: int = Field(ge=1, le=12)
    site_seconds: int = Field(ge=1, le=600)
    max_failures: int = Field(ge=1, le=3)
    max_api_calls: int = Field(ge=1, le=300)
    max_total_tokens: int = Field(ge=1, le=600000)
    api_timeout_seconds: int = Field(ge=1, le=30)
    api_retries: int = Field(ge=0, le=2)


class Site(StrictModel):
    id: str
    name: str
    start_url: str
    allowed_hosts: list[str]
    local_path: str
    # Narrow, signed-off exceptions: product pages whose address contains the word "buy".
    allowed_paths: list[str] = []
    # Static files (CSS, JS, images, fonts) a product page needs, whose path contains "buy".
    allowed_asset_paths: list[str] = []
    # Signed-off read-only searches that the site sends as a POST: "host /exact/path-pattern".
    # Only XHR/fetch calls to that host and path may use POST; everything else stays read-only.
    allowed_read_posts: list[str] = []


class Task(StrictModel):
    id: str
    goal: str


class Track(StrictModel):
    id: str
    title: str
    persona: str
    model: str
    model_validation: str
    sites: list[Site]
    default_sites: list[str] = []
    tasks: list[Task]
    limits: Limits


class Answers(StrictModel):
    discovery: Literal["yes", "partly", "no"]
    discovery_detail: str
    product_page_confidence: Literal[1, 2, 3, 4, 5]
    product_page_missing: str
    price_transparency: Literal["yes", "partly", "no"]
    price_transparency_missing: str
    purchase_intent: Literal[1, 2, 3, 4, 5]
    change_my_mind: str
    team_answer: str


class Issue(StrictModel):
    title: str
    site: str
    task: str
    step_ids: list[str]
    screenshot: str
    what_happened: str
    why_it_matters: str
    label: Literal["site_friction", "information_unavailable"]


class AgentError(StrictModel):
    title: str
    step_ids: list[str]
    what_happened: str


class Analysis(StrictModel):
    customer_and_question: str
    weakest_dell_stage: Literal["Discovery", "Product page", "Price transparency", "Purchase intent", "Unclear"]
    website_issues: list[Issue]
    competitor_comparison: str
    agent_errors: list[AgentError]
    recommendation_for_dell: str
    how_to_validate: str
    limitation: str
