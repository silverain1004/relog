"""HTML 리포트 생성 모듈 (self-contained, CDN 없음)."""
import html
import os
from collections import Counter
from datetime import datetime


def _esc(text) -> str:
    return html.escape(str(text) if text is not None else "")


def _bar_chart(items: dict, max_items: int = 15) -> str:
    if not items:
        return '<p class="empty">데이터 없음</p>'
    sorted_items = sorted(items.items(), key=lambda x: x[1], reverse=True)[:max_items]
    peak = max(v for _, v in sorted_items) or 1
    rows = []
    for label, count in sorted_items:
        pct = round(count / peak * 100)
        rows.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{_esc(label)}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f'<span class="bar-value">{count:,}</span></div>'
        )
    return "\n".join(rows)


def _vbar_chart(pairs: list, fill_cls: str = "") -> str:
    """세로 막대 차트 (시간 흐름용: 일별·시간대별). pairs = [(라벨, 건수), ...] 순서 그대로."""
    peak = max((c for _, c in pairs), default=0) or 1
    cols = []
    for i, (label, count) in enumerate(pairs):
        pct = round(count / peak * 100)
        cols.append(
            f'<div class="vbar" data-i="{i}" data-v="{count}"><span class="vbar-val">{count:,}</span>'
            f'<div class="vbar-col"><div class="vbar-fill {fill_cls}" style="height:{pct}%"></div></div>'
            f'<span class="vbar-lbl">{_esc(label)}</span></div>'
        )
    return ('<div class="vchart">' + _VCHART_TOOLS +
            f'<div class="vbars n{len(pairs)}">' + "".join(cols) + '</div></div>' + _VCHART_JS)


# 세로 막대 차트 오른쪽 위 정렬·필터 아이콘 (메뉴에서 고르면 막대 순서·표시가 바뀜)
_VCHART_TOOLS = (
    '<div class="vtools">'
    '<div class="vtool"><button type="button" class="vtool-btn" data-menu="sort" title="정렬" aria-label="정렬" aria-expanded="false">'
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M7 4v16M3 16l4 4 4-4M17 20V4M13 8l4-4 4 4"/></svg></button>'
    '<div class="vmenu" data-for="sort" role="menu">'
    '<button type="button" data-sort="time" class="on">시간순</button>'
    '<button type="button" data-sort="desc">많은 순</button>'
    '<button type="button" data-sort="asc">적은 순</button></div></div>'
    '<div class="vtool"><button type="button" class="vtool-btn" data-menu="filter" title="필터" aria-label="필터" aria-expanded="false">'
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
    '<path d="M3 5h18l-7 8v6l-4 2v-8z"/></svg></button>'
    '<div class="vmenu" data-for="filter" role="menu">'
    '<button type="button" data-filter="all" class="on">전체</button>'
    '<button type="button" data-filter="nonzero">0건 제외</button>'
    '<button type="button" data-filter="avg">평균 이상</button></div></div>'
    '</div>'
)

_VCHART_JS = """<script>
(function () {
  if (window.__relogVchart) return; window.__relogVchart = true;
  function apply(chart) {
    var box = chart.querySelector('.vbars'), bars = Array.prototype.slice.call(box.querySelectorAll('.vbar'));
    var sort = chart.dataset.sort || 'time', filter = chart.dataset.filter || 'all';
    var vals = bars.map(function (b) { return +b.dataset.v; });
    var avg = vals.reduce(function (a, b) { return a + b; }, 0) / (vals.length || 1);
    bars.sort(function (a, b) {
      if (sort === 'desc') return b.dataset.v - a.dataset.v || a.dataset.i - b.dataset.i;
      if (sort === 'asc') return a.dataset.v - b.dataset.v || a.dataset.i - b.dataset.i;
      return a.dataset.i - b.dataset.i;
    }).forEach(function (b) {
      var v = +b.dataset.v;
      b.hidden = (filter === 'nonzero' && v === 0) || (filter === 'avg' && v < avg);
      box.appendChild(b);
    });
    var on = sort !== 'time' || filter !== 'all';
    chart.classList.toggle('is-filtered', on);
  }
  document.addEventListener('click', function (e) {
    var btn = e.target.closest('.vtool-btn'), item = e.target.closest('.vmenu button');
    document.querySelectorAll('.vtool.open').forEach(function (t) {
      if (!btn || t !== btn.parentNode) { t.classList.remove('open'); t.querySelector('.vtool-btn').setAttribute('aria-expanded', 'false'); }
    });
    if (btn) {
      var open = btn.parentNode.classList.toggle('open');
      btn.setAttribute('aria-expanded', String(open));
    } else if (item) {
      var chart = item.closest('.vchart'), menu = item.parentNode;
      menu.querySelectorAll('button').forEach(function (b) { b.classList.toggle('on', b === item); });
      if (item.dataset.sort) chart.dataset.sort = item.dataset.sort;
      if (item.dataset.filter) chart.dataset.filter = item.dataset.filter;
      menu.parentNode.querySelector('.vtool-btn').classList.toggle('active', !item.classList.contains('on') || item !== menu.querySelector('button'));
      apply(chart);
    }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') document.querySelectorAll('.vtool.open').forEach(function (t) { t.classList.remove('open'); });
  });
})();
</script>"""


def _daily_chart(daily: dict) -> str:
    if not daily:
        return '<p class="empty">데이터 없음</p>'
    return _vbar_chart([(day[5:] if len(day) >= 10 else day, count)
                        for day, count in sorted(daily.items())], "daily")


def _hour_chart(hourly: dict) -> str:
    """시간대별 분포: 0~23시를 시간순으로 (건수순 아님, 0건인 시간도 표시)."""
    if not hourly or not any(hourly.values()):
        return '<p class="empty">데이터 없음</p>'
    counts = {int(h): c for h, c in hourly.items()}
    return _vbar_chart([(f"{h}시", counts.get(h, 0)) for h in range(24)])


def _top_table(rows: list, col1: str, col2: str) -> str:
    if not rows:
        return '<p class="empty">데이터 없음</p>'
    trs = "".join(
        f"<tr><td>{_esc(k)}</td><td class='num'>{v:,}</td></tr>" for k, v in rows
    )
    return f"<table class='top-table'><thead><tr><th>{_esc(col1)}</th><th>{_esc(col2)}</th></tr></thead><tbody>{trs}</tbody></table>"


def _base_styles() -> str:
    return """
:root { --bg:#0E0E0C; --card:#1A1A18; --border:#2E2D2A; --text:#F4F3EF; --muted:#9C9A93;
        --accent:#FF2D6B; --warn:#D4B483; --danger:#FF4D82; --ok:#3CB371; }
* { box-sizing:border-box; margin:0; padding:0; }
body { font-family:'Segoe UI',system-ui,sans-serif; background:var(--bg); color:var(--text); line-height:1.5; padding:24px; }
/* 요약·차트는 읽기 편한 폭으로, 상세 로그 표가 있는 섹션만 전체 폭 */
.header,.grid,section { max-width:1080px; margin-left:auto; margin-right:auto; }
section:has(.log-wrap) { max-width:none; }
/* 세로 막대 (일별·시간대별) */
.vbars { display:flex; align-items:stretch; gap:6px; height:220px; overflow-x:auto; padding-top:4px; }
.vbar { flex:1 1 0; min-width:28px; display:flex; flex-direction:column; align-items:center; gap:4px; }
.vbars.n24 .vbar { min-width:22px; }
.vbar-col { flex:1; width:100%; display:flex; align-items:flex-end; background:transparent; border-radius:4px 4px 0 0; }
.vbar-fill { width:100%; min-height:2px; background:var(--accent); border-radius:4px 4px 0 0; }
.vbar-fill.daily { background:#F7D0DC; }
.vbar-val { font-size:0.7rem; color:var(--text); font-variant-numeric:tabular-nums; white-space:nowrap; }
.vbars.n24 .vbar-val { font-size:0.62rem; }
.vbar-lbl { font-size:0.72rem; color:var(--muted); white-space:nowrap; }
.vbars.n28,.vbars.n29,.vbars.n30,.vbars.n31 { gap:3px; }
.vbars.n28 .vbar,.vbars.n29 .vbar,.vbars.n30 .vbar,.vbars.n31 .vbar { min-width:0; }
.vbars.n28 .vbar-val,.vbars.n29 .vbar-val,.vbars.n30 .vbar-val,.vbars.n31 .vbar-val,.vbars.n28 .vbar-lbl,.vbars.n29 .vbar-lbl,.vbars.n30 .vbar-lbl,.vbars.n31 .vbar-lbl { font-size:0.56rem; letter-spacing:-.02em; }
a { color:var(--accent); text-decoration:none; }
a:hover { text-decoration:underline; }
.header { margin-bottom:24px; }
.header h1 { font-size:1.5rem; margin-bottom:4px; }
.header .sub { color:var(--muted); font-size:0.9rem; }
.grid { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:24px; }
.card { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:16px; }
.card .label { color:var(--muted); font-size:0.8rem; margin-bottom:4px; }
.card .value { font-size:1.8rem; font-weight:700; }
.card.warn .value { color:var(--warn); }
.card.danger .value { color:var(--danger); }
.card.ok .value { color:var(--ok); }
section { background:var(--card); border:1px solid var(--border); border-radius:10px; padding:20px; margin-bottom:20px; }
section h2 { font-size:1.1rem; margin-bottom:16px; padding-bottom:8px; border-bottom:1px solid var(--border); }
.bar-row { display:grid; grid-template-columns:100px 1fr 60px; gap:8px; align-items:center; margin-bottom:6px; font-size:0.85rem; }
.bar-label { color:var(--muted); text-align:right; }
.bar-track { background:var(--bg); border-radius:4px; height:18px; overflow:hidden; }
.bar-fill { background:var(--accent); height:100%; border-radius:4px; min-width:2px; }
.bar-fill.daily { background:#F7D0DC; }
.bar-value { text-align:right; font-variant-numeric:tabular-nums; }
.empty { color:var(--muted); font-style:italic; }
.top-table { width:100%; border-collapse:collapse; font-size:0.85rem; }
.top-table th,.top-table td { padding:8px 12px; text-align:left; border-bottom:1px solid var(--border); }
.top-table th { color:var(--muted); font-weight:600; }
.top-table .num { text-align:right; font-variant-numeric:tabular-nums; }
.badge { display:inline-block; padding:2px 10px; border-radius:12px; font-size:0.75rem; font-weight:600; }
.badge.ok { background:rgba(60,179,113,.18); color:var(--ok); }
.badge.warn { background:rgba(212,180,131,.2); color:var(--warn); }
.log-controls { display:flex; gap:12px; margin-bottom:12px; flex-wrap:wrap; }
.log-controls input,.log-controls select { background:var(--bg); border:1px solid var(--border); color:var(--text); padding:8px 12px; border-radius:6px; font-size:0.85rem; }
.log-controls input { flex:1; min-width:200px; }
.log-table { width:100%; border-collapse:collapse; font-size:0.78rem; }
.log-table th,.log-table td { padding:6px 8px; text-align:left; border-bottom:1px solid var(--border); vertical-align:top; }
.log-table th { color:var(--muted); position:sticky; top:0; background:var(--card); }
.log-table tr:hover { background:rgba(255,45,107,.07); }
.log-table .raw { max-width:600px; word-break:break-all; color:var(--muted); }
.log-wrap { max-height:500px; overflow:auto; }
details { margin-top:12px; }
details summary { cursor:pointer; color:var(--muted); padding:8px 0; }
.btn-more { background:var(--accent); color:#fff; border:none; padding:8px 16px; border-radius:6px; cursor:pointer; margin-top:8px; font-size:0.85rem; }
.btn-more:hover { opacity:.9; }
.index-list { list-style:none; }
.index-list li { padding:12px 0; border-bottom:1px solid var(--border); }
.l4-bars { display:grid; grid-template-columns:1fr 1fr; gap:20px; }
.l4-bar-item .name { margin-bottom:6px; font-weight:600; }
/* Re.log 웹과 같은 톤: 폰트(Inter Tight · Noto Sans KR · JetBrains Mono), 둥근 카드, 알약 칩 */
body { font-family:'Inter Tight','Noto Sans KR',system-ui,sans-serif; letter-spacing:-.01em; padding:40px 24px 64px; }
.header { margin-bottom:28px; }
.header::before { content:"Re.log"; display:block; margin-bottom:18px; font-size:1.1rem; font-weight:700; letter-spacing:-.04em; color:var(--text); }
.header h1 { font-size:2rem; font-weight:600; letter-spacing:-.04em; margin-bottom:6px; }
.header .sub,.sub { font-family:'Noto Sans KR','Inter Tight',sans-serif; }
.header a { font-size:.85rem; }
.card { border-radius:18px; padding:20px 22px; }
.card .label { font-family:'Noto Sans KR','Inter Tight',sans-serif; font-size:.8rem; }
.card .value { font-size:2.2rem; font-weight:500; letter-spacing:-.05em; line-height:1.15; font-variant-numeric:tabular-nums; }
section { border-radius:20px; padding:24px 26px; }
section h2 { font-family:'Noto Sans KR','Inter Tight',sans-serif; font-size:1rem; font-weight:600; letter-spacing:-.01em; }
.badge { border-radius:999px; padding:3px 10px; }
.btn-more { border-radius:999px; padding:10px 20px; font-weight:600; }
.log-controls input,.log-controls select { border-radius:999px; padding:9px 16px; }
.log-table,.top-table td:first-child,.log-table .raw { font-family:'JetBrains Mono',ui-monospace,monospace; }
.log-table { font-size:0.74rem; }
.bar-track { border-radius:999px; }
.bar-fill { border-radius:999px; }
.vbar-fill { border-radius:6px 6px 0 0; }
.vbar-col { border-radius:6px 6px 0 0; transition:background-color .2s; }
.vbar:hover .vbar-col { background:var(--bg); }
.vbar:hover .vbar-val { color:var(--accent); }
/* 세로 막대 정렬·필터 */
section:has(.vchart) { position:relative; }
.vtools { position:absolute; top:18px; right:22px; display:flex; gap:6px; }
.vtool { position:relative; }
.vtool-btn { display:flex; align-items:center; justify-content:center; width:32px; height:32px; border:1px solid var(--border); border-radius:999px; background:transparent; color:var(--muted); cursor:pointer; transition:color .2s,border-color .2s; }
.vtool-btn:hover,.vtool.open .vtool-btn { color:var(--text); border-color:var(--muted); }
.vtool-btn.active { color:var(--accent); border-color:var(--accent); }
.vmenu { position:absolute; right:0; top:calc(100% + 6px); z-index:5; min-width:120px; padding:6px; border:1px solid var(--border); border-radius:14px; background:var(--bg); box-shadow:0 12px 28px rgba(0,0,0,.4); display:none; }
.vtool.open .vmenu { display:block; }
.vmenu button { display:block; width:100%; padding:8px 12px; border:0; border-radius:8px; background:transparent; color:var(--muted); font:inherit; font-size:.82rem; text-align:left; cursor:pointer; }
.vmenu button:hover { background:var(--card); color:var(--text); }
.vmenu button.on { color:var(--accent); font-weight:600; }
.vmenu button.on::after { content:" ✓"; }
.vbar[hidden] { display:none; }
/* 스크롤바: 사이트와 같은 얇은 반투명 막대 (페이지 · 로그 표 · 막대 그래프 공통) */
html,.log-wrap,.vbars,.top-table { scrollbar-width:thin; scrollbar-color:rgba(244,243,239,.22) transparent; }
::-webkit-scrollbar { width:8px; height:8px; }
::-webkit-scrollbar-track { background:transparent; }
::-webkit-scrollbar-thumb { background:rgba(244,243,239,.22); border-radius:999px; border:2px solid transparent; background-clip:padding-box; }
::-webkit-scrollbar-thumb:hover { background-color:var(--accent); }
::-webkit-scrollbar-corner { background:transparent; }
.log-wrap { border-radius:12px; }
/* 표 머리글 줄바꿈 방지 · 섹션 안내문 톤 */
.log-table th,.log-table td:nth-child(-n+5) { white-space:nowrap; }
section .sub { color:var(--muted); font-size:.85rem; }
.top-table th:last-child { text-align:right; }
.top-pair { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1.8fr); gap:20px; max-width:1080px; margin:0 auto 20px; align-items:start; }
.top-pair section { margin:0; max-width:none; }
.top-pair .top-table td:first-child { word-break:break-all; }
@media (max-width:760px) { .top-pair { grid-template-columns:minmax(0,1fr); } }
"""

# 웹과 같은 폰트 (오프라인으로 ZIP을 열면 시스템 글꼴로 대체됨)
FONT_LINK = ('<link rel="preconnect" href="https://fonts.googleapis.com">'
             '<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@400;500;600;700'
             '&family=JetBrains+Mono:wght@400;500&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">')


def _log_table_js(table_id: str, show_more_id: str, page_size: int = 200) -> str:
    return f"""
<script>
(function() {{
  const rows = Array.from(document.querySelectorAll('#{table_id} tbody tr'));
  const search = document.getElementById('{table_id}-search');
  const filter = document.getElementById('{table_id}-filter');
  const btn = document.getElementById('{show_more_id}');
  let visibleLimit = {page_size};

  function applyFilter() {{
    const q = (search?.value || '').toLowerCase();
    const kw = filter?.value || '';
    let shown = 0, matched = 0;
    rows.forEach(row => {{
      const text = row.textContent.toLowerCase();
      const kws = row.dataset.keywords || '';
      const ok = (!q || text.includes(q)) && (!kw || kws.includes(kw));
      if (ok) {{
        matched++;
        row.style.display = shown < visibleLimit ? '' : 'none';
        if (shown < visibleLimit) shown++;
      }} else {{
        row.style.display = 'none';
      }}
    }});
    if (btn) {{ btn.style.display = matched > visibleLimit ? '' : 'none'; btn.textContent = Math.min(50, matched - visibleLimit).toLocaleString() + '개 더 보기'; }}
  }}

  if (search) search.addEventListener('input', () => {{ visibleLimit = {page_size}; applyFilter(); }});
  if (filter) filter.addEventListener('change', () => {{ visibleLimit = {page_size}; applyFilter(); }});
  if (btn) btn.addEventListener('click', () => {{ visibleLimit += 50; applyFilter(); }});
  applyFilter();
}})();
</script>
"""


def _render_log_section(entries: list, section_id: str, keywords: list) -> str:
    if not entries:
        return '<p class="empty">해당 항목 없음</p>'
    kw_options = "".join(f'<option value="{_esc(k)}">{_esc(k)}</option>' for k in sorted(set(keywords)))
    rows = []
    for e in entries:
        kws = ",".join(e.get("keywords", []))
        status = e.get("status", "")
        status_cls = "danger" if status and status.startswith("5") else ("warn" if status == "401" else "")
        rows.append(
            f"<tr data-keywords='{_esc(kws)}'>"
            f"<td>{_esc(e.get('date',''))}</td>"
            f"<td>{_esc(e.get('hour',''))}시</td>"
            f"<td>{_esc(e.get('file',''))}</td>"
            f"<td>{_esc(e.get('ip',''))}</td>"
            f"<td class='{status_cls}'>{_esc(status)}</td>"
            f"<td>{_esc(e.get('url',''))}</td>"
            f"<td class='raw'>{_esc(e.get('raw',''))}</td></tr>"
        )
    return f"""
<div class="log-controls">
  <input type="text" id="{section_id}-search" placeholder="검색 (IP, URL, 메시지...)">
  <select id="{section_id}-filter"><option value="">전체 키워드</option>{kw_options}</select>
</div>
<div class="log-wrap">
<table class="log-table" id="{section_id}">
<thead><tr><th>날짜</th><th>시간</th><th>파일</th><th>IP</th><th>상태</th><th>URL</th><th>내용</th></tr></thead>
<tbody>{"".join(rows)}</tbody>
</table>
</div>
<button class="btn-more" id="{section_id}-more" style="display:none">더 보기</button>
{_log_table_js(section_id, f"{section_id}-more")}
"""


def build_win_report(output_path: str, sys_name: str, period_label: str, data: dict) -> str:
    breakdown_html = _bar_chart(data.get("breakdown", {}))
    hourly_html = _hour_chart(data.get("hourly", {}))
    daily_html = _daily_chart(data.get("daily", {}))
    top_ips = _top_table(data.get("top_ips", []), "IP", "건수")
    top_urls = _top_table(data.get("top_urls", []), "URL", "건수")
    all_kws = list(data.get("breakdown", {}).keys())
    logs_html = _render_log_section(data.get("entries", []), "main-logs", all_kws)
    noise_html = _render_log_section(data.get("noise_entries", []), "noise-logs", ["401"])

    content = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(sys_name)} 리포트 — {_esc(period_label)}</title>
{FONT_LINK}<style>{_base_styles()}</style></head><body>
<div class="header">
  <p><a href="index_{data['period_key']}.html">← 목차</a></p>
  <h1>{_esc(sys_name)} 로그 분석</h1>
  <p class="sub">{_esc(period_label)}</p>
</div>
<div class="grid">
  <div class="card"><div class="label">주요 탐지</div><div class="value">{data.get('main_count',0):,}</div></div>
  <div class="card warn"><div class="label">노이즈 (refresh-token 401)</div><div class="value">{data.get('noise_count',0):,}</div></div>
  <div class="card"><div class="label">분석 일수</div><div class="value">{data.get('day_count',0)}</div></div>
</div>
<section><h2>키워드 / 상태코드 분류</h2>{breakdown_html}</section>
<section><h2>일별 추이</h2>{daily_html}</section>
<section><h2>시간대별 분포</h2>{hourly_html}</section>
<div class="top-pair">
<section><h2>Top IP</h2>{top_ips}</section>
<section><h2>Top URL</h2>{top_urls}</section>
</div>
<section><h2>상세 로그 (주요 탐지)</h2>{logs_html}</section>
<section><h2>노이즈 로그 — refresh-token 401</h2>
<p class="sub" style="margin-bottom:12px">토큰 갱신 실패 등 정상 운영 중 발생 가능한 401. 주요 탐지 집계에서 제외됨.</p>
{noise_html}</section>
</body></html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


def build_linux_report(output_path: str, period_label: str, data: dict) -> str:
    l4 = data.get("l4", {})
    web1, web2 = l4.get("web1", 0), l4.get("web2", 0)
    total = web1 + web2 or 1
    w1_pct = round(web1 / total * 100)
    w2_pct = round(web2 / total * 100)
    dev_rate = l4.get("dev_rate", 0)
    status = l4.get("status", "정상")
    badge_cls = "ok" if status == "정상" else "warn"

    daily_traffic = data.get("daily_traffic", {})
    daily_errors = data.get("daily_errors", {})
    traffic_chart = _daily_chart({
        d: v.get("WEB1", 0) + v.get("WEB2", 0) for d, v in sorted(daily_traffic.items())
    })
    error_chart = _daily_chart(daily_errors)

    server_cards = []
    for name, srv in data.get("servers", {}).items():
        traffic_n = srv.get("traffic", 0)
        err_n = srv.get("error_count", 0)
        server_cards.append(
            f'<div class="card"><div class="label">{_esc(name)}</div>'
            f'<div class="value" style="font-size:1.2rem">트래픽 {traffic_n:,}</div>'
            f'<div class="label" style="margin-top:8px">노이즈 {err_n:,}건</div></div>'
        )

    category_totals = Counter()
    for name, srv in data.get("servers", {}).items():
        for label, cnt in srv.get("categories", {}).items():
            category_totals[label] += cnt
    category_chart = _bar_chart(dict(category_totals))

    server_details = []
    for name, srv in data.get("servers", {}).items():
        errors = srv.get("errors", [])
        err_n = srv.get("error_count", 0)
        cat_chart = _bar_chart(dict(srv.get("categories", {})))
        err_rows = "".join(f"<tr><td class='raw'>{_esc(line)}</td></tr>" for line in errors[:500])
        server_details.append(
            f"<details><summary>{_esc(name)} — 노이즈 {err_n:,}건 (표시 {min(len(errors),500)}건)</summary>"
            f"<div style='margin:12px 0'>{cat_chart}</div>"
            f"<div class='log-wrap'><table class='log-table'><tbody>{err_rows}</tbody></table></div></details>"
        )

    content = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>E-BIZ 리포트 — {_esc(period_label)}</title>
{FONT_LINK}<style>{_base_styles()}</style></head><body>
<div class="header">
  <h1>E-BIZ 통합 로그 분석</h1>
  <p class="sub">{_esc(period_label)}</p>
</div>
<section><h2>L4 로드밸런싱 트래픽 (기간 합산)</h2>
<div class="l4-bars">
  <div class="l4-bar-item"><div class="name">WEB1 — {web1:,}건 ({w1_pct}%)</div>
    <div class="bar-track"><div class="bar-fill" style="width:{w1_pct}%"></div></div></div>
  <div class="l4-bar-item"><div class="name">WEB2 — {web2:,}건 ({w2_pct}%)</div>
    <div class="bar-track"><div class="bar-fill" style="width:{w2_pct}%"></div></div></div>
</div>
<p style="margin-top:16px">편차율: <strong>{dev_rate:.1f}%</strong> <span class="badge {badge_cls}">{_esc(status)}</span></p>
</section>
<section><h2>일별 WEB 트래픽 추이</h2>{traffic_chart}</section>
<section><h2>일별 노이즈 추이 (전 노드 합산)</h2>{error_chart}</section>
<section><h2>노이즈 유형 분류 (스캔 시그니처 기반, 전 노드 합산)</h2>
<p class="sub" style="margin-bottom:12px">알려진 취약점 스캐너 패턴과 매칭한 결과. "기타(미분류)"가 늘어나면 실제 애플리케이션 에러일 수 있어 우선 확인 권장.</p>
{category_chart}</section>
<section><h2>서버별 요약</h2><div class="grid">{"".join(server_cards)}</div></section>
<section><h2>서버별 노이즈 상세</h2>{"".join(server_details)}</section>
</body></html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path


# ── 이메일 전용 렌더링 ──────────────────────────────────────────────
# Gmail 등 웹메일은 <style> 블록의 CSS 변수(var(--x))와 grid를 지원하지 않아
# 위 브라우저용 리포트를 그대로 넣으면 스타일이 깨진다. 메일 본문은 전부
# 인라인 스타일 + <table> 레이아웃으로 별도 렌더링한다.

_EC = {
    "bg": "#f3f4f6", "card": "#ffffff", "border": "#e5e7eb",
    "text": "#1f2937", "muted": "#6b7280", "accent": "#2563eb",
}

# 노이즈/주요 탐지가 이 건수 이상이면 "조치 가이드"에 노출한다 (단순 고정 임계치 — 필요시 조정).
_GUIDANCE_ALERT_THRESHOLD = 10


def _email_guidance_box(lines: list) -> str:
    items = lines or ["특이사항 없음 (정상 범위)"]
    rows = "".join(
        f'<div style="padding:3px 0;color:{_EC["text"]};font-size:13px;line-height:1.6">- {_esc(line)}</div>'
        for line in items
    )
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
style="background:{_EC['bg']};border-left:4px solid {_EC['accent']};border-radius:4px;margin-bottom:16px">
<tr><td style="padding:14px 16px">
<div style="font-size:13px;font-weight:600;color:{_EC['text']};margin-bottom:6px">조치 가이드</div>
{rows}
</td></tr></table>"""


def _email_ai_box(ai_lines) -> str:
    """Claude가 쓴 요약. 없으면 빈 문자열 (AI 비활성/실패 시 기존 메일과 동일)."""
    if not ai_lines:
        return ""
    head, rest = ai_lines[0], ai_lines[1:]
    color = _EC["accent"]
    if "위험" in head:
        color = "#c0392b"
    elif "주의" in head:
        color = "#d68910"
    rows = "".join(
        f'<div style="padding:3px 0;color:{_EC["text"]};font-size:13px;line-height:1.6">- {_esc(line)}</div>'
        for line in rest
    )
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
style="background:{_EC['card']};border:1px solid {_EC['border']};border-left:4px solid {color};border-radius:4px;margin-bottom:16px">
<tr><td style="padding:14px 16px">
<div style="font-size:12px;color:{_EC['muted']};margin-bottom:4px">AI 요약 (Claude)</div>
<div style="font-size:14px;font-weight:700;color:{color};margin-bottom:6px">{_esc(head)}</div>
{rows}
</td></tr></table>"""


def _linux_guidance_lines(data: dict) -> list:
    lines = []
    l4 = data.get("l4", {})
    if l4.get("status") == "편차 심함":
        lines.append(
            f"L4 편차 {l4.get('dev_rate', 0):.1f}%로 임계치를 초과했습니다 — WEB1/WEB2 헬스체크 및 L4 세션 분배 설정 점검 필요"
        )
    for name, srv in data.get("servers", {}).items():
        err_n = srv.get("error_count", 0)
        unclassified = srv.get("categories", {}).get("기타(미분류)", 0)
        if unclassified >= _GUIDANCE_ALERT_THRESHOLD:
            lines.append(f"{name}: 미분류 노이즈 {unclassified:,}건 — 알려진 스캔 시그니처와 불일치, 실제 에러 여부 확인 권장")
        elif err_n >= _GUIDANCE_ALERT_THRESHOLD:
            lines.append(f"{name}: 노이즈 {err_n:,}건 발생 (대부분 알려진 스캔 시그니처) — 참고용, 조치 불필요")
    for name, reason in data.get("failed_nodes", {}).items():
        lines.append(f"{name}: 로그 수집 실패 ({reason}) — SSH 접속/키 상태 확인 필요")
    return lines


def _win_guidance_lines(systems: list) -> list:
    lines = []
    for sys_name, data in systems:
        main_n = data.get("main_count", 0)
        if main_n >= _GUIDANCE_ALERT_THRESHOLD:
            lines.append(f"{sys_name}: 주요 탐지 {main_n:,}건 — 첨부 ZIP 또는 로그 미리보기에서 내용 확인 필요")
    return lines


def _email_card(label: str, value, sub: str = None, width_pct: int = 33) -> str:
    # sub가 없어도 자리를 항상 차지하는 빈 줄을 넣어야 카드 높이가 균일해진다.
    # (일부 카드만 height:56px 같은 min-height를 content가 넘겨버리면 그 카드만 더 커짐)
    sub_text = _esc(sub) if sub else "&nbsp;"
    return f"""<td width="{width_pct}%" style="padding:6px" valign="top">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_EC['card']};border:1px solid {_EC['border']};border-radius:8px">
<tr><td style="padding:14px 16px" valign="top">
<div style="font-size:12px;color:{_EC['muted']}">{_esc(label)}</div>
<div style="font-size:22px;font-weight:700;color:{_EC['text']};margin-top:2px">{_esc(value)}</div>
<div style="font-size:12px;color:{_EC['muted']};margin-top:4px">{sub_text}</div>
</td></tr></table></td>"""


def _email_card_row(cards: list, per_row: int = 3) -> str:
    """cards: [(label, value, sub), ...] — per_row개씩 한 줄로 묶는다."""
    rows = []
    for i in range(0, len(cards), per_row):
        chunk = cards[i:i + per_row]
        tds = "".join(_email_card(*c, width_pct=round(100 / per_row)) for c in chunk)
        pad = f'<td width="{round(100 / per_row)}%"></td>' * (per_row - len(chunk))
        rows.append(f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>{tds}{pad}</tr></table>')
    return "".join(rows)


def _email_section(title: str, inner_html: str) -> str:
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
style="background:{_EC['card']};border:1px solid {_EC['border']};border-radius:8px;margin-bottom:16px">
<tr><td style="padding:16px">
<div style="font-size:14px;font-weight:600;color:{_EC['text']};padding-bottom:10px;border-bottom:1px solid {_EC['border']};margin-bottom:12px">{_esc(title)}</div>
{inner_html}
</td></tr></table>"""


def _email_bar_rows(items: dict, max_items: int = 15, sort_by_value: bool = True, label_fn=None) -> str:
    if not items:
        return f'<div style="color:{_EC["muted"]};font-style:italic;font-size:13px">데이터 없음</div>'
    entries = sorted(items.items(), key=lambda x: x[1], reverse=True) if sort_by_value else sorted(items.items())
    entries = entries[:max_items]
    peak = max(v for _, v in entries) or 1
    rows = []
    for label, count in entries:
        shown_label = label_fn(label) if label_fn else label
        pct = max(round(count / peak * 100), 2)
        rows.append(f"""<tr>
<td width="90" style="font-size:12px;color:{_EC['muted']};text-align:right;padding:3px 8px 3px 0">{_esc(shown_label)}</td>
<td style="padding:3px 0">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
<td width="{pct}%" style="background:{_EC['accent']};border-radius:3px;font-size:0;line-height:12px">&nbsp;</td>
<td width="{100 - pct}%" style="font-size:0;line-height:12px">&nbsp;</td>
</tr></table></td>
<td width="55" style="font-size:12px;color:{_EC['text']};text-align:right;padding:3px 0 3px 8px">{count:,}</td>
</tr>""")
    return f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0">{"".join(rows)}</table>'


def _email_top_table(rows: list, col1: str, col2: str) -> str:
    if not rows:
        return f'<div style="color:{_EC["muted"]};font-style:italic;font-size:13px">데이터 없음</div>'
    trs = "".join(
        f'<tr><td style="padding:5px 8px;border-bottom:1px solid {_EC["border"]};font-size:12px;color:{_EC["text"]}">{_esc(k)}</td>'
        f'<td style="padding:5px 8px;border-bottom:1px solid {_EC["border"]};font-size:12px;color:{_EC["text"]};text-align:right">{v:,}</td></tr>'
        for k, v in rows
    )
    return f"""<table role="presentation" width="100%" cellpadding="0" cellspacing="0">
<tr><th style="text-align:left;padding:5px 8px;font-size:11px;color:{_EC['muted']};border-bottom:1px solid {_EC['border']}">{_esc(col1)}</th>
<th style="text-align:right;padding:5px 8px;font-size:11px;color:{_EC['muted']};border-bottom:1px solid {_EC['border']}">{_esc(col2)}</th></tr>
{trs}</table>"""


def _email_log_preview(entries: list, limit: int = 5) -> str:
    """entries: 문자열 리스트 또는 {'raw': ...} 딕셔너리 리스트. 앞 N건만 미리보기로 보여주고
    나머지는 개수만 안내 — 전체를 넣으면 Gmail의 메시지 크기 제한(약 102KB)에 걸려 잘릴 수 있다."""
    if not entries:
        return f'<div style="color:{_EC["muted"]};font-style:italic;font-size:13px">해당 항목 없음</div>'
    rows = "".join(
        f'<div style="font-size:11px;color:{_EC["muted"]};padding:4px 0;border-bottom:1px solid {_EC["border"]};word-break:break-all">'
        f'{_esc(line if isinstance(line, str) else line.get("raw", ""))}</div>'
        for line in entries[:limit]
    )
    more = len(entries) - limit
    if more > 0:
        rows += f'<div style="font-size:11px;color:{_EC["muted"]};padding-top:6px">외 {more:,}건 — 첨부 ZIP에서 전체 확인</div>'
    return rows


def _email_wrapper(title: str, platform: str, period_label: str, summary_lines: list, body_html: str) -> str:
    meta_lines = [
        f"플랫폼: {platform}",
        f"분석 기간: {period_label}",
        f"생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
    ] + list(summary_lines)
    summary_html = "<br>".join(_esc(line) for line in meta_lines)
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(title)} — {_esc(period_label)}</title></head>
<body style="margin:0;padding:0;background:{_EC['bg']};font-family:'Segoe UI',Arial,sans-serif;color:{_EC['text']}">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_EC['bg']}">
<tr><td align="center" style="padding:24px 12px">
<table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%">
<tr><td style="padding-bottom:16px">
<div style="font-size:20px;font-weight:700;color:{_EC['text']}">{_esc(title)}</div>
</td></tr>
<tr><td style="background:{_EC['card']};border:1px solid {_EC['border']};border-radius:8px;padding:16px;font-size:13px;color:{_EC['muted']};line-height:1.7">
{summary_html}
</td></tr>
<tr><td style="height:16px;font-size:0;line-height:0">&nbsp;</td></tr>
<tr><td>{body_html}</td></tr>
<tr><td style="padding-top:8px;font-size:12px;color:{_EC['muted']}">
상세 로그 및 인터랙티브 대시보드는 첨부된 ZIP 파일을 열어 확인하실 수 있습니다.
</td></tr>
</table>
</td></tr>
</table>
</body></html>"""


def build_linux_email_html(period_label: str, data: dict, summary_lines: list, ai_lines=None) -> str:
    l4 = data.get("l4", {})
    web1, web2 = l4.get("web1", 0), l4.get("web2", 0)
    dev_rate = l4.get("dev_rate", 0)
    status = l4.get("status", "정상")

    l4_cards = [
        ("WEB1 트래픽", f"{web1:,}", None),
        ("WEB2 트래픽", f"{web2:,}", None),
        ("L4 편차율", f"{dev_rate:.1f}%", status),
    ]
    server_cards = []
    for name, srv in data.get("servers", {}).items():
        err_n = srv.get("error_count", 0)
        server_cards.append((name, f"{srv.get('traffic', 0):,}", f"노이즈 {err_n:,}건"))

    date_label = lambda d: d[5:] if len(d) >= 10 else d
    daily_traffic = data.get("daily_traffic", {})
    traffic_bars = _email_bar_rows(
        {d: v.get("WEB1", 0) + v.get("WEB2", 0) for d, v in daily_traffic.items()},
        max_items=31, sort_by_value=False, label_fn=date_label,
    )
    error_bars = _email_bar_rows(data.get("daily_errors", {}), max_items=31, sort_by_value=False, label_fn=date_label)

    category_totals = Counter()
    for name, srv in data.get("servers", {}).items():
        for label, cnt in srv.get("categories", {}).items():
            category_totals[label] += cnt
    category_bars = _email_bar_rows(dict(category_totals))

    server_sections = "".join(
        _email_section(
            f"{name} — 노이즈 미리보기 ({srv.get('error_count', 0):,}건)",
            _email_bar_rows(dict(srv.get("categories", {}))) + _email_log_preview(srv.get("errors", [])),
        )
        for name, srv in data.get("servers", {}).items()
    )

    body = (
        _email_ai_box(ai_lines)
        + _email_guidance_box(_linux_guidance_lines(data))
        + _email_card_row(l4_cards)
        + _email_card_row(server_cards, per_row=2)
        + _email_section("일별 WEB 트래픽 추이", traffic_bars)
        + _email_section("일별 노이즈 추이 (전 노드 합산)", error_bars)
        + _email_section("노이즈 유형 분류 (스캔 시그니처 기반, 전 노드 합산)", category_bars)
        + server_sections
    )
    return _email_wrapper("E-BIZ 시스템 통합 로그 리포트", "Linux", period_label, summary_lines, body)


def build_win_email_html(period_label: str, summary_lines: list, systems: list, ai_lines=None) -> str:
    """systems: [(sys_name, data), ...]"""
    date_label = lambda d: d[5:] if len(d) >= 10 else d
    blocks = []
    for idx, (sys_name, data) in enumerate(systems):
        main_n = data.get("main_count", 0)
        noise_n = data.get("noise_count", 0)
        cards = [
            ("주요 탐지", f"{main_n:,}", None),
            ("노이즈", f"{noise_n:,}", "refresh-token 401"),
            ("분석 일수", f"{data.get('day_count', 0)}", None),
        ]
        heading = (
            f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin-top:{0 if idx == 0 else 24}px">'
            f'<tr><td style="font-size:16px;font-weight:700;color:{_EC["text"]};padding-bottom:8px">'
            f'{_esc(sys_name)}</td></tr></table>'
        )
        inner = (
            _email_card_row(cards)
            + _email_section("키워드 / 상태코드 분류", _email_bar_rows(data.get("breakdown", {})))
            + _email_section("일별 추이", _email_bar_rows(data.get("daily", {}), max_items=31, sort_by_value=False, label_fn=date_label))
            + _email_section("Top IP", _email_top_table(data.get("top_ips", []), "IP", "건수"))
            + _email_section("Top URL", _email_top_table(data.get("top_urls", []), "URL", "건수"))
            + _email_section("상세 로그 미리보기 (주요 탐지)", _email_log_preview(data.get("entries", [])))
        )
        blocks.append(heading + inner)
    guidance = _email_ai_box(ai_lines) + _email_guidance_box(_win_guidance_lines(systems))
    return _email_wrapper("E-OUT, IN-OUT 시스템 통합 로그 리포트", "Windows", period_label, summary_lines, guidance + "".join(blocks))


def build_index(output_path: str, period_label: str, period_key: str, links: list) -> str:
    items = "".join(
        f'<li><a href="{_esc(href)}">{_esc(title)}</a> <span class="sub">— {_esc(desc)}</span></li>'
        for title, href, desc in links
    )
    content = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>로그 분석 목차 — {_esc(period_label)}</title>
{FONT_LINK}<style>{_base_styles()}</style></head><body>
<div class="header">
  <h1>로그 분석 대시보드</h1>
  <p class="sub">{_esc(period_label)}</p>
</div>
<section><h2>리포트 목록</h2><ul class="index-list">{items}</ul></section>
</body></html>"""

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(content)
    return output_path
