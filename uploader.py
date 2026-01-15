import pandas as pd
import os
import json
from supabase import Client, create_client
from dotenv import load_dotenv
from tqdm import tqdm

load_dotenv()

# --- CONFIGURATION ---
INPUT_FILE = "embedded_data.csv"
TABLE_NAME = "documents"

def upload_to_supabase(csv_file):
    print("Uploader: Connecting to Supabase...")
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found in .env")
        return

    supabase: Client = create_client(url, key)

    print(f"Uploader: Reading {csv_file}...")
    df = pd.read_csv(csv_file)

    # Filter successful rows only
    df = df[df['status'] == 'Success'].copy()

    # --- STEP 1: GET EXISTING URLS (PREVENT DUPLICATES) ---
    print("Uploader: Checking for existing URLs...")
    try:
        # We only fetch the 'url' column to save bandwidth/time
        existing_data = supabase.table(TABLE_NAME).select("url").execute()
        existing_urls = set([item['url'] for item in existing_data.data])
        print(f"Uploader: Found {len(existing_urls)} existing URLs.")
    except Exception as e:
        print(f"Uploader: Could not check existing URLs (might be first run). {e}")
        existing_urls = set()

    # --- STEP 2: PREPARE RECORDS ---
    records_to_upload = []
    skipped_count = 0

    print(f"Uploader: Preparing {len(df)} records for upload...")

    for _, row in df.iterrows():
        url = str(row['url'])
        
        # CHECK: Skip if URL already exists
        if url in existing_urls:
            skipped_count += 1
            continue
        
        embedding_str = str(row['embedding'])
        
        # CHECK: Skip invalid embeddings
        if embedding_str == "None" or not embedding_str.startswith("["):
            continue
        
        try:
            # Convert string to list
            embedding_str = embedding_str.replace("'", '"')
            embedding = json.loads(embedding_str)
        except:
            continue

        record = {
            "content": str(row['content']),
            "title": str(row['title']),
            "url": url,
            "metadata": {
                "status": str(row['status']), 
                "source": "scraper",
                # Store chunking info for RAG deduplication
                "chunk_index": int(row['chunk_index']),
                "total_chunks": int(row['total_chunks'])
            },
            "embedding": embedding, 
            "chunk_index": int(row['chunk_index']), 
            "total_chunks": int(row['total_chunks'])
        }
        
        records_to_upload.append(record)

    print(f"Uploader: Skipped {skipped_count} duplicates.")
    print(f"Uploader: Uploading {len(records_to_upload)} NEW records to Supabase...")
    
    # --- STEP 3: UPLOAD ---
    BATCH_SIZE = 100
    for i in tqdm(range(0, len(records_to_upload), BATCH_SIZE), desc="Uploading to Supabase"):
        batch = records_to_upload[i:i + BATCH_SIZE]
        
        try:
            # Insert ONLY. Since we filtered existing ones, this is safe.
            # If you wanted to Update (overwrite) instead of skip, you'd need logic to find ID.
            response = supabase.table(TABLE_NAME).insert(batch).execute()
        except Exception as e:
            print(f"\nUploader: Error inserting batch starting at index {i}: {e}")

    print("Uploader: Upload Complete.")

if __name__ == "__main__":
    upload_to_supabase(INPUT_FILE)