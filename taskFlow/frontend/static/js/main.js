class TaskFlowDashboard {
    constructor() {
        this.rawData = null;
        this.filteredData = null;
        this.charts = {};
        this.init();
    }

    init() {
        if (typeof window.rawData !== 'undefined' && window.rawData) {
            this.rawData = window.rawData;
            this.filteredData = { ...window.rawData };
            this.populateFilters();
            this.renderAll();
        }
    }

    populateFilters() {
        if (!this.filteredData?.distributions) return;

        const { by_author, by_sprint, by_type, by_priority } = this.filteredData.distributions;

        this.fillSelect('filter-author', Object.keys(by_author || {}).sort());
        this.fillSelect('filter-sprint', Object.keys(by_sprint || {}).sort());
        this.fillSelect('filter-type', Object.keys(by_type || {}).sort());
        this.fillSelect('filter-priority', Object.keys(by_priority || {}).sort());
    }

    fillSelect(id, values) {
        const select = document.getElementById(id);
        if (!select) return;

        const currentValue = select.value;
        select.innerHTML = '<option value="">All</option>';

        values.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v;
            opt.textContent = v;
            select.appendChild(opt);
        });

        if (currentValue && values.includes(currentValue)) {
            select.value = currentValue;
        }
    }

    applyFilters() {
        const author = document.getElementById('filter-author')?.value;
        const sprint = document.getElementById('filter-sprint')?.value;
        const type = document.getElementById('filter-type')?.value;
        const priority = document.getElementById('filter-priority')?.value;

        console.log('Filters applied:', { author, sprint, type, priority });
    }

    renderAll() {
        this.renderKPIs();
        this.renderCharts();
    }

    renderKPIs() {
        const d = this.filteredData?.summary || {};
        const container = document.getElementById('kpi');
        if (!container) return;

        container.innerHTML = `
            <div class="col-md-3"><div class="kpi-card"><div class="kpi-value">${d.total_issues || 0}</div><div class="kpi-label">Total Issues</div></div></div>
            <div class="col-md-3"><div class="kpi-card"><div class="kpi-value">${(d.avg_lead_time_days || 0).toFixed(1)}д</div><div class="kpi-label">Avg Lead Time</div></div></div>
            <div class="col-md-3"><div class="kpi-card"><div class="kpi-value">${(d.avg_cycle_time_days || 0).toFixed(1)}д</div><div class="kpi-label">Avg Cycle Time</div></div></div>
            <div class="col-md-3"><div class="kpi-card"><div class="kpi-value">${Object.values(d.status_distribution || {}).reduce((a,b)=>a+b,0)}</div><div class="kpi-label">Total Transitions</div></div></div>
        `;
    }

    renderCharts() {
        this.renderSankey();
        this.renderStageTimes();
        this.renderLeadCycle();
        this.renderDistributions();
        this.renderWorklog();
        this.renderTrends();
    }

    renderSankey() {
        const d = this.filteredData?.flow_data;
        if (!d?.nodes || !d?.links) return;

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

        Plotly.newPlot('chart-sankey', [trace], {
            title: 'Flow of Tasks Between Statuses',
            font: {size: 12},
            margin: {t: 40, l: 20, r: 20, b: 20}
        });
    }

    renderStageTimes() {
        const d = this.filteredData?.stage_times;
        if (!d) return;

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
            xaxis: {title: 'Stage'},
            margin: {t: 40, l: 50, r: 20, b: 50}
        });
    }

    renderLeadCycle() {
        const d = this.filteredData?.summary;
        if (!d) return;

        const trace = {
            type: 'bar',
            x: ['Lead Time', 'Cycle Time'],
            y: [d.avg_lead_time_hours || 0, d.avg_cycle_time_hours || 0],
            text: [`${(d.avg_lead_time_hours || 0).toFixed(1)}h`, `${(d.avg_cycle_time_hours || 0).toFixed(1)}h`],
            textposition: 'auto',
            marker: {color: ['#0d6efd', '#198754']}
        };

        Plotly.newPlot('chart-lead-cycle', [trace], {
            title: 'Lead Time vs Cycle Time (Hours)',
            yaxis: {title: 'Hours'},
            margin: {t: 40, l: 50, r: 20, b: 50}
        });
    }

    renderDistributions() {
        const d = this.filteredData?.distributions;
        if (!d) return;

        if (d.by_author) {
            Plotly.newPlot('chart-by-author', [{
                type: 'pie',
                labels: Object.keys(d.by_author),
                values: Object.values(d.by_author),
                textinfo: 'label+percent'
            }], {
                title: 'Tasks by Author',
                margin: {t: 40, l: 20, r: 20, b: 20}
            });
        }

        if (d.by_status) {
            Plotly.newPlot('chart-by-status', [{
                type: 'pie',
                labels: Object.keys(d.by_status),
                values: Object.values(d.by_status),
                textinfo: 'label+percent'
            }], {
                title: 'Tasks by Status',
                margin: {t: 40, l: 20, r: 20, b: 20}
            });
        }
    }

    renderWorklog() {
        const w = this.filteredData?.worklog;
        if (!w) return;

        if (w.by_month) {
            const months = Object.keys(w.by_month).sort();
            const hours = months.map(m => w.by_month[m].hours);
            const issues = months.map(m => w.by_month[m].issues);

            const trace1 = {type: 'bar', x: months, y: hours, name: 'Hours', yaxis: 'y'};
            const trace2 = {type: 'scatter', x: months, y: issues, name: 'Issues', yaxis: 'y2', mode: 'lines+markers'};

            Plotly.newPlot('chart-worklog-month', [trace1, trace2], {
                title: 'Worklog by Month',
                yaxis: {title: 'Hours'},
                yaxis2: {title: 'Issues', overlaying: 'y', side: 'right'},
                margin: {t: 40, l: 50, r: 50, b: 50}
            });
        }

        if (w.by_type) {
            Plotly.newPlot('chart-worklog-type', [{
                type: 'pie',
                labels: Object.keys(w.by_type),
                values: Object.values(w.by_type),
                textinfo: 'label+percent'
            }], {
                title: 'Worklog by Type',
                margin: {t: 40, l: 20, r: 20, b: 20}
            });
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
                yaxis2: {title: 'Issues', overlaying: 'y', side: 'right'},
                margin: {t: 40, l: 50, r: 50, b: 50}
            });
        }
    }

    renderTrends() {
        const t = this.filteredData?.trends;
        if (!t?.by_month || t.by_month.length === 0) return;

        const months = t.by_month.map(p => p.period);
        const leadTimes = t.by_month.map(p => (p.avg_lead_time || 0) / 8);
        const cycleTimes = t.by_month.map(p => (p.avg_cycle_time || 0) / 8);

        const trace1 = {type: 'scatter', x: months, y: leadTimes, name: 'Lead Time (days)', mode: 'lines+markers'};
        const trace2 = {type: 'scatter', x: months, y: cycleTimes, name: 'Cycle Time (days)', mode: 'lines+markers'};

        Plotly.newPlot('chart-trends', [trace1, trace2], {
            title: 'Lead Time & Cycle Time Trends',
            yaxis: {title: 'Days'},
            margin: {t: 40, l: 50, r: 20, b: 50}
        });
    }

    exportData() {
        if (!this.filteredData) return;
        const blob = new Blob([JSON.stringify(this.filteredData, null, 2)], {type: 'application/json'});
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = 'taskflow-data.json';
        a.click();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    window.dashboard = new TaskFlowDashboard();
});