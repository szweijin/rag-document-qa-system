from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Document, QuestionAnswer
from .serializers import DocumentSerializer, QuestionAnswerSerializer
from .tasks import parse_and_vectorize_document_task, answer_question_with_rag_task
from django.shortcuts import render # 用於前端頁面

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all().order_by('-uploaded_at')
    serializer_class = DocumentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        # 啟動 Celery 任務來處理文件
        document_id = serializer.instance.id
        parse_and_vectorize_document_task.delay(str(document_id)) # 使用 .delay 觸發非同步任務

        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

class QuestionAnswerViewSet(viewsets.ModelViewSet):
    queryset = QuestionAnswer.objects.all().order_by('-created_at')
    serializer_class = QuestionAnswerSerializer

    def create(self, request, *args, **kwargs):
        document_id = request.data.get('document')
        question = request.data.get('question')

        if not document_id or not question:
            return Response({"detail": "document_id and question are required."},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            document = Document.objects.get(id=document_id)
            if document.status != 'COMPLETED':
                return Response({"detail": "Document not yet processed or failed. Please wait or check document status."},
                                status=status.HTTP_400_BAD_REQUEST)
        except Document.DoesNotExist:
            return Response({"detail": "Document not found."},
                            status=status.HTTP_404_NOT_FOUND)

        # 創建 QA 實例並設置為 PENDING
        qa_instance = QuestionAnswer.objects.create(
            document=document,
            question=question,
            status='PENDING'
        )
        serializer = self.get_serializer(qa_instance)

        # 啟動 Celery 任務來回答問題
        answer_question_with_rag_task.delay(str(qa_instance.id), str(document_id), question)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

def index_view(request):
    return render(request, 'rag_app/index.html')