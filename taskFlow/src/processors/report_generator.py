import json
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional
import logging

from src.config import OUTPUT_DIR, TEMPLATES_DIR

logger = logging.getLogger(__name__)


def prepare_dashboard_data(
    timelines: Dict[str, Any],
    metrics: Dict,
    worklog: Dict,
    flow_nodes: list,
    flow_links: list,
    distributions: Dict,
    trends: Dict,
) -> Dict[str, Any]:
    summary = {
        "total_issues": len(timelines),
        "avg_lead_time_hours": round(metrics.get("lead_time", {}).get("mean", 0), 1),
        "avg_lead_time_days": round(metrics.get("lead_time", {}).get("mean", 0) / 8, 1),
        "avg_cycle_time_hours": round(metrics.get("cycle_time", {}).get("mean", 0), 1),
        "avg_cycle_time_days": round(metrics.get("cycle_time", {}).get("mean", 0) / 8, 1),
        "status_distribution": distributions.get("by_status", {}),
        "by_type": distributions.get("by_type", {}),
        "by_author": distributions.get("by_author", {}),
        "by_sprint": distributions.get("by_sprint", {}),
    }

    stage_times = {}
    for stage in ["analytics", "development", "testing"]:
        stage_metrics = metrics.get("stage_times", {}).get(stage, {})
        stage_times[stage] = {
            "median_hours": round(stage_metrics.get("median", 0), 1),
            "mean_hours": round(stage_metrics.get("mean", 0), 1),
            "p90_hours": round(stage_metrics.get("p90", 0), 1),
            "p75_hours": round(stage_metrics.get("p75", 0), 1),
            "median_days": round(stage_metrics.get("median", 0) / 8, 1),
            "mean_days": round(stage_metrics.get("mean", 0) / 8, 1),
            "p90_days": round(stage_metrics.get("p90", 0) / 8, 1),
            "p75_days": round(stage_metrics.get("p75", 0) / 8, 1),
        }

    total_stage = {}
    for metric in ["median", "mean", "p90", "p75"]:
        total = sum(
            metrics.get("stage_times", {}).get(s, {}).get(metric, 0)
            for s in ["analytics", "development", "testing"]
        )
        total_stage[f"{metric}_hours"] = round(total, 1)
        total_stage[f"{metric}_days"] = round(total / 8, 1)
    stage_times["total"] = total_stage

    flow_data = {
        "nodes": flow_nodes,
        "links": flow_links,
    }

    return {
        "summary": summary,
        "stage_times": stage_times,
        "worklog": worklog,
        "flow_data": flow_data,
        "distributions": distributions,
        "trends": trends,
        "generated_at": datetime.now().isoformat(),
    }


def save_json(data: Dict, filename: Optional[str] = None) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)

    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data_{timestamp}.json"

    filepath = OUTPUT_DIR / filename

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

    logger.info(f"JSON data saved to: {filepath}")
    return filepath


def load_html_template() -> str:
    return get_default_template()


def get_default_template() -> str:
    return """<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>TaskFlow Analytics Dashboard</title>
    <script src="https://cdn.plot.ly/plotly-2.20.0.min.js"></script>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: #f8f9fa; font-family: 'Segoe UI', sans-serif; }
        .kpi-card { background: white; border-radius: 10px; padding: 20px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .chart-container { background: white; border-radius: 10px; padding: 20px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .kpi-value { font-size: 2em; font-weight: bold; color: #0d6efd; }
        .kpi-label { color: #6c757d; }
        .filter-section { background: white; border-radius: 10px; padding: 20px; margin: 10px 0; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .js-plotly-plot .plotly { width: 100% !important; height: 100% !important; }
    </style>
</head>
<body>
    <div class="container-fluid py-4">
        <div class="d-flex justify-content-between align-items-center mb-4">
            <h1>📊 TaskFlow Analytics Dashboard</h1>
            <button class="btn btn-primary" onclick="exportData()">📥 Export JSON</button>
        </div>
        
        <div id="filters" class="filter-section mb-4">
            <div class="row">
                <div class="col-md-3">
                    <label class="form-label">Author</label>
                    <select id="filter-author" class="form-select" onchange="applyFilters()">
                        <option value="">All Authors</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <label class="form-label">Sprint</label>
                    <select id="filter-sprint" class="form-select" onchange="applyFilters()">
                        <option value="">All Sprints</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <label class="form-label">Issue Type</label>
                    <select id="filter-type" class="form-select" onchange="applyFilters()">
                        <option value="">All Types</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <label class="form-label">Priority</label>
                    <select id="filter-priority" class="form-select" onchange="applyFilters()">
                        <option value="">All Priorities</option>
                    </select>
                </div>
            </div>
        </div>

        <div id="kpi" class="row mb-4">
        </div>

        <div class="row">
            <div class="col-12 chart-container">
                <h4>📈 Flow Diagram (Sankey)</h4>
                <div id="chart-sankey" style="height: 500px;"></div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-6 chart-container">
                <h4>⏱ Stage Times</h4>
                <div id="chart-stage-times" style="height: 400px;"></div>
            </div>
            <div class="col-md-6 chart-container">
                <h4>📊 Lead & Cycle Time</h4>
                <div id="chart-lead-cycle" style="height: 400px;"></div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-6 chart-container">
                <h4>👥 Tasks by Author</h4>
                <div id="chart-by-author" style="height: 400px;"></div>
            </div>
            <div class="col-md-6 chart-container">
                <h4>📋 Tasks by Status</h4>
                <div id="chart-by-status" style="height: 400px;"></div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-6 chart-container">
                <h4>🔧 Worklog by Month</h4>
                <div id="chart-worklog-month" style="height: 400px;"></div>
            </div>
            <div class="col-md-6 chart-container">
                <h4>📈 Trends</h4>
                <div id="chart-trends" style="height: 400px;"></div>
            </div>
        </div>

        <div class="row">
            <div class="col-md-6 chart-container">
                <h4>📊 Worklog by Type</h4>
                <div id="chart-worklog-type" style="height: 400px;"></div>
            </div>
            <div class="col-md-6 chart-container">
                <h4>🎯 Worklog by Quarter</h4>
                <div id="chart-worklog-quarter" style="height: 400px;"></div>
            </div>
        </div>
    </div>

    <script>
        const rawData = {{DATA}};
        let filteredData = rawData;

        function initDashboard() {
            populateFilters();
            renderKPIs();
            renderCharts();
        }

        function populateFilters() {
            const authors = new Set();
            const sprints = new Set();
            const types = new Set();
            const priorities = new Set();

            Object.keys(rawData.distributions.by_author || {}).forEach(a => authors.add(a));
            Object.keys(rawData.distributions.by_sprint || {}).forEach(s => sprints.add(s));
            Object.keys(rawData.distributions.by_type || {}).forEach(t => types.add(t));
            Object.keys(rawData.distributions.by_priority || {}).forEach(p => priorities.add(p));

            fillSelect('filter-author', Array.from(authors).sort());
            fillSelect('filter-sprint', Array.from(sprints).sort());
            fillSelect('filter-type', Array.from(types).sort());
            fillSelect('filter-priority', Array.from(priorities).sort());
        }

        function fillSelect(id, values) {
            const select = document.getElementById(id);
            values.forEach(v => {
                const opt = document.createElement('option');
                opt.value = v;
                opt.textContent = v;
                select.appendChild(opt);
            });
        }

        function applyFilters() {
            const author = document.getElementById('filter-author').value;
            const sprint = document.getElementById('filter-sprint').value;
            const type = document.getElementById('filter-type').value;
            const priority = document.getElementById('filter-priority').value;

            alert('Filtering not fully implemented in standalone mode. Use the web server for interactive filtering.');
        }

        function renderKPIs() {
            const d = filteredData.summary;
            const kpiHtml = `
                <div class="col-md-3"><div class="kpi-card"><div class="kpi-value">${d.total_issues}</div><div class="kpi-label">Total Issues</div></div></div>
                <div class="col-md-3"><div class="kpi-card"><div class="kpi-value">${d.avg_lead_time_days}д</div><div class="kpi-label">Avg Lead Time</div></div></div>
                <div class="col-md-3"><div class="kpi-card"><div class="kpi-value">${d.avg_cycle_time_days}д</div><div class="kpi-label">Avg Cycle Time</div></div></div>
                <div class="col-md-3"><div class="kpi-card"><div class="kpi-value">${Object.values(d.status_distribution).reduce((a,b)=>a+b,0)}</div><div class="kpi-label">Total Transitions</div></div></div>
            `;
            document.getElementById('kpi').innerHTML = kpiHtml;
        }

        function renderCharts() {
            renderSankey();
            renderStageTimes();
            renderLeadCycle();
            renderDistributions();
            renderWorklog();
            renderTrends();
        }

        function renderSankey() {
            const d = filteredData.flow_data;
            if (!d.nodes || !d.links) return;

            const trace = {
                type: 'sankey',
                node: {
                    pad: 15,
                    thickness: 20,
                    line: {color: 'black', width: 0.5},
                    label: d.nodes.map(n => n.name),
                    color: 'rgba(13, 110, 253, 0.8)'
                },
                link: {
                    source: d.links.map(l => l.source),
                    target: d.links.map(l => l.target),
                    value: d.links.map(l => l.value)
                }
            };

            Plotly.newPlot('chart-sankey', [trace], {title: 'Flow of Tasks Between Statuses', font: {size: 12}});
        }

        function renderStageTimes() {
            const d = filteredData.stage_times;
            const stages = ['analytics', 'development', 'testing'];
            const metrics = ['median', 'mean', 'p90'];

            const traces = metrics.map(m => ({
                type: 'bar',
                name: m.charAt(0).toUpperCase() + m.slice(1),
                x: stages.map(s => s.charAt(0).toUpperCase() + s.slice(1)),
                y: stages.map(s => d[s]?.[`${m}_hours`] || 0),
                text: stages.map(s => `${(d[s]?.[`${m}_hours`] || 0).toFixed(1)}h`),
                textposition: 'auto'
            }));

            Plotly.newPlot('chart-stage-times', traces, {
                title: 'Time Spent by Stage (Hours)',
                barmode: 'group',
                yaxis: {title: 'Hours'},
                xaxis: {title: 'Stage'}
            });
        }

        function renderLeadCycle() {
            const d = filteredData.summary;
            const trace = {
                type: 'bar',
                x: ['Lead Time', 'Cycle Time'],
                y: [d.avg_lead_time_hours, d.avg_cycle_time_hours],
                text: [`${d.avg_lead_time_hours.toFixed(1)}h`, `${d.avg_cycle_time_hours.toFixed(1)}h`],
                textposition: 'auto',
                marker: {color: ['#0d6efd', '#198754']}
            };

            Plotly.newPlot('chart-lead-cycle', [trace], {
                title: 'Lead Time vs Cycle Time (Hours)',
                yaxis: {title: 'Hours'}
            });
        }

        function renderDistributions() {
            const d = filteredData.distributions;

            if (d.by_author) {
                Plotly.newPlot('chart-by-author', [{
                    type: 'pie',
                    labels: Object.keys(d.by_author),
                    values: Object.values(d.by_author),
                    textinfo: 'label+percent'
                }], {title: 'Tasks by Author'});
            }

            if (d.by_status) {
                Plotly.newPlot('chart-by-status', [{
                    type: 'pie',
                    labels: Object.keys(d.by_status),
                    values: Object.values(d.by_status),
                    textinfo: 'label+percent'
                }], {title: 'Tasks by Status'});
            }
        }

        function renderWorklog() {
            const w = filteredData.worklog;

            if (w.by_month) {
                const months = Object.keys(w.by_month).sort();
                const hours = months.map(m => w.by_month[m].hours);
                const issues = months.map(m => w.by_month[m].issues);

                const trace1 = {type: 'bar', x: months, y: hours, name: 'Hours', yaxis: 'y'};
                const trace2 = {type: 'scatter', x: months, y: issues, name: 'Issues', yaxis: 'y2', mode: 'lines+markers'};

                Plotly.newPlot('chart-worklog-month', [trace1, trace2], {
                    title: 'Worklog by Month',
                    yaxis: {title: 'Hours'},
                    yaxis2: {title: 'Issues', overlaying: 'y', side: 'right'}
                });
            }

            if (w.by_type) {
                Plotly.newPlot('chart-worklog-type', [{
                    type: 'pie',
                    labels: Object.keys(w.by_type),
                    values: Object.values(w.by_type),
                    textinfo: 'label+percent'
                }], {title: 'Worklog by Type'});
            }

            if (w.by_quarter) {
                const quarters = Object.keys(w.by_quarter).sort();
                const hours = quarters.map(q => w.by_quarter[q].hours);
                const issues = quarters.map(q => w.by_quarter[q].issues);

                const trace1 = {type: 'bar', x: quarters, y: hours, name: 'Hours', yaxis: 'y'};
                const trace2 = {type: 'scatter', x: quarters, y: issues, name: 'Issues', yaxis: 'y2', mode: 'lines+markers'};

                Plotly.newPlot('chart-worklog-quarter', [trace1, trace2], {
                    title: 'Worklog by Quarter',
                    yaxis: {title: 'Hours'},
                    yaxis2: {title: 'Issues', overlaying: 'y', side: 'right'}
                });
            }
        }

        function renderTrends() {
            const t = filteredData.trends;
            if (!t.by_month || t.by_month.length === 0) return;

            const months = t.by_month.map(p => p.period);
            const leadTimes = t.by_month.map(p => p.avg_lead_time / 8);
            const cycleTimes = t.by_month.map(p => p.avg_cycle_time / 8);

            const trace1 = {type: 'scatter', x: months, y: leadTimes, name: 'Lead Time (days)', mode: 'lines+markers'};
            const trace2 = {type: 'scatter', x: months, y: cycleTimes, name: 'Cycle Time (days)', mode: 'lines+markers'};

            Plotly.newPlot('chart-trends', [trace1, trace2], {
                title: 'Lead Time & Cycle Time Trends',
                yaxis: {title: 'Days'}
            });
        }

        function exportData() {
            const blob = new Blob([JSON.stringify(filteredData, null, 2)], {type: 'application/json'});
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'taskflow-data.json';
            a.click();
        }

        document.addEventListener('DOMContentLoaded', initDashboard);
    </script>
</body>
</html>"""


def generate_html_report(data: Dict[str, Any], output_path: Optional[Path] = None) -> Path:
    template = load_html_template()

    json_str = json.dumps(data, ensure_ascii=False, default=str)

    html_content = template.replace("{{DATA}}", json_str)

    if output_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"report_{timestamp}.html"

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    logger.info(f"HTML report saved to: {output_path}")
    return output_path


def generate_report(
    timelines: Dict[str, Any],
    metrics: Dict,
    worklog: Dict,
    flow_nodes: list,
    flow_links: list,
    distributions: Dict,
    trends: Dict,
    output_path: Optional[Path] = None,
) -> Path:
    data = prepare_dashboard_data(
        timelines, metrics, worklog, flow_nodes, flow_links, distributions, trends
    )

    save_json(data)

    return generate_html_report(data, output_path)