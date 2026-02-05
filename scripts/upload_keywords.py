"""
Upload banned keywords to Cloudflare R2.
This keeps keywords secure and prevents users from discovering the complete list.

Usage:
    python scripts/upload_keywords.py
"""
import json

# Add parent directory to path to import services
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from services.r2_storage import get_r2_storage

# Banned keywords list (consolidated from content_filter.py)
BANNED_KEYWORDS = [
    # NSFW - Explicit sexual content & euphemisms
    "nsfw", "nude", "naked", "sex", "porn", "xxx", "rape", "hentai", "erotic", "sexual",
    "vagina", "penis", "breast", "nipple", "genitals", "intercourse",
    "fuck", "orgasm", "masturbat", "blowjob", "handjob",
    "making love", "make love", "erotic photography", "sensual photography",
    "裸", "裸体", "色情", "性", "性交", "强奸", "淫", "做爱", "阴道", "阴茎", "乳房", "生殖器",

    # NSFW - Suggestive poses/clothing (reduced - bikini removed)
    "lingerie", "underwear", "panties", "bra", "thong", "topless", "bottomless",
    "内衣", "内裤", "胸罩", "半裸", "露点",

    # NSFW - Adult content types
    "playboy", "pornstar", "stripper", "escort", "prostitute", "brothel", "onlyfans",
    "色情明星", "脱衣舞", "妓女", "援交", "卖淫",

    # Violence/Gore
    "gore", "bloody", "violence", "violent", "kill", "murder", "torture",
    "decapitate", "dismember", "mutilate", "corpse", "dead body",
    "死亡", "暴力", "血腥", "杀", "谋杀", "酷刑", "尸体", "斩首",

    # Minors - Sexual context
    "child porn", "minor sex", "underage", "loli", "shota",
    "school girl sex", "young girl naked", "young boy naked", "preteen",
    "儿童色情", "未成年性", "萝莉", "正太",

    # Drugs - Explicit use/production
    "cocaine use", "heroin inject", "meth lab", "snorting cocaine", "shooting heroin",
    "吸毒", "海洛因注射", "冰毒实验室",

    # Illegal/Dangerous - Explicit instructions
    "bomb making", "explosive device", "suicide method", "how to kill",
    "制作炸弹", "爆炸装置", "自杀方法", "如何杀人",
]


def upload_keywords_to_r2():
    """Upload banned keywords JSON to R2."""
    # Initialize R2 storage
    r2 = get_r2_storage()

    if not r2.is_available:
        print("❌ R2 storage is not available. Please check your configuration.")
        print("   Required env vars: R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY")
        return False

    # Prepare keywords data
    keywords_data = {
        "version": "1.0",
        "last_updated": "2025-12-14",
        "description": "Banned keywords for content safety filtering",
        "keywords": BANNED_KEYWORDS,
        "total_count": len(BANNED_KEYWORDS)
    }

    # Convert to JSON
    json_content = json.dumps(keywords_data, ensure_ascii=False, indent=2)

    try:
        # Upload to R2
        r2._client.put_object(
            Bucket=r2.bucket_name,
            Key="config/banned_keywords.json",
            Body=json_content.encode("utf-8"),
            ContentType="application/json"
        )

        print(f"✅ Successfully uploaded {len(BANNED_KEYWORDS)} keywords to R2")
        print(f"   Bucket: {r2.bucket_name}")
        print("   Key: config/banned_keywords.json")
        return True

    except Exception as e:
        print(f"❌ Failed to upload keywords to R2: {e}")
        return False


def save_local_backup():
    """Save a local backup of keywords (for reference only)."""
    backup_path = Path(__file__).parent / "banned_keywords_backup.json"

    keywords_data = {
        "version": "1.0",
        "last_updated": "2025-12-14",
        "description": "Banned keywords backup (DO NOT commit to git)",
        "keywords": BANNED_KEYWORDS,
        "total_count": len(BANNED_KEYWORDS)
    }

    with open(backup_path, "w", encoding="utf-8") as f:
        json.dump(keywords_data, f, ensure_ascii=False, indent=2)

    print(f"💾 Local backup saved to: {backup_path}")
    print("   ⚠️  DO NOT commit this file to git!")


if __name__ == "__main__":
    print("=" * 60)
    print("Uploading Banned Keywords to Cloudflare R2")
    print("=" * 60)
    print()

    # Upload to R2
    success = upload_keywords_to_r2()

    if success:
        # Save local backup
        save_local_backup()
        print()
        print("=" * 60)
        print("✅ Upload Complete!")
        print("=" * 60)
        print()
        print("Next steps:")
        print("1. The keyword list is now loaded from R2")
        print("2. Users cannot see the full list in your code")
        print("3. You can update keywords anytime by running this script")
        print("4. Keywords are cached for 1 hour on the server")
    else:
        print()
        print("=" * 60)
        print("❌ Upload Failed")
        print("=" * 60)
        print()
        print("Please check your R2 configuration in .env")
