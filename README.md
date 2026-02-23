# AI-Line-Bot - 智能 LINE 聊天機器人平台 (ZZZ LAZY 版)

AI-Line-Bot 是一個專為企業與個人設計的智能 LINE 聊天機器人平台。基於 Flask 架構，整合了 **Google Gemini 2.0 Flash Lite** 與 **Retreival-Augmented Generation (RAG)** 技術，讓機器人不僅能進行自然語言對話，還能根據您的專屬知識庫提供精準的回覆。

## 🌟 主要特點

- 🤖 **多重人格風格**：預設提供貼心、風趣、認真、專業等多種對話風格，並支援完全客製化。
- 🧠 **先進 AI 模型**：整合 Google Gemini 2.0 Flash Lite，回應速度極快且具備強大的理解力。
- 📚 **高效能 RAG 知識庫**：
  - 支援多格式文件吸收 (TXT, PDF, DOCX, MD, CSV)。
  - **智慧吸收**：免手動標題，支援文字直傳與自動標題生成。
  - **雲端持久化**：向量數據直接存儲於 PostgreSQL，完美支持 Render 等容器化部署，無需本地索引檔案。
- 🚨 **真人接手機制 (Escalation System)**：
  - **自動偵測**：當用戶提及購買、客訴或 AI 不確定時，自動觸發關鍵回報。
  - **即時通知**：支援 SMTP 郵件通知，隨時掌握重要客戶訊息。
- 📊 **專業管理後台**：
  - **分頁管理**：所有列表均支援分頁，效能卓越。
  - **對話歷史**：完整記錄機器人與用戶的對話細節。
  - **即時狀態**：監控知識庫學習進度。

## 🔧 技術架構

- **核心框架**：Flask (Python 3.11+)
- **數據存儲**：PostgreSQL (存儲用戶、對話、權限與**向量嵌入數據**)
- **AI 引擎**：Google Gemini 2.0 Flash Lite
- **部署支援**：Docker, Render (包含 `Procfile`, `runtime.txt`)
- **前端美學**：現代高對比 Bauhaus 設計語言，極簡且具時尚感。

## 📋 快速開始

### Render 部署建議 (推薦)
1. **建立資料庫**：在 Render 建立一個 PostgreSQL 資料庫。
2. **部署 Web Service**：連結您的 GitHub 存儲庫，Render 會自動識別 `Procfile`。
3. **設定環境變數**：
   - `GEMINI_API_KEY`: 您的 Google AI 密鑰。
   - `DATABASE_URL`: 指向您的 PostgreSQL。
   - `SESSION_SECRET`: 隨機字串用於會話安全。

### 本地開發
1. 克隆並安裝依賴：
   ```bash
   pip install -r requirements.txt
   ```
2. 啟動服務：
   ```bash
   python main.py
   ```

## 🛠️ 管理員資訊
- **預設網址**：`https://您的網域/admin`
- **預設帳號**：`admin` / **密碼**：`admin` (請務必在登入後修改密碼)

## 📜 授權條款
本項目採用 MIT 授權條款。

---
**開發團隊**：FlyPig AI x Antigravity  
**當前版本**：V1.2.0 (已優化 RAG 與分頁功能)