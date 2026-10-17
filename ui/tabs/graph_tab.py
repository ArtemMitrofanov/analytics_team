"""ui/tabs/graph_tab.py — 3D-граф взаимодействий исполнителей (только admin)."""
import json

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

from db import (
    get_all_events,
    get_graph_edges,
    get_graph_edges_agg,
    upsert_graph_edges,
    upsert_graph_edges_agg,
    clear_graph_edges,
    get_graph_fingerprint,
    get_graph_agg_fingerprint,
    get_graph_meta,
    set_graph_meta,
    is_graph_dirty,
)
from data.graph import (
    build_edges,
    aggregate_edges,
    score_edges,
    score_nodes,
    find_chains,
    default_team_config,
    STAGE_LABELS_RU,
    ROLE_LABELS_RU,
)

_GRAPH_HTML = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
  html,body{margin:0;height:100%;overflow:hidden;
    background:radial-gradient(circle at 50% 38%, #121a2b 0%, #0a0f1a 45%, #05070d 100%);
    color:#e6ebf5;font-family:'Lab Grotesque K',system-ui,sans-serif;}
  #g{width:100%;height:100%;}
  #title{position:absolute;left:16px;top:14px;font-size:13px;letter-spacing:.3px;color:#aeb8c8;}
  #legend{position:absolute;right:16px;top:14px;display:flex;gap:14px;font-size:12px;color:#c3ccda;}
  .chip{display:flex;align-items:center;gap:6px;}
  .dot{width:9px;height:9px;border-radius:50%;background:currentColor;box-shadow:0 0 8px currentColor;}
  #hint{position:absolute;left:16px;bottom:12px;font-size:12px;color:#8a94a6;}
  #labels{position:absolute;inset:0;pointer-events:none;overflow:hidden;}
  .lbl{position:absolute;transform:translate(-50%,-50%);font-size:11px;line-height:1;
       color:#dbe4f0;background:rgba(8,12,20,0.55);padding:2px 6px;border-radius:6px;
       white-space:nowrap;will-change:transform;border:1px solid rgba(120,140,180,0.18);}
  .lbl.dim{opacity:.12;}
</style>
<script src="https://unpkg.com/3d-force-graph/dist/3d-force-graph.min.js"></script>
</head>
<body>
<div id="g"></div>
<div id="labels"></div>
<div id="title">Граф взаимодействий</div>
<div id="legend">
  <div class="chip"><span class="dot" style="color:#16C79A"></span>Аналитика</div>
  <div class="chip"><span class="dot" style="color:#2E9BFF"></span>Разработка</div>
  <div class="chip"><span class="dot" style="color:#FFB224"></span>QA</div>
  <div class="chip"><span class="dot" style="color:#8A94A6"></span>Прочие / мало данных</div>
</div>
<div id="hint">Клик по вершине — её связи · клик по фону — сброс · автоповорот паузается при выборе · зум — колесо</div>
<script>
  const data = __DATA__;
  const SHOW_LABELS = __LABELS__;
  const ROLE_COLORS = {analytics:'#16C79A', dev:'#2E9BFF', qa:'#FFB224', other:'#8A94A6'};
  let selectedId = null, hoverId = null;
  let connected = new Set();

  const ends = l => [typeof l.source === 'object' ? l.source.id : l.source,
                     typeof l.target === 'object' ? l.target.id : l.target];
  const touches = l => { const [s, t] = ends(l); return selectedId && (s === selectedId || t === selectedId); };
  const baseNode = n => n.insufficient_data ? '#54607a' : (ROLE_COLORS[n.group] || '#8A94A6');

  const nodeColorFn = n => (selectedId && n.id !== selectedId && !connected.has(n.id))
    ? 'rgba(120,132,152,0.12)' : baseNode(n);
  const nodeValFn = n => (n.id === selectedId || n.id === hoverId)
    ? 14 : (n.insufficient_data ? 3 : 4 + Math.min(10, Math.abs(n.z_score || 0) * 4));
  const linkColorFn = l => (!selectedId ? l.color : (touches(l) ? l.color : 'rgba(120,132,152,0.05)'));
  const linkWidthFn = l => (!selectedId ? (l.color === '#FF4D6D' ? 2 : 1) : (touches(l) ? 2.4 : 0.3));
  const linkOpacityFn = l => (!selectedId ? 0.35 : (touches(l) ? 0.95 : 0.04));
  const linkParticlesFn = l => (selectedId && touches(l)) ? 4 : 0;
  const apply = () => Graph.nodeColor(nodeColorFn).nodeVal(nodeValFn)
    .linkColor(linkColorFn).linkWidth(linkWidthFn).linkOpacity(linkOpacityFn)
    .linkDirectionalParticles(linkParticlesFn);

  const Graph = ForceGraph3D()(document.getElementById('g'))
    .backgroundColor('#0a0f1a')
    .graphData(data)
    .nodeRelSize(4)
    .nodeResolution(16)
    .nodeLabel(n => `<b>${n.id}</b><br>${n.role} · z=${n.z_score === null ? '—' : n.z_score} · rework=${(n.rework_rate_node*100).toFixed(0)}%`)
    .nodeColor(nodeColorFn)
    .nodeVal(nodeValFn)
    .linkColor(linkColorFn)
    .linkWidth(linkWidthFn)
    .linkOpacity(linkOpacityFn)
    .linkCurvature(0.12)
    .linkResolution(6)
    .linkDirectionalArrowLength(3.5)
    .linkDirectionalArrowRelPos(1)
    .linkDirectionalParticles(linkParticlesFn)
    .linkDirectionalParticleWidth(2)
    .linkDirectionalParticleSpeed(0.004)
    .linkLabel(l => `${l.edge_type} · E=${l.E === null ? '—' : l.E} · rework=${(l.rework_rate*100).toFixed(0)}% · SLA-slip=${(l.deadline_slip_rate*100).toFixed(0)}%`)
    .onNodeHover(n => { hoverId = n ? n.id : null; document.body.style.cursor = n ? 'pointer' : 'default'; apply(); })
    .onNodeClick(n => {
      selectedId = n.id;
      connected = new Set();
      data.links.forEach(l => { const [s, t] = ends(l); if (s === selectedId) connected.add(t); if (t === selectedId) connected.add(s); });
      Graph.controls().autoRotate = false;
      apply();
    })
    .onBackgroundClick(() => { selectedId = null; connected = new Set(); apply(); });

  Graph.d3Force('charge').strength(-160);
  Graph.d3Force('link').distance(60);
  const controls = Graph.controls();
  controls.autoRotate = true; controls.autoRotateSpeed = 0.45;
  controls.enableDamping = true; controls.dampingFactor = 0.08;
  setTimeout(() => Graph.zoomToFit(800, 80), 1000);

  // Подписи имён — HTML-оверлей над canvas (без второй копии three).
  const labelLayer = document.getElementById('labels');
  const labelEls = {};
  const buildLabels = () => {
    labelLayer.innerHTML = '';
    data.nodes.forEach(n => {
      const el = document.createElement('div');
      el.className = 'lbl';
      el.textContent = n.id;
      labelLayer.appendChild(el);
      labelEls[n.id] = el;
    });
  };
  const updateLabels = () => {
    if (!SHOW_LABELS) {
      labelLayer.style.display = 'none';
    } else {
      labelLayer.style.display = 'block';
      data.nodes.forEach(n => {
        const el = labelEls[n.id];
        if (!el) return;
        if (n.x === undefined) { el.style.display = 'none'; return; }
        const c = Graph.graph2ScreenCoords(n.x, n.y, n.z);
        el.style.display = 'block';
        el.style.transform = `translate(-50%,-50%) translate(${c.x}px, ${c.y}px)`;
        el.classList.toggle('dim', !!selectedId && n.id !== selectedId && !connected.has(n.id));
      });
    }
    requestAnimationFrame(updateLabels);
  };
  buildLabels();
  requestAnimationFrame(updateLabels);
</script>
</body>
</html>
"""


def _ensure_graph():
    """Ленивая пересборка сырых рёбер по fingerprint. Возвращает (edges_df, rebuilt)."""
    raw_fp = get_graph_fingerprint()
    rebuilt = (
        get_graph_meta("raw_fingerprint") != raw_fp
        or is_graph_dirty()
        or get_graph_edges().empty
    )
    if rebuilt:
        events = get_all_events()
        edges = build_edges(events, default_team_config())
        clear_graph_edges()
        upsert_graph_edges(edges)
        set_graph_meta("raw_fingerprint", raw_fp)
        set_graph_meta("dirty", "0")
    return get_graph_edges(), rebuilt


def _ensure_agg(period_months: int, raw_rebuilt: bool):
    """Ленивая пересборка агрегата по (fingerprint, период)."""
    agg_fp = get_graph_agg_fingerprint(period_months)
    stored = get_graph_meta(f"agg_fingerprint_{period_months}")
    need = (
        raw_rebuilt
        or stored != agg_fp
        or get_graph_edges_agg(period_months).empty
    )
    if need:
        agg = aggregate_edges(get_graph_edges(), period_months)
        if not agg.empty:
            upsert_graph_edges_agg(agg)
        set_graph_meta(f"agg_fingerprint_{period_months}", agg_fp)
    return get_graph_edges_agg(period_months)


def _clean(v):
    if v is None:
        return None
    if isinstance(v, float) and (np.isnan(v) or np.isinf(v)):
        return None
    if pd.isna(v):
        return None
    return v


def _build_graph_json(scored_df: pd.DataFrame, nodes_df: pd.DataFrame) -> str:
    node_records = {}
    for _, r in nodes_df.iterrows():
        node_records[r["actor"]] = {
            "id": r["actor"],
            "role": ROLE_LABELS_RU.get(r["role"], r["role"]),
            "z_score": _clean(round(float(r["z_score"]), 3)) if pd.notna(r["z_score"]) else None,
            "rework_rate_node": round(float(r["rework_rate_node"] or 0.0), 3),
            "insufficient_data": bool(r["insufficient_data_node"]),
            "group": r["role"],
        }

    links = []
    for _, r in scored_df.iterrows():
        if r["from_actor"] not in node_records or r["to_actor"] not in node_records:
            continue
        insufficient = bool(r.get("insufficient_data", False))
        rework = float(r.get("rework_rate", 0.0) or 0.0)
        if insufficient:
            color = "#54607a"
        elif rework > 0:
            color = "#FF4D6D"
        else:
            color = "#2E9BFF"
        links.append({
            "source": r["from_actor"],
            "target": r["to_actor"],
            "edge_type": f"{r['edge_type']} ({STAGE_LABELS_RU.get(r['stage'], r['stage'])})",
            "E": _clean(round(float(r["E"]), 3)) if pd.notna(r.get("E")) else None,
            "rework_rate": round(rework, 3),
            "deadline_slip_rate": round(float(r.get("deadline_slip_rate", 0.0) or 0.0), 3),
            "color": color,
        })
    return json.dumps({"nodes": list(node_records.values()), "links": links}, ensure_ascii=False)


def _render_chains(scored_df: pd.DataFrame, edges_df: pd.DataFrame):
    st.markdown("#### 🔗 Цепочки «от постановщика до релиза»")
    actors = sorted(set(scored_df["from_actor"]).union(set(scored_df["to_actor"])))
    if not actors:
        st.info("Нет рёбер для поиска цепочек.")
        return

    c1, c2, c3 = st.columns([2, 2, 1])
    with c1:
        from_actor = st.selectbox("От (постановщик):", options=actors, key="graph_chain_from")
    with c2:
        to_actor = st.selectbox("До (релиз):", options=actors, key="graph_chain_to")
    with c3:
        top_n = st.number_input("Топ-N", 1, 20, 5, key="graph_chain_topn")

    chains = find_chains(scored_df, edges_df, from_actor, to_actor, top_n=int(top_n))
    healthy, problem = chains["healthy"], chains["problem"]

    left, right = st.columns(2)

    def _fmt(items):
        return pd.DataFrame([
            {"Цепочка": " → ".join(c["actors"]), "E (сумма)": c["total_E"], "Рёбер": c["edge_count"]}
            for c in items
        ])

    with left:
        st.markdown("##### ✅ Здоровые (максимум E)")
        if healthy:
            st.dataframe(_fmt(healthy), use_container_width=True, hide_index=True)
        else:
            st.info("Здоровые цепочки не найдены (мало данных или нет пути).")
    with right:
        st.markdown("##### ⚠️ Проблемные (минимум E)")
        if problem:
            st.dataframe(_fmt(problem), use_container_width=True, hide_index=True)
        else:
            st.info("Проблемные цепочки не найдены.")


def render_graph_tab():
    if st.session_state.get("user_role") != "admin":
        st.stop()

    st.subheader("🕸️ Граф взаимодействий исполнителей")
    st.caption("3D-граф связей по задачам и поиск цепочек «от постановщика до релиза». Доступен только администраторам.")

    with st.spinner("Проверяю актуальность графа..."):
        edges_df, raw_rebuilt = _ensure_graph()

    if edges_df.empty:
        st.info("Нет данных для построения графа. Загрузите журнал задач.")
        return

    period_months = st.slider("Период, месяцев:", 1, 24, 6, key="graph_period")
    with st.spinner("Агрегирую рёбра..."):
        agg_df = _ensure_agg(int(period_months), raw_rebuilt)

    if agg_df.empty:
        st.info("За выбранный период рёбер не найдено.")
        return

    scored = score_edges(agg_df)
    nodes = score_nodes(scored, edges_df)

    edge_types = sorted(scored["edge_type"].dropna().unique())
    role_options = sorted(set(scored["from_role"]).union(set(scored["to_role"])))

    f1, f2, f3, f4 = st.columns(4)
    with f1:
        sel_roles = st.multiselect("Роли:", role_options, default=role_options, key="graph_roles")
    with f2:
        sel_types = st.multiselect("Тип рёбер:", edge_types, default=edge_types, key="graph_types")
    with f3:
        valid_e = scored["E"].dropna()
        if not valid_e.empty:
            e_min, e_max = round(float(valid_e.min()), 2), round(float(valid_e.max()), 2)
        else:
            e_min, e_max = -1.0, 1.0
        if e_max <= e_min:
            e_max = e_min + 0.01
        e_threshold = st.slider("Порог E:", e_min, e_max, e_min, key="graph_e_thr")
    with f4:
        only_core = st.checkbox("Только core team", value=False, key="graph_core")

    lbl1, lbl2 = st.columns([1, 3])
    with lbl1:
        show_labels = st.checkbox("Подписи имён", value=True, key="graph_labels")
    with lbl2:
        st.caption("Подписи можно отключить, если вершин много и граф выглядит перегруженным.")

    view = scored.copy()
    if sel_types:
        view = view[view["edge_type"].isin(sel_types)]
    if sel_roles:
        view = view[view["from_role"].isin(sel_roles) & view["to_role"].isin(sel_roles)]
    if only_core:
        view = view[(view["from_role"] != "other") & (view["to_role"] != "other")]
    # порог E применяем только к рёбрам с посчитанным E (серые остаются для контекста)
    view = view[view["E"].isna() | (view["E"] >= e_threshold)]

    if view.empty:
        st.info("После фильтров не осталось рёбер.")
        return

    node_ids = set(view["from_actor"]).union(set(view["to_actor"]))
    nodes = nodes[nodes["actor"].isin(node_ids)]

    html = (
        _GRAPH_HTML
        .replace("__DATA__", _build_graph_json(view, nodes))
        .replace("__LABELS__", "true" if show_labels else "false")
    )
    components.html(html, height=800, scrolling=False)

    st.markdown("---")
    _render_chains(view, edges_df)
