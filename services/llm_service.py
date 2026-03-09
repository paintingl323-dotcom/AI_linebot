import os
import json
import logging
import datetime
import google.generativeai as genai
from routes.utils.config_service import ConfigManager, get_gemini_api_key, get_llm_settings

logger = logging.getLogger(__name__)

class LLMService:
    """Service for interacting with Google Gemini LLM"""
    
    @staticmethod
    def get_client():
        """Get a configured Gemini client instance with the current API key"""
        # Try to get API key from config (supports both GEMINI_API_KEY and OPENAI_API_KEY for backward compatibility)
        api_key = os.environ.get('GEMINI_API_KEY') or get_gemini_api_key()
        if not api_key:
            logger.error("Gemini API key not configured")
            return None
        
        try:
            genai.configure(api_key=api_key)
            return True
        except Exception as e:
            logger.error(f"Failed to configure Gemini: {e}")
            return None
    
    @staticmethod
    def get_bot_style(style_name=None):
        """Get the bot style prompt by name or use the active style"""
        # Import here to avoid circular imports
        from app import db, BotStyle
        
        if not style_name:
            style_name = ConfigManager.get("ACTIVE_BOT_STYLE", "貼心")
        
        style = BotStyle.query.filter_by(name=style_name).first()
        if not style:
            # Fallback to default style
            style = BotStyle.query.filter_by(name="貼心").first()
            
            # If no default style exists, create it
            if not style:
                style = BotStyle(
                    name="貼心",
                    prompt="你是小艾,艾可公司的首位AI智能小編,熱情活潑,充滿正能量,總是用繁體中文交談,給人鼓勵與關懷。",
                    is_default=True
                )
                db.session.add(style)
                db.session.commit()
        
        return style
    
    @staticmethod
    def generate_response(user_message, style_name=None, rag_context=None, user_name=None):
        """Generate a response using the Gemini API with the specified style"""
        client = LLMService.get_client()
        if not client:
            return "抱歉,無法連接 AI 服務,請檢查 API 設定。"
        
        # Get the bot style
        style = LLMService.get_bot_style(style_name)
        
        # Get LLM settings
        settings = get_llm_settings()
        
        # Get current date information (Taiwan time UTC+8)
        taiwan_tz = datetime.timezone(datetime.timedelta(hours=8))
        current_date = datetime.datetime.now(tz=taiwan_tz)
        date_info = {
            "year": current_date.year,
            "month": current_date.month,
            "day": current_date.day,
            "weekday": current_date.strftime("%A"),
            "hour": current_date.hour,
            "minute": current_date.minute,
            "second": current_date.second,
            "iso_date": current_date.strftime("%Y-%m-%d"),
            "full_date": current_date.strftime("%Y年%m月%d日"),
            "full_time": current_date.strftime("%H:%M:%S"),
            "full_datetime": current_date.strftime("%Y年%m月%d日 %H:%M:%S")
        }
        
        date_prompt = f"""
今天是 {date_info['full_date']},星期{['一', '二', '三', '四', '五', '六', '日'][current_date.weekday()]}。
當前時間是 {date_info['full_time']}。
如果用戶詢問當前日期或時間,請使用以上信息回答。
"""
        personalization_prompt = f"用戶的名稱為: {user_name}。請在對話中自然地稱呼用戶。" if user_name else ""

        # Consolidate and Streamline Prompt for Speed
        system_prompt = f"""{style.prompt}
【核心規則】
1. 你是 "ZZZ LAZY AI助手"。禁止提及 "艾可公司" 或無關品牌。
2. 僅回答當前用戶問題，嚴禁洩露其他用戶個資。
3. 知識庫案例需泛化處理（如：一位客戶）。
4. **純文字回覆**：絕對禁止提供、提及、推薦任何圖片或影片（包含網址或 YouTube 等連結），僅以純文字進行回覆。
5. **真人接手**：偵測到「購買、付款、客訴、尋求真人」意圖時，回覆開頭必須包含 `[ESCALATE: 原因]`。
{date_prompt}
{personalization_prompt}
"""
        
        # Add RAG context if available - Cleaned up to save tokens
        if rag_context:
            system_prompt += f"\n【參考資料】\n{rag_context}\n請優先根據上方資料回答，保持簡潔專業。"
        
        # Build the full prompt for Gemini
        full_prompt = f"{system_prompt}\n\n用戶: {user_message}\n\n助手:"
        
        try:
            # Use gemini-2.0-flash-lite-001 for low latency
            model = genai.GenerativeModel('gemini-2.0-flash-lite-001')
            
            # Optimized for speed
            generation_config = {
                'temperature': settings.get("temperature", 0.7),
                'max_output_tokens': settings.get("max_tokens", 800), # Slightly lower for faster finish
                'top_p': 0.95,
            }
            
            response = model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            
            return response.text
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"抱歉，處理發生延遲，請稍後再試。"
    
    @staticmethod
    def validate_api_key(api_key):
        """Validate that the provided Gemini API key works"""
        try:
            genai.configure(api_key=api_key)
            model = genai.GenerativeModel('gemini-2.0-flash-lite-001')
            
            # Make a small request to validate the key
            response = model.generate_content(
                "Hello",
                generation_config={'max_output_tokens': 5}
            )
            return True, "API key is valid"
        except Exception as e:
            logger.error(f"API key validation error: {e}")
            return False, f"API key validation failed: {str(e)}"