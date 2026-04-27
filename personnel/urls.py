from django.urls import path

from .views import (
    ResumeCandidateCheckOtipbView,
    ResumeCandidateCreateView,
    ResumeCandidateDeleteView,
    ResumeCandidateDetailView,
    ResumeCandidateDocumentDeleteView,
    ResumeCandidateDocumentDownloadView,
    ResumeCandidateDocumentPreviewView,
    ResumeCandidateDocumentUploadView,
    ResumeCandidateExportExcelView,
    ResumeCandidateKanbanReorderView,
    ResumeCandidateKanbanView,
    ResumeCandidateListView,
    ResumeCandidateStageUpdateView,
    ResumeCandidateUpdateView,
    ResumeStageCreateView,
    ResumeStageDeleteView,
    ResumeStageListView,
    ResumeStageUpdateView,
)

app_name = 'personnel'

urlpatterns = [
    path('resume/', ResumeCandidateListView.as_view(), name='resume_candidate_list'),
    path('resume/export/excel/', ResumeCandidateExportExcelView.as_view(), name='resume_candidate_export_excel'),
    path('resume/kanban/', ResumeCandidateKanbanView.as_view(), name='resume_candidate_kanban'),
    path('resume/kanban/reorder/', ResumeCandidateKanbanReorderView.as_view(), name='resume_candidate_kanban_reorder'),
    path('resume/check-otipb/', ResumeCandidateCheckOtipbView.as_view(), name='resume_candidate_check_otipb'),
    path('resume/add/', ResumeCandidateCreateView.as_view(), name='resume_candidate_add'),
    path('resume/<int:pk>/', ResumeCandidateDetailView.as_view(), name='resume_candidate_detail'),
    path('resume/<int:pk>/edit/', ResumeCandidateUpdateView.as_view(), name='resume_candidate_edit'),
    path('resume/<int:pk>/delete/', ResumeCandidateDeleteView.as_view(), name='resume_candidate_delete'),
    path('resume/<int:pk>/stage/<str:stage>/', ResumeCandidateStageUpdateView.as_view(), name='resume_candidate_stage'),
    path('resume/<int:pk>/documents/upload/', ResumeCandidateDocumentUploadView.as_view(), name='document_upload'),
    path('resume/documents/<int:pk>/preview/', ResumeCandidateDocumentPreviewView.as_view(), name='document_preview'),
    path('resume/documents/<int:pk>/download/', ResumeCandidateDocumentDownloadView.as_view(), name='document_download'),
    path('resume/documents/<int:pk>/delete/', ResumeCandidateDocumentDeleteView.as_view(), name='document_delete'),
    path('stages/', ResumeStageListView.as_view(), name='resume_stage_list'),
    path('stages/add/', ResumeStageCreateView.as_view(), name='resume_stage_add'),
    path('stages/<int:pk>/edit/', ResumeStageUpdateView.as_view(), name='resume_stage_edit'),
    path('stages/<int:pk>/delete/', ResumeStageDeleteView.as_view(), name='resume_stage_delete'),
    path('records/', ResumeCandidateListView.as_view(), name='record_list'),
    path('records/add/', ResumeCandidateCreateView.as_view(), name='record_create'),
]
