import pandas as pd
import os
from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
INPUT_FILE = "scraped_data.csv"
OUTPUT_FILE = "embedded_data.csv"
MODEL_NAME = "text-embedding-3-small"
BATCH_SIZE = 50 # Reduced to 50 (now refers to 50 *chunks*, not articles)
CHUNK_SIZE = 3000 # Characters per chunk (approx 750 tokens)

def split_text(text, limit):
    """
    Splits text into chunks of roughly 'limit' characters.
    Tries to split by paragraphs to keep sentences intact.
    """
    paragraphs = text.split('\n')
    chunks = []
    current_chunk = ""
    
    for para in paragraphs:
        # If paragraph is massive (e.g., a wall of text), we might need to force split it
        if len(para) > limit:
            if current_chunk:
                chunks.append(current_chunk)
                current_chunk = ""
            # Force split the huge paragraph
            for i in range(0, len(para), limit):
                chunks.append(para[i:i+limit])
            continue

        if len(current_chunk) + len(para) < limit:
            current_chunk += para + "\n"
        else:
            chunks.append(current_chunk)
            current_chunk = para + "\n"
            
    if current_chunk:
        chunks.append(current_chunk)
        
    return chunks

def get_embeddings_batch(texts):
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    try:
        response = client.embeddings.create(
            input=texts,
            model=MODEL_NAME
        )
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return [None] * len(texts)

def generate_embeddings(input_file, output_file):
    print(f"Embedder: Reading {input_file}...")
    df = pd.read_csv(input_file)

    df_success = df[df['status'] == 'Success'].copy()
    
    if df_success.empty:
        print("Embedder: No successful rows to embed.")
        return

    print(f"Embedder: Processing {len(df_success)} articles...")

    # --- CHUNKING LOGIC ---
    # We expand the dataframe. 1 Article becomes N Rows (Chunks)
    expanded_rows = []
    
    for _, row in df_success.iterrows():
        full_content = str(row['content'])
        
        # Split content into chunks
        chunks = split_text(full_content, CHUNK_SIZE)
        
        # Create a row for EACH chunk
        for i, chunk_text in enumerate(chunks):
            # Skip empty chunks
            if not chunk_text.strip():
                continue
                
            expanded_rows.append({
                "url": row['url'],
                "title": row['title'],
                "content": chunk_text, # Only the chunk text
                "status": row['status'],
                "chunk_index": i,
                "total_chunks": len(chunks)
            })
            
    print(f"Embedder: Expanded into {len(expanded_rows)} total chunks.")

    # --- EMBEDDING LOGIC ---
    texts_to_embed = [r['content'] for r in expanded_rows]
    embeddings_list = []
    
    for i in tqdm(range(0, len(texts_to_embed), BATCH_SIZE), desc="Generating Embeddings"):
        batch_texts = texts_to_embed[i:i + BATCH_SIZE]
        batch_embeddings = get_embeddings_batch(batch_texts)
        embeddings_list.extend(batch_embeddings)

    # Add embeddings to our expanded list
    for i in range(len(expanded_rows)):
        expanded_rows[i]['embedding'] = embeddings_list[i]

    # Create final DataFrame
    df_final = pd.DataFrame(expanded_rows)

    print(f"Embedder: Saving to {output_file}...")
    df_final.to_csv(output_file, index=False)
    print("Embedder: Done.")

if __name__ == "__main__":
    generate_embeddings(INPUT_FILE, OUTPUT_FILE)