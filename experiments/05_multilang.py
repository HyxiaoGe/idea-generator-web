"""
Experiment 05: Multilingual Capabilities
Generate images with text in different languages and translate between them.
"""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from config import OUTPUT_DIR, PRO_MODEL_ID, client
from google.genai import types


def generate_multilingual_image(
    prompt: str, aspect_ratio: str = "16:9", filename: str = "05_multilang.png"
):
    """Generate an image with text in a specific language."""

    response = client.models.generate_content(
        model=PRO_MODEL_ID,
        contents=prompt,
        config=types.GenerateContentConfig(
            response_modalities=["Text", "Image"],
            image_config=types.ImageConfig(aspect_ratio=aspect_ratio),
        ),
    )

    # Process response parts
    for part in response.parts:
        if part.text:
            print(f"[Response] {part.text}")
        if image := part.as_image():
            output_path = os.path.join(OUTPUT_DIR, filename)
            image.save(output_path)
            print(f"Image saved to: {output_path}")
            return output_path

    return None


def chat_and_translate():
    """Use chat mode to generate and then translate an infographic."""

    # Create a chat session
    chat = client.chats.create(model=PRO_MODEL_ID)

    # Step 1: Generate infographic in English
    print("Step 1: Generating English infographic...")
    print("-" * 50)

    response1 = chat.send_message(
        "Make an infographic explaining how coffee is made, from bean to cup, in English",
        config={"response_modalities": ["TEXT", "IMAGE"], "image_config": {"aspect_ratio": "9:16"}},
    )

    for part in response1.parts:
        if part.text:
            print(f"[Response] {part.text}")
        if image := part.as_image():
            output_path = os.path.join(OUTPUT_DIR, "05_multilang_en.png")
            image.save(output_path)
            print(f"Image saved to: {output_path}")

    # Step 2: Translate to Chinese
    print("\nStep 2: Translating to Chinese...")
    print("-" * 50)

    response2 = chat.send_message(
        "Translate this infographic to Chinese, keeping everything else the same",
        config={"response_modalities": ["TEXT", "IMAGE"], "image_config": {"aspect_ratio": "9:16"}},
    )

    for part in response2.parts:
        if part.text:
            print(f"[Response] {part.text}")
        if image := part.as_image():
            output_path = os.path.join(OUTPUT_DIR, "05_multilang_zh.png")
            image.save(output_path)
            print(f"Image saved to: {output_path}")


if __name__ == "__main__":
    print("=" * 50)
    print("Multilingual Image Generation Demo")
    print("=" * 50)

    # Option 1: Single language generation
    # generate_multilingual_image(
    #     "Create a motivational poster with the text 'Never Give Up' in Japanese calligraphy style",
    #     filename="05_multilang_jp.png"
    # )

    # Option 2: Chat mode with translation
    chat_and_translate()

    print("\nDone!")
