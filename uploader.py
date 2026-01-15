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

    records_to_upload = []

    for _, row in df.iterrows():
        # Convert embedding string to list
        try:
            embedding_str = str(row['embedding'])
            embedding_str = embedding_str.replace("'", '"')
            embedding = json.loads(embedding_str)
        except:
            embedding = []

        # Prepare Record
        record = {
            "content": str(row['content']), # This is now just the chunk
            "title": str(row['title']),
            "url": str(row['url']),
            "metadata": {
                "status": str(row['status']),
                "source": "scraper"
            },
            "embedding": embedding, 
            # Use actual chunk data from CSV
            "chunk_index": int(row['chunk_index']), 
            "total_chunks": int(row['total_chunks'])
        }
        
        records_to_upload.append(record)

    print(f"Uploader: Uploading {len(records_to_upload)} chunks to Supabase...")
    
    BATCH_SIZE = 100
    for i in tqdm(range(0, len(records_to_upload), BATCH_SIZE), desc="Uploading to Supabase"):
        batch = records_to_upload[i:i + BATCH_SIZE]
        
        try:
            response = supabase.table(TABLE_NAME).insert(batch).execute()
        except Exception as e:
            print(f"\nUploader: Error inserting batch starting at index {i}: {e}")

    print("Uploader: Upload Complete.")

if __name__ == "__main__":
    upload_to_supabase(INPUT_FILE)