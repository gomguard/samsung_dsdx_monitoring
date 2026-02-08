"""
공통 UI 컴포넌트 Template Tags

사용법:
{% load components %}
{% search_box fields="id:ID,name:카테고리명" show_status=True %}
{% stat_chips stats="total:전체,active:활성" %}
{% pagination id="pagination" %}
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()


@register.simple_tag
def search_box(fields="", show_status=True, input_placeholder="검색어 입력...",
               field_id="filterField", input_id="filterInput", status_id="filterStatus",
               on_search="applyFilter()", on_reset="resetFilter()"):
    """
    조회박스 컴포넌트

    Args:
        fields: "value:label,value:label" 형식 (예: "id:ID,name:카테고리명")
        show_status: 활성여부 드롭다운 표시 여부
        input_placeholder: 입력창 플레이스홀더
        field_id: 필드 드롭다운 ID
        input_id: 입력창 ID
        status_id: 상태 드롭다운 ID
        on_search: 조회 버튼 onclick
        on_reset: 해제 버튼 onclick
    """
    html = '<div class="search-box">'

    # 필드 드롭다운
    if fields:
        html += f'<select class="search-box-select" id="{field_id}">'
        for field in fields.split(','):
            parts = field.strip().split(':')
            value = parts[0]
            label = parts[1] if len(parts) > 1 else parts[0]
            html += f'<option value="{value}">{label}</option>'
        html += '</select>'

    # 검색 입력창
    html += f'''<input type="text" class="search-box-input" id="{input_id}"
                placeholder="{input_placeholder}"
                onkeypress="if(event.key==='Enter') {on_search}">'''

    # 활성여부 드롭다운
    if show_status:
        html += f'''<select class="search-box-select" id="{status_id}">
            <option value="">활성여부 (전체)</option>
            <option value="active">활성</option>
            <option value="inactive">비활성</option>
        </select>'''

    # 버튼
    html += f'''<button class="search-box-btn search-box-btn-search" onclick="{on_search}">조회</button>
        <button class="search-box-btn search-box-btn-reset" onclick="{on_reset}">해제</button>
    </div>'''

    return mark_safe(html)


@register.simple_tag
def stat_chips(stats=""):
    """
    통계 칩 컴포넌트

    Args:
        stats: "id:label:value,id:label:value" 형식 (예: "statTotal:전체:100,statActive:활성:50")
               value는 생략 가능 (JS에서 동적으로 설정)
    """
    html = '<div class="stat-chips">'

    if stats:
        for stat in stats.split(','):
            parts = stat.strip().split(':')
            stat_id = parts[0]
            label = parts[1] if len(parts) > 1 else parts[0]
            value = parts[2] if len(parts) > 2 else '0'
            html += f'<span class="stat-chip">{label}<strong id="{stat_id}">{value}</strong></span>'

    html += '</div>'
    return mark_safe(html)


@register.simple_tag
def pagination(container_id="pagination"):
    """
    페이지네이션 컴포넌트 (JS에서 렌더링)

    Args:
        container_id: 컨테이너 ID
    """
    return mark_safe(f'<div class="pagination" id="{container_id}"></div>')


@register.simple_tag
def badge(text, status="active"):
    """
    배지 컴포넌트

    Args:
        text: 표시할 텍스트
        status: active, inactive, primary, warning
    """
    return mark_safe(f'<span class="badge badge-{status}">{text}</span>')
