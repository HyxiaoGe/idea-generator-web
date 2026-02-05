"""
Experiment 06: Advanced Image Blending
Combine multiple images into one coherent scene.
Pro model supports up to 14 images (Flash only supports 3).
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import OUTPUT_DIR, PRO_MODEL_ID, client
from google.genai import types
from PIL import Image as PILImage


def blend_images(prompt: str, image_paths: list, aspect_ratio: str = "16:9"):
    """
    Blend multiple images based on a prompt.

    Args:
        prompt: Description of how to combine the images
        image_paths: List of paths to input images (max 14 for Pro)
        aspect_ratio: Output aspect ratio
    """

    # Build contents with prompt and images
    contents = [prompt]

    for path in image_paths:
        if os.path.exists(path):
            img = PILImage.open(path)
            contents.append(img)
            print(f"Loaded: {path}")
        else:
            print(f"Warning: {path} not found, skipping...")

    if len(contents) == 1:
        print("No images loaded. Please provide valid image paths.")
        return None

    response = client.models.generate_content(
        model=PRO_MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        ),
    )

    # Process response
    for part in response.parts:
        if part.text:
            print(f"\n[Response] {part.text}")
        if image := part.as_image():
            output_path = os.path.join(OUTPUT_DIR, "06_blend.png")
            image.save(output_path)
            print(f"\nImage saved to: {output_path}")
            return output_path

    return None


def demo_style_transfer():
    """Demo: Apply style from one image to another."""

    # First, generate two base images to work with
    print("Generating base images for blending demo...")
    print("-" * 50)

    # Generate a photo
    response1 = client.models.generate_content(
        model=PRO_MODEL_ID,
        contents="A simple photo of a cat sitting on a windowsill",
        config={"response_modalities": ["IMAGE"], "image_config": {"aspect_ratio": "1:1"}},
    )

    for part in response1.parts:
        if image := part.as_image():
            path1 = os.path.join(OUTPUT_DIR, "06_base_photo.png")
            image.save(path1)
            print(f"Base photo saved: {path1}")

    # Generate a style reference
    response2 = client.models.generate_content(
        model=PRO_MODEL_ID,
        contents="Abstract colorful watercolor painting with vibrant splashes",
        config={"response_modalities": ["IMAGE"], "image_config": {"aspect_ratio": "1:1"}},
    )

    for part in response2.parts:
        if image := part.as_image():
            path2 = os.path.join(OUTPUT_DIR, "06_style_ref.png")
            image.save(path2)
            print(f"Style reference saved: {path2}")

    # Now blend them
    print("\nBlending images...")
    print("-" * 50)

    blend_images(
        prompt="Apply the artistic style from the second image to the first image, creating a watercolor painting of the cat",
        image_paths=[
            os.path.join(OUTPUT_DIR, "06_base_photo.png"),
            os.path.join(OUTPUT_DIR, "06_style_ref.png"),
        ],
        aspect_ratio="1:1",
    )


if __name__ == "__main__":
    print("=" * 50)
    print("Image Blending Demo")
    print("=" * 50)

    # Run the style transfer demo
    demo_style_transfer()

    # Or use your own images:
    # blend_images(
    #     prompt="Create a group photo of these people at a beach party",
    #     image_paths=["person1.png", "person2.png", "person3.png"],
    #     aspect_ratio="16:9"
    # )

    print("\nDone!")
