import json
import logging
import os
import numpy as np
import google.generativeai as genai
from config import is_rag_enabled
from services.llm_service import LLMService

logger = logging.getLogger(__name__)


class RAGService:
    """Service for Retrieval Augmented Generation (RAG).
    
    Embeddings are stored as JSON in the PostgreSQL `document.embedding_json` column.
    This means they survive Render restarts and never need a local FAISS index file.
    """

    EMBEDDING_MODEL = "models/gemini-embedding-001"
    EMBEDDING_DIM = 3072
    # Maximum characters to embed per document (to stay within API limits)
    MAX_CONTENT_CHARS = 8000

    # ------------------------------------------------------------------ #
    #  Embedding helpers                                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_embedding(text):
        """Return a list[float] embedding for *text*, or None on failure."""
        if not LLMService.get_client():
            logger.error("Failed to configure Gemini for embeddings")
            return None

        # Truncate very long texts
        text = text[:RAGService.MAX_CONTENT_CHARS]

        try:
            result = genai.embed_content(
                model=RAGService.EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_document",
            )
            return result["embedding"]
        except Exception as e:
            logger.error(f"Error getting embedding: {e}")
            return None

    @staticmethod
    def get_query_embedding(text):
        """Return a query-optimised embedding (different task_type)."""
        if not LLMService.get_client():
            return None
        text = text[:RAGService.MAX_CONTENT_CHARS]
        try:
            result = genai.embed_content(
                model=RAGService.EMBEDDING_MODEL,
                content=text,
                task_type="retrieval_query",
            )
            return result["embedding"]
        except Exception as e:
            logger.error(f"Error getting query embedding: {e}")
            return None

    # ------------------------------------------------------------------ #
    #  Individual document add                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def add_document(title, content, filename):
        """Add a single document and store its embedding in the DB.
        
        Returns (True, document) on success, (False, error_message) on failure.
        """
        # import here to avoid circular import at module load time
        from app import db
        from models import Document

        try:
            # Create DB record first (without embedding)
            doc = Document(
                title=title,
                content=content,
                filename=filename,
                is_active=True,
            )
            db.session.add(doc)
            db.session.commit()

            # Generate and store embedding
            embedding = RAGService.get_embedding(content)
            if embedding:
                doc.embedding_json = json.dumps(embedding)
                db.session.commit()
                logger.info(f"Document '{title}' added with embedding (id={doc.id})")
            else:
                logger.warning(f"Document '{title}' added WITHOUT embedding (embedding failed)")

            return True, doc

        except Exception as e:
            logger.error(f"Error adding document '{title}': {e}", exc_info=True)
            try:
                from app import db as _db
                _db.session.rollback()
            except Exception:
                pass
            return False, str(e)

    # ------------------------------------------------------------------ #
    #  Bulk add                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _embed_docs_in_background(doc_ids, app):
        """Background thread: generate and save embeddings for a list of doc IDs."""
        with app.app_context():
            from app import db
            from models import Document
            for doc_id in doc_ids:
                try:
                    doc = db.session.get(Document, doc_id)
                    if doc and not doc.embedding_json:
                        embedding = RAGService.get_embedding(doc.content)
                        if embedding:
                            doc.embedding_json = json.dumps(embedding)
                            db.session.commit()
                            logger.info(f"Background: embedded doc id={doc_id}")
                except Exception as e:
                    logger.error(f"Background embedding error for doc {doc_id}: {e}")

    # ------------------------------------------------------------------ #
    #  Bulk add                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def bulk_add_documents(documents_list):
        """Add multiple documents from a list of dicts with keys: title, content, filename.
        
        Documents are saved to the database immediately (fast), and embeddings are
        generated in a background thread so the user doesn't have to wait.
        
        Returns (True, count) or (False, error_message).
        """
        import threading
        from flask import current_app
        from app import db
        from models import Document

        try:
            saved_ids = []
            for item in documents_list:
                title = item.get("title", "Untitled")
                content = item.get("content", "")
                filename = item.get("filename")

                if not content:
                    continue

                doc = Document(
                    title=title,
                    content=content,
                    filename=filename,
                    is_active=True,
                )
                db.session.add(doc)
                db.session.commit()
                saved_ids.append(doc.id)
                logger.info(f"Bulk-saved document '{title}' (id={doc.id}), embedding pending")

            if saved_ids:
                # Start background thread to generate embeddings without blocking
                app = current_app._get_current_object()
                t = threading.Thread(
                    target=RAGService._embed_docs_in_background,
                    args=(saved_ids, app),
                    daemon=True,
                )
                t.start()
                logger.info(f"Started background embedding thread for {len(saved_ids)} documents")

            return True, len(saved_ids)

        except Exception as e:
            logger.error(f"Error in bulk_add_documents: {e}", exc_info=True)
            try:
                db.session.rollback()
            except Exception:
                pass
            return False, str(e)

    # ------------------------------------------------------------------ #
    #  Similarity search (no FAISS, pure numpy)                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _cosine_similarity(vec_a, vec_b):
        """Cosine similarity between two numpy arrays."""
        a = np.array(vec_a, dtype="float32")
        b = np.array(vec_b, dtype="float32")
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    @staticmethod
    def search_similar(query, top_k=3):
        """Return the top_k most similar documents to *query*.
        
        Returns a list of (Document, similarity_score) tuples.
        """
        from models import Document

        query_emb = RAGService.get_query_embedding(query)
        if query_emb is None:
            logger.warning("Could not get query embedding; returning empty results")
            return []

        docs = Document.query.filter_by(is_active=True).all()
        scored = []
        for doc in docs:
            if not doc.embedding_json:
                continue
            try:
                doc_emb = json.loads(doc.embedding_json)
                score = RAGService._cosine_similarity(query_emb, doc_emb)
                scored.append((doc, score))
            except Exception as e:
                logger.error(f"Error computing similarity for doc {doc.id}: {e}")

        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:top_k]

    # ------------------------------------------------------------------ #
    #  Context builder (used by webhook)                                   #
    # ------------------------------------------------------------------ #

    @staticmethod
    def get_context_for_query(query, top_k=3, min_score=0.3):
        """Return a formatted context string for the top matching documents.
        
        Returns None (not an empty string) when RAG is disabled or no match found.
        """
        if not is_rag_enabled():
            return None

        results = RAGService.search_similar(query, top_k=top_k)
        if not results:
            return None

        # Filter by minimum similarity
        relevant = [(doc, score) for doc, score in results if score >= min_score]
        if not relevant:
            return None

        context_parts = []
        for doc, score in relevant:
            context_parts.append(
                f"[來源: {doc.title}]\n{doc.content[:1500]}"
            )

        return "\n\n---\n\n".join(context_parts)

    # ------------------------------------------------------------------ #
    #  Index rebuild (now just re-embeds docs that are missing embeddings) #
    # ------------------------------------------------------------------ #

    @staticmethod
    def update_index():
        """Re-embed any documents that are missing their embedding_json.
        
        This replaces the old FAISS index rebuild and is safe to call at any time.
        """
        from app import db
        from models import Document

        if not LLMService.get_client():
            logger.error("Cannot update embeddings: Gemini configuration failed")
            return False

        try:
            docs_missing = Document.query.filter(
                Document.is_active == True,
                Document.embedding_json.is_(None),
            ).all()

            if not docs_missing:
                logger.info("All documents already have embeddings.")
                return True

            logger.info(f"Re-embedding {len(docs_missing)} documents...")
            for doc in docs_missing:
                embedding = RAGService.get_embedding(doc.content)
                if embedding:
                    doc.embedding_json = json.dumps(embedding)
                    db.session.commit()
                    logger.info(f"Embedded doc id={doc.id} title='{doc.title}'")
                else:
                    logger.warning(f"Could not embed doc id={doc.id}")

            return True

        except Exception as e:
            logger.error(f"Error in update_index: {e}", exc_info=True)
            return False

    # ------------------------------------------------------------------ #
    #  Backward-compat stubs (so existing route calls don't break)         #
    # ------------------------------------------------------------------ #

    @staticmethod
    def initialize_index():
        """Stub – index is now the database, nothing to initialise on disk."""
        return None, {}

    @staticmethod
    def save_index(*args, **kwargs):
        """Stub – embeddings are saved to DB immediately, no file needed."""
        pass
