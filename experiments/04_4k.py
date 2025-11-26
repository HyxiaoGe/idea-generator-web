"""
Experiment 04: 4K Ultra HD Generation
Generate high-resolution images for print-quality output.
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import client, PRO_MODEL_ID, OUTPUT_DIR
from google.genai import types


def generate_4k_image(prompt: str, resolution: str = "4K", aspect_ratio: str = "16:9"):
    """
    Generate a high-resolution image.
    
    Args:
        prompt: Image description
        resolution: "1K", "2K", or "4K" (must be uppercase)
        aspect_ratio: Image aspect ratio
    """
    
    response = client.models.generate_content(
        model=PRO_MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio,
                image_size=resolution
            )
        )
    )
    
    # Process response parts
    for part in response.parts:
        if part.text:
            print(f"[Response] {part.text}")
        if image := part.as_image():
            output_path = os.path.join(OUTPUT_DIR, f"04_{resolution}.png")
            image.save(output_path)
            
            print(f"Image saved to: {output_path}")
            return output_path
    
    return None


if __name__ == "__main__":
    prompt = "A photo of an oak tree experiencing every season, split into four quadrants showing spring blossoms, summer leaves, autumn colors, and winter snow"
    
    # Compare different resolutions
    # Note: 4K costs more ($0.24 vs $0.134 for 1K/2K)
    resolution = "4K"  # Options: "1K", "2K", "4K"
    
    print(f"Prompt: {prompt}")
    print(f"Resolution: {resolution}")
    print("=" * 50)
    print("Generating high-resolution image...")
    print("=" * 50)
    
    result = generate_4k_image(prompt, resolution=resolution, aspect_ratio="1:1")
    
    if result:
        print("\nDone!")
    else:
        print("No image generated.")