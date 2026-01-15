import pandas as pd
import os
from openai import OpenAI
from tqdm import tqdm

# --- CONFIGURATION ---
INPUT_FILE = "scraped_data.xlsx"
OUTPUT_FILE = "embedded_data.xlsx"
MODEL_NAME = "text-embedding-3-small"
BATCH_SIZE = 100  # Send 100 texts at once (Optimal for speed/API limits)

def get_embeddings_batch(texts):
    """
    Generates embeddings for a list of texts using OpenAI.
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    try:
        response = client.embeddings.create(
            input=texts,
            model=MODEL_NAME
        )
        # Extract the vector data from the response
        return [item.embedding for item in response.data]
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return [None] * len(texts)

def generate_embeddings(input_file, output_file):
    print(f"Embedder: Reading {input_file}...")
    df = pd.read_excel(input_file)

    # Filter successful rows only
    df_success = df[df['status'] == 'Success'].copy()
    
    if df_success.empty:
        print("Embedder: No successful rows to embed.")
        return

    print(f"Embedder: Processing {len(df_success)} rows...")

    # Prepare text to embed (Combining Title and Content for better retrieval)
    texts_to_embed = []
    for index, row in df_success.iterrows():
        text_content = f"{row['title']} {row['content']}"
        texts_to_embed.append(text_content)

    embeddings_list = []
    
    # Process in batches
    for i in tqdm(range(0, len(texts_to_embed), BATCH_SIZE), desc="Generating Embeddings"):
        batch_texts = texts_to_embed[i:i + BATCH_SIZE]
        
        # Get embeddings from OpenAI
        batch_embeddings = get_embeddings_batch(batch_texts)
        embeddings_list.extend(batch_embeddings)

    # Add embeddings to dataframe
    df_success['embedding'] = embeddings_list

    # Merge back with failed rows (optional, or just save successes)
    # Here we save only successful embeddings
    print(f"Embedder: Saving to {output_file}...")
    df_success.to_excel(output_file, index=False)
    print("Embedder: Done.")

if __name__ == "__main__":
    # Ensure you have OPENAI_API_KEY in your environment variables
    generate_embeddings(INPUT_FILE, OUTPUT_FILE)