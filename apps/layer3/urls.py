from django.urls import path
from . import views
from .api import views as api_views

app_name = 'layer3'

urlpatterns = [
    path('', views.index, name='index'),
    path('api/stats/', api_views.layer_stats, name='api_stats'),
    path('api/price-anomalies/', api_views.price_anomalies, name='api_price_anomalies'),
    path('api/price-changes/', api_views.price_changes, name='api_price_changes'),
    path('api/cross-field-detail/', api_views.cross_field_detail, name='api_cross_field_detail'),
    path('api/sentiment-cross-detail/', api_views.sentiment_cross_detail, name='api_sentiment_cross_detail'),
    path('api/comp-product-cross-detail/', api_views.comp_product_cross_detail, name='api_comp_product_cross_detail'),
    path('api/time-series-detail/', api_views.time_series_detail, name='api_time_series_detail'),
    path('api/duplicate-detail/', api_views.duplicate_detail, name='api_duplicate_detail'),
    path('api/review-change-detail/', api_views.review_change_detail, name='api_review_change_detail'),
    path('api/category-spec-detail/', api_views.category_spec_detail, name='api_category_spec_detail'),
    path('api/field-missing/', api_views.field_missing_detection, name='api_field_missing'),
    path('api/field-missing-detail-all/', api_views.field_missing_detail_all, name='api_field_missing_detail_all'),
    path('api/field-missing-detail-problem/', api_views.field_missing_detail_problem, name='api_field_missing_detail_problem'),
    path('api/field-missing-detail-by-field/', api_views.field_missing_detail_by_field, name='api_field_missing_detail_by_field'),
    path('api/crossfield-rules/', api_views.crossfield_rules, name='api_crossfield_rules'),
    path('api/category-rules/', api_views.category_rules, name='api_category_rules'),
]
