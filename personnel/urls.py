from django.urls import path
from .views import (
    ResumeCandidateListView,
    ResumeCandidateKanbanView,
    ResumeCandidateCreateView,
    ResumeCandidateUpdateView,
    ResumeCandidateDeleteView,
    ResumeCandidateStageUpdateView,
    ResumeCandidateKanbanReorderView,
)

app_name = 'personnel'

urlpatterns = [
    # Новый модуль "Резюме / Подбор персонала"
    path('resume/', ResumeCandidateListView.as_view(), name='resume_candidate_list'),
    path('resume/kanban/', ResumeCandidateKanbanView.as_view(), name='resume_candidate_kanban'),
    path('resume/add/', ResumeCandidateCreateView.as_view(), name='resume_candidate_add'),
    path('resume/<int:pk>/edit/', ResumeCandidateUpdateView.as_view(), name='resume_candidate_edit'),
    path('resume/<int:pk>/delete/', ResumeCandidateDeleteView.as_view(), name='resume_candidate_delete'),
    path('resume/<int:pk>/stage/<str:stage>/', ResumeCandidateStageUpdateView.as_view(), name='resume_candidate_stage'),

    # Новый AJAX endpoint для drag-and-drop
    path('resume/kanban/reorder/', ResumeCandidateKanbanReorderView.as_view(), name='resume_candidate_kanban_reorder'),

    # Алиасы для совместимости со старыми ссылками
    path('records/', ResumeCandidateListView.as_view(), name='record_list'),
    path('records/add/', ResumeCandidateCreateView.as_view(), name='record_create'),
]