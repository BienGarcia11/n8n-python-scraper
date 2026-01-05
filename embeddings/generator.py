"""OpenAI embedding generation."""
import logging
from typing import List, Optional
from openai import AsyncOpenAI
from config import Config

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generates embeddings using OpenAI API."""
    
    def __init__(self):
        """Initialize OpenAI client."""
        self.client = AsyncOpenAI(api_key=Config.OPENAI_API_KEY)
        self.model = Config.EMBEDDING_MODEL
        logger.info(f"Embedding generator initialized with model: {self.model}")
    
    async def generate_embedding(self, text: str) -> Optional[List[float]]:
        """Generate embedding for a single text."""
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=text
            )
            
            embedding = response.data[0].embedding
            logger.debug(f"Generated embedding for text ({len(text)} chars)")
            return embedding
            
        except Exception as e:
            logger.error(f"Error generating embedding: {e}")
            return None
    
    async def generate_embeddings_batch(
        self, 
        texts: List[str], 
        batch_size: int = 100
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for multiple texts in batches."""
        embeddings = []
        
        for i in range(0, len(texts), batch_size):
            batch = texts[i:i + batch_size]
            logger.info(f"Processing embedding batch {i//batch_size + 1}/{(len(texts)-1)//batch_size + 1}")
            
            try:
                response = await self.client.embeddings.create(
                    model=self.model,
                    input=batch
                )
                
                batch_embeddings = [item.embedding for item in response.data]
                embeddings.extend(batch_embeddings)
                
                logger.debug(f"Generated {len(batch_embeddings)} embeddings in batch")
                
            except Exception as e:
                logger.error(f"Error in embedding batch {i//batch_size + 1}: {e}")
                # Add None for failed items
                embeddings.extend([None] * len(batch))
        
        return embeddings
    
    async def generate_embeddings_for_documents(
        self, 
        documents: List[dict], 
        content_key: str = 'content'
    ) -> List[Optional[List[float]]]:
        """Generate embeddings for a list of documents."""
        texts = [doc.get(content_key, '') for doc in documents]
        embeddings = await self.generate_embeddings_batch(texts)
        
        # Pair embeddings with documents
        for doc, embedding in zip(documents, embeddings):
            if embedding is not None:
                doc['embedding'] = embedding
        
        return embeddings
    
    def calculate_token_count(self, text: str) -> int:
        """Estimate token count for text (rough estimate)."""
        # Rough approximation: ~4 characters per token
        return len(text) // 4
    
    def is_text_too_long(self, text: str, max_tokens: int = 8191) -> bool:
        """Check if text exceeds token limit for embedding model."""
        token_count = self.calculate_token_count(text)
        return token_count > max_tokens
    
    def truncate_text(self, text: str, max_tokens: int = 8000) -> str:
        """Truncate text to fit within token limit."""
        if not self.is_text_too_long(text, max_tokens):
            return text
        
        # Roughly truncate to stay under limit
        target_length = max_tokens * 4
        return text[:target_length]
