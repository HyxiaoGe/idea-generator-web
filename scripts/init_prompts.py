"""
Initialize prompt library with AI-generated prompts.
Run this script to populate the prompt library for the first time.
"""
import os
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv

from services.prompt_generator import get_prompt_generator
from services.prompt_storage import get_prompt_storage

load_dotenv()


def init_prompt_library():
    """Initialize the prompt library with AI-generated prompts."""
    print("🍌 Initializing Nano Banana Prompt Library...")
    print()

    # Check API key
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("❌ Error: GOOGLE_API_KEY not found in environment")
        print("Please set your API key in .env file")
        return False

    # Initialize services
    generator = get_prompt_generator(api_key)
    storage = get_prompt_storage()

    # Categories to generate
    categories = {
        "portrait": {
            "styles": ["photorealistic", "artistic", "vintage"],
            "count": 30
        },
        "product": {
            "styles": ["commercial", "lifestyle", "minimalist"],
            "count": 30
        },
        "landscape": {
            "styles": ["natural", "dramatic", "serene"],
            "count": 30
        },
        "art": {
            "styles": ["abstract", "impressionist", "digital"],
            "count": 30
        },
        "food": {
            "styles": ["gourmet", "rustic", "healthy"],
            "count": 30
        },
        "architecture": {
            "styles": ["modern", "classical", "futuristic"],
            "count": 30
        }
    }

    total_categories = len(categories)
    total_tasks = total_categories * 2  # English + Chinese
    success_count = 0
    task_num = 0

    for _idx, (category, config) in enumerate(categories.items(), 1):
        # Generate English prompts
        task_num += 1
        print(f"[{task_num}/{total_tasks}] Generating English prompts for: {category}")

        try:
            all_prompts_en = []
            for style in config["styles"]:
                print(f"  - Style: {style}...")
                prompts = generator.generate_category_prompts(
                    category=category,
                    style=style,
                    count=config["count"] // len(config["styles"]) + 1,
                    language="en"
                )
                all_prompts_en.extend(prompts)

            if storage.save_category_prompts(category, all_prompts_en[:config["count"]], language="en"):
                print(f"  ✅ Saved {len(all_prompts_en[:config['count']])} English prompts")
                success_count += 1
            else:
                print("  ❌ Failed to save English prompts")

        except Exception as e:
            print(f"  ❌ Error: {e}")

        print()

        # Generate Chinese prompts
        task_num += 1
        print(f"[{task_num}/{total_tasks}] Generating Chinese prompts for: {category}")

        try:
            all_prompts_zh = []
            for style in config["styles"]:
                print(f"  - 风格: {style}...")
                prompts = generator.generate_category_prompts(
                    category=category,
                    style=style,
                    count=config["count"] // len(config["styles"]) + 1,
                    language="zh"
                )
                all_prompts_zh.extend(prompts)

            if storage.save_category_prompts(category, all_prompts_zh[:config["count"]], language="zh"):
                print(f"  ✅ 已保存 {len(all_prompts_zh[:config['count']])} 条中文提示词")
                success_count += 1
            else:
                print("  ❌ 保存中文提示词失败")

        except Exception as e:
            print(f"  ❌ 错误: {e}")

        print()

    print("✨ Initialization complete!")
    print(f"   Successfully generated: {success_count}/{total_tasks} tasks")
    print(f"   Categories: {total_categories} (English + Chinese)")
    print(f"   Storage location: {storage.base_dir}")

    # Sync to cloud if available
    if storage.r2_enabled:
        print()
        print("☁️  Syncing to Cloudflare R2...")
        results = storage.sync_all_to_cloud()
        synced = sum(1 for v in results.values() if v)
        print(f"   Synced: {synced}/{len(results)} categories")

    return success_count == total_categories


if __name__ == "__main__":
    success = init_prompt_library()
    sys.exit(0 if success else 1)
