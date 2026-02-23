import json
import logging
import os
from flask import Blueprint, request, abort, current_app
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage,
)
from app import db
from models import LineUser, ChatMessage
from routes.utils.config_service import ConfigManager
from services.llm_service import LLMService
from rag_service import RAGService
import re
import threading

webhook_bp = Blueprint('webhook', __name__)
logger = logging.getLogger(__name__)

# Use default values for initialization at module level
# These will be replaced with actual values during request processing
DEFAULT_ACCESS_TOKEN = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN', "dummy_token")
DEFAULT_CHANNEL_SECRET = os.environ.get('LINE_CHANNEL_SECRET', "dummy_secret")

# Initialize a global handler that will be replaced during request processing
_line_bot_api = LineBotApi(DEFAULT_ACCESS_TOKEN)
_webhook_handler = WebhookHandler(DEFAULT_CHANNEL_SECRET)

def get_line_bot_api():
    """Get a LINE Bot API instance with current config"""
    # First check for an environment variable
    token = os.environ.get('LINE_CHANNEL_ACCESS_TOKEN')
    
    # If not found in environment, try the database
    if not token:
        token = ConfigManager.get("LINE_CHANNEL_ACCESS_TOKEN", DEFAULT_ACCESS_TOKEN)
    
    return LineBotApi(token)

def get_line_webhook_handler():
    """Get a LINE Webhook handler with current config"""
    # First check for an environment variable
    secret = os.environ.get('LINE_CHANNEL_SECRET')
    
    # If not found in environment, try the database
    if not secret:
        secret = ConfigManager.get("LINE_CHANNEL_SECRET", DEFAULT_CHANNEL_SECRET)
    
    return WebhookHandler(secret)

# LINE Bot webhook route
@webhook_bp.route('/webhook', methods=['POST'])
def line_webhook():
    """Handle LINE webhook events"""
    # Get X-Line-Signature header value
    signature = request.headers['X-Line-Signature']
    
    # Get request body as text
    body = request.get_data(as_text=True)
    
    # Log the request
    logger.info("Request body: %s", body)
    
    # Initialize the webhook handler with current config
    handler = get_line_webhook_handler()
    
    try:
        # Define the message handler here, inside the request context
        @handler.add(MessageEvent, message=TextMessage)
        def handle_message(event):
            handle_text_message(event)
            
        # Handle the webhook
        handler.handle(body, signature)
    except InvalidSignatureError:
        logger.error("Invalid signature. Check your channel secret.")
        abort(400)
    
    return 'OK'

# Define the actual message handling function (not decorated directly)
def handle_text_message(event):
    """Handle text messages from LINE users"""
    try:
        # Get message content
        user_id = event.source.user_id
        user_message = event.message.text
        
        logger.info(f"Received message from user {user_id}: {user_message}")
        
        # Get or create the LINE user
        line_user = LineUser.query.filter_by(line_user_id=user_id).first()
        if not line_user:
            logger.info(f"Creating new LINE user with ID: {user_id}")
            # Initialize LINE Bot API
            line_bot_api = get_line_bot_api()
            
            try:
                # Get user profile from LINE
                profile = line_bot_api.get_profile(user_id)
                line_user = LineUser(
                    line_user_id=user_id,
                    display_name=profile.display_name,
                    picture_url=profile.picture_url,
                    status_message=profile.status_message
                )
                logger.info(f"Retrieved profile for user {user_id}: {profile.display_name}")
            except Exception as e:
                logger.error(f"Error getting user profile: {e}")
                # Create a minimal user record
                line_user = LineUser(line_user_id=user_id)
            
            db.session.add(line_user)
            db.session.commit()
            logger.info(f"New LINE user created: {user_id}")
        else:
            logger.info(f"Found existing LINE user: {line_user.line_user_id}, display name: {line_user.display_name}")
        
        # Save user message to database
        chat_message = ChatMessage(
            line_user_id=user_id,
            is_user_message=True,
            message_text=user_message
        )
        db.session.add(chat_message)
        db.session.commit()
        logger.info(f"Saved user message to database: {chat_message.id}")
        
        # Check for ignored keywords (Rich Menu triggers)
        ignored_keywords_str = ConfigManager.get("IGNORED_KEYWORDS", "")
        if ignored_keywords_str:
            ignored_list = [k.strip() for k in ignored_keywords_str.replace("，", ",").split(",") if k.strip()]
            if user_message.strip() in ignored_list:
                logger.info(f"Ignored message '{user_message}' matched ignored keywords list. Skipping response.")
                return

        # Check for style command
        bot_style = None
        if user_message.startswith('/style '):
            style_name = user_message[7:].strip()
            logger.info(f"Style command detected: {style_name}")
            # Set user's preferred style
            line_user.active_style = style_name
            db.session.commit()
            
            response_text = f"風格設定為: {style_name}"
            logger.info(f"Setting user style to: {style_name}")
            
            # Save bot response to database
            bot_message = ChatMessage(
                line_user_id=user_id,
                is_user_message=False,
                message_text=response_text,
                bot_style=style_name
            )
            db.session.add(bot_message)
            db.session.commit()
            
            # Send response
            line_bot_api = get_line_bot_api()
            logger.info(f"Replying to style command with token: {event.reply_token}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=response_text)
            )
            logger.info("Style command response sent successfully")
            return
        
        # Log LINE configuration values
        access_token = ConfigManager.get("LINE_CHANNEL_ACCESS_TOKEN", "not_set")
        channel_secret = ConfigManager.get("LINE_CHANNEL_SECRET", "not_set")
        logger.info(f"LINE credentials - Access token length: {len(access_token)}, Channel secret length: {len(channel_secret)}")
        
        # Get RAG context if enabled
        rag_context = None
        try:
            rag_enabled = ConfigManager.get("RAG_ENABLED", "False")
            logger.info(f"RAG enabled: {rag_enabled}")
            if rag_enabled.lower() == "true":
                logger.info("Getting RAG context for query")
                rag_context = RAGService.get_context_for_query(user_message)
                logger.info(f"RAG context retrieved, length: {len(rag_context) if rag_context else 0}")
        except Exception as e:
            logger.error(f"Error retrieving RAG context: {e}")
        
        # Use the user's preferred style if set
        active_bot_style = ConfigManager.get("ACTIVE_BOT_STYLE", "預設")
        if line_user.active_style:
            bot_style = line_user.active_style
            logger.info(f"Using user's preferred style: {bot_style}")
        else:
            bot_style = active_bot_style
            logger.info(f"Using default bot style: {bot_style}")
        
        # Get Gemini API key
        gemini_api_key = ConfigManager.get("GEMINI_API_KEY", "not_set")
        logger.info(f"Gemini API key length: {len(gemini_api_key)}")
        
        # Generate response using Gemini
        logger.info(f"Generating response with style: {bot_style}")
        try:
            response_text = LLMService.generate_response(user_message, bot_style, rag_context, user_name=line_user.display_name)
            logger.info(f"Response generated, length: {len(response_text)}")
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}", exc_info=True)
            response_text = "抱歉，目前無法處理您的請求。請稍後再試。"
        
        # Save bot response to database first
        # Senior Backend: Strip tags before saving to message history for cleanliness
        clean_db_response = re.sub(r'\[ESCALATE:.*?\]', '', response_text).strip()
        clean_db_response = re.sub(r'\[IMAGE:.*?\]', '', clean_db_response).strip()
        
        bot_message = ChatMessage(
            line_user_id=user_id,
            is_user_message=False,
            message_text=clean_db_response or response_text,
            bot_style=bot_style
        )
        db.session.add(bot_message)
        db.session.commit()
        logger.info(f"Bot response saved to database: {bot_message.id}")
        
        # Priority: Send response to LINE immediately
        try:
            logger.info(f"Sending response with reply token: {event.reply_token}")
            line_bot_api = get_line_bot_api()
            
            # Senior Backend: Parse semantic escalation tags
            escalate_pattern = r'\[ESCALATE:\s*(.*?)\]'
            escalate_match = re.search(escalate_pattern, response_text)
            ai_reason = escalate_match.group(1) if escalate_match else None
            
            # Clean text for sending to user (strip escalation tags)
            clean_response = re.sub(escalate_pattern, '', response_text).strip()
            if not clean_response:
                clean_response = "這是一則系統提醒（AI 偵測到重要意圖並非直接回應內容）。" if ai_reason else "抱歉，我現在無法生成回應。"
            
            # Parse response for multiple messages (text and images)
            messages_to_send = []
            
            # Find image tags in the clean text
            image_pattern = r'\[IMAGE:\s*(https?://[^\s\]]+)\]'
            image_matches = list(re.finditer(image_pattern, clean_response))
            
            if image_matches:
                # Split text by image tags and create multiple message objects
                last_end = 0
                for match in image_matches:
                    start, end = match.span()
                    # Add preceding text if not empty
                    text_part = clean_response[last_end:start].strip()
                    if text_part:
                        messages_to_send.append(TextSendMessage(text=text_part))
                    
                    # Add the image
                    image_url = match.group(1).strip()
                    if image_url:
                        messages_to_send.append(ImageSendMessage(
                            original_content_url=image_url,
                            preview_image_url=image_url
                        ))
                    last_end = end
                
                # Add remaining text if any
                remaining_text = clean_response[last_end:].strip()
                if remaining_text:
                    messages_to_send.append(TextSendMessage(text=remaining_text))
            else:
                # No images found, send clean text
                messages_to_send.append(TextSendMessage(text=clean_response))
            
            # Respect LINE's 5 message limit per reply
            messages_to_send = [m for m in messages_to_send if m][:5]
            
            if not messages_to_send:
                messages_to_send = [TextSendMessage(text=clean_response)]
            
            line_bot_api.reply_message(
                event.reply_token,
                messages_to_send
            )
            logger.info(f"Multi-message response sent successfully ({len(messages_to_send)} bubbles)")
        except Exception as e:
            logger.error(f"Error sending LINE response: {e}", exc_info=True)

        # --- HUMAN ESCALATION LOGIC (Asynchronous & Context-Safe) ---
        # Senior Backend: Pre-fetch data and app-object outside the thread
        u_display_name = line_user.display_name or "未知用戶"
        app_obj = current_app._get_current_object()
        
        # Pre-fetch keywords to avoid database access in thread if possible
        keywords_str = ConfigManager.get("ESCALATION_KEYWORDS", "購買,下單,匯款,轉帳,價格,多少錢,現貨,怎麼買,沒收到,寄錯,瑕疵,退貨,換貨,不滿,客服,找人,真人,聯絡我,緊急")
        
        def process_escalation_task(app_instance, u_id, u_disp_name, u_msg, r_text, target_keywords_str, ai_semantic_reason):
            with app_instance.app_context():
                try:
                    from services.email_service import EmailService
                    from models import Escalation
                    
                    # Check if already triggered by AI semantic tag
                    triggered = False
                    if ai_semantic_reason:
                        logger.info(f"[Escalation] AI semantic trigger: {ai_semantic_reason}")
                        esc = Escalation(
                            line_user_id=u_id,
                            user_display_name=u_disp_name,
                            message_text=u_msg,
                            reason=f"AI 意圖偵測 ({ai_semantic_reason})"
                        )
                        db.session.add(esc)
                        db.session.commit()
                        triggered = True
                        
                        try:
                            EmailService.notify_escalation(u_id, u_msg, f"AI 意圖偵測 ({ai_semantic_reason})")
                        except Exception as e:
                            logger.error(f"[Escalation] AI Email error: {e}")

                    # 1. Keyword check (only if not already triggered by AI)
                    if not triggered:
                        keywords = [k.strip() for k in target_keywords_str.replace("，", ",").split(",") if k.strip()]
                        match = next((k for k in keywords if k.lower() in u_msg.lower()), None)
                        if match:
                            logger.info(f"[Escalation] Keyword matched: {match}")
                            esc = Escalation(
                                line_user_id=u_id,
                                user_display_name=u_disp_name,
                                message_text=u_msg,
                                reason=f"關鍵字觸發 ({match})"
                            )
                            db.session.add(esc)
                            db.session.commit()
                            triggered = True
                            
                            try:
                                EmailService.notify_escalation(u_id, u_msg, f"關鍵字觸發 ({match})")
                            except Exception as e:
                                logger.error(f"[Escalation] Keyword email error: {e}")
                    
                    # 2. AI phrasing check (legacy fallback)
                    if not triggered:
                        human_phrases = ["真人接手", "聯繫客服", "無法處理", "需要人為幫助"]
                        ai_phrase = next((p for p in human_phrases if p in r_text), None)
                        if ai_phrase:
                            logger.info(f"[Escalation] AI phrase matched: {ai_phrase}")
                            esc = Escalation(
                                line_user_id=u_id,
                                user_display_name=u_disp_name,
                                message_text=u_msg,
                                reason=f"AI 建議真人接手 ({ai_phrase})"
                            )
                            db.session.add(esc)
                            db.session.commit()
                            
                            try:
                                EmailService.notify_escalation(u_id, u_msg, f"AI 建議真人接手 ({ai_phrase})")
                            except Exception as e:
                                logger.error(f"[Escalation] AI phrase email error: {e}")
                            
                except Exception as ex:
                    logger.error(f"[Escalation] Thread execution failed: {ex}", exc_info=True)
                finally:
                    db.session.remove()

        # Use daemon thread to avoid blocking the webhook response
        threading.Thread(
            target=process_escalation_task, 
            args=(app_obj, user_id, u_display_name, user_message, response_text, keywords_str, ai_reason), 
            daemon=True
        ).start()
        # -------------------------------------------------------------------------


    
    except Exception as e:
        db.session.rollback()
        logger.error(f"Unhandled exception in handle_text_message: {e}", exc_info=True)

# Webhook verification endpoint
@webhook_bp.route('/webhook', methods=['GET'])
def verify_webhook():
    """Verify the webhook URL for LINE Platform"""
    return 'Webhook OK'
