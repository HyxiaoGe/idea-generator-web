"""
AI-powered prompt generator service using Google Gemini.
Generates high-quality image generation prompts for various categories.
"""

import json
import os
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()


class PromptGenerator:
    """AI-driven prompt generator using Gemini."""

    # Use cheaper text model for prompt generation
    MODEL_ID = "gemini-2.0-flash-exp"

    # Fallback model if flash is not available
    FALLBACK_MODEL_ID = "gemini-1.5-flash"

    def __init__(self, api_key: str | None = None):
        """
        Initialize the prompt generator.

        Args:
            api_key: Google API key. If not provided, will try to get from environment.
        """
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY")
        if not self._api_key:
            raise ValueError("GOOGLE_API_KEY not found")
        self.client = genai.Client(api_key=self._api_key)

    def generate_category_prompts(
        self, category: str, style: str | None = None, count: int = 15, language: str = "en"
    ) -> list[dict[str, Any]]:
        """
        Generate prompts for a specific category.

        Args:
            category: Category name (e.g., "portrait", "landscape", "food")
            style: Optional style preference (e.g., "photorealistic", "artistic")
            count: Number of prompts to generate
            language: Language for prompts ("en" or "zh")

        Returns:
            List of prompt dictionaries with text, description, and tags
        """
        # Build the generation prompt
        system_prompt = self._build_generation_prompt(category, style, count, language)

        try:
            response = self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=system_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,  # Higher creativity
                    top_p=0.95,
                    max_output_tokens=4096,
                ),
            )

            # Parse JSON response
            text = response.text.strip()
            # Remove markdown code blocks if present
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            prompts_data = json.loads(text)

            # Ensure it's a list
            if isinstance(prompts_data, dict) and "prompts" in prompts_data:
                prompts_data = prompts_data["prompts"]

            # Validate and format
            formatted_prompts = []
            for item in prompts_data[:count]:
                if isinstance(item, str):
                    # Simple string format
                    formatted_prompts.append(
                        {
                            "prompt": item,
                            "description": "",
                            "tags": [category],
                            "source": "ai_generated",
                        }
                    )
                elif isinstance(item, dict):
                    # Structured format
                    formatted_prompts.append(
                        {
                            "prompt": item.get("prompt", item.get("text", "")),
                            "description": item.get("description", ""),
                            "tags": item.get("tags", [category]),
                            "source": "ai_generated",
                        }
                    )

            return formatted_prompts

        except json.JSONDecodeError as e:
            print(f"Failed to parse JSON response: {e}")
            print(f"Response text: {text[:200]}")
            return self._get_fallback_prompts(category, count)
        except Exception as e:
            print(f"Prompt generation failed: {e}")
            return self._get_fallback_prompts(category, count)

    def _build_generation_prompt(
        self, category: str, style: str | None, count: int, language: str
    ) -> str:
        """Build the system prompt for generation."""
        if language == "zh":
            return f"""
生成 {count} 个高质量的 AI 图像生成提示词，类别：{category}
{f"风格偏好：{style}" if style else ""}

要求：
- 每个提示词 20-50 个字
- 使用清晰、直白的描述语言，避免过于专业的术语
- 重点描述视觉效果，而非技术参数
- 包含：主体、场景、光线、色彩、氛围、视角
- 适合 Gemini 图像生成模型
- 多样化且富有创意
- 使用自然流畅的中文

示例格式：
"一位年轻女性的肖像，柔和的窗户光线照亮她的脸庞，背景模糊，
温暖的色调，宁静的氛围，特写镜头"

返回 JSON 格式：
[
  {{
    "prompt": "详细的提示词文本",
    "description": "简短说明（可选）",
    "tags": ["标签1", "标签2"]
  }}
]

只返回 JSON 数组，不要其他文字。
"""
        else:
            return f"""
Generate {count} high-quality AI image generation prompts for category: {category}
{f"Style preference: {style}" if style else ""}

Requirements:
- Each prompt should be 20-50 words
- Use clear, descriptive language - avoid overly technical photography terms
- Focus on visual effects rather than technical parameters
- Include: subject, scene, lighting, colors, mood, perspective
- Optimized for Gemini image generation model
- Diverse and creative
- Natural, conversational English

Example format:
"A young woman portrait, soft window light illuminating her face,
blurred background, warm tones, peaceful atmosphere, close-up view"

Return JSON format:
[
  {{
    "prompt": "detailed prompt text",
    "description": "brief explanation (optional)",
    "tags": ["tag1", "tag2"]
  }}
]

Return ONLY the JSON array, no other text.
"""

    def enhance_prompt(self, basic_prompt: str, language: str = "en") -> str:
        """
        Enhance a basic prompt with more details.

        Args:
            basic_prompt: User's simple prompt
            language: Language for enhancement

        Returns:
            Enhanced prompt with more details
        """
        if language == "zh":
            system_prompt = f"""
优化这个图像生成提示词，使其更详细和有效：
"{basic_prompt}"

添加以下细节：
- 艺术风格（如：写实、插画、油画等）
- 光照和氛围（如：金色时光、柔和光线等）
- 构图和视角（如：特写、广角、俯视等）
- 色彩方案（如：暖色调、冷色调等）

只返回优化后的提示词，不要解释。保持在 50 字以内。
"""
        else:
            system_prompt = f"""
Enhance this image generation prompt to be more detailed and effective:
"{basic_prompt}"

Add details about:
- Artistic style (e.g., photorealistic, illustration, oil painting)
- Lighting and atmosphere (e.g., golden hour, soft ambient light)
- Composition and perspective (e.g., close-up, wide angle, bird's eye view)
- Color palette (e.g., warm tones, vibrant colors)

Return only the enhanced prompt, no explanation. Keep it under 50 words.
"""

        try:
            response = self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=system_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.7,
                    max_output_tokens=256,
                ),
            )
            return response.text.strip().strip('"').strip("'")
        except Exception as e:
            print(f"Prompt enhancement failed: {e}")
            return basic_prompt

    def generate_variations(
        self, base_prompt: str, count: int = 5, variation_type: str = "style"
    ) -> list[str]:
        """
        Generate variations of a base prompt.

        Args:
            base_prompt: The original prompt
            count: Number of variations to generate
            variation_type: Type of variation ("style", "mood", "composition")

        Returns:
            List of prompt variations
        """
        system_prompt = f"""
Generate {count} variations of this image prompt:
"{base_prompt}"

Variation type: {variation_type}
- If "style": Change artistic style while keeping subject
- If "mood": Change atmosphere and emotion while keeping subject
- If "composition": Change perspective and framing while keeping subject

Return as JSON array of strings:
["variation 1", "variation 2", ...]

Only return the JSON array, no other text.
"""

        try:
            response = self.client.models.generate_content(
                model=self.MODEL_ID,
                contents=system_prompt,
                config=types.GenerateContentConfig(
                    temperature=0.9,
                    max_output_tokens=1024,
                ),
            )

            text = response.text.strip()
            if text.startswith("```json"):
                text = text[7:]
            if text.startswith("```"):
                text = text[3:]
            if text.endswith("```"):
                text = text[:-3]
            text = text.strip()

            variations = json.loads(text)
            return variations[:count]

        except Exception as e:
            print(f"Variation generation failed: {e}")
            return [base_prompt]

    def _get_fallback_prompts(self, category: str, count: int) -> list[dict[str, Any]]:
        """Get fallback prompts if generation fails."""
        fallback_templates = {
            "portrait": [
                "professional headshot photo with studio lighting",
                "artistic portrait with dramatic side lighting",
                "vintage style portrait with film grain effect",
            ],
            "product": [
                "clean product photography on white background",
                "lifestyle product shot with natural lighting",
                "minimalist product display with soft shadows",
            ],
            "landscape": [
                "breathtaking mountain landscape at golden hour",
                "serene beach sunset with palm trees silhouette",
                "misty forest morning with sunbeams",
            ],
            "art": [
                "abstract oil painting with vibrant colors",
                "watercolor illustration in soft pastel tones",
                "digital art in cyberpunk neon style",
            ],
            "food": [
                "gourmet food photography with elegant plating",
                "rustic homemade dish on wooden table",
                "colorful healthy breakfast spread from above",
            ],
            "architecture": [
                "modern minimalist building with clean lines",
                "cozy interior design with warm ambient lighting",
                "futuristic architecture concept with glass and steel",
            ],
        }

        templates = fallback_templates.get(
            category,
            [
                f"high quality {category} image",
                f"professional {category} photography",
                f"artistic {category} illustration",
            ],
        )

        return [
            {"prompt": prompt, "description": "", "tags": [category], "source": "fallback"}
            for prompt in templates[:count]
        ]


# Global instance cache
_generator_instance: PromptGenerator | None = None


def get_prompt_generator(api_key: str | None = None) -> PromptGenerator:
    """Get or create the global prompt generator instance."""
    global _generator_instance
    if _generator_instance is None or api_key:
        _generator_instance = PromptGenerator(api_key=api_key)
    return _generator_instance
