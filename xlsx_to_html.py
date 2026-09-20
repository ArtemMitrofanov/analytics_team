import pandas as pd
import html
import json

def escape_html(text):
    return html.escape(str(text))

def df_to_html_table(df, sheet_name):
    if df.empty:
        return '<div class="empty-state"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"></path></svg><p>Нет данных</p></div>'
    
    cols = [escape_html(c) for c in df.columns]
    thead = '<thead><tr>' + ''.join(f'<th>{c}</th>' for c in cols) + '</tr></thead>'
    
    rows = []
    for idx, row in df.iterrows():
        cells = ''.join(f'<td>{escape_html(v)}</td>' for v in row)
        rows.append(f'<tr data-row-index="{idx}">{cells}</tr>')
    
    tbody = '<tbody>' + ''.join(rows) + '</tbody>'
    
    return f'''<div class="table-container" data-sheet="{escape_html(sheet_name)}">
        <div class="table-wrapper"><table>{thead}{tbody}</table></div>
        <div class="table-footer">
            <span class="row-count">Строк: <strong>{len(df)}</strong></span>
        </div>
    </div>'''

def generate_html(sheets_data):
    tab_buttons = []
    tab_panels = []
    
    for i, (sheet_name, df) in enumerate(sheets_data.items()):
        safe_id = sheet_name.replace(' ', '_').replace('(', '').replace(')', '').replace(',', '').replace('-', '_')
        active = ' active' if i == 0 else ''
        
        tab_buttons.append(
            f'<button class="tab-button{active}" data-tab="{safe_id}" role="tab" aria-selected="{i == 0}">{escape_html(sheet_name)}</button>'
        )
        
        table_html = df_to_html_table(df, sheet_name)
        tab_panels.append(
            f'<div class="tab-panel{active}" id="{safe_id}" role="tabpanel" aria-hidden="{i != 0}">{table_html}</div>'
        )
    
    searchable_columns = {}
    for sheet_name, df in sheets_data.items():
        cols = []
        for idx, col in enumerate(df.columns):
            col_lower = col.lower()
            if any(kw in col_lower for kw in ['issue', 'задач', 'id', 'key', 'номер', 'task']):
                cols.append(idx)
        if cols:
            searchable_columns[sheet_name] = cols
    
    total_rows = sum(len(df) for df in sheets_data.values())
    num_sheets = len(sheets_data)
    searchable_json = json.dumps(searchable_columns)
    
    # Write template to a temp file and read it back to avoid f-string issues
    # Actually, let's use string.Template with safe_substitute
    from string import Template
    
    # Read the HTML template from a separate string (using triple quotes with different delimiter)
    template_str = r"""<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YT Задачи по статусам тестирования</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg: #f8fafc;
            --bg-elevated: #ffffff;
            --border: #e2e8f0;
            --border-strong: #cbd5e1;
            --text: #0f172a;
            --text-muted: #64748b;
            --text-subtle: #94a3b8;
            --primary: #2563eb;
            --primary-hover: #1d4ed8;
            --primary-light: #eff6ff;
            --accent: #0ea5e9;
            --success: #10b981;
            --warning: #f59e0b;
            --danger: #ef4444;
            --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.05);
            --shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.04);
            --shadow-lg: 0 10px 15px -3px rgba(15, 23, 42, 0.07), 0 4px 6px -4px rgba(15, 23, 42, 0.03);
            --radius: 12px;
            --radius-sm: 8px;
            --transition: 150ms cubic-bezier(0.4, 0, 0.2, 1);
        }
        
        @media (prefers-color-scheme: dark) {
            :root {
                --bg: #0f172a;
                --bg-elevated: #1e293b;
                --border: #334155;
                --border-strong: #475569;
                --text: #f1f5f9;
                --text-muted: #94a3b8;
                --text-subtle: #64748b;
                --primary: #3b82f6;
                --primary-hover: #60a5fa;
                --primary-light: #1e3a5f;
                --shadow-sm: 0 1px 2px rgba(0, 0, 0, 0.3);
                --shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.4), 0 2px 4px -2px rgba(0, 0, 0, 0.3);
                --shadow-lg: 0 10px 15px -3px rgba(0, 0, 0, 0.4), 0 4px 6px -4px rgba(0, 0, 0, 0.2);
            }
        }
        
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html { font-size: 14px; }
        
        body {
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            line-height: 1.6;
            color: var(--text);
            background: var(--bg);
            min-height: 100vh;
            -webkit-font-smoothing: antialiased;
            -moz-osx-font-smoothing: grayscale;
        }
        
        .container { max-width: 1500px; margin: 0 auto; padding: 32px 20px; }
        .page-header { margin-bottom: 32px; }
        .header-top { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; margin-bottom: 16px; }
        .header-left h1 { font-size: 1.75rem; font-weight: 700; color: var(--text); letter-spacing: -0.02em; }
        .header-left .subtitle { color: var(--text-muted); margin-top: 4px; font-size: 0.95rem; font-weight: 400; }
        .header-stats { display: flex; gap: 16px; flex-wrap: wrap; }
        .stat-badge { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 8px 16px; font-size: 0.8125rem; font-weight: 500; color: var(--text-muted); display: flex; align-items: center; gap: 6px; }
        .stat-badge strong { color: var(--text); font-weight: 600; }
        .search-bar { margin-bottom: 24px; }
        .search-wrapper { position: relative; max-width: 520px; }
        .search-input { width: 100%; padding: 12px 16px 12px 48px; font-size: 0.9375rem; font-family: inherit; color: var(--text); background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius); transition: all var(--transition); box-shadow: var(--shadow-sm); }
        .search-input:focus { outline: none; border-color: var(--primary); box-shadow: 0 0 0 3px var(--primary-light), var(--shadow); }
        .search-input::placeholder { color: var(--text-subtle); }
        .search-icon { position: absolute; left: 16px; top: 50%; transform: translateY(-50%); width: 20px; height: 20px; color: var(--text-subtle); pointer-events: none; transition: color var(--transition); }
        .search-input:focus + .search-icon { color: var(--primary); }
        .search-clear { position: absolute; right: 12px; top: 50%; transform: translateY(-50%); width: 28px; height: 28px; border: none; background: transparent; color: var(--text-subtle); cursor: pointer; border-radius: var(--radius-sm); display: flex; align-items: center; justify-content: center; opacity: 0; visibility: hidden; transition: all var(--transition); }
        .search-clear.visible { opacity: 1; visibility: visible; }
        .search-clear:hover { background: var(--border); color: var(--text); }
        .search-hint { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 0.75rem; color: var(--text-subtle); }
        .kbd { display: inline-flex; align-items: center; justify-content: center; min-width: 24px; height: 24px; padding: 0 8px; font-family: inherit; font-size: 0.7rem; font-weight: 500; color: var(--text-muted); background: var(--bg); border: 1px solid var(--border); border-radius: 6px; box-shadow: var(--shadow-sm); }
        .tabs { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius); box-shadow: var(--shadow); overflow: hidden; }
        .tab-list { display: flex; background: linear-gradient(180deg, var(--bg) 0%, var(--bg-elevated) 100%); border-bottom: 1px solid var(--border); overflow-x: auto; flex-wrap: nowrap; padding: 4px; }
        .tab-button { padding: 12px 20px; border: none; background: transparent; cursor: pointer; font-size: 0.875rem; font-weight: 500; font-family: inherit; color: var(--text-muted); white-space: nowrap; transition: all var(--transition); border-radius: var(--radius-sm); position: relative; }
        .tab-button::before { content: ''; position: absolute; bottom: 0; left: 50%; width: 0; height: 2px; background: var(--primary); transition: all var(--transition); transform: translateX(-50%); }
        .tab-button:hover { color: var(--text); background: var(--bg); }
        .tab-button.active { color: var(--primary); background: var(--bg-elevated); box-shadow: var(--shadow-sm); }
        .tab-button.active::before { width: calc(100% - 16px); }
        .tab-panel { display: none; padding: 24px; animation: fadeIn 0.2s ease; }
        .tab-panel.active { display: block; }
        @keyframes fadeIn { from { opacity: 0; transform: translateY(4px); } to { opacity: 1; transform: translateY(0); } }
        .table-container { background: var(--bg-elevated); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow-sm); }
        .table-wrapper { overflow-x: auto; width: 100%; }
        table { width: 100%; border-collapse: collapse; font-size: 0.875rem; min-width: 700px; }
        th { background: var(--bg); color: var(--text-muted); font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; text-align: left; padding: 14px 16px; border-bottom: 1px solid var(--border); white-space: nowrap; position: sticky; top: 0; z-index: 1; }
        td { padding: 12px 16px; border-bottom: 1px solid var(--border); color: var(--text); font-size: 0.875rem; transition: background var(--transition); }
        tbody tr { transition: background var(--transition); }
        tbody tr:hover { background: var(--primary-light); }
        tbody tr:nth-child(even) { background: rgba(15, 23, 42, 0.02); }
        @media (prefers-color-scheme: dark) { tbody tr:nth-child(even) { background: rgba(255, 255, 255, 0.02); } tbody tr:hover { background: rgba(59, 130, 246, 0.15); } }
        tbody tr.highlight { background: #fef3c7 !important; box-shadow: inset 3px 0 0 var(--warning); }
        @media (prefers-color-scheme: dark) { tbody tr.highlight { background: rgba(245, 158, 11, 0.2) !important; } }
        .table-footer { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; border-top: 1px solid var(--border); background: var(--bg); font-size: 0.8125rem; color: var(--text-muted); }
        .row-count strong { color: var(--text); }
        .match-count { color: var(--primary); font-weight: 500; }
        .empty-state { display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 64px 24px; color: var(--text-subtle); text-align: center; }
        .empty-state svg { width: 48px; height: 48px; margin-bottom: 16px; opacity: 0.5; }
        .empty-state p { font-size: 0.9375rem; font-weight: 500; }
        .highlight-match { background: #fef08a; padding: 1px 3px; border-radius: 3px; font-weight: 500; }
        @media (prefers-color-scheme: dark) { .highlight-match { background: rgba(250, 204, 21, 0.3); } }
        @media (max-width: 768px) { .container { padding: 20px 16px; } .header-top { flex-direction: column; align-items: flex-start; } .header-stats { width: 100%; justify-content: space-between; } .stat-badge { flex: 1; justify-content: center; min-width: 0; } .tab-button { padding: 10px 16px; font-size: 0.8125rem; } .tab-panel { padding: 16px; } th, td { padding: 10px 12px; font-size: 0.8125rem; } .search-input { padding: 14px 16px 14px 48px; font-size: 1rem; } }
        @media (max-width: 480px) { .header-stats { flex-direction: column; gap: 8px; } h1 { font-size: 1.5rem; } }
        .tab-button:focus-visible, .search-input:focus-visible, .search-clear:focus-visible { outline: 2px solid var(--primary); outline-offset: 2px; }
        @media (prefers-reduced-motion: reduce) { * { transition: none !important; animation: none !important; } }
    </style>
</head>
<body>
    <div class="container">
        <header class="page-header">
            <div class="header-top">
                <div class="header-left">
                    <h1>YT. Задачи по статусам тестирования</h1>
                    <p class="subtitle">Данные экспортированы из Excel — $num_sheets листов</p>
                </div>
                <div class="header-stats" id="globalStats">
                    <span class="stat-badge">Всего строк: <strong id="totalRows">$total_rows</strong></span>
                    <span class="stat-badge">Листов: <strong>$num_sheets</strong></span>
                </div>
            </div>
            <div class="search-bar">
                <div class="search-wrapper">
                    <input type="search" class="search-input" id="globalSearch" placeholder="Поиск по задачам (IssueId, Задача)..." aria-label="Поиск по задачам" autocomplete="off" spellcheck="false">
                    <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="8"></circle><path d="M21 21l-4.35-4.35"></path></svg>
                    <button class="search-clear" id="searchClear" aria-label="Очистить поиск" type="button"><svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg></button>
                </div>
                <div class="search-hint"><kbd>⌘</kbd><kbd>K</kbd> фокус поиска · <kbd>Esc</kbd> очистить · ввод фильтрует все таблицы</div>
            </div>
        </header>
        <div class="tabs">
            <div class="tab-list" role="tablist">$tab_buttons</div>
            $tab_panels
        </div>
    </div>
    <script>
        (function() {
            const searchableColumns = $searchable_json;
            let searchQuery = '';
            let activeTabId = null;
            const searchInput = document.getElementById('globalSearch');
            const searchClear = document.getElementById('searchClear');
            const tabButtons = document.querySelectorAll('.tab-button');
            const tabPanels = document.querySelectorAll('.tab-panel');
            const tables = document.querySelectorAll('.table-container table');
            document.addEventListener('DOMContentLoaded', init);
            function init() { setupTabs(); setupSearch(); setupKeyboardShortcuts(); updateActiveTab(); }
            function setupTabs() { tabButtons.forEach(btn => { btn.addEventListener('click', () => { const tabId = btn.dataset.tab; switchTab(tabId); }); }); }
            function switchTab(tabId) { tabButtons.forEach(b => { b.classList.toggle('active', b.dataset.tab === tabId); b.setAttribute('aria-selected', b.dataset.tab === tabId); }); tabPanels.forEach(p => { p.classList.toggle('active', p.id === tabId); p.setAttribute('aria-hidden', p.id !== tabId); }); activeTabId = tabId; applySearchToActiveTable(); }
            function updateActiveTab() { const activeBtn = document.querySelector('.tab-button.active'); if (activeBtn) activeTabId = activeBtn.dataset.tab; }
            function setupSearch() { let debounceTimer = null; searchInput.addEventListener('input', (e) => { clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { searchQuery = e.target.value.trim().toLowerCase(); updateClearButton(); applySearchToAllTables(); }, 100); }); searchClear.addEventListener('click', () => { searchInput.value = ''; searchQuery = ''; updateClearButton(); applySearchToAllTables(); searchInput.focus(); }); searchInput.addEventListener('focus', () => { searchInput.parentElement.classList.add('focused'); }); searchInput.addEventListener('blur', () => { searchInput.parentElement.classList.remove('focused'); }); }
            function updateClearButton() { searchClear.classList.toggle('visible', searchQuery.length > 0); }
            function applySearchToAllTables() { tables.forEach(table => applySearchToTable(table)); }
            function applySearchToActiveTable() { const activePanel = document.querySelector('.tab-panel.active'); if (activePanel) { const table = activePanel.querySelector('table'); if (table) applySearchToTable(table); } }
            function applySearchToTable(table) { const container = table.closest('.table-container'); if (!container) return; const sheetName = container.dataset.sheet; const searchableCols = searchableColumns[sheetName] || []; const rows = table.querySelectorAll('tbody tr'); let visibleCount = 0; let totalCount = rows.length; rows.forEach(row => { let shouldShow = true; if (searchQuery) { shouldShow = false; const cells = row.querySelectorAll('td'); const colsToCheck = searchableCols.length > 0 ? searchableCols : Array.from(cells.keys()); for (const colIdx of colsToCheck) { const cell = cells[colIdx]; if (cell) { const text = cell.textContent.toLowerCase(); if (text.includes(searchQuery)) { shouldShow = true; break; } } } } row.style.display = shouldShow ? '' : 'none'; row.classList.toggle('highlight', shouldShow && searchQuery); if (shouldShow) visibleCount++; if (shouldShow && searchQuery) { highlightMatches(row, searchQuery, colsToCheck); } else { removeHighlights(row); } }); updateFooter(container, visibleCount, totalCount); }
            function highlightMatches(row, query, colsToCheck) { const cells = row.querySelectorAll('td'); const escapeMap = { '&': '&', '<': '<', '>': '>', '"': '"', "'": ''' }; const escapeHtml = (s) => s.replace(/[&<>"']/g, m => escapeMap[m]); const queryEscaped = query.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); const regex = new RegExp('(' + queryEscaped + ')', 'gi'); colsToCheck.forEach(colIdx => { const cell = cells[colIdx]; if (!cell) return; const originalText = cell.textContent; const lowerText = originalText.toLowerCase(); if (lowerText.includes(query.toLowerCase())) { const escaped = escapeHtml(originalText); const highlighted = escaped.replace(regex, '<mark class="highlight-match">$1</mark>'); cell.innerHTML = highlighted; } }); }
            function removeHighlights(row) { row.querySelectorAll('td').forEach(cell => { if (cell.querySelector('.highlight-match')) { cell.textContent = cell.textContent; } }); }
            function updateFooter(container, visible, total) { let footer = container.querySelector('.table-footer'); if (!footer) return; let matchEl = footer.querySelector('.match-count'); if (searchQuery) { if (!matchEl) { matchEl = document.createElement('span'); matchEl.className = 'match-count'; footer.appendChild(matchEl); } matchEl.textContent = ' (найдено: ' + visible + ' из ' + total + ')'; } else if (matchEl) { matchEl.remove(); } }
            function setupKeyboardShortcuts() { document.addEventListener('keydown', (e) => { if ((e.metaKey || e.ctrlKey) && e.key === 'k') { e.preventDefault(); searchInput.focus(); searchInput.select(); } if (e.key === 'Escape' && searchQuery) { searchInput.value = ''; searchQuery = ''; updateClearButton(); applySearchToAllTables(); searchInput.blur(); } if (e.key >= '1' && e.key <= '9' && !e.metaKey && !e.ctrlKey && !e.altKey) { const index = parseInt(e.key) - 1; if (tabButtons[index] && document.activeElement !== searchInput) { e.preventDefault(); switchTab(tabButtons[index].dataset.tab); tabButtons[index].focus(); } } }); }
        })();
    </script>
</body>
</html>"""
    
    template = Template(template_str)
    return template.safe_substitute(
        num_sheets=num_sheets,
        total_rows=total_rows,
        tab_buttons=''.join(tab_buttons),
        tab_panels=''.join(tab_panels),
        searchable_json=searchable_json
    )

def main():
    input_file = 'YT._Задачи_по_статусам_тестирования_(без_привязки_к_Юзеру)_2026_08_26.xlsx'
    output_file = 'index.html'
    
    print(f'Чтение файла: {input_file}')
    xls = pd.ExcelFile(input_file)
    
    sheets_data = {}
    for sheet_name in xls.sheet_names:
        print(f'  Обработка листа: {sheet_name}')
        df = pd.read_excel(xls, sheet_name=sheet_name)
        sheets_data[sheet_name] = df
    
    html_output = generate_html(sheets_data)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(html_output)
    
    print(f'Готово! Результат сохранен в {output_file}')

if __name__ == '__main__':
    main()