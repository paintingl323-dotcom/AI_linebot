
import os
import sys
import logging
from app import app, db
from models import Document
from rag_service import RAGService

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_rag():
    print("Starting RAG verification test...")
    
    with app.app_context():
        # 1. Initialize DB and Index
        print("Initializing database and RAG index...")
        db.create_all()
        RAGService.initialize_index()
        
        # 2. Add a test document
        test_title = "Antigravity Test Doc"
        test_content = "Antigravity is a secret project by Google Deepmind. It involves advanced agentic coding capabilities."
        print(f"Adding test document: {test_title}")
        
        success, result = RAGService.add_document(test_title, test_content)
        if not success:
            print(f"FAILED to add document: {result}")
            return
        
        print(f"Document added successfully. Doc ID: {result}")
        
        # 3. Verify document in DB
        doc = Document.query.get(result)
        if not doc:
            print("FAILED: Document not found in database after addition.")
            return
        print("Document verified in database.")
        
        # 4. Test Search (Retrieval)
        query = "What is Antigravity?"
        print(f"Testing search with query: '{query}'")
        
        results = RAGService.search(query)
        
        if not results:
            print("FAILED: Search returned no results.")
            return
            
        print(f"Search returned {len(results)} results.")
        found = False
        for res in results:
            print(f" - Found: {res['title']}")
            if res['title'] == test_title:
                found = True
        
        if found:
            print("SUCCESS: Test document was retrieved correctly!")
        else:
            print("FAILED: Test document was not among the search results.")

        # 5. Cleanup (Optional but good for repeated testing)
        print("Cleaning up test document...")
        RAGService.delete_document(result)
        print("Cleanup complete.")

if __name__ == "__main__":
    # Ensure we use the .env file we just updated
    # The main.py does a manual load, let's replicate that or just rely on the fact we are running in the same dir
    # But python-dotenv might not be installed, so we rely on finding the env vars or the config service loading them
    # For this test, we need to make sure os.environ has the key if config_service relies on it and we are not running via `flask run`
    
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        print(f"Loading environment from {env_path}")
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()

    try:
        test_rag()
    except Exception as e:
        print(f"Test crashed with error: {e}")
        import traceback
        traceback.print_exc()

