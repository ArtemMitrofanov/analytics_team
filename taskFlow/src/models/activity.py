from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class StatusTransition(BaseModel):
    issue_id: str
    from_status: str
    to_status: str
    from_date: datetime
    to_date: datetime
    duration_hours: float
    duration_days: float
    author: Optional[str] = None


class WorkItem(BaseModel):
    issue_id: str
    author: str
    author_full_name: Optional[str] = None
    work_type: str
    duration_minutes: int
    duration_hours: float
    date: datetime
    text: Optional[str] = None
    timestamp: datetime


class IssueTimeline(BaseModel):
    issue_id: str
    transitions: List[StatusTransition] = []
    work_items: List[WorkItem] = []
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    first_dev_at: Optional[datetime] = None

    @property
    def total_time_hours(self) -> float:
        return sum(t.duration_hours for t in self.transitions)

    def get_stage_time(self, stage: str) -> float:
        stage_statuses = {
            "analytics": {
                "К аналитике",
                "В аналитике",
                "К ревью (аналитика)",
                "Ревью аналитика",
            },
            "development": {"К разработке", "В разработке", "К ревью", "Код ревью"},
            "testing": {"К тестированию", "В тестировании", "Протестировано"},
        }
        statuses = stage_statuses.get(stage, set())
        return sum(
            t.duration_hours
            for t in self.transitions
            if t.from_status in statuses or t.to_status in statuses
        )


class AggregatedMetrics(BaseModel):
    median: float = 0
    mean: float = 0
    p90: float = 0
    p75: float = 0
    min: float = 0
    max: float = 0
    count: int = 0


class StageMetrics(BaseModel):
    analytics: AggregatedMetrics = Field(default_factory=AggregatedMetrics)
    development: AggregatedMetrics = Field(default_factory=AggregatedMetrics)
    testing: AggregatedMetrics = Field(default_factory=AggregatedMetrics)
    total: AggregatedMetrics = Field(default_factory=AggregatedMetrics)


class WorklogMetrics(BaseModel):
    by_author: Dict[str, Dict[str, Any]] = {}
    by_month: Dict[str, Dict[str, Any]] = {}
    by_quarter: Dict[str, Dict[str, Any]] = {}


class FlowData(BaseModel):
    nodes: List[Dict[str, Any]] = []
    links: List[Dict[str, Any]] = []


class DistributionData(BaseModel):
    by_status: Dict[str, int] = {}
    by_author: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_priority: Dict[str, int] = {}
    by_sprint: Dict[str, int] = {}


class SummaryData(BaseModel):
    total_issues: int = 0
    avg_lead_time_hours: float = 0
    avg_lead_time_days: float = 0
    avg_cycle_time_hours: float = 0
    avg_cycle_time_days: float = 0
    status_distribution: Dict[str, int] = {}
    by_type: Dict[str, int] = {}
    by_author: Dict[str, int] = {}
    by_sprint: Dict[str, int] = {}


class DashboardData(BaseModel):
    summary: SummaryData = Field(default_factory=SummaryData)
    stage_times: StageMetrics = Field(default_factory=StageMetrics)
    worklog: WorklogMetrics = Field(default_factory=WorklogMetrics)
    flow_data: FlowData = Field(default_factory=FlowData)
    distributions: DistributionData = Field(default_factory=DistributionData)