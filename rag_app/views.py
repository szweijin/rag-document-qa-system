from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from .models import Document, QuestionAnswer
from .serializers import DocumentSerializer, QuestionAnswerSerializer
from .tasks import parse_and_vectorize_document_task, answer_question_with_rag_task, delete_document_data_task, delete_qa_record_task
from django.shortcuts import render
from django.db import transaction
import os # 引入 os 模組

class DocumentViewSet(viewsets.ModelViewSet):
    queryset = Document.objects.all().order_by('-uploaded_at')
    serializer_class = DocumentSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        headers = self.get_success_headers(serializer.data)

        document_id = serializer.instance.id
        parse_and_vectorize_document_task.delay(str(document_id))

        return Response(serializer.data, status=status.HTTP_201_CREATED, headers=headers)

    def destroy(self, request, *args, **kwargs):
        # 覆寫 destroy 方法，以便在 Celery 中處理刪除邏輯
        instance = self.get_object()
        document_id = str(instance.id)
        file_path = instance.file.path # 獲取文件路徑

        # 啟動 Celery 任務來異步處理刪除操作
        delete_document_data_task.delay(document_id, file_path)

        # 立即返回成功響應，但實際刪除操作在後台執行
        return Response(status=status.HTTP_204_NO_CONTENT)


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

        qa_instance = QuestionAnswer.objects.create(
            document=document,
            question=question,
            status='PENDING'
        )
        serializer = self.get_serializer(qa_instance)

        answer_question_with_rag_task.delay(str(qa_instance.id), str(document_id), question)

        return Response(serializer.data, status=status.HTTP_201_CREATED)

    # 針對 QuestionAnswer 實例的刪除
    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        qa_id = str(instance.id)
        delete_qa_record_task.delay(qa_id) # 異步刪除 QA 記錄
        return Response(status=status.HTTP_204_NO_CONTENT)



def index_view(request):
    return render(request, 'rag_app/index.html')