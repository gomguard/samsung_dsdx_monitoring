from django.shortcuts import render


def index(request):
    context = {
        'layer': {
            'number': 4,
            'name': 'LLM 의미 검증',
            'name_en': 'LLM Semantic Validation',
            'color': '#764ba2'
        }
    }
    return render(request, 'layer4/index.html', context)
