import json
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, TemplateView

from .forms import ResumeCandidateForm
from .models import ResumeCandidate


class ResumeCandidateListView(LoginRequiredMixin, ListView):
    model = ResumeCandidate
    template_name = 'personnel/resume_candidate_list.html'
    context_object_name = 'candidates'
    paginate_by = 50

    def get_queryset(self):
        queryset = ResumeCandidate.objects.all().order_by('-date', '-id')

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


class ResumeCandidateCreateView(LoginRequiredMixin, CreateView):
    model = ResumeCandidate
    form_class = ResumeCandidateForm
    template_name = 'personnel/resume_candidate_form.html'
    success_url = reverse_lazy('personnel:resume_candidate_list')


class ResumeCandidateUpdateView(LoginRequiredMixin, UpdateView):
    model = ResumeCandidate
    form_class = ResumeCandidateForm
    template_name = 'personnel/resume_candidate_form.html'
    success_url = reverse_lazy('personnel:resume_candidate_list')


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
        max_sort = ResumeCandidate.objects.filter(stage=stage).aggregate(
            max_sort=Q()
        )

        last_sort = ResumeCandidate.objects.filter(stage=stage).order_by('-sort_order').first()
        candidate.sort_order = (last_sort.sort_order + 1) if last_sort else 1
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

            # Обновляем порядок карточек в целевой колонке
            for index, item_id in enumerate(ordered_ids, start=1):
                ResumeCandidate.objects.filter(pk=item_id).update(
                    stage=new_stage,
                    sort_order=index
                )

            return JsonResponse({'status': 'ok'})

        except Exception as e:
            return JsonResponse({'status': 'error', 'message': str(e)}, status=500)