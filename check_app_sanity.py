import sys
import os
import logging

# Configure logging to console
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("SanityCheck")

def check_imports():
    logger.info("Checking for circular imports...")
    try:
        import app
        logger.info("✅ app.py imported successfully")
        from models import User, Config, Document
        logger.info("✅ models.py imported successfully")
        from routes.admin import admin_bp
        logger.info("✅ routes/admin.py imported successfully")
        from routes.webhook import webhook_bp
        logger.info("✅ routes/webhook.py imported successfully")
    except ImportError as e:
        logger.error(f"❌ Import failed: {e}")
        return False
    except Exception as e:
        logger.error(f"❌ Error during import: {e}")
        return False
    return True

def check_db():
    logger.info("Checking database connection and models...")
    try:
        from app import app, db
        from models import User, Config
        with app.app_context():
            # Try a simple query
            user_count = User.query.count()
            logger.info(f"✅ Database connection OK. User count: {user_count}")
            
            # Check for critical configs
            configs = Config.query.all()
            logger.info(f"✅ Config table accessible. Entry count: {len(configs)}")
    except Exception as e:
        logger.error(f"❌ Database/SQLAlchemy error: {e}")
        return False
    return True

def check_forms():
    logger.info("Checking form instantiation...")
    try:
        from forms import EmailSettingsForm
        from app import app
        with app.app_context():
            # This will fail if dependencies like email-validator are missing
            form = EmailSettingsForm()
            logger.info("✅ EmailSettingsForm instantiated successfully")
    except Exception as e:
        logger.error(f"❌ Form instantiation failed: {e}")
        return False
    return True

if __name__ == "__main__":
    logger.info("=== STARTING RIGOROUS SANITY CHECK ===")
    
    # 1. Check basic imports
    if not check_imports():
        sys.exit(1)
        
    # 2. Check Forms (Catch missing validators)
    if not check_forms():
        sys.exit(1)
        
    # 3. Check DB
    if not check_db():
        logger.warning("DB check failed (might be expected if DATABASE_URL is not set locally)")
    
    logger.info("=== SANITY CHECK COMPLETED ===")

