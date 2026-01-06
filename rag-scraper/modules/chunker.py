"""
Text chunking module with token-aware splitting.
Splits text into overlapping chunks for RAG applications.
"""
import logging
from typing import List, Tuple
import tiktoken
import re

logger = logging.getLogger(__name__)


class TextChunker:
    """Splits text into token-aware chunks with overlap."""
    
    def __init__(
        self,
        model: str = "text-embedding-3-small",
        chunk_size_tokens: int = 500,
        chunk_overlap_tokens: int = 50,
    ):
        """
        Initialize the text chunker.
        
        Args:
            model: OpenAI model name for tokenizer
            chunk_size_tokens: Target chunk size in tokens
            chunk_overlap_tokens: Overlap between chunks in tokens
        """
        self.model = model
        self.chunk_size_tokens = chunk_size_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens
        
        # Initialize tokenizer
        try:
            self.encoding = tiktoken.encoding_for_model(model)
        except KeyError:
            logger.warning(f"Model {model} not found in tiktoken, using cl100k_base")
            self.encoding = tiktoken.get_encoding("cl100k_base")
        
        logger.info(
            f"Initialized chunker: {chunk_size_tokens} tokens/chunk, "
            f"{chunk_overlap_tokens} tokens overlap"
        )
    
    def count_tokens(self, text: str) -> int:
        """
        Count the number of tokens in text.
        
        Args:
            text: Input text
            
        Returns:
            Number of tokens
        """
        return len(self.encoding.encode(text))
    
    def _split_sentences(self, text: str) -> List[str]:
        """
        Split text into sentences while preserving sentence boundaries.
        
        Args:
            text: Input text
            
        Returns:
            List of sentences
        """
        # Split on sentence boundaries (., !, ?)
        # Keep the delimiter with the sentence
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        # Filter out empty sentences
        sentences = [s.strip() for s in sentences if s.strip()]
        
        return sentences
    
    def _create_chunks(
        self,
        sentences: List[str],
        max_chunk_tokens: int,
        overlap_tokens: int,
    ) -> List[str]:
        """
        Create chunks from sentences with token limits.
        
        Args:
            sentences: List of sentences
            max_chunk_tokens: Maximum tokens per chunk
            overlap_tokens: Overlap tokens between chunks
            
        Returns:
            List of text chunks
        """
        chunks = []
        current_chunk = []
        current_tokens = 0
        overlap_sentences = []
        
        for sentence in sentences:
            sentence_tokens = self.count_tokens(sentence)
            
            # If single sentence exceeds chunk size, split it
            if sentence_tokens > max_chunk_tokens:
                # Save current chunk if it exists
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                
                # Process large sentence in parts
                words = sentence.split()
                temp_chunk = []
                temp_tokens = 0
                
                for word in words:
                    word_tokens = self.count_tokens(word + " ")
                    
                    if temp_tokens + word_tokens > max_chunk_tokens:
                        if temp_chunk:
                            chunks.append(" ".join(temp_chunk))
                        temp_chunk = [word]
                        temp_tokens = word_tokens
                    else:
                        temp_chunk.append(word)
                        temp_tokens += word_tokens
                
                if temp_chunk:
                    chunks.append(" ".join(temp_chunk))
                
                # Reset for next chunk
                current_chunk = []
                current_tokens = 0
                overlap_sentences = []
                continue
            
            # Check if adding this sentence would exceed chunk size
            if current_tokens + sentence_tokens > max_chunk_tokens:
                # Save current chunk
                if current_chunk:
                    chunks.append(" ".join(current_chunk))
                
                # Start new chunk with overlap
                # Keep sentences that fit within overlap_tokens
                overlap_chunk = []
                overlap_tokens_count = 0
                
                # Add overlap sentences in reverse order (most recent first)
                for sent in reversed(overlap_sentences[-5:]):  # Keep last 5 sentences
                    sent_tokens = self.count_tokens(sent)
                    if overlap_tokens_count + sent_tokens <= overlap_tokens:
                        overlap_chunk.insert(0, sent)
                        overlap_tokens_count += sent_tokens
                
                current_chunk = overlap_chunk
                current_tokens = overlap_tokens_count
                overlap_sentences = overlap_chunk
            
            # Add sentence to current chunk
            current_chunk.append(sentence)
            current_tokens += sentence_tokens
            overlap_sentences.append(sentence)
        
        # Add final chunk
        if current_chunk:
            chunks.append(" ".join(current_chunk))
        
        return chunks
    
    def chunk_text(
        self,
        text: str,
        title: str = "",
    ) -> List[Tuple[str, int, int]]:
        """
        Split text into token-aware chunks with overlap.
        
        Args:
            text: Input text to chunk
            title: Optional title to prepend to chunks
            
        Returns:
            List of tuples (chunk_text, chunk_index, total_chunks)
        """
        if not text or not text.strip():
            logger.warning("Empty text provided for chunking")
            return []
        
        # Prepend title if provided
        if title:
            text = f"{title}\n\n{text}"
        
        # Split into sentences
        sentences = self._split_sentences(text)
        
        if not sentences:
            logger.warning("No sentences found in text")
            return []
        
        # Create chunks
        chunks = self._create_chunks(
            sentences,
            self.chunk_size_tokens,
            self.chunk_overlap_tokens,
        )
        
        # Validate chunks
        valid_chunks = []
        for i, chunk in enumerate(chunks):
            token_count = self.count_tokens(chunk)
            if token_count > 0:
                valid_chunks.append((chunk, i, len(chunks)))
            else:
                logger.warning(f"Chunk {i} has 0 tokens, skipping")
        
        logger.info(
            f"Created {len(valid_chunks)} chunks from {len(text)} characters "
            f"(target: {self.chunk_size_tokens} tokens/chunk)"
        )
        
        return valid_chunks
    
    def validate_chunks(self, chunks: List[Tuple[str, int, int]]) -> bool:
        """
        Validate that chunks meet requirements.
        
        Args:
            chunks: List of (chunk_text, chunk_index, total_chunks) tuples
            
        Returns:
            True if all chunks are valid
        """
        if not chunks:
            return False
        
        for i, (chunk, chunk_index, total_chunks) in enumerate(chunks):
            # Check chunk index matches position
            if chunk_index != i:
                logger.error(f"Chunk index mismatch: {chunk_index} != {i}")
                return False
            
            # Check token count
            token_count = self.count_tokens(chunk)
            if token_count == 0:
                logger.error(f"Chunk {i} has 0 tokens")
                return False
            
            # Log chunks that significantly exceed target
            if token_count > self.chunk_size_tokens * 1.5:
                logger.warning(
                    f"Chunk {i} significantly exceeds target: "
                    f"{token_count} > {self.chunk_size_tokens}"
                )
        
        return True
