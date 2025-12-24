"""DS Layer 4 API"""
from django.http import JsonResponse

def layer_stats(request):
    return JsonResponse({'message': 'DS Layer 4 API - 준비 중'})
