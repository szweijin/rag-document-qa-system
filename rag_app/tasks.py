import os
from celery import shared_task
from django.conf import settings
from .models import Document, QuestionAnswer
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Ollama
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from django.db import transaction

# Chroma DB 的持久化路徑
CHROMA_DB_PATH = os.path.join(settings.BASE_DIR, "chroma_db")

# 初始化嵌入模型
embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2", model_kwargs={'device': 'cpu'})


@shared_task(bind=True)
def parse_and_vectorize_document_task(self, document_id):
    """
    Celery 任務：解析文件，分塊，生成嵌入，並存儲到 ChromaDB。
    """
    try:
        with transaction.atomic():
            document = Document.objects.get(id=document_id)
            document.status = 'PROCESSING'
            document.processing_message = '文件解析與向量化中...'
            document.save()

        file_path = document.file.path
        file_ext = os.path.splitext(file_path)[1].lower()
        documents_to_process = []

        if file_ext == '.pdf':
            loader = PyPDFLoader(file_path)
        elif file_ext == '.txt':
            loader = TextLoader(file_path, encoding='utf-8')
        elif file_ext == '.docx':
            loader = Docx2txtLoader(file_path)
        else:
            raise ValueError(f"不支援的文件類型: {file_ext}")

        loaded_docs = loader.load()

        for doc in loaded_docs:
            doc.metadata['source_file_id'] = str(document.id)
            doc.metadata['source_filename'] = document.filename
        documents_to_process.extend(loaded_docs)

        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_documents(documents_to_process)

        if not chunks:
            raise ValueError("文件解析後沒有生成任何內容區塊。")

        # 持久化到 ChromaDB
        vector_db = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=CHROMA_DB_PATH,
            collection_name=str(document_id) # 使用文件ID作為Collection名稱
        )
        vector_db.persist() # 顯式調用 persist() 確保資料寫入磁碟

        with transaction.atomic():
            document.status = 'COMPLETED'
            document.processing_message = '文件處理完成。'
            document.save()

        print(f"文件 {document.filename} (ID: {document_id}) 處理完成並存入 ChromaDB。")

    except Document.DoesNotExist:
        print(f"錯誤: 文件 (ID: {document_id}) 不存在。")
    except Exception as e:
        print(f"處理文件 {document_id} 時發生錯誤: {e}")
        with transaction.atomic():
            document = Document.objects.get(id=document_id)
            document.status = 'FAILED'
            document.processing_message = f'處理失敗: {str(e)}'
            document.save()


@shared_task(bind=True)
def answer_question_with_rag_task(self, qa_id, document_id, question):
    """
    Celery 任務：使用 RAG 從 ChromaDB 檢索資訊並生成答案。
    """
    try:
        with transaction.atomic():
            qa_instance = QuestionAnswer.objects.get(id=qa_id)
            qa_instance.status = 'ANSWERING'
            qa_instance.save()

        vector_store = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings,
            collection_name=str(document_id)
        )

        llm = Ollama(model="llama3.2") # 確保您在 Ollama 中實際運行的 Llama 3.2 模型名稱

        prompt_template = """
        Use the following pieces of context to answer the user's question.
        If you don't know the answer, just say that you don't know, don't try to make up an answer.
        ----------------
        Context: {context}
        ----------------
        Question: {question}
        ----------------
        Helpful Answer:"""

        QA_CHAIN_PROMPT = PromptTemplate.from_template(prompt_template)

        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff",
            retriever=vector_store.as_retriever(search_kwargs={"k": 5}),
            return_source_documents=True,
            chain_type_kwargs={"prompt": QA_CHAIN_PROMPT}
        )

        result = qa_chain.invoke({"query": question})

        answer = result["result"]
        source_documents = []
        for doc in result.get("source_documents", []):
            source_info = {
                "content": doc.page_content[:200] + "...",
                "metadata": doc.metadata
            }
            source_documents.append(source_info)

        with transaction.atomic():
            qa_instance.answer = answer
            qa_instance.source_documents = source_documents
            qa_instance.status = 'COMPLETED'
            qa_instance.save()

        print(f"問題 '{question}' (QA ID: {qa_id}) 已回答。")

    except QuestionAnswer.DoesNotExist:
        print(f"錯誤: 問答實例 (ID: {qa_id}) 不存在。")
    except Document.DoesNotExist:
        print(f"錯誤: 文件 (ID: {document_id}) 不存在或未經處理。")
    except Exception as e:
        print(f"回答問題 {question} (QA ID: {qa_id}) 時發生錯誤: {e}")
        with transaction.atomic():
            qa_instance = QuestionAnswer.objects.get(id=qa_id)
            qa_instance.answer = "無法生成答案，請檢查後台日誌或重試。"
            qa_instance.error_message = f"錯誤: {str(e)}"
            qa_instance.status = 'FAILED'
            qa_instance.save()

@shared_task
def delete_document_data_task(document_id, file_path):
    """
    Celery 任務：刪除 Document 記錄、其相關的 QA 記錄、物理文件和 ChromaDB 向量索引。
    """
    try:
        # 1. 刪除 Django Document 記錄 (會級聯刪除相關的 QuestionAnswer 記錄)
        with transaction.atomic():
            document = Document.objects.get(id=document_id)
            document.delete()
        print(f"Django Document (ID: {document_id}) 及其所有相關 QA 記錄已刪除。")

        # 2. 刪除 ChromaDB 中對應的 Collection
        try:
            chroma_client = Chroma(persist_directory=CHROMA_DB_PATH, embedding_function=embeddings)
            # 確保 collection_name 與創建時一致
            chroma_client.delete_collection(name=str(document_id))
            print(f"ChromaDB Collection '{document_id}' 已刪除。")
        except Exception as e:
            print(f"警告: 刪除 ChromaDB Collection '{document_id}' 失敗: {e}")
            # 如果 collection 不存在或有其他錯誤，不阻止繼續刪除文件

        # 3. 刪除物理文件
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"物理文件 '{file_path}' 已刪除。")
        else:
            print(f"警告: 物理文件 '{file_path}' 不存在，無需刪除。")

    except Document.DoesNotExist:
        print(f"錯誤: 嘗試刪除文件 (ID: {document_id}) 時，該文件不存在。")
    except Exception as e:
        print(f"刪除文件 {document_id} 及相關資料時發生錯誤: {e}")

@shared_task
def delete_qa_record_task(qa_id):
    """
    Celery 任務：刪除單個 QuestionAnswer 記錄。
    """
    try:
        with transaction.atomic():
            qa_record = QuestionAnswer.objects.get(id=qa_id)
            qa_record.delete()
        print(f"QuestionAnswer 記錄 (ID: {qa_id}) 已刪除。")
    except QuestionAnswer.DoesNotExist:
        print(f"錯誤: 嘗試刪除 QA 記錄 (ID: {qa_id}) 時，該記錄不存在。")
    except Exception as e:
        print(f"刪除 QA 記錄 {qa_id} 時發生錯誤: {e}")