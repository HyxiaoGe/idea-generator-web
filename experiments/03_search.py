"""
Experiment 03: Search Grounding
Generate images based on real-time search data.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import OUTPUT_DIR, PRO_MODEL_ID, client
from google.genai import types


def generate_with_search(prompt: str, aspect_ratio: str = "16:9"):
    """Generate an image using real-time search data."""

    response = client.models.generate_content(
        model=PRO_MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
            tools=[{"google_search": {}}],
        ),
    )

    # Process response parts
    for part in response.parts:
        if part.text:
            print(f"[Response] {part.text}")
        if image := part.as_image():
            output_path = os.path.join(OUTPUT_DIR, "03_search.png")
            image.save(output_path)
            print(f"\nImage saved to: {output_path}")

    # Show search sources (required by Google's policy)
    if response.candidates and response.candidates[0].grounding_metadata:
        metadata = response.candidates[0].grounding_metadata
        if hasattr(metadata, "search_entry_point") and metadata.search_entry_point:
            print("\n[Search Sources]")
            print(metadata.search_entry_point.rendered_content)

    return None


if __name__ == "__main__":
    # Try different prompts that benefit from real-time data
    prompts = [
        "Visualize the current weather forecast for the next 5 days in Guangdong Province, China as a clean, modern weather chart",
        # "Create an infographic about the latest AI news this week",
        # "Generate an image showing the current top 3 movies in theaters",
    ]

    prompt = prompts[0]  # Change index to try different prompts

    print(f"Prompt: {prompt}")
    print("=" * 50)
    print("Generating with search grounding...")
    print("=" * 50)

    generate_with_search(prompt, aspect_ratio="16:9")

    print("\nDone!")
