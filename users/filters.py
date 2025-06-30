import django_filters
from .models import ProfessionalService

class ProfessionalServiceFilter(django_filters.FilterSet):
    min_price = django_filters.NumberFilter(field_name='fixed_price', lookup_expr='gte')
    max_price = django_filters.NumberFilter(field_name='fixed_price', lookup_expr='lte')
    category = django_filters.CharFilter(field_name='category__name')

    class Meta:
        model = ProfessionalService
        fields = ['min_price', 'max_price', 'category']
