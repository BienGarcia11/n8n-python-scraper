"""
Embedding module using OpenAI API.
Generates vector embeddings for text chunks using text-embedding-3-small.
"""
import logging
from typing import List, Optional
import asyncio
from openai import AsyncOpenAI, RateLimitError, APITimeoutError
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
)

logger = logging.getLogger(__name__)


class EmbeddingGenerator:
    """Generates embeddings using OpenAI API with retry logic."""
    
    def __init__(
        self,
        api_key: str,
        model: str = "text-embedding-3-small",
        batch_size: int = 100,
        max_retries: int = 3,
    ):
        """
        Initialize embedding generator.
        
        Args:
            api_key: OpenAI API key
            model: Model name for embeddings
            batch_size: Maximum number of texts per API call
            max_retries: Maximum number of retry attempts
        """
        self.model = model
        self.batch_size = batch_size
        self.max_retries = max_retries
        
        # Initialize async OpenAI client
        self.client = AsyncOpenAI(api_key=api_key)
        
        logger.info(
            f"Initialized embedding generator: model={model}, "
            f"batch_size={batch_size}, max_retries={max_retries}"
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((RateLimitError, APITimeoutError)),
    )
    async def _embed_batch(
        self,
        texts: List[str],
        attempt: int = 1,
    ) -> List[List[float]]:
        """
        Embed a batch of texts with retry logic.
        
        Args:
            texts: List of text strings to embed
            attempt: Current attempt number (for logging)
            
        Returns:
            List of embedding vectors
            
        Raises:
            Exception: If all retries are exhausted
        """
        try:
            response = await self.client.embeddings.create(
                model=self.model,
                input=texts,
            )
            
            embeddings = [item.embedding for item in response.data]
            logger.info(
                f"Generated {len(embeddings)} embeddings "
                f"(attempt {attempt})"
            )
            return embeddings
            
        except RateLimitError as e:
            logger.warning(f"Rate limit hit on attempt {attempt}: {e}")
            raise
        except APITimeoutError as e:
            logger.warning(f"API timeout on attempt {attempt}: {e}")
            raise
        except Exception as e:
            logger.error(f"Error generating embeddings on attempt {attempt}: {e}")
            raise
    
    async def embed_chunks(
        self,
        chunks: List[str],
    ) -> Optional[List[List[float]]]:
        """
        Generate embeddings for a list of text chunks.
        
        Args:
            chunks: List of text chunks to embed
            
        Returns:
            List of embedding vectors, or None if failed
        """
        if not chunks:
            logger.warning("No chunks provided for embedding")
            return None
        
        # Filter empty chunks
        valid_chunks = [c for c in chunks if c and c.strip()]
        if len(valid_chunks) != len(chunks):
            logger.warning(
                f"Filtered {len(chunks) - len(valid_chunks)} empty chunks"
            )
        
        if not valid_chunks:
            logger.error("No valid chunks to embed")
            return None
        
        embeddings = []
        
        # Process in batches
        for i in range(0, len(valid_chunks), self.batch_size):
            batch = valid_chunks[i:i + self.batch_size]
            batch_num = (i // self.batch_size) + 1
            total_batches = (len(valid_chunks) + self.batch_size - 1) // self.batch_size
            
            logger.info(
                f"Processing batch {batch_num}/{total_batches} "
                f"({len(batch)} chunks)"
            )
            
            try:
                batch_embeddings = await self._embed_batch(batch)
                embeddings.extend(batch_embeddings)
            except Exception as e:
                logger.error(
                    f"Failed to embed batch {batch_num}/{total_batches}: {e}"
                )
                # Return partial results if some batches succeeded
                if embeddings:
                    logger.warning(
                        f"Returning {len(embeddings)} partial embeddings "
                        f"out of {len(valid_chunks)} requested"
                    )
                return None
        
        logger.info(
            f"Successfully generated {len(embeddings)} embeddings "
            f"({len(valid_chunks)} chunks requested)"
        )
        
        return embeddings
    
    async def embed_single(
        self,
        text: str,
    ) -> Optional[List[float]]:
        """
        Generate embedding for a single text.
        
        Args:
            text: Text to embed
            
        Returns:
            Embedding vector, or None if failed
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for embedding")
            return None
        
        try:
            result = await self._embed_batch([text])
            return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to embed single text: {e}")
            return None
    
    async def validate_embedding(
        self,
        embedding: List[float],
        expected_dim: int = 1536,
    ) -> bool:
        """
        Validate that embedding has correct dimensions.
        
        Args:
            embedding: Embedding vector to validate
            expected_dim: Expected dimension
            
        Returns:
            True if valid, False otherwise
        """
        if not isinstance(embedding, list):
            logger.error("Embedding is not a list")
            return False
        
        if len(embedding) != expected_dim:
            logger.error(
                f"Embedding dimension mismatch: "
                f"{len(embedding)} != {expected_dim}"
            )
            return False
        
        # Check all values are floats
        if not all(isinstance(v, (int, float)) for v in embedding):
            logger.error("Embedding contains non-numeric values")
            return False
        
        return True
    
    async def close(self):
        """Close the OpenAI client."""
        await self.client.close()
        logger.info("Closed embedding generator client")
