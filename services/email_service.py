import smtplib
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from routes.utils.config_service import ConfigManager

logger = logging.getLogger(__name__)

class EmailService:
    """Service to handle sending email notifications via SMTP"""
    
    @staticmethod
    def send_email(subject, body, to_email=None):
        """Send an email using configured SMTP settings"""
        enabled = ConfigManager.get("EMAIL_NOTIFICATIONS_ENABLED", "False") == "True"
        if not enabled:
            logger.info("Email notifications are disabled")
            return False
            
        admin_email = to_email or ConfigManager.get("ADMIN_EMAIL", "")
        smtp_server = ConfigManager.get("SMTP_SERVER", "smtp.gmail.com")
        smtp_port = int(ConfigManager.get("SMTP_PORT", "587"))
        smtp_user = ConfigManager.get("SMTP_USER", "")
        smtp_pass = ConfigManager.get("SMTP_PASS", "")
        
        if not all([admin_email, smtp_server, smtp_user, smtp_pass]):
            logger.error("Email configuration is incomplete. Please check SMTP settings.")
            return False
            
        try:
            # Create message
            message = MIMEMultipart()
            message["From"] = smtp_user
            message["To"] = admin_email
            message["Subject"] = f"[LazyBot 提醒] {subject}"
            
            # Add body
            message.attach(MIMEText(body, "plain"))
            
            # Connect and send
            with smtplib.SMTP(smtp_server, smtp_port) as server:
                server.starttls()
                server.login(smtp_user, smtp_pass)
                server.send_message(message)
                
            logger.info(f"Escalation email sent to {admin_email}")
            return True
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False

    @staticmethod
    def notify_escalation(user_id, user_message, reason, context_link=None):
        """Prepare and send an escalation notification email"""
        subject = f"真人接手請求: {reason}"
        
        body = f""" LazyBot 個人化客製通知
---
【事件發生】
用戶 ID: {user_id}
觸發原因: {reason}

【對話內容】
用戶說: "{user_message}"

{f'【點此查看對話記錄】\n{context_link}' if context_link else '【建議】請立即登入後台查看相關對話。'}

---
這是一封由 LazyBot 自動發送的通知。
"""
        return EmailService.send_email(subject, body)
