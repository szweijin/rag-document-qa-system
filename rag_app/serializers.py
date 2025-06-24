from rest_framework import serializers
from .models import Document, QuestionAnswer

class DocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Document
        fields = ['id', 'file', 'filename', 'uploaded_at', 'status', 'processing_message']
        read_only_fields = ['uploaded_at', 'status', 'processing_message', 'filename']

class QuestionAnswerSerializer(serializers.ModelSerializer):
    document_filename = serializers.CharField(source='document.filename', read_only=True)

    class Meta:
        model = QuestionAnswer
        fields = ['id', 'document', 'document_filename', 'question', 'answer', 'source_documents', 'created_at', 'status', 'error_message']
        read_only_fields = ['answer', 'source_documents', 'created_at', 'status', 'error_message']