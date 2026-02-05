"""
Experiment 02: Thinking Process
See how the model reasons before generating an image.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import OUTPUT_DIR, PRO_MODEL_ID, client
from google.genai import types


def generate_with_thinking(prompt: str, aspect_ratio: str = "16:9"):
    """Generate an image and show the model's thinking process."""

    response = client.models.generate_content(
        model=PRO_MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            thinking_config=types.ThinkingConfig(include_thoughts=True),
        ),
    )

    # Save image and print text
    for part in response.parts:
        if part.thought:
            print(f"[Thinking] {part.text}")
            print("-" * 50)
        elif part.text:
            print(f"[Response] {part.text}")
        if image := part.as_image():
            output_path = os.path.join(OUTPUT_DIR, "02_thinking.png")
            image.save(output_path)
            print(f"Image saved to: {output_path}")
            return output_path

    return None


if __name__ == "__main__":
    # A complex prompt that requires reasoning
    prompt = "Create an unusual but realistic image that might go viral on social media"

    print(f"Prompt: {prompt}")
    print("=" * 50)
    print("Generating with thinking enabled...")
    print("=" * 50)

    result = generate_with_thinking(prompt, aspect_ratio="16:9")

    if result:
        print("\nDone!")
    else:
        print("No image generated.")
