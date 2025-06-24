from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import DocumentViewSet, QuestionAnswerViewSet, index_view

router = DefaultRouter()
router.register(r'documents', DocumentViewSet)
router.register(r'qa', QuestionAnswerViewSet)

urlpatterns = [
    path('', index_view, name='index'), # 為前端頁面新增路由
    path('api/', include(router.urls)),
]