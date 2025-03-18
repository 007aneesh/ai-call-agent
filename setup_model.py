import os
import requests
import zipfile
from tqdm import tqdm

def download_model():
    # Create model directory if it doesn't exist
    if not os.path.exists('model'):
        os.makedirs('model')
    
    # Small model for English
    model_url = "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    zip_path = "model.zip"
    
    print("Downloading Vosk model...")
    response = requests.get(model_url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    
    with open(zip_path, 'wb') as file, tqdm(
        desc="Downloading",
        total=total_size,
        unit='iB',
        unit_scale=True,
        unit_divisor=1024,
    ) as progress_bar:
        for data in response.iter_content(chunk_size=1024):
            size = file.write(data)
            progress_bar.update(size)
    
    print("\nExtracting model...")
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        zip_ref.extractall("model_temp")
    
    # Move contents from the extracted directory to model directory
    extracted_dir = os.path.join("model_temp", os.listdir("model_temp")[0])
    for item in os.listdir(extracted_dir):
        os.rename(
            os.path.join(extracted_dir, item),
            os.path.join("model", item)
        )
    
    # Clean up
    os.remove(zip_path)
    os.rmdir(extracted_dir)
    os.rmdir("model_temp")
    
    print("Model setup complete!")

if __name__ == "__main__":
    download_model()
