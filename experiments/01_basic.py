"""
Experiment 01: Basic Image Generation
"""
import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import client, PRO_MODEL_ID, OUTPUT_DIR
from google.genai import types

def generate_basic_image(prompt: str, aspect_ratio: str = "16:9"):
    """Generate an image with basic settings."""

    response = client.models.generate_content(
        model=PRO_MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(
                aspect_ratio=aspect_ratio
            )
        )
    )

    # Save image and print text
    for part in response.parts:
        if part.text:
            print(f"Model response: {part.text}")
        if image := part.as_image():
            output_path = os.path.join(OUTPUT_DIR, "01_basic.png")
            image.save(output_path)
            print(f"Image saved to: {output_path}")
            return output_path

    return None

if __name__ == "__main__":
    # Try your own prompt here
    prompt = "A cute corgi wearing sunglasses, sitting on a beach at sunset, photorealistic"
    
    print(f"Prompt: {prompt}")
    print("Generating...")
    
    result = generate_basic_image(prompt, aspect_ratio="16:9")
    
    if result:
        print("Done!")
    else:
        print("No image generated.")