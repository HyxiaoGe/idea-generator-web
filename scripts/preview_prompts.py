"""
Preview prompt generation - see what AI generates before full initialization.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))


from dotenv import load_dotenv

from services.prompt_generator import get_prompt_generator

load_dotenv()


def preview_prompts():
    """Preview generated prompts for different categories and languages."""
    print("🔍 Preview: AI-Generated Prompts")
    print("=" * 70)
    print()

    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ Error: GOOGLE_API_KEY not found")
        return False

    generator = get_prompt_generator(api_key)

    # Test categories
    test_cases = [
        {"category": "portrait", "style": "photorealistic", "language": "en", "count": 5},
        {"category": "portrait", "style": "写实", "language": "zh", "count": 5},
        {"category": "landscape", "style": "dramatic", "language": "en", "count": 3},
        {"category": "food", "style": "美食摄影", "language": "zh", "count": 3},
    ]

    for idx, test in enumerate(test_cases, 1):
        print(f"\n{'='*70}")
        print(f"Test {idx}: {test['category'].upper()} - {test['style']} ({test['language']})")
        print(f"{'='*70}\n")

        try:
            prompts = generator.generate_category_prompts(
                category=test["category"],
                style=test["style"],
                count=test["count"],
                language=test["language"]
            )

            if prompts:
                for i, prompt_data in enumerate(prompts, 1):
                    prompt_text = prompt_data.get("prompt", "")
                    description = prompt_data.get("description", "")
                    tags = prompt_data.get("tags", [])

                    print(f"{i}. {prompt_text}")
                    if description:
                        print(f"   📝 {description}")
                    if tags:
                        print(f"   🏷️  {', '.join(tags)}")
                    print()
            else:
                print("❌ No prompts generated")

        except Exception as e:
            print(f"❌ Error: {e}")
            import traceback
            traceback.print_exc()

        print()

    print("=" * 70)
    print("✨ Preview Complete!")
    print()
    print("💡 Tips:")
    print("   - Check if prompts are detailed enough")
    print("   - Verify language quality (English/Chinese)")
    print("   - Ensure prompts are suitable for image generation")
    print()
    print("If satisfied, run: python scripts/init_prompts.py")
    print()

    return True


if __name__ == "__main__":
    success = preview_prompts()
    sys.exit(0 if success else 1)
