"""DS Layer 3 API"""
from django.http import JsonResponse

def layer_stats(request):
    return JsonResponse({'message': 'DS Layer 3 API - 준비 중'})
