"""DS Layer 2 API"""
from django.http import JsonResponse

def layer_stats(request):
    return JsonResponse({'message': 'DS Layer 2 API - 준비 중'})
