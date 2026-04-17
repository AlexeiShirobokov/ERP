import json
import os

from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q, Max
from django.http import FileResponse, Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView, TemplateView

from .forms import ResumeCandidateForm, ResumeCandidateDocumentForm
from .models import ResumeCandidate, ResumeCandidateDocument


class ResumeCandidateListView(LoginRequiredMixin, ListView):
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_list.html'
    context_object_name = 'candidates'
    paginate_by = 50

    def get_queryset(self):
        queryset = ResumeCandidate.objects.all().prefetch_related('documents').order_by('-date', '-id')

        q = self.request.GET.get('q', '').strip()
        stage = self.request.GET.get('stage', '').strip()
        medical = self.request.GET.get('medical', '').strip()

        if q:
            queryset = queryset.filter(
                Q(full_name__icontains=q) |
                Q(hh_vacancy__icontains=q) |
                Q(position__icontains=q) |
                Q(contacts__icontains=q) |
                Q(ticket__icontains=q)
            )

        if stage:
            queryset = queryset.filter(stage=stage)

        if medical:
            queryset = queryset.filter(medical_commission=medical)

        return queryset

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['q'] = self.request.GET.get('q', '')
        context['stage'] = self.request.GET.get('stage', '')
        context['medical'] = self.request.GET.get('medical', '')
        context['stage_choices'] = ResumeCandidate.STAGE_CHOICES
        context['medical_choices'] = ResumeCandidate.MEDICAL_CHOICES
        return context


class ResumeCandidateKanbanView(LoginRequiredMixin, TemplateView):
    template_name = 'personnel/resume_candidate_kanban.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        columns = []
        for stage_code, stage_name in ResumeCandidate.STAGE_CHOICES:
            items = ResumeCandidate.objects.filter(stage=stage_code).order_by('sort_order', '-date', '-id')
            columns.append({
                'code': stage_code,
                'name': stage_name,
                'items': items,
                'count': items.count(),
            })

        context['columns'] = columns
        return context


class ResumeCandidateDetailView(LoginRequiredMixin, DetailView):
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_detail.html'
    context_object_name = 'record'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = self.object.documents.all()
        context['document_form'] = ResumeCandidateDocumentForm()
        return context


class ResumeCandidateCreateView(LoginRequiredMixin, CreateView):
    model = ResumeCandidate
    form_class = ResumeCandidateForm
    template_name = 'personnel/resume_candidate_form.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = []
        context['document_form'] = None
        context['is_create'] = True
        return context

    def form_valid(self, form):
        response = super().form_valid(form)

        document_file = form.cleaned_data.get('document_file')
        document_title = form.cleaned_data.get('document_title')
        document_comment = form.cleaned_data.get('document_comment')

        if document_file:
            ResumeCandidateDocument.objects.create(
                record=self.object,
                title=document_title or document_file.name,
                file=document_file,
                comment=document_comment or '',
                uploaded_by=self.request.user if self.request.user.is_authenticated else None,
            )

        return response

    def get_success_url(self):
        return reverse_lazy('personnel:resume_candidate_edit', kwargs={'pk': self.object.pk})


class ResumeCandidateUpdateView(LoginRequiredMixin, UpdateView):
    model = ResumeCandidate
    form_class = ResumeCandidateForm
    template_name = 'personnel/resume_candidate_form.html'
    success_url = reverse_lazy('personnel:resume_candidate_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['documents'] = self.object.documents.all()
        context['document_form'] = ResumeCandidateDocumentForm()
        context['is_create'] = False
        return context


class ResumeCandidateDeleteView(LoginRequiredMixin, DeleteView):
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_confirm_delete.html'
    success_url = reverse_lazy('personnel:resume_candidate_list')


class ResumeCandidateStageUpdateView(LoginRequiredMixin, View):
    def post(self, request, pk, stage):
        candidate = get_object_or_404(ResumeCandidate, pk=pk)
        valid_stages = [item[0] for item in ResumeCandidate.STAGE_CHOICES]

        if stage not in valid_stages:
            return JsonResponse({'status': 'error', 'message': 'Некорректный этап'}, status=400)

        candidate.stage = stage
        last_sort = ResumeCandidate.objects.filter(stage=stage).aggregate(
            max_sort=Max('sort_order')
        )['max_sort'] or 0
        candidate.sort_order = last_sort + 1
        candidate.save()

        if request.headers.get('x-requested-with') == 'XMLHttpRequest':
            return JsonResponse({'status': 'ok'})

        return redirect('personnel:resume_candidate_kanban')


class ResumeCandidateKanbanReorderView(LoginRequiredMixin, View):
    def post(self, request):
        try:
            data = json.loads(request.body)
            candidate_id = data.get('candidate_id')
            new_stage = data.get('new_stage')
            ordered_ids = data.get('ordered_ids', [])

            if not candidate_id or not new_stage or not isinstance(ordered_ids, list):
                return JsonResponse({'status': 'error', 'message': 'Некорректные данные'}, status=400)

            valid_stages = [item[0] for item in ResumeCandidate.STAGE_CHOICES]
            if new_stage not in valid_stages:
                return JsonResponse({'status': 'error', 'message': 'Некорректный этап'}, status=400)

            candidate = get_object_or_404(ResumeCandidate, pk=candidate_id)
            candidate.stage = new_stage
            candidate.save()

            for index, item_id in enumerate(ordered_ids, start=1):
                ResumeCandidate.objects.filter(pk=item_id).update(
                    stage=new_stage,
                    sort_order=index
                )

            return JsonResponse({'status': 'ok'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)


class ResumeCandidateDocumentUploadView(LoginRequiredMixin, View):
    def post(self, request, pk):
        record = get_object_or_404(ResumeCandidate, pk=pk)
        form = ResumeCandidateDocumentForm(request.POST, request.FILES)

        if form.is_valid():
            document = form.save(commit=False)
            document.record = record
            document.uploaded_by = request.user
            document.save()

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)

        return redirect('personnel:resume_candidate_edit', pk=record.pk)


class ResumeCandidateDocumentDownloadView(LoginRequiredMixin, View):
    def get(self, request, pk):
        document = get_object_or_404(ResumeCandidateDocument, pk=pk)

        if not document.file:
            raise Http404('Файл не найден')

        file_handle = document.file.open('rb')
        filename = os.path.basename(document.file.name)
        return FileResponse(file_handle, as_attachment=True, filename=filename)


class ResumeCandidateDocumentDeleteView(LoginRequiredMixin, View):
    def post(self, request, pk):
        document = get_object_or_404(ResumeCandidateDocument, pk=pk)
        record_pk = document.record.pk

        if document.file:
            document.file.delete(save=False)

        document.delete()

        next_url = request.POST.get('next')
        if next_url:
            return redirect(next_url)

        return redirect('personnel:resume_candidate_edit', pk=record_pk)