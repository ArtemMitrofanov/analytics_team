from typing import List, Dict, Any
import numpy as np
from pydantic import BaseModel, Field


class AggregationResult(BaseModel):
    median: float = 0
    mean: float = 0
    p90: float = 0
    p75: float = 0
    min: float = 0
    max: float = 0
    count: int = 0


class StageTimeMetrics(BaseModel):
    analytics: AggregationResult = Field(default_factory=AggregationResult)
    development: AggregationResult = Field(default_factory=AggregationResult)
    testing: AggregationResult = Field(default_factory=AggregationResult)
    total: AggregationResult = Field(default_factory=AggregationResult)


class LeadCycleMetrics(BaseModel):
    lead_time: AggregationResult = Field(default_factory=AggregationResult)
    cycle_time: AggregationResult = Field(default_factory=AggregationResult)


class WorklogByAuthor(BaseModel):
    total_hours: float = 0
    by_type: Dict[str, float] = {}
    by_month: Dict[str, float] = {}


class WorklogMetrics(BaseModel):
    by_author: Dict[str, WorklogByAuthor] = {}
    by_month: Dict[str, Dict[str, Any]] = {}
    by_quarter: Dict[str, Dict[str, Any]] = {}


class FlowNode(BaseModel):
    id: int
    name: str


class FlowLink(BaseModel):
    source: int
    target: int
    value: int


class SankeyData(BaseModel):
    nodes: List[FlowNode] = []
    links: List[FlowLink] = []


class TrendPoint(BaseModel):
    period: str
    avg_lead_time: float = 0
    avg_cycle_time: float = 0
    issues_count: int = 0


class TrendsData(BaseModel):
    by_week: List[TrendPoint] = []
    by_month: List[TrendPoint] = []


class FullMetrics(BaseModel):
    lead_cycle: LeadCycleMetrics = Field(default_factory=LeadCycleMetrics)
    stage_times: StageTimeMetrics = Field(default_factory=StageTimeMetrics)
    worklog: WorklogMetrics = Field(default_factory=WorklogMetrics)
    flow_data: SankeyData = Field(default_factory=SankeyData)
    trends: TrendsData = Field(default_factory=TrendsData)
    distributions: Dict[str, Dict[str, int]] = {}


def calculate_aggregations(values: List[float]) -> Dict:
    if not values:
        return {"median": 0, "mean": 0, "p90": 0, "p75": 0, "min": 0, "max": 0, "count": 0}

    arr = np.array(values)
    return {
        "median": float(np.median(arr)),
        "mean": float(np.mean(arr)),
        "p90": float(np.percentile(arr, 90)),
        "p75": float(np.percentile(arr, 75)),
        "min": float(np.min(arr)),
        "max": float(np.max(arr)),
        "count": len(arr),
    }


def hours_to_days(hours: float) -> float:
    return round(hours / 8, 1)


def hours_to_calendar_days(hours: float) -> float:
    return round(hours / 24, 1)