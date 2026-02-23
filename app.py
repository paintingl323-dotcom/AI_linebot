import os
import logging
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import DeclarativeBase
from flask_login import LoginManager

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

class Base(DeclarativeBase):
    pass

# Initialize Flask extensions
db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Create the app
app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "flypig-line-bot-secret")

# Configure the database
database_url = os.environ.get("DATABASE_URL", "sqlite:///flypig.db")
# Ensure PostgreSQL URL compatibility with SQLAlchemy
if database_url.startswith("postgres://"):
    database_url = database_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

# Initialize extensions with app
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

# Import and initialize models
import models

# Setup model classes with SQLAlchemy
models.User = type('User', (models.User, db.Model), {})
models.LineUser = type('LineUser', (models.LineUser, db.Model), {})
models.ChatMessage = type('ChatMessage', (models.ChatMessage, db.Model), {})
models.BotStyle = type('BotStyle', (models.BotStyle, db.Model), {})
models.Config = type('Config', (models.Config, db.Model), {})
models.Document = type('Document', (models.Document, db.Model), {})
models.LogEntry = type('LogEntry', (models.LogEntry, db.Model), {})

# Import for easy access
User = models.User
LineUser = models.LineUser
ChatMessage = models.ChatMessage
BotStyle = models.BotStyle
Config = models.Config
Document = models.Document
LogEntry = models.LogEntry

# Setup login manager
@login_manager.user_loader
def load_user(user_id):
    from models import User
    try:
        return User.query.get(int(user_id))
    except Exception:
        return None

# Register blueprints
from routes.admin import admin_bp
from routes.webhook import webhook_bp
from routes.auth import auth_bp
from routes.api import api_bp

app.register_blueprint(admin_bp, url_prefix='/admin')
app.register_blueprint(webhook_bp)
app.register_blueprint(auth_bp)
app.register_blueprint(api_bp)

@app.route('/')
def index():
    from flask import redirect, url_for
    return redirect(url_for('admin.dashboard'))

# Create tables and initialize data on startup
try:
    with app.app_context():
        db.create_all()
        
        # Migrate: add embedding_json column if it doesn't exist (for PostgreSQL)
        # SQLAlchemy create_all() does NOT alter existing tables, so we do it manually
        try:
            from sqlalchemy import text
            with db.engine.connect() as conn:
                conn.execute(text(
                    "ALTER TABLE document ADD COLUMN IF NOT EXISTS embedding_json TEXT"
                ))
                conn.commit()
            logger.info("Migration: embedding_json column ensured in document table")
        except Exception as col_err:
            # SQLite doesn't support IF NOT EXISTS – try without it
            try:
                from sqlalchemy import text as text2
                with db.engine.connect() as conn:
                    conn.execute(text2("ALTER TABLE document ADD COLUMN embedding_json TEXT"))
                    conn.commit()
                logger.info("Migration: embedding_json column added (SQLite)")
            except Exception:
                pass  # Column may already exist

        if not User.query.first():
            from werkzeug.security import generate_password_hash
            admin = User(
                username="admin",
                email="admin@example.com",
                password_hash=generate_password_hash("admin"),
                is_admin=True
            )
            db.session.add(admin)
            default_styles = [
                BotStyle(name="貼心", prompt="你是小艾，艾可公司的首位AI智能小編，熱情活潑，充滿正能量，總是用繁體中文交談，給人鼓勵與關懷。", is_default=True),
                BotStyle(name="風趣", prompt="你是一位風趣幽默的小艾，擅長用輕鬆詼諧的語調回答問題。"),
                BotStyle(name="正式", prompt="你是小艾，一位非常專業的助理，使用正式繁體中文進行溝通。"),
                BotStyle(name="專業", prompt="你是小艾，一位技術專家助理，提供詳細專業的繁體中文回應。"),
            ]
            for style in default_styles:
                db.session.add(style)
            default_configs = [
                Config(key="GEMINI_TEMPERATURE", value="0.7"),
                Config(key="GEMINI_MAX_TOKENS", value="500"),
                Config(key="LINE_CHANNEL_ID", value=""),
                Config(key="LINE_CHANNEL_SECRET", value=""),
                Config(key="LINE_CHANNEL_ACCESS_TOKEN", value=""),
                Config(key="ACTIVE_BOT_STYLE", value="貼心"),
                Config(key="RAG_ENABLED", value="True"),
            ]
            for config in default_configs:
                db.session.add(config)
            db.session.commit()
            logger.info("Created initial admin user and default settings")
        # Ensure RAG_ENABLED exists and is True (for existing deployments)
        rag_config = Config.query.filter_by(key="RAG_ENABLED").first()
        if not rag_config:
            db.session.add(Config(key="RAG_ENABLED", value="True"))
            logger.info("Migration: set RAG_ENABLED=True in config")
        elif rag_config.value == "False":
            rag_config.value = "True"
            logger.info("Migration: updated RAG_ENABLED from False to True")
        
        db.session.commit()
        
        # Ensure Email Notification settings exist
        email_configs = {
            "EMAIL_NOTIFICATIONS_ENABLED": "False",
            "ADMIN_EMAIL": "",
            "SMTP_SERVER": "smtp.gmail.com",
            "SMTP_PORT": "587",
            "SMTP_USER": "",
            "SMTP_PASS": "",
            "ESCALATION_KEYWORDS": "購買,下單,退貨,客服,購買方式"
        }
        for key, default_val in email_configs.items():
            if not Config.query.filter_by(key=key).first():
                db.session.add(Config(key=key, value=default_val))
                logger.info(f"Migration: added {key} to config")
        db.session.commit()
except Exception as e:
    logger.error(f"Error during startup initialization: {e}")


# Create knowledge_base directory if it doesn't exist
try:
    kb_dir = os.environ.get('KNOWLEDGE_BASE_DIR', 'knowledge_base')
    if not os.path.exists(kb_dir):
        os.makedirs(kb_dir)
        logger.info("Created knowledge_base directory")
except Exception as e:
    logger.error(f"Error creating knowledge_base directory: {e}")

if __name__ == '__main__':

    logger.info("Application initialization complete")
    
    # Run the application
    app.run(host='0.0.0.0', port=5000, debug=True)
