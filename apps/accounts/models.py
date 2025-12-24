"""
사용자 프로필 모델
DS/DX 접근 권한, 로그인 실패 횟수, 계정 잠금 관리
"""

from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone


class UserProfile(models.Model):
    """
    사용자 프로필 확장 모델
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')

    # 접근 권한
    can_access_dx = models.BooleanField(default=False, verbose_name='DX 접근 권한')
    can_access_ds = models.BooleanField(default=False, verbose_name='DS 접근 권한')

    # 로그인 실패 관리
    failed_login_attempts = models.IntegerField(default=0, verbose_name='로그인 실패 횟수')
    is_locked = models.BooleanField(default=False, verbose_name='계정 잠금')
    locked_at = models.DateTimeField(null=True, blank=True, verbose_name='잠금 시간')

    # 마지막 활동 시간
    last_activity = models.DateTimeField(null=True, blank=True, verbose_name='마지막 활동')

    class Meta:
        verbose_name = '사용자 프로필'
        verbose_name_plural = '사용자 프로필'

    def __str__(self):
        return f'{self.user.username} 프로필'

    def increment_failed_attempts(self):
        """로그인 실패 횟수 증가, 5회 이상이면 계정 잠금"""
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= 5:
            self.is_locked = True
            self.locked_at = timezone.now()
        self.save()

    def reset_failed_attempts(self):
        """로그인 성공 시 실패 횟수 초기화"""
        self.failed_login_attempts = 0
        self.save()

    def unlock_account(self):
        """계정 잠금 해제 (관리자용)"""
        self.is_locked = False
        self.locked_at = None
        self.failed_login_attempts = 0
        self.save()

    def update_activity(self):
        """마지막 활동 시간 업데이트"""
        self.last_activity = timezone.now()
        self.save()


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """User 생성 시 자동으로 UserProfile 생성"""
    if created:
        UserProfile.objects.create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    """User 저장 시 UserProfile도 저장"""
    if hasattr(instance, 'profile'):
        instance.profile.save()
