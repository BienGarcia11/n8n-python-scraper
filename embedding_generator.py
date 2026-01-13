"""
Embedding Generator for Xero Article Data
Creates chunked embeddings using OpenAI's text-embedding-3-small model
"""

import json
import os
from typing import List, Dict
import tiktoken
from openai import OpenAI
import numpy as np
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


class EmbeddingGenerator:
    """Generates embeddings from scraped article data"""
    
    def __init__(self, api_key: str = None):
        """Initialize with OpenAI API key"""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        
        # Debug: Print if key was found (without revealing it)
        if self.api_key:
            print(f"✓ API key loaded (starts with: {self.api_key[:7]}...)")
        else:
            print(f"✗ API key not found in environment variables")
            print(f"  Current env vars: {[k for k in os.environ.keys() if 'OPENAI' in k.upper()]}")
            raise ValueError("OpenAI API key not found. Please set OPENAI_API_KEY environment variable.")
        
        # Initialize OpenAI client with new v1.0+ API
        self.client = OpenAI(api_key=self.api_key)
        self.model = "text-embedding-3-small"
        
        # Initialize tokenizer for accurate chunking
        self.encoding = tiktoken.encoding_for_model(self.model)
    
    def load_data(self, json_file: str) -> Dict:
        """Load scraped data from JSON file"""
        print(f"Loading data from {json_file}...")
        
        with open(json_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        print(f"✓ Data loaded successfully")
        print(f"  - Title: {data.get('metadata', {}).get('title', 'N/A')}")
        print(f"  - URL: {data.get('url', 'N/A')}")
        print(f"  - Full text length: {len(data.get('full_text', ''))} characters")
        
        return data
    
    def chunk_text(self, text: str, chunk_size: int = 800, overlap: int = 200) -> List[Dict]:
        """Split text into chunks respecting sentence boundaries using token-aware chunking"""
        print(f"\nChunking text (max tokens: {chunk_size}, overlap tokens: {overlap})...")
        
        import re
        
        # Clean the text first - remove excessive whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Split into sentences (preserving sentence structure)
        sentences = re.split(r'(?<=[.!?])\s+', text)
        
        chunks = []
        current_chunk = []
        current_tokens = 0
        
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
                
            sentence_tokens = len(self.encoding.encode(sentence))
            
            # If adding this sentence would exceed max tokens and we have content, save current chunk
            if current_tokens + sentence_tokens > chunk_size and current_chunk:
                # Save current chunk
                chunks.append({
                    'chunk_id': len(chunks),
                    'text': ' '.join(current_chunk),
                    'token_count': current_tokens
                })
                
                # Start new chunk with overlap (last few sentences)
                overlap_sentences = []
                overlap_tokens_used = 0
                
                # Walk backwards through current_chunk to build overlap
                for sent in reversed(current_chunk):
                    sent_tokens = len(self.encoding.encode(sent))
                    if overlap_tokens_used + sent_tokens <= overlap:
                        overlap_sentences.insert(0, sent)
                        overlap_tokens_used += sent_tokens
                    else:
                        break
                
                # Start new chunk with overlap + current sentence
                current_chunk = overlap_sentences + [sentence]
                current_tokens = overlap_tokens_used + sentence_tokens
            else:
                # Add sentence to current chunk
                current_chunk.append(sentence)
                current_tokens += sentence_tokens
            
            # Progress indicator
            if len(chunks) > 0 and len(chunks) % 5 == 0 and len(current_chunk) == 1:
                print(f"  Chunks created: {len(chunks)}...", end='\r')
        
        # Don't forget to add the last chunk if it has content
        if current_chunk:
            chunks.append({
                'chunk_id': len(chunks),
                'text': ' '.join(current_chunk),
                'token_count': current_tokens
            })
        
        print(f"✓ Created {len(chunks)} chunks (respecting sentence boundaries)")
        avg_tokens = sum(c['token_count'] for c in chunks) / len(chunks) if chunks else 0
        print(f"  Average tokens per chunk: {avg_tokens:.1f}")
        return chunks
    
    def generate_embedding(self, text: str) -> List[float]:
        """Generate embedding for a single text using OpenAI API"""
        try:
            response = self.client.embeddings.create(
                model=self.model,
                input=text
            )
            embedding = response.data[0].embedding
            return embedding
        except Exception as e:
            print(f"✗ Error generating embedding: {e}")
            return None
    
    def generate_embeddings_batch(self, chunks: List[Dict], batch_size: int = 20) -> List[Dict]:
        """Generate embeddings for multiple chunks in batches - reduced batch size for better performance"""
        print(f"\nGenerating embeddings using {self.model}...")
        print(f"Processing {len(chunks)} chunks in smaller batches of {batch_size}...")
        
        results = []
        total_chunks = len(chunks)
        total_batches = (total_chunks - 1) // batch_size + 1
        
        for i in range(0, total_chunks, batch_size):
            batch = chunks[i:i + batch_size]
            batch_num = i // batch_size + 1
            
            print(f"\nBatch {batch_num}/{total_batches} ({len(batch)} chunks)...", end='\r')
            
            batch_texts = [chunk['text'] for chunk in batch]
            
            try:
                response = self.client.embeddings.create(
                    model=self.model,
                    input=batch_texts
                )
                
                # Combine embeddings with chunk data
                for j, chunk in enumerate(batch):
                    embedding = response.data[j].embedding
                    results.append({
                        **chunk,
                        'embedding': embedding
                    })
                
                print(f"Batch {batch_num}/{total_batches} ({len(batch)} chunks) ✓")
                
            except Exception as e:
                print(f"Batch {batch_num}/{total_batches} failed: {e}")
                # Add chunks without embeddings
                for chunk in batch:
                    results.append({
                        **chunk,
                        'embedding': None
                    })
        
        successful = sum(1 for r in results if r['embedding'] is not None)
        print(f"\n✓ Generated embeddings: {successful}/{len(results)} chunks ({successful/len(results)*100:.1f}%)")
        return results
    
    def create_output(self, data: Dict, chunks_with_embeddings: List[Dict]) -> Dict:
        """Create final output structure"""
        print("\nCreating output structure...")
        
        # Extract metadata
        metadata = {
            'source_url': data.get('url', ''),
            'title': data.get('metadata', {}).get('title', ''),
            'scraped_at': data.get('scraped_at', ''),
            'description': data.get('metadata', {}).get('description', ''),
            'model_used': self.model,
            'total_chunks': len(chunks_with_embeddings),
            'embedding_dimension': len(chunks_with_embeddings[0]['embedding']) if chunks_with_embeddings and chunks_with_embeddings[0]['embedding'] else 0
        }
        
        output = {
            'metadata': metadata,
            'chunks': chunks_with_embeddings
        }
        
        print(f"✓ Output structure created")
        print(f"  - Embedding dimension: {metadata['embedding_dimension']}")
        print(f"  - Total chunks: {metadata['total_chunks']}")
        
        return output
    
    def save_embeddings(self, output: Dict, filename: str):
        """Save embeddings to JSON file"""
        print(f"\nSaving to {filename}...")
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2, ensure_ascii=False)
        
        print(f"✓ Saved successfully!")
    
    def process(self, input_file: str, output_file: str = 'embeddings.json', 
                chunk_size: int = 800, overlap: int = 200) -> Dict:
        """Main processing pipeline - optimized for better performance"""
        print("="*60)
        print("EMBEDDING GENERATION")
        print("="*60)
        
        # Step 1: Load data
        data = self.load_data(input_file)
        
        # Step 2: Chunk text
        chunks = self.chunk_text(data['full_text'], chunk_size, overlap)
        
        # Step 3: Generate embeddings with smaller batches
        chunks_with_embeddings = self.generate_embeddings_batch(chunks, batch_size=20)
        
        # Step 4: Create output
        output = self.create_output(data, chunks_with_embeddings)
        
        # Step 5: Save to file
        self.save_embeddings(output, output_file)
        
        print("\n" + "="*60)
        print("SUMMARY")
        print("="*60)
        print(f"✓ Successfully processed {data.get('url', 'unknown')}")
        print(f"✓ Created {len(chunks)} chunks with embeddings")
        print(f"✓ Saved to {output_file}")
        print(f"✓ Model: {self.model}")
        print("="*60 + "\n")
        
        return output


def main():
    """Main function to run embedding generator"""
    # Configuration - optimized for better performance
    input_file = "xero_article_data.json"
    output_file = "embeddings.json"
    chunk_size = 800
    overlap = 100  # Reduced overlap for fewer chunks and less processing
    
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: {input_file} not found!")
        print("Please run the scraper first: python scraper.py")
        return
    
    try:
        # Create generator instance
        generator = EmbeddingGenerator()
        
        # Process data
        output = generator.process(
            input_file=input_file,
            output_file=output_file,
            chunk_size=chunk_size,
            overlap=overlap
        )
        
        print("\nEmbedding generation complete!")
        print(f"Output saved to: {output_file}")
        
    except ValueError as e:
        print(f"\nError: {e}")
        print("\nPlease set your OpenAI API key:")
        print("  Windows: set OPENAI_API_KEY=your_key_here")
        print("  Linux/Mac: export OPENAI_API_KEY=your_key_here")
        print("  Or create a .env file with: OPENAI_API_KEY=your_key_here")
        
    except Exception as e:
        print(f"\nUnexpected error: {e}")

if __name__ == "__main__":
    main()
