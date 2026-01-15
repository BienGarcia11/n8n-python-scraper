import pandas as pd
import os
from openai import OpenAI
from tqdm import tqdm
from dotenv import load_dotenv

load_dotenv()

# --- CONFIGURATION ---
INPUT_FILE = "scraped_data.csv"  # Note: Changed to CSV
OUTPUT_FILE = "embedded_data.csv" # Note: Changed to CSV
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
    
    # CHANGE: Use read_csv instead of read_excel
    df = pd.read_csv(input_file)

    # Filter successful rows only
    df_success = df[df['status'] == 'Success'].copy()
    
    if df_success.empty:
        print("Embedder: No successful rows to embed.")
        return

    print(f"Embedder: Processing {len(df_success)} rows...")

    # Prepare text to embed
    # No hard truncation limit (CSV handles large text)
    texts_to_embed = []
    for index, row in df_success.iterrows():
        # Convert content to string just in case
        text_content = f"{row['title']} {str(row['content'])}"
        texts_to_embed.append(text_content)

    embeddings_list = []
    
    for i in tqdm(range(0, len(texts_to_embed), BATCH_SIZE), desc="Generating Embeddings"):
        batch_texts = texts_to_embed[i:i + BATCH_SIZE]
        batch_embeddings = get_embeddings_batch(batch_texts)
        embeddings_list.extend(batch_embeddings)

    # Add embeddings to dataframe
    df_success['embedding'] = embeddings_list

    # CHANGE: Use to_csv instead of to_excel
    print(f"Embedder: Saving to {output_file}...")
    df_success.to_csv(output_file, index=False)
    print("Embedder: Done.")

if __name__ == "__main__":
    generate_embeddings(INPUT_FILE, OUTPUT_FILE)