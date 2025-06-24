import os
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import Chroma

# 假設的專案根目錄，請替換為您的實際路徑
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEST_CHROMA_DB_PATH = os.path.join(BASE_DIR, "test_chroma_db")
TEST_DOCUMENT_PATH = os.path.join(BASE_DIR, "test_document.txt")

# 創建一個測試文件
with open(TEST_DOCUMENT_PATH, "w", encoding="utf-8") as f:
    f.write("這是一段測試文本，用於測試 ChromaDB 的持久化功能。\n")
    f.write("它應該會被分割、嵌入，然後存儲到指定的資料夾中。\n")
    f.write("如果成功，您應該會看到 'test_chroma_db' 資料夾。")

print(f"測試文件已創建於: {TEST_DOCUMENT_PATH}")

try:
    # 1. 載入文件
    loader = TextLoader(TEST_DOCUMENT_PATH, encoding='utf-8')
    documents = loader.load()
    print(f"已載入 {len(documents)} 個文件。")

    # 2. 分割文本
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=100, chunk_overlap=20)
    chunks = text_splitter.split_documents(documents)
    print(f"已分割為 {len(chunks)} 個區塊。")

    # 3. 初始化嵌入模型
    # 確保您有足夠的記憶體載入模型
    print("正在初始化嵌入模型...")
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2", model_kwargs={'device': 'cpu'})
    print("嵌入模型初始化完成。")

    # 4. 創建並持久化 ChromaDB
    # 先清理舊的測試資料庫，確保乾淨啟動
    if os.path.exists(TEST_CHROMA_DB_PATH):
        import shutil
        shutil.rmtree(TEST_CHROMA_DB_PATH)
        print(f"已清除舊的測試資料庫: {TEST_CHROMA_DB_PATH}")

    print(f"正在創建 ChromaDB 於: {TEST_CHROMA_DB_PATH}")
    vector_db = Chroma.from_documents(
        documents=chunks,
        embedding=embeddings,
        persist_directory=TEST_CHROMA_DB_PATH,
        collection_name="test_collection"
    )
    vector_db.persist() # 顯式調用持久化
    print("ChromaDB 創建並持久化完成。")

    # 5. 載入並測試檢索 (可選)
    print("正在測試從 ChromaDB 載入並檢索...")
    loaded_vector_db = Chroma(
        persist_directory=TEST_CHROMA_DB_PATH,
        embedding_function=embeddings,
        collection_name="test_collection"
    )
    results = loaded_vector_db.similarity_search("這份文件是關於什麼？", k=1)
    print(f"檢索結果: {results[0].page_content[:50]}...") # 顯示部分內容

    print("\n所有步驟執行成功！")

except Exception as e:
    print(f"\n發生錯誤: {e}")
    import traceback
    traceback.print_exc() # 打印完整的錯誤堆疊

finally:
    # 清理測試文件
    if os.path.exists(TEST_DOCUMENT_PATH):
        os.remove(TEST_DOCUMENT_PATH)