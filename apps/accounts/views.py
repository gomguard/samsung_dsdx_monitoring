"""
사용자 인증 및 관리자 페이지 뷰
"""

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required, user_passes_test
from django.contrib.auth.models import User
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_POST
from django.core.paginator import Paginator
from .models import UserProfile
from apps.common.db import get_dx_connection, get_ds_connection
from apps.common.retail_columns import reload_retail_columns, reload_missing_exclude_rules
from apps.common.targets import reload_targets, format_time
from apps.common.dx_schedules import reload_schedules
import json
from datetime import datetime


def is_admin(user):
    """관리자 권한 체크"""
    return user.is_authenticated and (user.is_staff or user.is_superuser)


def get_or_create_profile(user):
    """사용자 프로필 가져오기 또는 생성"""
    try:
        return user.profile
    except UserProfile.DoesNotExist:
        return UserProfile.objects.create(user=user)


def login_view(request):
    """로그인 페이지"""
    if request.user.is_authenticated:
        return redirect('main:index')

    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        # 먼저 사용자 존재 여부 확인 (계정 잠금 체크용)
        try:
            user_obj = User.objects.get(username=username)
            profile = get_or_create_profile(user_obj)

            # 계정 잠금 확인
            if profile.is_locked:
                messages.error(request, '계정이 잠겼습니다. 관리자에게 문의하여 비밀번호를 재설정하세요.')
                return render(request, 'accounts/login.html')
        except User.DoesNotExist:
            user_obj = None
            profile = None

        user = authenticate(request, username=username, password=password)

        if user is not None:
            if user.is_active:
                # 로그인 성공 - 실패 횟수 초기화
                profile = get_or_create_profile(user)
                profile.reset_failed_attempts()
                profile.update_activity()

                login(request, user)
                next_url = request.GET.get('next', '/')
                return redirect(next_url)
            else:
                messages.error(request, '계정이 비활성화되어 있습니다. 관리자에게 문의하세요.')
        else:
            # 로그인 실패 - 실패 횟수 증가
            if profile:
                profile.increment_failed_attempts()
                remaining = 5 - profile.failed_login_attempts
                if profile.is_locked:
                    messages.error(request, '비밀번호를 5회 이상 틀렸습니다. 계정이 잠겼습니다. 관리자에게 문의하세요.')
                elif remaining > 0:
                    messages.error(request, f'아이디 또는 비밀번호가 올바르지 않습니다. (남은 시도: {remaining}회)')
            else:
                messages.error(request, '아이디 또는 비밀번호가 올바르지 않습니다.')

    return render(request, 'accounts/login.html')


@login_required
def logout_view(request):
    """로그아웃"""
    logout(request)
    messages.success(request, '로그아웃되었습니다.')
    return redirect('accounts:login')


@login_required
@user_passes_test(is_admin)
def admin_dashboard(request):
    """관리자 대시보드 - 회원 목록"""
    users = User.objects.select_related('profile').all().order_by('-date_joined')

    # 검색
    search = request.GET.get('search', '')
    if search:
        users = users.filter(username__icontains=search) | users.filter(email__icontains=search)

    # 필터
    status_filter = request.GET.get('status', '')
    if status_filter == 'active':
        users = users.filter(is_active=True)
    elif status_filter == 'inactive':
        users = users.filter(is_active=False)

    role_filter = request.GET.get('role', '')
    if role_filter == 'admin':
        users = users.filter(is_staff=True)
    elif role_filter == 'user':
        users = users.filter(is_staff=False)

    # 페이지네이션
    paginator = Paginator(users, 20)
    page = request.GET.get('page', 1)
    users_page = paginator.get_page(page)

    context = {
        'users': users_page,
        'total_users': User.objects.count(),
        'active_users': User.objects.filter(is_active=True).count(),
        'admin_users': User.objects.filter(is_staff=True).count(),
        'search': search,
        'status_filter': status_filter,
        'role_filter': role_filter,
        'admin_menu': 'members',
    }
    return render(request, 'accounts/admin_dashboard.html', context)


@login_required
@user_passes_test(is_admin)
def user_create(request):
    """회원 등록"""
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        email = request.POST.get('email', '').strip()
        password = request.POST.get('password', '')
        password_confirm = request.POST.get('password_confirm', '')
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        is_staff = request.POST.get('is_staff') == 'on'
        is_active = request.POST.get('is_active', 'on') == 'on'

        # 유효성 검사
        errors = []
        if not username:
            errors.append('아이디를 입력하세요.')
        elif User.objects.filter(username=username).exists():
            errors.append('이미 사용 중인 아이디입니다.')

        if not password:
            errors.append('비밀번호를 입력하세요.')
        elif len(password) < 8:
            errors.append('비밀번호는 8자 이상이어야 합니다.')
        elif password != password_confirm:
            errors.append('비밀번호가 일치하지 않습니다.')

        if email and User.objects.filter(email=email).exists():
            errors.append('이미 사용 중인 이메일입니다.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'accounts/user_form.html', {
                'mode': 'create',
                'form_data': request.POST,
                'admin_menu': 'members',
            })

        # 사용자 생성
        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name
        )
        user.is_staff = is_staff
        user.is_active = is_active
        user.save()

        # DS/DX 권한 설정
        profile = get_or_create_profile(user)
        profile.can_access_dx = request.POST.get('can_access_dx') == 'on'
        profile.can_access_ds = request.POST.get('can_access_ds') == 'on'
        profile.can_access_report = request.POST.get('can_access_report') == 'on'
        profile.save()

        messages.success(request, f'회원 "{username}"이(가) 등록되었습니다.')
        return redirect('accounts:admin_dashboard')

    return render(request, 'accounts/user_form.html', {'mode': 'create', 'admin_menu': 'members'})


@login_required
@user_passes_test(is_admin)
def user_edit(request, user_id):
    """회원 수정"""
    user = get_object_or_404(User, id=user_id)

    if request.method == 'POST':
        email = request.POST.get('email', '').strip()
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        is_staff = request.POST.get('is_staff') == 'on'
        is_active = request.POST.get('is_active') == 'on'
        new_password = request.POST.get('new_password', '')

        # 유효성 검사
        errors = []
        if email and User.objects.filter(email=email).exclude(id=user_id).exists():
            errors.append('이미 사용 중인 이메일입니다.')

        if new_password and len(new_password) < 8:
            errors.append('비밀번호는 8자 이상이어야 합니다.')

        # 자기 자신의 관리자 권한은 해제 불가
        if user == request.user and not is_staff:
            errors.append('자신의 관리자 권한은 해제할 수 없습니다.')

        if errors:
            for error in errors:
                messages.error(request, error)
            return render(request, 'accounts/user_form.html', {
                'mode': 'edit',
                'edit_user': user,
                'admin_menu': 'members',
            })

        # 사용자 정보 업데이트
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        user.is_staff = is_staff
        user.is_active = is_active

        if new_password:
            user.set_password(new_password)

        user.save()

        # DS/DX 권한 및 계정 잠금 해제
        profile = get_or_create_profile(user)
        profile.can_access_dx = request.POST.get('can_access_dx') == 'on'
        profile.can_access_ds = request.POST.get('can_access_ds') == 'on'
        profile.can_access_report = request.POST.get('can_access_report') == 'on'

        # 계정 잠금 해제
        if request.POST.get('unlock_account') == 'on':
            profile.unlock_account()
        else:
            profile.save()

        messages.success(request, f'회원 "{user.username}" 정보가 수정되었습니다.')
        return redirect('accounts:admin_dashboard')

    return render(request, 'accounts/user_form.html', {
        'mode': 'edit',
        'edit_user': user,
        'admin_menu': 'members',
    })


@login_required
@user_passes_test(is_admin)
@require_POST
def user_delete(request, user_id):
    """회원 삭제"""
    user = get_object_or_404(User, id=user_id)

    # 자기 자신은 삭제 불가
    if user == request.user:
        return JsonResponse({'success': False, 'error': '자신의 계정은 삭제할 수 없습니다.'})

    username = user.username
    user.delete()

    return JsonResponse({'success': True, 'message': f'회원 "{username}"이(가) 삭제되었습니다.'})


@login_required
@user_passes_test(is_admin)
@require_POST
def user_toggle_active(request, user_id):
    """회원 활성화/비활성화 토글"""
    user = get_object_or_404(User, id=user_id)

    # 자기 자신은 비활성화 불가
    if user == request.user:
        return JsonResponse({'success': False, 'error': '자신의 계정은 비활성화할 수 없습니다.'})

    user.is_active = not user.is_active
    user.save()

    status = '활성화' if user.is_active else '비활성화'
    return JsonResponse({
        'success': True,
        'is_active': user.is_active,
        'message': f'회원 "{user.username}"이(가) {status}되었습니다.'
    })


# ============================================================
# 수집항목 관리 (monitoring_retail_columns)
# ============================================================

@login_required
@user_passes_test(is_admin)
def retail_columns(request):
    """수집항목 관리 페이지"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, product_line, column_name, retailer, duplicate_key,
                   skip_missing_check, related_columns, is_active,
                   created_id, updated_id, created_at, updated_at, memo
            FROM monitoring_retail_columns
            WHERE is_del = false
            ORDER BY product_line, retailer, column_name
        """)
        columns_desc = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns_desc, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
    except Exception as e:
        rows = []
        print(f"[ERROR] Failed to load retail columns: {e}")

    context = {
        'admin_menu': 'retail_columns',
        'rows': rows,
    }
    return render(request, 'accounts/retail_columns.html', context)


@login_required
@user_passes_test(is_admin)
@require_POST
def retail_columns_create(request):
    """수집항목 추가"""
    try:
        data = json.loads(request.body)
        product_line = data.get('product_line', '').strip().lower()
        column_name = data.get('column_name', '').strip()
        retailer = data.get('retailer', '').strip().lower()
        duplicate_key = data.get('duplicate_key', False)
        skip_missing_check = data.get('skip_missing_check', False)
        related_columns = data.get('related_columns', '').strip()
        is_active = data.get('is_active', True)
        memo = data.get('memo', '').strip()

        if not product_line or not column_name or not retailer:
            return JsonResponse({'success': False, 'error': 'product_line, column_name, retailer는 필수입니다.'})

        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_retail_columns
                (product_line, column_name, retailer, duplicate_key, skip_missing_check,
                 related_columns, is_active, created_id, updated_id, created_at, updated_at, memo)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (product_line, column_name, retailer, duplicate_key, skip_missing_check,
              related_columns or None, is_active, request.user.username, request.user.username, now, now, memo or None))
        new_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        reload_retail_columns()
        return JsonResponse({'success': True, 'id': new_id, 'message': '수집항목이 추가되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def retail_columns_update(request, column_id):
    """수집항목 수정"""
    try:
        data = json.loads(request.body)
        product_line = data.get('product_line', '').strip().lower()
        column_name = data.get('column_name', '').strip()
        retailer = data.get('retailer', '').strip().lower()
        duplicate_key = data.get('duplicate_key', False)
        skip_missing_check = data.get('skip_missing_check', False)
        related_columns = data.get('related_columns', '').strip()
        is_active = data.get('is_active', True)
        memo = data.get('memo', '').strip()

        if not product_line or not column_name or not retailer:
            return JsonResponse({'success': False, 'error': 'product_line, column_name, retailer는 필수입니다.'})

        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_retail_columns
            SET product_line = %s, column_name = %s, retailer = %s,
                duplicate_key = %s, skip_missing_check = %s,
                related_columns = %s, is_active = %s,
                updated_id = %s, updated_at = %s, memo = %s
            WHERE id = %s
        """, (product_line, column_name, retailer, duplicate_key, skip_missing_check,
              related_columns or None, is_active, request.user.username, now, memo or None, column_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_retail_columns()
        return JsonResponse({'success': True, 'message': '수집항목이 수정되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def retail_columns_delete(request, column_id):
    """수집항목 삭제"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_retail_columns
            SET is_del = true, is_active = false, updated_id = %s, updated_at = NOW()
            WHERE id = %s
        """, (request.user.username, column_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_retail_columns()
        return JsonResponse({'success': True, 'message': '수집항목이 삭제되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def retail_columns_toggle(request, column_id):
    """수집항목 활성/비활성 토글"""
    try:
        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_retail_columns
            SET is_active = NOT is_active, updated_id = %s, updated_at = %s
            WHERE id = %s
            RETURNING is_active
        """, (request.user.username, now, column_id))
        new_status = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        reload_retail_columns()
        status = '활성화' if new_status else '비활성화'
        return JsonResponse({'success': True, 'is_active': new_status, 'message': f'수집항목이 {status}되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ============================================================
# 관리자 페이지 - 누락필드 예외조건 관리
# ============================================================

@login_required
@user_passes_test(is_admin)
def exclude_rules(request):
    """누락필드 예외조건 관리 페이지"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, product_line, retailer, table_name, field_name, exclude_condition,
                   description, is_active, created_id, updated_id, created_at, updated_at
            FROM monitoring_missing_exclude_rules
            WHERE is_del = false
            ORDER BY product_line, retailer, field_name
        """)
        columns_desc = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns_desc, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
    except Exception as e:
        rows = []
        print(f"[ERROR] Failed to load exclude rules: {e}")

    context = {
        'admin_menu': 'exclude_rules',
        'rows': rows,
    }
    return render(request, 'accounts/exclude_rules.html', context)


@login_required
@user_passes_test(is_admin)
@require_POST
def exclude_rules_create(request):
    """예외조건 추가"""
    try:
        data = json.loads(request.body)
        product_line = data.get('product_line', '').strip().lower()
        retailer = data.get('retailer', '').strip()
        table_name = data.get('table_name', '').strip()
        field_name = data.get('field_name', '').strip()
        exclude_condition = data.get('exclude_condition', '').strip()
        description = data.get('description', '').strip()
        is_active = data.get('is_active', True)

        if not product_line or not retailer or not table_name or not field_name or not exclude_condition:
            return JsonResponse({'success': False, 'error': 'product_line, retailer, table_name, field_name, exclude_condition은 필수입니다.'})

        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_missing_exclude_rules
                (product_line, retailer, table_name, field_name, exclude_condition, description,
                 is_active, created_id, updated_id, created_at, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (product_line, retailer, table_name, field_name, exclude_condition, description or None,
              is_active, request.user.username, request.user.username, now, now))
        new_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        reload_missing_exclude_rules()
        return JsonResponse({'success': True, 'id': new_id, 'message': '예외조건이 추가되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def exclude_rules_update(request, rule_id):
    """예외조건 수정"""
    try:
        data = json.loads(request.body)
        product_line = data.get('product_line', '').strip().lower()
        retailer = data.get('retailer', '').strip()
        table_name = data.get('table_name', '').strip()
        field_name = data.get('field_name', '').strip()
        exclude_condition = data.get('exclude_condition', '').strip()
        description = data.get('description', '').strip()
        is_active = data.get('is_active', True)

        if not product_line or not retailer or not table_name or not field_name or not exclude_condition:
            return JsonResponse({'success': False, 'error': 'product_line, retailer, table_name, field_name, exclude_condition은 필수입니다.'})

        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_missing_exclude_rules
            SET product_line = %s, retailer = %s, table_name = %s, field_name = %s,
                exclude_condition = %s, description = %s, is_active = %s,
                updated_id = %s, updated_at = %s
            WHERE id = %s
        """, (product_line, retailer, table_name, field_name, exclude_condition, description or None,
              is_active, request.user.username, now, rule_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_missing_exclude_rules()
        return JsonResponse({'success': True, 'message': '예외조건이 수정되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def exclude_rules_delete(request, rule_id):
    """예외조건 삭제"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_missing_exclude_rules
            SET is_del = true, is_active = false, updated_id = %s, updated_at = NOW()
            WHERE id = %s
        """, (request.user.username, rule_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_missing_exclude_rules()
        return JsonResponse({'success': True, 'message': '예외조건이 삭제되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def exclude_rules_toggle(request, rule_id):
    """예외조건 활성/비활성 토글"""
    try:
        now = datetime.now()
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_missing_exclude_rules
            SET is_active = NOT is_active, updated_id = %s, updated_at = %s
            WHERE id = %s
            RETURNING is_active
        """, (request.user.username, now, rule_id))
        new_status = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        reload_missing_exclude_rules()
        status = '활성화' if new_status else '비활성화'
        return JsonResponse({'success': True, 'is_active': new_status, 'message': f'예외조건이 {status}되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ============================================================
# 관리자 페이지 - DS 스케줄 설정 (ds_monitoring_targets)
# ============================================================

@login_required
@user_passes_test(is_admin)
def schedule_settings(request):
    """DS 스케줄 설정 페이지"""
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT retailer_id AS id, table_name, retailer, region, korea_time, local_time,
                   country, mall_name, is_active, updated_id, updated_at
            FROM ssd_crawl_db.ds_monitoring_targets
            WHERE is_del = false
            ORDER BY retailer_id
        """)
        columns_desc = [desc[0] for desc in cursor.description]
        rows = []
        for row in cursor.fetchall():
            d = dict(zip(columns_desc, row))
            d['korea_time'] = format_time(d['korea_time'])
            d['local_time'] = format_time(d['local_time'])
            d['is_active'] = bool(d['is_active'])
            rows.append(d)
        cursor.close()
        conn.close()
    except Exception as e:
        rows = []
        print(f"[ERROR] Failed to load schedule settings: {e}")

    context = {
        'admin_menu': 'schedule',
        'rows': rows,
    }
    return render(request, 'accounts/schedule_settings.html', context)


@login_required
@user_passes_test(is_admin)
@require_POST
def schedule_settings_create(request):
    """DS 스케줄 추가"""
    try:
        data = json.loads(request.body)
        table_name = data.get('table_name', '').strip()
        retailer = data.get('retailer', '').strip()
        region = data.get('region', '').strip()
        korea_time = data.get('korea_time', '').strip()
        local_time = data.get('local_time', '').strip()
        country = data.get('country', '').strip()
        mall_name = data.get('mall_name', '').strip()
        is_active = data.get('is_active', True)

        if not table_name or not retailer or not country or not mall_name:
            return JsonResponse({'success': False, 'error': 'table_name, retailer, country, mall_name은 필수입니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_targets
                (table_name, retailer, region, korea_time, local_time, country, mall_name, is_active,
                 updated_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (table_name, retailer, region or None, korea_time or None, local_time or None,
              country, mall_name, is_active, request.user.username, datetime.now()))
        new_id = cursor.lastrowid
        conn.commit()
        cursor.close()
        conn.close()

        reload_targets()
        return JsonResponse({'success': True, 'id': new_id, 'message': '스케줄이 추가되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def schedule_settings_update(request, target_id):
    """DS 스케줄 수정"""
    try:
        data = json.loads(request.body)
        table_name = data.get('table_name', '').strip()
        retailer = data.get('retailer', '').strip()
        region = data.get('region', '').strip()
        korea_time = data.get('korea_time', '').strip()
        local_time = data.get('local_time', '').strip()
        country = data.get('country', '').strip()
        mall_name = data.get('mall_name', '').strip()
        is_active = data.get('is_active', True)

        if not table_name or not retailer or not country or not mall_name:
            return JsonResponse({'success': False, 'error': 'table_name, retailer, country, mall_name은 필수입니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_targets
            SET table_name = %s, retailer = %s, region = %s,
                korea_time = %s, local_time = %s,
                country = %s, mall_name = %s, is_active = %s,
                updated_id = %s, updated_at = %s
            WHERE retailer_id = %s
        """, (table_name, retailer, region or None, korea_time or None, local_time or None,
              country, mall_name, is_active, request.user.username, datetime.now(), target_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_targets()
        return JsonResponse({'success': True, 'message': '스케줄이 수정되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def schedule_settings_delete(request, target_id):
    """DS 스케줄 삭제"""
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_targets
            SET is_del = true, is_active = false, updated_id = %s, updated_at = NOW()
            WHERE retailer_id = %s
        """, (request.user.username, target_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_targets()
        return JsonResponse({'success': True, 'message': '스케줄이 삭제되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def schedule_settings_toggle(request, target_id):
    """DS 스케줄 활성/비활성 토글"""
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        # MySQL: 현재 값 조회 후 반전
        cursor.execute("SELECT is_active FROM ssd_crawl_db.ds_monitoring_targets WHERE retailer_id = %s", (target_id,))
        current = cursor.fetchone()
        if not current:
            return JsonResponse({'success': False, 'error': '해당 스케줄을 찾을 수 없습니다.'})
        new_status = not bool(current[0])
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_targets
            SET is_active = %s, updated_id = %s, updated_at = %s
            WHERE retailer_id = %s
        """, (new_status, request.user.username, datetime.now(), target_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_targets()
        status = '활성화' if new_status else '비활성화'
        return JsonResponse({'success': True, 'is_active': new_status, 'message': f'스케줄이 {status}되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# ============================================================
# 관리자 페이지 - DX 수집 스케줄 설정 (monitoring_collection_schedule)
# ============================================================

@login_required
@user_passes_test(is_admin)
def dx_schedule_settings(request):
    """DX 수집 스케줄 설정 페이지"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, check_type, name, category, us_start_hour,
                   collection_duration_min, schedule_type, description,
                   is_active, updated_id, updated_at
            FROM monitoring_collection_schedule
            WHERE is_del = false
            ORDER BY id
        """)
        columns_desc = [desc[0] for desc in cursor.description]
        rows = [dict(zip(columns_desc, row)) for row in cursor.fetchall()]
        cursor.close()
        conn.close()
    except Exception as e:
        rows = []
        print(f"[ERROR] Failed to load DX schedule settings: {e}")

    context = {
        'admin_menu': 'dx_schedule',
        'rows': rows,
    }
    return render(request, 'accounts/dx_schedule_settings.html', context)


@login_required
@user_passes_test(is_admin)
@require_POST
def dx_schedule_settings_create(request):
    """DX 수집 스케줄 추가"""
    try:
        data = json.loads(request.body)
        check_type = data.get('check_type', '').strip()
        name = data.get('name', '').strip()
        category = data.get('category', '').strip()
        us_start_hour = data.get('us_start_hour')
        collection_duration_min = data.get('collection_duration_min')
        schedule_type = data.get('schedule_type', '').strip()
        description = data.get('description', '').strip()
        is_active = data.get('is_active', True)

        if not check_type or not name:
            return JsonResponse({'success': False, 'error': 'check_type, name은 필수입니다.'})

        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO monitoring_collection_schedule
                (check_type, name, category, us_start_hour, collection_duration_min,
                 schedule_type, description, is_active, updated_id, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (check_type, name, category or None, us_start_hour, collection_duration_min,
              schedule_type or None, description or None, is_active,
              request.user.username, datetime.now()))
        new_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
        conn.close()

        reload_schedules()
        return JsonResponse({'success': True, 'id': new_id, 'message': '스케줄이 추가되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def dx_schedule_settings_update(request, schedule_id):
    """DX 수집 스케줄 수정"""
    try:
        data = json.loads(request.body)
        check_type = data.get('check_type', '').strip()
        name = data.get('name', '').strip()
        category = data.get('category', '').strip()
        us_start_hour = data.get('us_start_hour')
        collection_duration_min = data.get('collection_duration_min')
        schedule_type = data.get('schedule_type', '').strip()
        description = data.get('description', '').strip()
        is_active = data.get('is_active', True)

        if not check_type or not name:
            return JsonResponse({'success': False, 'error': 'check_type, name은 필수입니다.'})

        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_collection_schedule
            SET check_type = %s, name = %s, category = %s,
                us_start_hour = %s, collection_duration_min = %s,
                schedule_type = %s, description = %s, is_active = %s,
                updated_id = %s, updated_at = %s
            WHERE id = %s
        """, (check_type, name, category or None, us_start_hour, collection_duration_min,
              schedule_type or None, description or None, is_active,
              request.user.username, datetime.now(), schedule_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_schedules()
        return JsonResponse({'success': True, 'message': '스케줄이 수정되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def dx_schedule_settings_delete(request, schedule_id):
    """DX 수집 스케줄 삭제"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_collection_schedule
            SET is_del = true, is_active = false, updated_id = %s, updated_at = NOW()
            WHERE id = %s
        """, (request.user.username, schedule_id))
        conn.commit()
        cursor.close()
        conn.close()

        reload_schedules()
        return JsonResponse({'success': True, 'message': '스케줄이 삭제되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def dx_schedule_settings_toggle(request, schedule_id):
    """DX 수집 스케줄 활성/비활성 토글"""
    try:
        conn = get_dx_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE monitoring_collection_schedule
            SET is_active = NOT is_active, updated_id = %s, updated_at = %s
            WHERE id = %s
            RETURNING is_active
        """, (request.user.username, datetime.now(), schedule_id))
        result = cursor.fetchone()
        if not result:
            return JsonResponse({'success': False, 'error': '해당 스케줄을 찾을 수 없습니다.'})
        new_status = result[0]
        conn.commit()
        cursor.close()
        conn.close()

        reload_schedules()
        status = '활성화' if new_status else '비활성화'
        return JsonResponse({'success': True, 'is_active': new_status, 'message': f'스케줄이 {status}되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# =====================================================
# DS 이상치 원인 옵션 관리
# =====================================================

@login_required
@user_passes_test(is_admin)
def anomaly_causes(request):
    """이상치 원인 옵션 관리 페이지"""
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 필터링
        retailer_filter = request.GET.get('retailer', '')

        # 원인 옵션 목록 조회 (JOIN으로 retailer 이름 가져오기)
        if retailer_filter:
            cursor.execute("""
                SELECT o.option_id, t.retailer, o.option_name, o.sort_order, o.is_active, o.created_at, o.retailer_id
                FROM ssd_crawl_db.ds_monitoring_anomaly_causes_options o
                JOIN ssd_crawl_db.ds_monitoring_targets t ON o.retailer_id = t.retailer_id
                WHERE t.retailer = %s
                ORDER BY o.sort_order, o.option_id
            """, (retailer_filter,))
        else:
            cursor.execute("""
                SELECT o.option_id, t.retailer, o.option_name, o.sort_order, o.is_active, o.created_at, o.retailer_id
                FROM ssd_crawl_db.ds_monitoring_anomaly_causes_options o
                JOIN ssd_crawl_db.ds_monitoring_targets t ON o.retailer_id = t.retailer_id
                ORDER BY t.sort_order, t.retailer, o.sort_order, o.option_id
            """)

        causes = []
        for row in cursor.fetchall():
            causes.append({
                'option_id': row[0],
                'retailer': row[1],
                'option_name': row[2],
                'sort_order': row[3],
                'is_active': row[4],
                'created_at': row[5],
                'retailer_id': row[6]
            })

        # 모니터링 대상 리테일러 목록 (필터 및 추가용)
        cursor.execute("""
            SELECT retailer_id, retailer FROM ssd_crawl_db.ds_monitoring_targets
            WHERE is_active = 1
            ORDER BY sort_order, retailer
        """)
        all_retailers = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
        retailers = [r['name'] for r in all_retailers]

        cursor.close()
        conn.close()

        return render(request, 'accounts/anomaly_causes.html', {
            'causes': causes,
            'retailers': retailers,
            'all_retailers': all_retailers,
            'retailer_filter': retailer_filter,
            'total_count': len(causes),
            'admin_menu': 'anomaly_causes'
        })
    except Exception as e:
        messages.error(request, f'오류가 발생했습니다: {str(e)}')
        return render(request, 'accounts/anomaly_causes.html', {
            'causes': [],
            'retailers': [],
            'all_retailers': [],
            'retailer_filter': '',
            'total_count': 0,
            'admin_menu': 'anomaly_causes'
        })


@login_required
@user_passes_test(is_admin)
@require_POST
def anomaly_causes_create(request):
    """이상치 원인 옵션 추가"""
    try:
        data = json.loads(request.body)
        retailer_id = data.get('retailer_id')
        option_name = data.get('option_name')
        sort_order = data.get('sort_order', 0)

        if not retailer_id or not option_name:
            return JsonResponse({'success': False, 'error': '리테일러와 원인 옵션은 필수입니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')

        # 중복 체크
        cursor.execute("""
            SELECT option_id FROM ssd_crawl_db.ds_monitoring_anomaly_causes_options
            WHERE retailer_id = %s AND option_name = %s
        """, (retailer_id, option_name))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '이미 등록된 원인 옵션입니다.'})

        cursor.execute("""
            INSERT INTO ssd_crawl_db.ds_monitoring_anomaly_causes_options
            (retailer_id, option_name, sort_order, is_active, created_at)
            VALUES (%s, %s, %s, 1, %s)
        """, (retailer_id, option_name, sort_order, now))
        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'message': '원인 옵션이 추가되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def anomaly_causes_update(request, cause_id):
    """이상치 원인 옵션 수정"""
    try:
        data = json.loads(request.body)
        option_name = data.get('option_name')
        sort_order = data.get('sort_order', 0)

        if not option_name:
            return JsonResponse({'success': False, 'error': '원인 옵션은 필수입니다.'})

        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_anomaly_causes_options
            SET option_name = %s, sort_order = %s
            WHERE option_id = %s
        """, (option_name, sort_order, cause_id))
        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'message': '원인 옵션이 수정되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def anomaly_causes_delete(request, cause_id):
    """이상치 원인 옵션 삭제"""
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM ssd_crawl_db.ds_monitoring_anomaly_causes_options
            WHERE option_id = %s
        """, (cause_id,))
        conn.commit()
        cursor.close()
        conn.close()

        return JsonResponse({'success': True, 'message': '원인 옵션이 삭제되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@login_required
@user_passes_test(is_admin)
@require_POST
def anomaly_causes_toggle(request, cause_id):
    """이상치 원인 옵션 활성/비활성 토글"""
    try:
        conn = get_ds_connection()
        cursor = conn.cursor()

        # 현재 상태 조회
        cursor.execute("""
            SELECT is_active FROM ssd_crawl_db.ds_monitoring_anomaly_causes_options
            WHERE option_id = %s
        """, (cause_id,))
        row = cursor.fetchone()
        if not row:
            cursor.close()
            conn.close()
            return JsonResponse({'success': False, 'error': '해당 원인 옵션을 찾을 수 없습니다.'})

        new_status = 0 if row[0] else 1
        cursor.execute("""
            UPDATE ssd_crawl_db.ds_monitoring_anomaly_causes_options
            SET is_active = %s
            WHERE option_id = %s
        """, (new_status, cause_id))
        conn.commit()
        cursor.close()
        conn.close()

        status = '활성화' if new_status else '비활성화'
        return JsonResponse({'success': True, 'is_active': new_status, 'message': f'원인 옵션이 {status}되었습니다.'})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})
