import google.genai as genai
from stratos.config import settings

# Initialize the GenAI Client
client = genai.Client(api_key=settings.gemini_api_key)

def embed_text(text: str) -> list[float]:
    """Generate a single text embedding using Gemini's text-embedding-001 model."""
    try:
        # Use the exact pattern requested by the user
        result = client.models.embed_content(
            model="models/gemini-embedding-001",
            contents=text
        )
        return result.embeddings[0].values
    except Exception as e:
        print(f"Error generating embedding: {e}")
        return []

def embed_batch(texts: list[str]) -> list[list[float]]:
    """Generate embeddings for a batch of texts."""
    embeddings = []
    for text in texts:
        vector = embed_text(text)
        if vector:
            embeddings.append(vector)
        else:
            print(f"Skipping failed embedding for text: {text[:50]}...")
    return embeddings

if __name__ == "__main__":
    test_text = "competitive intelligence signal about AI product launch"
    print(f"Testing embedding for: '{test_text}'")
    result = embed_text(test_text)
    
    if result:
        dimension = len(result)
        print(f"Embedding dimension: {dimension}")
        print(f"First 5 values: {result[:5]}")
        
        if dimension == 768:
            print("Embeddings working correctly (dimension 768)")
        else:
            print(f"Unexpected embedding dimension: {dimension}")
    else:
        print("Embedding generation failed.")
