import os
from celery import shared_task
from django.conf import settings
from .models import Document, QuestionAnswer
from langchain_community.document_loaders import PyPDFLoader, TextLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma
from langchain_community.llms import Ollama # 使用 Ollama 來載入本地模型
from langchain.chains import RetrievalQA
from langchain.prompts import PromptTemplate
from django.db import transaction

# Chroma DB 的持久化路徑
CHROMA_DB_PATH = os.path.join(settings.BASE_DIR, "chroma_db")

# 初始化嵌入模型
# 確保 HuggingFaceEmbeddings 載入成功
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

        # 根據文件類型選擇 Loader
        if file_ext == '.pdf':
            loader = PyPDFLoader(file_path)
        elif file_ext == '.txt':
            loader = TextLoader(file_path, encoding='utf-8')
        elif file_ext == '.docx':
            loader = Docx2txtLoader(file_path)
        else:
            raise ValueError(f"不支援的文件類型: {file_ext}")

        loaded_docs = loader.load()

        # 添加源文件資訊到每個文檔塊的元數據中
        for doc in loaded_docs:
            doc.metadata['source_file_id'] = str(document.id)
            doc.metadata['source_filename'] = document.filename
        documents_to_process.extend(loaded_docs)

        # 分割文件
        text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
        chunks = text_splitter.split_documents(documents_to_process)

        if not chunks:
            raise ValueError("文件解析後沒有生成任何內容區塊。")

        # 持久化到 ChromaDB
        # 這裡會創建一個新的 collection 或更新現有的，名稱基於 document_id
        # 這樣每個文件都有自己的向量索引，避免不同文件的知識混淆
        vector_db = Chroma.from_documents(
            documents=chunks,
            embedding=embeddings,
            persist_directory=CHROMA_DB_PATH,  # 確保這個路徑存在且可寫
            collection_name=str(document_id)
        )
        vector_db.persist()  # 顯式調用 persist() 確保資料寫入磁碟

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
            document = Document.objects.get(id=document_id) # 再次獲取以防前面已保存
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

        # 從持久化目錄加載 ChromaDB，指定對應文件的 collection
        vector_store = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=embeddings,
            collection_name=str(document_id)
        )

        # 設置本地 LLM
        llm = Ollama(model="llama3.2")

        # 定義提示模板，引導 LLM 回答
        # 確保提示清晰地指示 LLM 僅根據提供的上下文回答
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

        # 建立 RetrievalQA 鏈
        qa_chain = RetrievalQA.from_chain_type(
            llm=llm,
            chain_type="stuff", # 將所有檢索到的文件「填充」到 LLM 的上下文
            retriever=vector_store.as_retriever(search_kwargs={"k": 5}), # 檢索最相關的 5 個塊
            return_source_documents=True, # 返回來源文件
            chain_type_kwargs={"prompt": QA_CHAIN_PROMPT}
        )

        # 執行查詢
        result = qa_chain.invoke({"query": question})

        answer = result["result"]
        source_documents = []
        for doc in result.get("source_documents", []):
            # 提取元數據中我們關心的部分，如頁碼 (如果適用)
            # PyPDFLoader 的頁碼在 metadata['page']
            source_info = {
                "content": doc.page_content[:200] + "...", # 顯示部分內容
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
            qa_instance = QuestionAnswer.objects.get(id=qa_id) # 再次獲取以防前面已保存
            qa_instance.answer = "無法生成答案，請檢查後台日誌或重試。"
            qa_instance.error_message = f"錯誤: {str(e)}"
            qa_instance.status = 'FAILED'
            qa_instance.save()