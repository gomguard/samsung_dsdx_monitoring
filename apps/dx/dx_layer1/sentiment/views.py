from django.shortcuts import render
from apps.dx.dx_layer1.common.context import build_context


def sentiment(request):
    """Sentiment 검증"""
    return render(request, 'dx_layer1_sentiment.html', build_context('sentiment', request))
