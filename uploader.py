import pandas as pd
import os
import json
import ast
from supabase import Client, create_client
from dotenv import load_dotenv
from tqdm import tqdm

# Load environment variables
load_dotenv()

# --- CONFIGURATION ---
INPUT_FILE = "embedded_data.csv"
TABLE_NAME = "documents"

def upload_to_supabase(csv_file):
    """
    Reads CSV and uploads to Supabase 'documents' table.
    """
    print("Uploader: Connecting to Supabase...")
    
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        print("Error: SUPABASE_URL or SUPABASE_KEY not found in .env")
        return

    supabase: Client = create_client(url, key)

    # Read Data
    print(f"Uploader: Reading {csv_file}...")
    df = pd.read_csv(csv_file)

    # Filter only successful rows (optional, but good practice)
    df = df[df['status'] == 'Success'].copy()

    # Prepare Data for Supabase
    records_to_upload = []

    for _, row in df.iterrows():
        # 1. Convert Embedding string back to list of floats
        # CSV saves vectors as strings like "[0.1, 0.2]". Supabase needs actual list [0.1, 0.2].
        try:
            # Handle potential formatting issues from CSV read
            embedding_str = str(row['embedding'])
            # Replace Python single quotes with double quotes for json.loads
            embedding_str = embedding_str.replace("'", '"')
            embedding = json.loads(embedding_str)
        except:
            # If parsing fails, use empty list to prevent crash
            embedding = []

        # 2. Prepare the Row Object based on your Schema
        # Schema: id(bigserial), content, metadata(jsonb), embedding(vector), url, title, chunk_index, total_chunks
        record = {
            "content": str(row['content']),
            "title": str(row['title']),
            "url": str(row['url']),
            "metadata": {
                "status": str(row['status']),
                "source": "scraper" # You can add extra meta here
            },
            "embedding": embedding, # Must be a list of floats
            "chunk_index": 0,      # Defaulting to 0 (no chunking implemented yet)
            "total_chunks": 1       # Defaulting to 1 (no chunking implemented yet)
        }
        
        records_to_upload.append(record)

    # 3. Upload in Batches
    # Supabase can get slow if you upload all 5000 rows at once.
    # We upload in chunks of 100 rows.
    print(f"Uploader: Uploading {len(records_to_upload)} records to Supabase...")
    
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