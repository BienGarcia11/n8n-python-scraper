import pandas as pd
import os
from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv  # <--- IMPORT THIS

# Load environment variables from .env file
load_dotenv()  # <--- ADD THIS

# --- CONFIGURATION ---
INPUT_FILE = "scraped_data.xlsx"
OUTPUT_FILE = "embedded_data.xlsx"
MODEL_NAME = "text-embedding-3-small"
BATCH_SIZE = 100

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
    df = pd.read_excel(input_file)

    df_success = df[df['status'] == 'Success'].copy()
    
    if df_success.empty:
        print("Embedder: No successful rows to embed.")
        return

    print(f"Embedder: Processing {len(df_success)} rows...")

    texts_to_embed = []
    for index, row in df_success.iterrows():
        text_content = f"{row['title']} {row['content']}"
        texts_to_embed.append(text_content)

    embeddings_list = []
    
    for i in tqdm(range(0, len(texts_to_embed), BATCH_SIZE), desc="Generating Embeddings"):
        batch_texts = texts_to_embed[i:i + BATCH_SIZE]
        batch_embeddings = get_embeddings_batch(batch_texts)
        embeddings_list.extend(batch_embeddings)

    df_success['embedding'] = embeddings_list

    print(f"Embedder: Saving to {output_file}...")
    df_success.to_excel(output_file, index=False)
    print("Embedder: Done.")

if __name__ == "__main__":
    generate_embeddings(INPUT_FILE, OUTPUT_FILE)