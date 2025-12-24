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
import json


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
                'form_data': request.POST
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
        profile.save()

        messages.success(request, f'회원 "{username}"이(가) 등록되었습니다.')
        return redirect('accounts:admin_dashboard')

    return render(request, 'accounts/user_form.html', {'mode': 'create'})


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
                'edit_user': user
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

        # 계정 잠금 해제
        if request.POST.get('unlock_account') == 'on':
            profile.unlock_account()
        else:
            profile.save()

        messages.success(request, f'회원 "{user.username}" 정보가 수정되었습니다.')
        return redirect('accounts:admin_dashboard')

    return render(request, 'accounts/user_form.html', {
        'mode': 'edit',
        'edit_user': user
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
