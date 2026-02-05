"""
Quick test script for prompt generation and storage.
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os

from dotenv import load_dotenv

from services.prompt_generator import get_prompt_generator
from services.prompt_storage import get_prompt_storage

load_dotenv()


def test_prompt_generation():
    """Test prompt generation."""
    print("🧪 Testing Prompt Generation...")
    print()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ GOOGLE_API_KEY not found")
        return False

    try:
        generator = get_prompt_generator(api_key)

        # Test 1: Generate category prompts
        print("Test 1: Generate category prompts")
        prompts = generator.generate_category_prompts(
            category="portrait",
            style="photorealistic",
            count=5,
            language="en"
        )
        print(f"✅ Generated {len(prompts)} prompts")
        for i, p in enumerate(prompts[:3], 1):
            print(f"   {i}. {p.get('prompt', '')[:60]}...")
        print()

        # Test 2: Enhance prompt
        print("Test 2: Enhance prompt")
        basic = "a cat on a windowsill"
        enhanced = generator.enhance_prompt(basic, language="en")
        print(f"   Original: {basic}")
        print(f"   Enhanced: {enhanced}")
        print()

        # Test 3: Generate variations
        print("Test 3: Generate variations")
        variations = generator.generate_variations(
            base_prompt="sunset over mountains",
            count=3,
            variation_type="style"
        )
        print(f"✅ Generated {len(variations)} variations")
        for i, v in enumerate(variations, 1):
            print(f"   {i}. {v[:60]}...")
        print()

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        return False


def test_prompt_storage():
    """Test prompt storage."""
    print("🧪 Testing Prompt Storage...")
    print()

    try:
        storage = get_prompt_storage()

        # Test 1: Save and load
        print("Test 1: Save and load prompts")
        test_prompts = [
            {
                "prompt": "test prompt 1",
                "description": "test description",
                "tags": ["test"],
                "source": "test"
            },
            {
                "prompt": "test prompt 2",
                "description": "test description 2",
                "tags": ["test"],
                "source": "test"
            }
        ]

        storage.save_category_prompts("test_category", test_prompts, sync_to_cloud=False)
        loaded = storage.load_category_prompts("test_category", try_cloud=False)
        print(f"✅ Saved and loaded {len(loaded)} prompts")
        print()

        # Test 2: Add to favorites
        print("Test 2: Add to favorites")
        storage.add_to_favorites(test_prompts[0])
        favorites = storage.get_favorites()
        print(f"✅ Favorites count: {len(favorites)}")
        print()

        # Test 3: Search
        print("Test 3: Search prompts")
        results = storage.search_prompts("test")
        print(f"✅ Found {len(results)} results")
        print()

        # Test 4: R2 status
        print("Test 4: R2 cloud storage")
        print(f"   R2 Enabled: {storage.r2_enabled}")
        if storage.r2_enabled:
            print(f"   Bucket: {storage._r2.bucket_name}")
        print()

        return True

    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """Run all tests."""
    print("=" * 60)
    print("🍌 Nano Banana Prompt System Test")
    print("=" * 60)
    print()

    results = []

    # Test generation
    results.append(("Prompt Generation", test_prompt_generation()))
    print()

    # Test storage
    results.append(("Prompt Storage", test_prompt_storage()))
    print()

    # Summary
    print("=" * 60)
    print("📊 Test Summary")
    print("=" * 60)
    for name, passed in results:
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"{status} - {name}")
    print()

    all_passed = all(r[1] for r in results)
    if all_passed:
        print("🎉 All tests passed!")
    else:
        print("⚠️  Some tests failed")

    return all_passed


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
