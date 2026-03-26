from django.shortcuts import render
from apps.dx.dx_layer2.common.context import build_context


def anomaly_validation(request):
    """중복 검증"""
    return render(request, 'layer2_anomaly_validation.html', build_context('anomaly_validation', request))
