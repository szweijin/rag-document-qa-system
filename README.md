
# 基於 RAG 架構的智慧文件問答系統

-----

## 專案簡介

這個專案建構了一個智能問答系統，核心採用 **Retrieval-Augmented Generation (RAG)** 架構。它允許用戶上傳 PDF、TXT、DOCX 等文件，系統會自動處理這些文件，並透過大型語言模型 (LLM) 回答關於文件內容的問題。

-----

## 解決的問題

  * **提升資訊檢索效率**：快速從大量非結構化文件中提取所需資訊。
  * **減少 LLM「幻覺」**：透過檢索機制，確保 LLM 的回答有據可依，避免生成不準確的內容。
  * **擴展 LLM 知識邊界**：讓 LLM 能夠利用專有或最新的文件知識進行回答，彌補其固定訓練數據的不足。

-----

## 技術棧

  * **後端框架**：Django, Django REST Framework (DRF)
  * **非同步任務**：Celery
  * **訊息代理/結果儲存**：Redis
  * **文件解析**：`pypdf`, `python-docx`
  * **AI 核心**：
      * `langchain`: LLM/向量資料庫整合框架
      * `sentence-transformers`: 生成文本嵌入 (Embeddings)
      * `chromadb`: 輕量級持久化向量資料庫
      * `ollama`: 本地運行 LLM (例如 Llama 3.2)
  * **前端**：HTML/JavaScript (Django Template)

-----

## 核心功能

  * **多格式文件上傳**：支援 PDF, TXT, DOCX 文件。
  * **文件非同步處理**：利用 **Celery** 在後台解析、分塊、嵌入文件，並建立向量索引，避免阻塞前端。
  * **狀態追蹤**：前端實時顯示文件處理和問答任務的進度。
  * **RAG 智能問答**：
      * **檢索 (Retrieval)**：根據用戶問題，從文件中精確檢索相關內容。
      * **生成 (Generation)**：將檢索到的上下文提供給 LLM，生成精準答案。
  * **問答歷史**：保存每次提問及回答的記錄，包含參考來源。

-----

## 安裝與運行指南

### 前置條件

1.  **Python 3.9+**
2.  **Redis 服務**：確保 Redis 服務器已啟動並運行 (用於 Celery)。
3.  **Ollama**：
      * 安裝 [Ollama](https://ollama.com/)。
      * 下載並啟動您偏好的 LLM 模型，例如 `llama3.2`：在終端機運行 `ollama run llama3.2`。

### 步驟

1.  **克隆專案**：

    ```bash
    git clone [您的專案URL]
    cd [您的專案資料夾]
    ```

2.  **建立並啟用虛擬環境**：

    ```bash
    python -m venv venv
    # macOS / Linux
    source venv/bin/activate
    # Windows
    .\venv\Scripts\activate
    ```

3.  **安裝 Python 套件**：

    ```bash
    pip install Django djangorestframework celery pillow pypdf python-docx langchain langchain-community sentence-transformers chromadb
    ```

4.  **執行資料庫遷移**：

    ```bash
    python manage.py makemigrations
    python manage.py migrate
    ```

5.  **啟動 Django 開發伺服器**：
    開啟**第一個終端機 (建議以管理員身份執行)**，確保在虛擬環境中，然後運行：

    ```bash
    python manage.py runserver
    ```

    訪問：`http://127.0.0.1:8000/`

6.  **啟動 Celery Worker (單進程模式，推薦 Windows)**：
    開啟**第二個終端機 (建議以管理員身份執行)**，確保在虛擬環境中，然後運行：

    ```bash
    celery -A rag_qa_project worker -l info --pool=solo
    ```

    **注意：** `--pool=solo` 參數在 Windows 環境下是關鍵，用於避免多進程的文件鎖定問題。

-----

## DEMO 演示

1.  **開啟瀏覽器**：訪問 `http://127.0.0.1:8000/`。
2.  **上傳文件**：在「文件上傳」區塊選擇您的 PDF/TXT/DOCX 文件並提交。
3.  **觀察文件處理**：文件狀態將從「已上傳」變為「處理中」，最終變為「已完成」。您可點擊「刷新文件列表」更新狀態。
4.  **提出問題**：文件狀態為「已完成」後，提問區塊將啟用。輸入關於文件內容的問題並提交。
5.  **查看答案與來源**：回答會連同相關的文件來源一起顯示在「問答歷史」中。

-----

## 專案亮點

  * **Celery 異步處理**：將耗時的 AI 任務卸載至後台，保證 Web 應用響應流暢。
  * **RAG 架構的實際應用**：清晰展示了如何結合檢索與生成，為 LLM 提供精確的上下文，實現可信賴的問答。
  * **本地 LLM 支持**：透過 **Ollama** 實現本地模型運行，提高數據隱私性並降低對外部 API 的依賴。
  * **模組化設計**：Django 模型、DRF API 和 Celery 任務分離，便於維護和擴展。

-----

## 注意事項

  * **本地 LLM 資源需求**：運行 LLM 需要足夠的 CPU/RAM 資源，對於大型模型可能需要 GPU 支持。
  * **ChromaDB 持久化**：`chroma_db/` 資料夾會自動在專案根目錄生成，用於儲存向量資料。部署時請將其添加到 `.gitignore`。
  * **文件編碼**：對於 TXT 文件，請確保使用 UTF-8 編碼以避免讀取錯誤。

-----

## 未來可擴展性

  * **更多文件類型支援**：整合更多解析器，支持 Markdown, CSV, 圖片 (OCR) 等。
  * **高級 RAG 策略**：探索多階段檢索、重排序、查詢擴展等技術，優化回答質量。
  * **實時通知**：使用 Django Channels 實現文件處理和問答結果的實時推送。
  * **使用者管理**：導入用戶認證與文件權限控制。
  * **前端框架升級**：採用 React/Vue/Angular 等現代前端框架，提供更豐富的用戶體驗。

