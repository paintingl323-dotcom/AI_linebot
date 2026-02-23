import os
import logging
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
import csv
import io
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from models import BotStyle, Config, ChatMessage, Document, LineUser, User
from forms import LLMSettingsForm, BotStyleForm, BotSettingsForm, DocumentForm, UserForm

admin_bp = Blueprint('admin', __name__)

from app import db
from routes.utils.config_service import ConfigManager
from services.llm_service import LLMService
from rag_service import RAGService

logger = logging.getLogger(__name__)

# Admin access decorator
def admin_required(f):
    """Decorator to require admin access for a route"""
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_admin:
            flash('Admin access required for this page.', 'danger')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return login_required(decorated_function)

# Date test page (doesn't require admin access)
@admin_bp.route('/date-test')
@login_required
def date_test():
    """Test page for date functionality"""
    return render_template('date_test.html')

# Dashboard
@admin_bp.route('/')
@admin_bp.route('/dashboard')
@admin_required
def dashboard():
    """Admin dashboard displaying system overview"""
    try:
        # Get stats with safe fallbacks
        total_messages = ChatMessage.query.count()
        user_messages = ChatMessage.query.filter_by(is_user_message=True).count()
        bot_messages = ChatMessage.query.filter_by(is_user_message=False).count()
        
        user_count = LineUser.query.count()
        document_count = Document.query.count()
        
        # Get recent messages
        recent_messages = ChatMessage.query.order_by(ChatMessage.timestamp.desc()).limit(10).all()
        
        # Get active style
        active_style_name = ConfigManager.get("ACTIVE_BOT_STYLE", "Default")
        active_style = BotStyle.query.filter_by(name=active_style_name).first()
        
        # Get Gemini API key status
        gemini_key = ConfigManager.get("GEMINI_API_KEY", "")
        api_status = "Configured" if gemini_key else "Not Configured"
        
        # Get RAG status
        rag_enabled = ConfigManager.get("RAG_ENABLED", "True") == "True"
        
        # Detect database type for persistence warning
        try:
            is_sqlite = db.engine.url.drivername == 'sqlite'
        except Exception:
            is_sqlite = False
        
        return render_template(
            'dashboard.html',
            user_count=user_count,
            total_messages=total_messages,
            user_messages=user_messages,
            bot_messages=bot_messages,
            document_count=document_count,
            recent_messages=recent_messages,
            active_style=active_style,
            api_status=api_status,
            rag_enabled=rag_enabled,
            is_sqlite=is_sqlite
        )
    except Exception as e:
        logger.error(f"Error in dashboard route: {e}", exc_info=True)
        # If it fails, render a minimal version or error page
        return f"儀表板啟動失敗，請檢查日誌。錯誤內容: {str(e)}", 500


# LLM Settings
@admin_bp.route('/llm_settings', methods=['GET', 'POST'])
@admin_required
def llm_settings():
    """LLM settings configuration page"""
    form = LLMSettingsForm()
    
    # Pre-fill form with current settings
    if request.method == 'GET':
        form.api_key.data = ConfigManager.get("GEMINI_API_KEY", "")
        form.temperature.data = float(ConfigManager.get("GEMINI_TEMPERATURE", "0.7"))
        form.max_tokens.data = int(ConfigManager.get("GEMINI_MAX_TOKENS", "500"))
    
    # Process form submission
    if form.validate_on_submit():
        # Validate API key
        valid, message = LLMService.validate_api_key(form.api_key.data)
        
        if valid:
            # Save settings
            ConfigManager.set("GEMINI_API_KEY", form.api_key.data)
            ConfigManager.set("GEMINI_TEMPERATURE", str(form.temperature.data))
            ConfigManager.set("GEMINI_MAX_TOKENS", str(form.max_tokens.data))
            
            flash('LLM settings updated successfully.', 'success')
            return redirect(url_for('admin.llm_settings'))
        else:
            flash(f'API key validation failed: {message}', 'danger')
    
    return render_template('llm_settings.html', form=form)

# Bot Settings
@admin_bp.route('/bot_settings', methods=['GET', 'POST'])
@admin_required
def bot_settings():
    """LINE Bot settings configuration page"""
    form = BotSettingsForm()
    
    # Get all available styles for the dropdown
    styles = BotStyle.query.all()
    form.active_style.choices = [(style.name, style.name) for style in styles]
    
    # Pre-fill form with current settings
    if request.method == 'GET':
        form.channel_id.data = ConfigManager.get("LINE_CHANNEL_ID", "2007002420")
        form.channel_secret.data = ConfigManager.get("LINE_CHANNEL_SECRET", "68de5af41837af7d0cf8998774f5dc04")
        form.channel_access_token.data = ConfigManager.get("LINE_CHANNEL_ACCESS_TOKEN", "VaPdPpIRKyOT8VQHAu3bt/KfCy4pJmLL0O76mv5NTtakPiDrDDEyXLPiNqvldZJlMUnLSJ+sWhNpdXgXpm7SiB4bHVJFbnagaftL6IX3PGz7n/msUBX//L2s/OvuLaNcfTMA1a20CuwIzgoGjiTzMgdB04t89/1O/w1cDnyilFU=")
        form.active_style.data = ConfigManager.get("ACTIVE_BOT_STYLE", "Default")
        form.ignored_keywords.data = ConfigManager.get("IGNORED_KEYWORDS", "")
        form.rag_enabled.data = ConfigManager.get("RAG_ENABLED", "True") == "True"
    
    # Process form submission
    if form.validate_on_submit():
        # Save settings
        ConfigManager.set("LINE_CHANNEL_ID", form.channel_id.data)
        ConfigManager.set("LINE_CHANNEL_SECRET", form.channel_secret.data)
        ConfigManager.set("LINE_CHANNEL_ACCESS_TOKEN", form.channel_access_token.data)
        ConfigManager.set("ACTIVE_BOT_STYLE", form.active_style.data)
        ConfigManager.set("IGNORED_KEYWORDS", form.ignored_keywords.data)
        ConfigManager.set("RAG_ENABLED", str(form.rag_enabled.data))
        
        flash('Bot settings updated successfully.', 'success')
        return redirect(url_for('admin.bot_settings'))
    
    # Get the webhook URL for display
    webhook_url = request.host_url.rstrip('/') + url_for('webhook.line_webhook')
    
    return render_template('bot_settings.html', form=form, webhook_url=webhook_url)

# Bot Styles
@admin_bp.route('/bot_styles')
@admin_required
def bot_styles():
    """Bot styles management page"""
    styles = BotStyle.query.all()
    form = BotStyleForm()
    return render_template('bot_styles.html', styles=styles, form=form)

@admin_bp.route('/bot_styles/add', methods=['GET', 'POST'])
@admin_required
def add_bot_style():
    """Add a new bot style"""
    form = BotStyleForm()
    
    # GET request - render the form
    if request.method == 'GET':
        return render_template('add_bot_style.html', form=form)
    
    if form.validate_on_submit():
        # Check if style name already exists
        existing = BotStyle.query.filter_by(name=form.name.data).first()
        if existing:
            flash(f'A style with name "{form.name.data}" already exists.', 'danger')
            return render_template('add_bot_style.html', form=form)
        
        # Create new style
        style = BotStyle(
            name=form.name.data,
            prompt=form.prompt.data,
            description=form.description.data,
            is_default=form.is_default.data
        )
        
        # If this is set as default, update other styles
        if form.is_default.data:
            BotStyle.query.update({'is_default': False})
            ConfigManager.set("ACTIVE_BOT_STYLE", form.name.data)
        
        db.session.add(style)
        db.session.commit()
        
        flash(f'Style "{form.name.data}" added successfully.', 'success')
        return redirect(url_for('admin.bot_styles'))
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
        # If validation fails, return to add form with current values
        return render_template('add_bot_style.html', form=form)
    

@admin_bp.route('/bot_styles/edit/<int:style_id>', methods=['GET', 'POST'])
@admin_required
def edit_bot_style(style_id):
    """Edit an existing bot style"""
    style = BotStyle.query.get_or_404(style_id)
    form = BotStyleForm()
    
    # GET request - populate form with style data
    if request.method == 'GET':
        form.name.data = style.name
        form.prompt.data = style.prompt
        form.description.data = style.description
        form.is_default.data = style.is_default
        return render_template('edit_bot_style.html', style=style, form=form)
    
    if form.validate_on_submit():
        # Check if renaming to an existing name
        if form.name.data != style.name:
            existing = BotStyle.query.filter_by(name=form.name.data).first()
            if existing:
                flash(f'A style with name "{form.name.data}" already exists.', 'danger')
                return redirect(url_for('admin.bot_styles'))
        
        # Update style
        style.name = form.name.data
        style.prompt = form.prompt.data
        style.description = form.description.data
        
        # Handle default status
        if form.is_default.data and not style.is_default:
            BotStyle.query.update({'is_default': False})
            style.is_default = True
            ConfigManager.set("ACTIVE_BOT_STYLE", form.name.data)
        elif form.is_default.data:
            style.is_default = True
            ConfigManager.set("ACTIVE_BOT_STYLE", form.name.data)
        
        db.session.commit()
        
        flash(f'Style "{form.name.data}" updated successfully.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
        # If validation fails, return to edit form with current values
        return render_template('edit_bot_style.html', style=style, form=form)
    
    return redirect(url_for('admin.bot_styles'))

@admin_bp.route('/bot_styles/delete/<int:style_id>', methods=['POST'])
@admin_required
def delete_bot_style(style_id):
    """Delete a bot style"""
    style = BotStyle.query.get_or_404(style_id)
    
    # Don't allow deleting the default style
    if style.is_default:
        flash('Cannot delete the default style.', 'danger')
        return redirect(url_for('admin.bot_styles'))
    
    # Check if this is the active style
    if ConfigManager.get("ACTIVE_BOT_STYLE") == style.name:
        # Find a new default style
        default_style = BotStyle.query.filter_by(is_default=True).first()
        if default_style:
            ConfigManager.set("ACTIVE_BOT_STYLE", default_style.name)
        else:
            # If no default, use the first available
            first_style = BotStyle.query.first()
            if first_style:
                ConfigManager.set("ACTIVE_BOT_STYLE", first_style.name)
                first_style.is_default = True
    
    style_name = style.name
    db.session.delete(style)
    db.session.commit()
    
    flash(f'Style "{style_name}" deleted successfully.', 'success')
    return redirect(url_for('admin.bot_styles'))

@admin_bp.route('/bot_styles/get/<int:style_id>')
@admin_required
def get_bot_style(style_id):
    """Get a bot style as JSON for editing"""
    style = BotStyle.query.get_or_404(style_id)
    return jsonify({
        'id': style.id,
        'name': style.name,
        'prompt': style.prompt,
        'description': style.description,
        'is_default': style.is_default
    })

# Message History
@admin_bp.route('/message_history')
@admin_required
def message_history():
    """Message history page"""
    # Get filter parameters
    user_id = request.args.get('user_id')
    page = request.args.get('page', 1, type=int)
    per_page = 50
    
    # Build query
    query = ChatMessage.query
    if user_id:
        query = query.filter_by(line_user_id=user_id)
    
    # Get paginated messages
    messages = query.order_by(ChatMessage.timestamp.desc()).paginate(page=page, per_page=per_page)
    
    # Get all LINE users for filter dropdown
    users = LineUser.query.all()
    
    return render_template('message_history.html', messages=messages, users=users, current_user_id=user_id)

@admin_bp.route('/notification_settings', methods=['GET', 'POST'])
@admin_required
def notification_settings():
    """Admin page for configuring email notifications and escalation"""
    try:
        form = EmailSettingsForm()
        
        # Pre-fill form with current settings
        if request.method == 'GET':
            form.email_enabled.data = ConfigManager.get("EMAIL_NOTIFICATIONS_ENABLED", "False") == "True"
            form.admin_email.data = ConfigManager.get("ADMIN_EMAIL", "")
            form.smtp_server.data = ConfigManager.get("SMTP_SERVER", "smtp.gmail.com")
            
            # Safe conversion for port
            smtp_port_val = ConfigManager.get("SMTP_PORT", "587")
            try:
                form.smtp_port.data = int(smtp_port_val) if smtp_port_val else 587
            except (ValueError, TypeError):
                form.smtp_port.data = 587
                
            form.smtp_user.data = ConfigManager.get("SMTP_USER", "")
            form.smtp_pass.data = ConfigManager.get("SMTP_PASS", "")
            form.escalation_keywords.data = ConfigManager.get("ESCALATION_KEYWORDS", "購買,下單,退貨,客服,購買方式")
        
        # Process form submission
        if form.validate_on_submit():
            ConfigManager.set("EMAIL_NOTIFICATIONS_ENABLED", str(form.email_enabled.data))
            ConfigManager.set("ADMIN_EMAIL", form.admin_email.data or "")
            ConfigManager.set("SMTP_SERVER", form.smtp_server.data or "smtp.gmail.com")
            ConfigManager.set("SMTP_PORT", str(form.smtp_port.data or 587))
            ConfigManager.set("SMTP_USER", form.smtp_user.data or "")
            
            # Only update password if provided
            if form.smtp_pass.data:
                ConfigManager.set("SMTP_PASS", form.smtp_pass.data)
                
            ConfigManager.set("ESCALATION_KEYWORDS", form.escalation_keywords.data or "")
            
            flash('通知設定已更新。', 'success')
            return redirect(url_for('admin.notification_settings'))
            
        return render_template('notification_settings.html', form=form)
    except Exception as e:
        logger.error(f"Error in notification_settings route: {e}", exc_info=True)
        return f"通知設定頁面啟動失敗，錯誤內容: {str(e)}", 500


@admin_bp.route('/notification_settings/test', methods=['POST'])
@admin_required
def test_email():
    """Send a test email to verify SMTP settings"""
    from services.email_service import EmailService
    
    admin_email = ConfigManager.get("ADMIN_EMAIL", "")
    if not admin_email:
        return jsonify({"success": False, "message": "請先設定管理員收件信箱。"})
        
    success = EmailService.send_email(
        "測試郵件 (Test Email)", 
        "這是一封來自 LazyBot 的測試郵件。如果您收到這封信，代表您的 SMTP 設定正確！"
    )
    
    if success:
        return jsonify({"success": True, "message": f"測試郵件已發送至 {admin_email}"})
    else:
        return jsonify({"success": False, "message": "發送失敗，請檢查 SMTP 設定與密碼。"})

# Knowledge Base
@admin_bp.route('/knowledge_base')
@admin_required
def knowledge_base():
    """Knowledge base management page"""
    try:
        documents = Document.query.order_by(Document.uploaded_at.desc()).all()
    except Exception as e:
        logger.error(f"Error loading knowledge base: {e}", exc_info=True)
        documents = []
        flash(f'知識庫載入錯誤：{str(e)}', 'danger')
    form = DocumentForm()
    return render_template('knowledge_base.html', documents=documents, form=form)

def parse_line_csv_content(csv_text):
    """
    Parse LINE Official Account CSV chat logs into readable transcript.
    Handles metadata rows and separate Date/Time columns.
    """
    output = []
    
    # Use io.StringIO to treat the string as a file for the csv module
    f = io.StringIO(csv_text)
    reader = csv.reader(f)
    
    rows = list(reader)
    
    # helper to find index by keywords
    def find_idx(row, keywords):
        for i, col in enumerate(row):
            if any(k in col.lower() for k in keywords):
                return i
        return -1

    # Find the header row
    header_row_idx = -1
    date_idx = -1
    time_idx = -1
    sender_idx = -1
    msg_idx = -1
    
    # Scan first 10 rows for headers
    for i, row in enumerate(rows[:10]):
        if not row: continue
        
        # Check if this row looks like headers
        d_idx = find_idx(row, ['date', '日期'])
        t_idx = find_idx(row, ['time', '時間'])
        s_idx = find_idx(row, ['sender', 'name', 'user', '發送者', '名稱', '用戶'])
        m_idx = find_idx(row, ['message', 'content', 'text', '訊息', '內容'])
        
        # We need at least Sender and Message, or Date and Message to be confident
        if (s_idx != -1 and m_idx != -1) or (d_idx != -1 and m_idx != -1):
            header_row_idx = i
            headers = row
            date_idx = d_idx
            time_idx = t_idx
            sender_idx = s_idx
            msg_idx = m_idx
            break
            
    # If no headers found by keywords, fallback to standard positions if 3+ cols
    if header_row_idx == -1:
        # Check if we have data that looks structured (skip potential metadata)
        # Assume start from row 0 if no metadata looks apparent, or row 1
        start_row = 0
        if len(rows) > 3 and len(rows[0]) < 3: start_row = 3 # Skip metadata guess
        
        header_row_idx = start_row - 1 # Treat start_row as data
        # Fallback indices
        date_idx = 0
        time_idx = -1
        sender_idx = 1
        msg_idx = 2
        
    # Process data rows
    for i in range(header_row_idx + 1, len(rows)):
        row = rows[i]
        if not row or len(row) < 2: continue
        
        # Get values
        date_str = row[date_idx] if date_idx != -1 and date_idx < len(row) else ""
        time_str = row[time_idx] if time_idx != -1 and time_idx < len(row) else ""
        sender = row[sender_idx] if sender_idx != -1 and sender_idx < len(row) else "User"
        message = row[msg_idx] if msg_idx != -1 and msg_idx < len(row) else ""
        
        # Cleanup
        sender = sender.strip()
        message = message.strip()
        
        # Combine date and time
        timestamp = f"{date_str} {time_str}".strip() if date_str or time_str else ""
        
        if not message: continue
        
        # Format: [Time] Sender: Message
        line = f"[{timestamp}] {sender}: {message}" if timestamp else f"{sender}: {message}"
        output.append(line)
        
    return "\n".join(output)


@admin_bp.route('/knowledge_base/add', methods=['POST'])
@admin_required
def add_document():
    """Add document(s) to the knowledge base"""
    form = DocumentForm()
    
    try:
        # We need to manually handle validation for multiple files if Flask-WTF doesn't fully support it
        # But usually validate_on_submit() works for the CSRF token and other fields
        if form.validate_on_submit():
            # Check for multiple files
            files = request.files.getlist(form.file.name)
            
            # If text content is provided, add it as a separate document
            if form.content.data and form.title.data:
                title = form.title.data
                content = form.content.data
                success, result = RAGService.add_document(title, content, None)
                if success:
                    flash(f'Document "{title}" added successfully.', 'success')
                else:
                    flash(f'Error adding document "{title}": {result}', 'danger')

            # If files are provided
            if files and files[0].filename:
                documents_to_add = []
                error_count = 0
                
                for file in files:
                    if not file.filename: continue
                    
                    filename = secure_filename(file.filename)
                    
                    # Use filename as title if one isn't explicitly provided for the batch
                    doc_title = filename
                    
                    try:
                        # Read file content
                        file.stream.seek(0) # Ensure we read from start
                        file_content = file.read().decode('utf-8', errors='replace')
                        
                        # Specialized handling for CSV files (LINE chat logs)
                        if filename.lower().endswith('.csv'):
                            try:
                                file_content = parse_line_csv_content(file_content)
                            except Exception as e:
                                logger.error(f"Error parsing CSV {filename}: {e}")
                                error_count += 1
                                continue # Skip this file if parsing fails
                        
                        if file_content:
                            documents_to_add.append({
                                'title': doc_title,
                                'content': file_content,
                                'filename': filename
                            })
                    except Exception as e:
                        logger.error(f"Error processing file {filename}: {e}")
                        error_count += 1

                # Perform bulk add
                if documents_to_add:
                    success, result = RAGService.bulk_add_documents(documents_to_add)
                    if success:
                        flash(f'Successfully added {len(documents_to_add)} documents. (Background indexing may continue)', 'success')
                    else:
                        flash(f'Error processing bulk upload: {result}', 'danger')
                
                if error_count > 0:
                    flash(f'Failed to process {error_count} files.', 'warning')

        else:
            for field, errors in form.errors.items():
                for error in errors:
                    flash(f'{field}: {error}', 'danger')
    except Exception as e:
        logger.error(f"Unhandled error in add_document: {e}", exc_info=True)
        flash(f'伺服器發生錯誤：{str(e)}', 'danger')
    
    return redirect(url_for('admin.knowledge_base'))

@admin_bp.route('/knowledge_base/delete/<int:doc_id>', methods=['POST'])
@admin_required
def delete_document(doc_id):
    """Delete a document from the knowledge base"""
    success, message = RAGService.delete_document(doc_id)
    
    if success:
        flash(message, 'success')
    else:
        flash(message, 'danger')
    
    return redirect(url_for('admin.knowledge_base'))

@admin_bp.route('/knowledge_base/view/<int:doc_id>')
@admin_required
def view_document(doc_id):
    """View a document's content"""
    document = Document.query.get_or_404(doc_id)
    return jsonify({
        'id': document.id,
        'title': document.title,
        'content': document.content
    })

@admin_bp.route('/knowledge_base/status')
@admin_required
def knowledge_base_status():
    """Return JSON status of all documents for live polling."""
    documents = Document.query.order_by(Document.uploaded_at.desc()).all()
    result = []
    for doc in documents:
        if doc.embedding_json:
            status = 'learned'
        elif doc.content:
            status = 'pending'
        else:
            status = 'no_content'
        result.append({'id': doc.id, 'status': status})
    
    has_pending = any(d['status'] == 'pending' for d in result)
    return jsonify({'documents': result, 'has_pending': has_pending})

@admin_bp.route('/knowledge_base/rebuild_index', methods=['POST'])
@admin_required
def rebuild_index():
    """Rebuild the FAISS index"""
    success = RAGService.update_index()
    
    if success:
        flash('Knowledge base index rebuilt successfully.', 'success')
    else:
        flash('Error rebuilding knowledge base index.', 'danger')
    
    return redirect(url_for('admin.knowledge_base'))

# User Management
@admin_bp.route('/user_management')
@admin_required
def user_management():
    """User management page for admin panel users"""
    users = User.query.all()
    form = UserForm()
    return render_template('user_management.html', users=users, form=form)

@admin_bp.route('/user_management/add', methods=['POST'])
@admin_required
def add_user():
    """Add a new admin panel user"""
    form = UserForm()
    
    if form.validate_on_submit():
        # Check if username or email already exists
        if User.query.filter_by(username=form.username.data).first():
            flash(f'Username "{form.username.data}" is already taken.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        if User.query.filter_by(email=form.email.data).first():
            flash(f'Email "{form.email.data}" is already registered.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        # Check for password
        if not form.password.data:
            flash('Password is required for new users.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        # Create new user
        from werkzeug.security import generate_password_hash
        user = User(
            username=form.username.data,
            email=form.email.data,
            password_hash=generate_password_hash(form.password.data),
            is_admin=form.is_admin.data
        )
        
        db.session.add(user)
        db.session.commit()
        
        flash(f'User "{form.username.data}" added successfully.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    
    return redirect(url_for('admin.user_management'))

@admin_bp.route('/user_management/edit/<int:user_id>', methods=['POST'])
@admin_required
def edit_user(user_id):
    """Edit an existing admin panel user"""
    user = User.query.get_or_404(user_id)
    form = UserForm()
    
    # Don't allow non-admin to edit the last admin
    if user.is_admin and not form.is_admin.data:
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            flash('Cannot remove admin status from the last admin user.', 'danger')
            return redirect(url_for('admin.user_management'))
    
    if form.validate_on_submit():
        # Check username and email uniqueness if changed
        if form.username.data != user.username and User.query.filter_by(username=form.username.data).first():
            flash(f'Username "{form.username.data}" is already taken.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        if form.email.data != user.email and User.query.filter_by(email=form.email.data).first():
            flash(f'Email "{form.email.data}" is already registered.', 'danger')
            return redirect(url_for('admin.user_management'))
        
        # Update user
        user.username = form.username.data
        user.email = form.email.data
        user.is_admin = form.is_admin.data
        
        # Update password if provided
        if form.password.data:
            from werkzeug.security import generate_password_hash
            user.password_hash = generate_password_hash(form.password.data)
        
        db.session.commit()
        
        flash(f'User "{form.username.data}" updated successfully.', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{field}: {error}', 'danger')
    
    return redirect(url_for('admin.user_management'))

@admin_bp.route('/user_management/delete/<int:user_id>', methods=['POST'])
@admin_required
def delete_user(user_id):
    """Delete an admin panel user"""
    user = User.query.get_or_404(user_id)
    
    # Don't allow deleting the last admin
    if user.is_admin:
        admin_count = User.query.filter_by(is_admin=True).count()
        if admin_count <= 1:
            flash('Cannot delete the last admin user.', 'danger')
            return redirect(url_for('admin.user_management'))
    
    # Don't allow deleting self
    if user.id == current_user.id:
        flash('Cannot delete your own account.', 'danger')
        return redirect(url_for('admin.user_management'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f'User "{username}" deleted successfully.', 'success')
    return redirect(url_for('admin.user_management'))

@admin_bp.route('/user_management/get/<int:user_id>')
@admin_required
def get_user(user_id):
    """Get a user as JSON for editing"""
    user = User.query.get_or_404(user_id)
    return jsonify({
        'id': user.id,
        'username': user.username,
        'email': user.email,
        'is_admin': user.is_admin
    })
