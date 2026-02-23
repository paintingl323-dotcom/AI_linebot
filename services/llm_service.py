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

        # Privacy and Personalization Prompt
        privacy_prompt = """
【重要規則 - 隱私與品牌保護】
1. 你的名字是 "ZZZ LAZY AI助手" (或根據風格設定)。
2. 絕對禁止提及 "艾可公司" (Aiko Company) 或任何與 ZZZ LAZY 無關的公司名稱。
3. 絕對禁止提及任何其他客戶、會員或第三方的名字。你只能回答當前對話用戶的問題。
4. 如果知識庫中包含具體的客戶案例或姓名，請將其泛化處理（例如將 "陳先生" 改為 "一位客戶"），絕不能透露真實姓名。
"""
        
        personalization_prompt = ""
        if user_name:
            personalization_prompt = f"當前對話的用戶名字是: {user_name}。請在適當的時候（例如問候或鼓勵時）親切地稱呼對方。"
        
        # Build the full system prompt
        system_prompt = f"{style.prompt}\n\n{date_prompt}\n\n{privacy_prompt}\n\n{personalization_prompt}"
        
        # Add RAG context if available
        if rag_context:
            system_prompt += f"\n\nHere is some additional context that might be helpful: {rag_context}"
        
        # Build the full prompt for Gemini
        full_prompt = f"{system_prompt}\n\n用戶: {user_message}\n\n助手:"
        
        try:
            # Use gemini-2.0-flash-lite-001 for better quota availability
            model = genai.GenerativeModel('gemini-2.0-flash-lite-001')
            
            # Configure generation settings
            generation_config = {
                'temperature': settings.get("temperature", 0.7),
                'max_output_tokens': settings.get("max_tokens", 1000),
            }
            
            response = model.generate_content(
                full_prompt,
                generation_config=generation_config
            )
            
            return response.text
        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return f"抱歉,生成回應時發生錯誤:{str(e)}"
    
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