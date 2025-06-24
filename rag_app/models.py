from django.db import models
import uuid

class Document(models.Model):
    # 文件的狀態
    STATUS_CHOICES = (
        ('UPLOADED', '已上傳'),
        ('PROCESSING', '處理中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失敗'),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    file = models.FileField(upload_to='documents/')
    filename = models.CharField(max_length=255, blank=True) # 儲存原始檔案名
    uploaded_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UPLOADED')
    processing_message = models.TextField(blank=True, null=True) # 處理訊息或錯誤

    def save(self, *args, **kwargs):
        # 如果是新文件且沒有 filename，則從 file 取得
        if not self.filename and self.file:
            self.filename = self.file.name
        super().save(*args, **kwargs)

    def __str__(self):
        return self.filename if self.filename else str(self.id)

class QuestionAnswer(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='qa_pairs')
    question = models.TextField()
    answer = models.TextField(blank=True, null=True)
    # 儲存參考來源，可以是 JSON 格式的列表
    source_documents = models.JSONField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    # 問題回答的狀態
    STATUS_CHOICES = (
        ('PENDING', '待處理'),
        ('ANSWERING', '回答中'),
        ('COMPLETED', '已完成'),
        ('FAILED', '失敗'),
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    error_message = models.TextField(blank=True, null=True)

    def __str__(self):
        return f"Q: {self.question[:50]}... A: {self.answer[:50]}..."