"""Supabase database operations."""
import logging
from typing import List, Dict, Any, Optional
from supabase import create_client, Client
from config import Config

logger = logging.getLogger(__name__)


class DatabaseManager:
    """Manages all database operations for the scraper."""
    
    def __init__(self):
        """Initialize Supabase client."""
        self.client: Client = create_client(
            Config.SUPABASE_URL,
            Config.SUPABASE_SERVICE_KEY
        )
        logger.info("Database manager initialized")
    
    def get_pending_urls(self, limit: int = None) -> List[Dict[str, Any]]:
        """Get pending URLs from the queue."""
        try:
            query = self.client.table('url_queue').select('*').eq('status', 'pending')
            if limit:
                query = query.limit(limit)
            
            result = query.order('created_at', asc=False).execute()
            logger.info(f"Retrieved {len(result.data)} pending URLs")
            return result.data
        except Exception as e:
            logger.error(f"Error fetching pending URLs: {e}")
            return []
    
    def update_url_status(
        self, 
        url_id: int, 
        status: str, 
        error_message: Optional[str] = None
    ) -> bool:
        """Update URL status in queue."""
        try:
            update_data = {
                'status': status,
                'updated_at': 'now()'
            }
            
            if error_message:
                update_data['error_message'] = error_message
            
            self.client.table('url_queue').update(update_data).eq('id', url_id).execute()
            logger.debug(f"Updated URL {url_id} to status: {status}")
            return True
        except Exception as e:
            logger.error(f"Error updating URL {url_id}: {e}")
            return False
    
    def insert_document(
        self, 
        content: str, 
        metadata: Dict[str, Any], 
        embedding: Optional[List[float]] = None
    ) -> Optional[int]:
        """Insert scraped document into documents table."""
        try:
            data = {
                'content': content,
                'metadata': metadata,
                'updated_at': 'now()'
            }
            
            if embedding:
                data['embedding'] = embedding
            
            result = self.client.table('documents').insert(data).execute()
            doc_id = result.data[0]['id']
            logger.info(f"Inserted document {doc_id}")
            return doc_id
        except Exception as e:
            logger.error(f"Error inserting document: {e}")
            return None
    
    def batch_insert_documents(
        self, 
        documents: List[Dict[str, Any]]
    ) -> List[int]:
        """Batch insert documents with embeddings."""
        try:
            result = self.client.table('documents').insert(documents).execute()
            doc_ids = [doc['id'] for doc in result.data]
            logger.info(f"Batch inserted {len(doc_ids)} documents")
            return doc_ids
        except Exception as e:
            logger.error(f"Error batch inserting documents: {e}")
            return []
    
    def get_statistics(self) -> Dict[str, int]:
        """Get scraping statistics."""
        try:
            # Get URL queue statistics
            queue_stats = self.client.table('url_queue').select('status').execute()
            status_counts = {}
            for item in queue_stats.data:
                status = item['status']
                status_counts[status] = status_counts.get(status, 0) + 1
            
            # Get documents count
            docs_result = self.client.table('documents').select('id', count='exact').execute()
            total_documents = docs_result.count if docs_result.count else 0
            
            stats = {
                **status_counts,
                'total_documents': total_documents,
                'total_urls': len(queue_stats.data)
            }
            
            return stats
        except Exception as e:
            logger.error(f"Error fetching statistics: {e}")
            return {}
    
    def update_url_batch_status(
        self, 
        url_ids: List[int], 
        status: str
    ) -> bool:
        """Update status for multiple URLs."""
        try:
            update_data = {
                'status': status,
                'updated_at': 'now()'
            }
            
            # Update in batches to avoid query size limits
            batch_size = 100
            for i in range(0, len(url_ids), batch_size):
                batch_ids = url_ids[i:i + batch_size]
                self.client.table('url_queue').update(update_data).in_('id', batch_ids).execute()
            
            logger.info(f"Updated {len(url_ids)} URLs to status: {status}")
            return True
        except Exception as e:
            logger.error(f"Error batch updating URLs: {e}")
            return False
