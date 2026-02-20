"""Seed script: Insert prompt templates (150 image + 80 video) into the database.

Usage:
    python scripts/seed_templates.py               # Full: clear DB → insert data → generate images
    python scripts/seed_templates.py --data-only    # Fast: clear DB → insert data (no images)
    python scripts/seed_templates.py --images-only  # Resume: generate images for NULL preview_image_url
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from datetime import UTC, datetime, timedelta  # noqa: E402
from uuid import uuid4  # noqa: E402

from sqlalchemy import delete, func, select  # noqa: E402

from database import get_session, init_database  # noqa: E402
from database.models.template import PromptTemplate  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def compute_trending(like: int, use: int, fav: int, hours_ago: float) -> float:
    return (like * 3 + use * 1 + fav * 2) / (hours_ago + 2) ** 1.5


# ═══════════════════════════════════════════════════════════════
#  TEMPLATE DATA — 150 image + 80 video hand-crafted templates
# ═══════════════════════════════════════════════════════════════

TEMPLATES: list[dict] = [
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PORTRAIT (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "A weathered fisherman mending nets on a wooden dock at dawn, "
            "deep lines etched across sun-darkened skin, calloused hands in sharp focus "
            "against a soft-focus harbor of sleeping boats. Side lighting from the rising sun "
            "casts long shadows across the dock planks and catches salt crystals in his beard. "
            "Shot from slightly below eye level to convey quiet dignity. "
            "Muted teal water and warm amber sky create a split complementary palette."
        ),
        "display_name_en": "Dawn Fisherman",
        "display_name_zh": "拂晓渔人",
        "description_en": "Character-driven environmental portrait using dawn light to sculpt texture and story into every weathered line",
        "description_zh": "以晨光雕刻纹理与叙事的环境人物肖像，渔人的沧桑在海港晨曦中尽显",
        "category": "portrait",
        "tags": ["portrait", "environmental", "character", "dawn", "documentary"],
        "style_keywords": ["side lighting", "split complementary", "environmental portrait"],
        "difficulty": "intermediate",
        "use_count": 820,
        "like_count": 275,
        "favorite_count": 140,
    },
    {
        "prompt_text": (
            "A young ballet dancer in a dusty rehearsal studio, caught mid-pirouette "
            "with one arm extended toward a floor-to-ceiling window. "
            "Afternoon sun floods through the glass, turning airborne dust into a golden haze "
            "around her silhouette. The wooden floor reflects warm light upward onto her face. "
            "Wide shot reveals scuffed barres and peeling wallpaper, grounding elegance in grit. "
            "Warm gold and cool shadow-gray bisect the frame diagonally."
        ),
        "display_name_en": "Rehearsal Light",
        "display_name_zh": "排练室的光",
        "description_en": "A dancer suspended in golden dust-light, where the worn studio tells as much story as the movement itself",
        "description_zh": "金色尘光中旋转的舞者，破旧排练室的每一道痕迹都在诉说坚持的故事",
        "category": "portrait",
        "tags": ["portrait", "dance", "natural-light", "silhouette", "movement"],
        "style_keywords": ["backlight silhouette", "dust particles", "diagonal composition"],
        "difficulty": "beginner",
        "use_count": 1150,
        "like_count": 380,
        "favorite_count": 210,
    },
    {
        "prompt_text": (
            "Close-up portrait of an elderly woman with silver hair pinned in a loose bun, "
            "laughing with her eyes half-closed, deep crow's feet radiating outward. "
            "A single overhead softbox creates a gentle Rembrandt triangle on her left cheek "
            "while the right side falls into soft shadow. "
            "Background is a simple charcoal gray gradient. "
            "The color palette is monochromatic warm — ivory skin, cream collar, taupe shadow."
        ),
        "display_name_en": "Silver Laughter",
        "display_name_zh": "银发笑颜",
        "description_en": "Intimate studio portrait capturing the warmth of genuine laughter in a restrained monochromatic palette",
        "description_zh": "素雅暖色调中捕捉真挚笑容的棚拍肖像，皱纹是岁月最温柔的书写",
        "category": "portrait",
        "tags": ["portrait", "studio", "elderly", "laughter", "monochromatic"],
        "style_keywords": ["Rembrandt lighting", "monochromatic warm", "tight crop"],
        "difficulty": "beginner",
        "use_count": 960,
        "like_count": 310,
        "favorite_count": 175,
    },
    {
        "prompt_text": (
            "Double exposure portrait blending a young man's profile with an aerial view "
            "of a winding river delta. His jawline becomes the riverbank, "
            "tributaries branch across his forehead like veins of thought. "
            "The river is rendered in desaturated olive green against the warm sienna "
            "of his skin tone. High-contrast black negative space frames the composition. "
            "The overlay is densest at the temples and fades toward the chin."
        ),
        "display_name_en": "River Mind",
        "display_name_zh": "川流意识",
        "description_en": "Surrealist double exposure merging human profile with river geography to visualize the flow of thought",
        "description_zh": "人物侧影与河流三角洲的超现实叠合，支流在额头蔓延如思绪的脉络",
        "category": "portrait",
        "tags": ["portrait", "double-exposure", "surreal", "conceptual", "river"],
        "style_keywords": ["double exposure", "high contrast", "conceptual portrait"],
        "difficulty": "advanced",
        "use_count": 430,
        "like_count": 185,
        "favorite_count": 98,
    },
    {
        "prompt_text": (
            "A street musician playing erhu on a rainy Shanghai laneway at night, "
            "neon signs reflecting in puddles around his feet. "
            "His eyes are closed, head tilted, completely absorbed in the melody. "
            "Rain streaks are frozen by a brief flash, creating silver threads "
            "against the warm orange-red glow of a dumpling shop behind him. "
            "Shallow depth of field throws the Chinese signage into bokeh circles."
        ),
        "display_name_en": "Rainy Erhu Player",
        "display_name_zh": "雨巷琴声",
        "description_en": "Street portrait of a musician lost in melody, neon and rain weaving color around his solitary figure",
        "description_zh": "雨夜弄堂里沉醉于二胡旋律的街头艺人，霓虹与雨丝编织出孤独的色彩",
        "category": "portrait",
        "tags": ["portrait", "street", "musician", "rain", "neon", "shanghai"],
        "style_keywords": ["flash-and-ambient mix", "neon bokeh", "street portrait"],
        "difficulty": "intermediate",
        "use_count": 710,
        "like_count": 248,
        "favorite_count": 130,
    },
    {
        "prompt_text": (
            "High-key beauty portrait of a model with geometric face paint — "
            "precise white triangles and black lines across cheekbones and forehead. "
            "Even, shadowless ring-light illumination on flawless dark skin. "
            "Pure white background with no visible edges. "
            "The only color is a single stroke of electric cobalt blue on the lower lip. "
            "Shot tight from collarbones up, perfectly centered and symmetrical."
        ),
        "display_name_en": "Geometric Beauty",
        "display_name_zh": "几何妆面",
        "description_en": "Graphic beauty portrait where geometric face paint transforms skin into a living canvas against pure white",
        "description_zh": "几何面部彩绘将肌肤化为画布，纯白背景上唯有一抹钴蓝点亮嘴唇",
        "category": "portrait",
        "tags": ["portrait", "beauty", "face-paint", "graphic", "high-key"],
        "style_keywords": ["high-key", "ring light", "graphic minimalism"],
        "difficulty": "beginner",
        "use_count": 1020,
        "like_count": 340,
        "favorite_count": 190,
    },
    {
        "prompt_text": (
            "An astronaut seated in a vintage barbershop chair, helmet off and resting on the counter, "
            "getting a shave from a barber in a classic striped apron. "
            "Warm tungsten bulbs line the mirror behind them, casting amber halos. "
            "The spacesuit is scuffed and lived-in, patches of lunar dust still visible on the knees. "
            "Framed at medium shot showing both figures, the mirror reflecting the scene in reverse. "
            "Retro mint-green tiles contrast with the metallic silver of the suit."
        ),
        "display_name_en": "Astronaut's Day Off",
        "display_name_zh": "宇航员的休息日",
        "description_en": "Surreal narrative portrait juxtaposing the cosmic and the mundane in a vintage barbershop setting",
        "description_zh": "宇航员在复古理发店刮胡子的超现实叙事，宇宙与日常在暖光中交汇",
        "category": "portrait",
        "tags": ["portrait", "surreal", "narrative", "astronaut", "vintage"],
        "style_keywords": ["narrative juxtaposition", "tungsten warmth", "surreal realism"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 165,
        "favorite_count": 88,
    },
    {
        "prompt_text": (
            "A grandmother and granddaughter sitting on a porch swing at dusk, "
            "faces turned toward each other in conversation. "
            "The grandmother's weathered hands hold a cup of tea, steam curling upward. "
            "Last light of day comes from behind the camera, "
            "warming their faces evenly while the background fades to deep indigo. "
            "Fireflies dot the darkening garden behind them as soft green pinpoints. "
            "The frame is wide enough to show the swing chains and hanging flower baskets."
        ),
        "display_name_en": "Porch Swing Dusk",
        "display_name_zh": "廊下黄昏",
        "description_en": "Two-generation portrait on a porch swing as dusk settles, fireflies punctuating the gathering dark",
        "description_zh": "暮色降临的门廊秋千上，祖孙对谈间萤火虫在花园深处明灭",
        "category": "portrait",
        "tags": ["portrait", "family", "dusk", "two-generation", "fireflies"],
        "style_keywords": ["golden hour frontal", "narrative warmth", "environmental duo"],
        "difficulty": "beginner",
        "use_count": 890,
        "like_count": 295,
        "favorite_count": 165,
    },
    {
        "prompt_text": (
            "A boxer in the corner of a dimly lit ring between rounds, "
            "towel draped over his shoulders, sweat glistening under a single overhead lamp. "
            "His trainer leans in close, one hand gripping the boxer's jaw to force eye contact. "
            "The ropes form strong diagonal lines across the background. "
            "Deep shadows carve out the musculature, "
            "while the overhead cone of light creates a natural vignette. "
            "Color palette of raw umber, blood red ropes, and cool steel-blue corner pad."
        ),
        "display_name_en": "Between Rounds",
        "display_name_zh": "回合之间",
        "description_en": "Gritty corner portrait between boxing rounds, a single overhead light sculpting determination and fatigue",
        "description_zh": "拳击回合间歇的角落肖像，头顶孤灯将坚毅与疲惫刻入每一条肌肉线条",
        "category": "portrait",
        "tags": ["portrait", "sports", "boxing", "dramatic-light", "gritty"],
        "style_keywords": ["overhead spot", "chiaroscuro", "sports documentary"],
        "difficulty": "intermediate",
        "use_count": 640,
        "like_count": 215,
        "favorite_count": 112,
    },
    {
        "prompt_text": (
            "A woman reading a letter by candlelight, seated at a dark wooden desk "
            "in what appears to be a 17th-century Dutch interior. "
            "The candle flame is the sole light source, painting her face and the parchment "
            "in warm amber while the rest of the room dissolves into rich darkness. "
            "A pearl earring catches a single point of reflected light. "
            "Painted in the style of Dutch Golden Age masters — visible brushwork, "
            "dark ground showing through glazed shadows."
        ),
        "display_name_en": "Letter by Candlelight",
        "display_name_zh": "烛光家书",
        "description_en": "Dutch Golden Age-inspired portrait where a single candle illuminates a private moment of reading",
        "description_zh": "致敬荷兰黄金时代的烛光阅读场景，一点珍珠光芒在暗色调中闪烁",
        "category": "portrait",
        "tags": ["portrait", "dutch-masters", "candlelight", "painting", "classical"],
        "style_keywords": ["single candle source", "Dutch Golden Age", "glazed shadows"],
        "difficulty": "advanced",
        "use_count": 350,
        "like_count": 155,
        "favorite_count": 82,
    },
    {
        "prompt_text": (
            "A chef in a white double-breasted jacket stands in the pass of a busy kitchen, "
            "plates lined up in front of him, steam rising from freshly plated dishes. "
            "Stainless-steel surfaces bounce the harsh fluorescent kitchen light "
            "into a complex web of reflections across his face. "
            "His expression is focused, mid-call, one hand raised with a ticket. "
            "Shot through the pass window, foreground heat-shimmer slightly warping the edges. "
            "Industrial whites and steel grays with pops of sauce color on the plates."
        ),
        "display_name_en": "The Pass",
        "display_name_zh": "出餐口",
        "description_en": "Documentary-style kitchen portrait shot through the pass window, heat shimmer and steel reflections framing command",
        "description_zh": "透过出餐窗口拍摄的厨房纪实肖像，热浪与钢面反光框住专注的指挥瞬间",
        "category": "portrait",
        "tags": ["portrait", "chef", "kitchen", "documentary", "industrial"],
        "style_keywords": ["through-window framing", "industrial light", "documentary realism"],
        "difficulty": "intermediate",
        "use_count": 560,
        "like_count": 190,
        "favorite_count": 98,
    },
    {
        "prompt_text": (
            "Extreme close-up of a single human eye, iris rendered in extraordinary detail — "
            "amber and green fibers radiating from the pupil like a sunburst. "
            "Individual eyelashes cast tiny shadows across the iris from soft top-light. "
            "A reflection of a window with tree branches is visible in the cornea. "
            "Skin texture around the eye shows fine pores and a faint freckle below the lower lash line. "
            "Color palette is entirely earth tones: amber, sage, umber, cream."
        ),
        "display_name_en": "Iris Universe",
        "display_name_zh": "瞳中宇宙",
        "description_en": "Macro-scale eye portrait revealing an iris landscape of amber fibers and reflected worlds",
        "description_zh": "微距瞳孔肖像，琥珀色虹膜纤维如日晕辐射，角膜倒映着窗外的树影",
        "category": "portrait",
        "tags": ["portrait", "macro", "eye", "detail", "earth-tones"],
        "style_keywords": ["macro photography", "iris detail", "earth tone palette"],
        "difficulty": "beginner",
        "use_count": 1280,
        "like_count": 420,
        "favorite_count": 235,
    },
    {
        "prompt_text": (
            "A teenager sitting cross-legged on her bedroom floor surrounded by vinyl records, "
            "oversized headphones around her neck, looking directly at the camera with a half-smile. "
            "Late afternoon window light rakes across the scene at a low angle, "
            "casting long record-sleeve shadows across the carpet. "
            "Walls covered in band posters and fairy lights provide warm background texture. "
            "Shot from above at a 45-degree angle to map out the vinyl collection radiating around her."
        ),
        "display_name_en": "Vinyl Floor Portrait",
        "display_name_zh": "黑胶唱片少女",
        "description_en": "Overhead-angle portrait of a teenager framed by her vinyl collection, afternoon light raking across the scene",
        "description_zh": "俯拍视角的少女被黑胶唱片环绕，午后斜光在唱片封套上投下长长的影子",
        "category": "portrait",
        "tags": ["portrait", "teenager", "music", "overhead-angle", "lifestyle"],
        "style_keywords": ["elevated angle", "raking light", "lifestyle environmental"],
        "difficulty": "beginner",
        "use_count": 980,
        "like_count": 325,
        "favorite_count": 180,
    },
    {
        "prompt_text": (
            "Cyanotype portrait of a woman in profile, rendered in deep Prussian blue and white. "
            "Botanical specimens — fern fronds and pressed flowers — are layered over her silhouette "
            "as if printed directly onto the image through a contact process. "
            "The ferns follow the curve of her neck and shoulder, "
            "becoming part of her form rather than mere overlay. "
            "Paper texture visible throughout, with characteristic cyanotype edge bleed."
        ),
        "display_name_en": "Cyanotype Botanica",
        "display_name_zh": "蓝晒植物志",
        "description_en": "Alternative-process portrait merging human form with botanical specimens in deep Prussian blue cyanotype",
        "description_zh": "蓝晒工艺将人物侧影与植物标本融为一体，蕨叶沿颈肩曲线自然生长",
        "category": "portrait",
        "tags": ["portrait", "cyanotype", "botanical", "alternative-process", "blue"],
        "style_keywords": ["cyanotype process", "botanical overlay", "Prussian blue"],
        "difficulty": "advanced",
        "use_count": 310,
        "like_count": 140,
        "favorite_count": 75,
    },
    {
        "prompt_text": (
            "A pair of identical twins in matching red qipao dresses standing back-to-back "
            "in a narrow Penang shophouse corridor. Ornate Peranakan tiles in turquoise and gold "
            "line the floor, while louvered shutters filter striped light across their faces. "
            "One twin looks left, the other right, creating perfect bilateral symmetry. "
            "The corridor converges to a bright courtyard at the vanishing point behind them. "
            "Rich palette of vermillion, turquoise, and aged wood brown."
        ),
        "display_name_en": "Mirror Twins",
        "display_name_zh": "镜像姐妹",
        "description_en": "Symmetrical twin portrait in a Peranakan corridor, louvered light and ornate tiles framing mirrored poses",
        "description_zh": "南洋骑楼走廊中的双胞胎对称肖像，百叶窗光与娘惹花砖铺陈镜像之美",
        "category": "portrait",
        "tags": ["portrait", "twins", "symmetry", "peranakan", "cultural"],
        "style_keywords": ["bilateral symmetry", "cultural setting", "louvered light"],
        "difficulty": "intermediate",
        "use_count": 520,
        "like_count": 195,
        "favorite_count": 105,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  LANDSCAPE (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Looking up through the interior of a slot canyon in Arizona, "
            "sinuous sandstone walls carved into flowing organic curves by millennia of flash floods. "
            "A single beam of midday light falls from the narrow opening above, "
            "illuminating swirling dust particles and painting the lower walls in deep burnt sienna "
            "while the upper walls glow in luminous peach and lavender. "
            "Extreme vertical composition emphasizing the sense of depth from canyon floor to sky."
        ),
        "display_name_en": "Slot Canyon Light Shaft",
        "display_name_zh": "一线天光",
        "description_en": "Vertical slot canyon with a single dramatic light beam revealing layered sandstone colors from sienna to lavender",
        "description_zh": "狭缝峡谷中一道光柱穿透而下，层层砂岩色彩在明暗中从赭石流转至薰衣紫",
        "category": "landscape",
        "tags": ["landscape", "canyon", "light-beam", "geological", "vertical"],
        "style_keywords": ["vertical composition", "natural light shaft", "geological texture"],
        "difficulty": "intermediate",
        "use_count": 690,
        "like_count": 230,
        "favorite_count": 120,
    },
    {
        "prompt_text": (
            "A solitary rowboat tethered to a wooden post on a perfectly still alpine lake at dawn. "
            "The water is so calm it creates a flawless mirror reflection of snow-capped peaks "
            "and a sky transitioning from deep violet at the zenith to pale rose at the horizon. "
            "Thin wisps of fog hover just above the waterline, partially obscuring the far shore. "
            "The boat sits on the left third of the frame, its weathered blue paint providing "
            "the only saturated color in an otherwise pastel scene."
        ),
        "display_name_en": "Still Water Mirror",
        "display_name_zh": "静水如镜",
        "description_en": "Alpine lake at dawn so still it doubles the world — a lone blue rowboat anchoring a pastel mirror-scape",
        "description_zh": "黎明高山湖泊平静如镜，孤舟的蓝色旧漆是粉彩倒影世界中唯一的饱和色",
        "category": "landscape",
        "tags": ["landscape", "lake", "reflection", "dawn", "alpine", "minimal"],
        "style_keywords": ["mirror reflection", "rule of thirds", "pastel palette"],
        "difficulty": "beginner",
        "use_count": 1350,
        "like_count": 440,
        "favorite_count": 245,
    },
    {
        "prompt_text": (
            "Terraced rice paddies cascading down a hillside in Yunnan province during planting season. "
            "Each terrace holds a thin sheet of water that reflects the overcast sky like shattered mirrors. "
            "Farmers in wide straw hats are scattered across the middle terraces, "
            "their reflections doubling the human figures. "
            "Low cloud wraps around the hilltop, cutting off the summit. "
            "The palette is a study in greens — chartreuse new shoots, "
            "emerald hillside vegetation, and slate-green distant mountains."
        ),
        "display_name_en": "Terraced Water Mirrors",
        "display_name_zh": "梯田碎镜",
        "description_en": "Yunnan rice terraces during planting season, each level a mirror-shard reflecting sky and scattered farmers",
        "description_zh": "云南插秧时节的梯田如碎裂的镜面，映出天光与农人，层层叠叠向山巅蔓延",
        "category": "landscape",
        "tags": ["landscape", "terraces", "rice-paddy", "yunnan", "agricultural", "green"],
        "style_keywords": ["layered planes", "green palette study", "aerial perspective"],
        "difficulty": "beginner",
        "use_count": 870,
        "like_count": 290,
        "favorite_count": 155,
    },
    {
        "prompt_text": (
            "A long-exposure seascape at twilight where incoming waves dissolve into smooth silk "
            "around dark volcanic rock formations jutting from the shore. "
            "The sky holds the last gradient of day — deep cobalt overhead fading to a thin band "
            "of copper-gold at the horizon. "
            "Foreground rocks are sharp and textured in contrast to the ethereal water. "
            "A single sea stack in the mid-ground provides a focal anchor. "
            "The overall mood is meditative, the world caught between movement and stillness."
        ),
        "display_name_en": "Silk Tide Twilight",
        "display_name_zh": "丝绸潮汐",
        "description_en": "Long-exposure seascape turning waves to silk around volcanic rock, the last copper light dissolving into cobalt",
        "description_zh": "长曝光将海浪化为丝绸般的存在，火山岩间最后一缕铜金色光线没入深蓝",
        "category": "landscape",
        "tags": ["landscape", "seascape", "long-exposure", "twilight", "volcanic"],
        "style_keywords": ["long exposure", "texture contrast", "twilight gradient"],
        "difficulty": "intermediate",
        "use_count": 740,
        "like_count": 255,
        "favorite_count": 135,
    },
    {
        "prompt_text": (
            "Northern lights arcing across an Arctic sky in curtains of electric green and violet, "
            "reflected in a network of meltwater channels on a glacial plain. "
            "The channels create branching silver lines that echo the aurora's curves above. "
            "A solitary research tent glows warm orange in the lower right corner, "
            "providing human scale against the vastness. "
            "Stars are visible through gaps in the aurora. "
            "The palette is split between cold cyan-greens above and warm tent-light below."
        ),
        "display_name_en": "Aurora Over Glacier",
        "display_name_zh": "冰原极光",
        "description_en": "Northern lights mirrored in glacial meltwater channels, a lone orange tent the only warmth in the Arctic expanse",
        "description_zh": "极光弧线倒映在冰川融水的分支河道中，孤帐橘光是北极荒原唯一的暖意",
        "category": "landscape",
        "tags": ["landscape", "aurora", "arctic", "glacier", "night-sky"],
        "style_keywords": ["aurora photography", "warm-cold contrast", "scale contrast"],
        "difficulty": "intermediate",
        "use_count": 680,
        "like_count": 240,
        "favorite_count": 130,
    },
    {
        "prompt_text": (
            "A single dead tree stands in the cracked white expanse of a salt flat, "
            "its bare branches casting a precise shadow-skeleton on the ground. "
            "The sky is a featureless gradient from white at the horizon to pale powder blue overhead. "
            "No other features exist — the frame is reduced to tree, shadow, sky, and cracked earth. "
            "Extreme minimalist composition with the tree placed at the intersection "
            "of lower-right power point. The monochrome near-whiteness conveys desolation and beauty."
        ),
        "display_name_en": "Salt Flat Solitude",
        "display_name_zh": "盐沼孤树",
        "description_en": "Extreme minimalist landscape — a single dead tree and its shadow on infinite white salt crust under blank sky",
        "description_zh": "极简风景的极致——无垠白色盐壳上一棵枯树与它的影子，天地间再无他物",
        "category": "landscape",
        "tags": ["landscape", "minimal", "salt-flat", "dead-tree", "desolation"],
        "style_keywords": ["extreme minimalism", "negative space", "monochrome near-white"],
        "difficulty": "beginner",
        "use_count": 1100,
        "like_count": 365,
        "favorite_count": 200,
    },
    {
        "prompt_text": (
            "Aerial view of a winding river cutting through autumn boreal forest, "
            "the water a dark slate-blue S-curve dividing forests of blazing orange birch "
            "on one bank and deep green spruce on the other. "
            "Morning mist fills the river valley, thinning as it rises up the hillsides. "
            "The color contrast between the two forest types is sharp and almost geometric "
            "where they meet at the riverbank. "
            "Drone altitude provides enough height to see three full meanders."
        ),
        "display_name_en": "Autumn River Meander",
        "display_name_zh": "秋河蜿蜒",
        "description_en": "Aerial autumn landscape where a dark river S-curves between blazing orange birch and deep green spruce",
        "description_zh": "无人机俯瞰秋日河流的S形蜿蜒，一岸金橙白桦一岸墨绿云杉，晨雾盈谷",
        "category": "landscape",
        "tags": ["landscape", "aerial", "autumn", "river", "boreal-forest"],
        "style_keywords": ["aerial drone", "complementary color divide", "S-curve composition"],
        "difficulty": "beginner",
        "use_count": 950,
        "like_count": 315,
        "favorite_count": 170,
    },
    {
        "prompt_text": (
            "A thunderstorm approaching across flat Kansas wheat fields, "
            "the sky divided into three distinct horizontal bands — "
            "bright sunlit gold at the left horizon, bruised purple-gray storm wall in center, "
            "and near-black base with visible rain curtains at right. "
            "The wheat field below glows in contrast-boosted gold from the last direct sun. "
            "A single dirt road runs straight to the vanishing point. "
            "The scale of sky to land is roughly 70/30, emphasizing atmospheric drama."
        ),
        "display_name_en": "Storm Front Wheat",
        "display_name_zh": "风暴前的麦田",
        "description_en": "Prairie storm front advancing over golden wheat — sky dominates the frame in bands of gold, purple, and black",
        "description_zh": "堪萨斯麦田上空风暴压境，天空以金、紫、黑三色横带占据七成画面",
        "category": "landscape",
        "tags": ["landscape", "storm", "wheat-field", "prairie", "dramatic-sky"],
        "style_keywords": ["sky-dominant ratio", "approaching storm", "horizontal bands"],
        "difficulty": "intermediate",
        "use_count": 620,
        "like_count": 210,
        "favorite_count": 110,
    },
    {
        "prompt_text": (
            "Fog-shrouded bamboo forest with a narrow stone path disappearing into white emptiness. "
            "Only the nearest bamboo stalks are fully visible — vertical jade-green columns "
            "fading progressively into the fog until they become ghost-gray silhouettes. "
            "Fallen bamboo leaves carpet the path in pale gold. "
            "No sky is visible; the canopy merges with the fog above. "
            "The mood is Zen-like, meditative, with depth suggested by tonal recession alone."
        ),
        "display_name_en": "Bamboo Fog Path",
        "display_name_zh": "竹林雾径",
        "description_en": "Zen bamboo forest where stalks fade from jade to ghost-gray in deepening fog, a stone path leading to silence",
        "description_zh": "竹影从翠绿渐隐为雾中灰影，落叶铺金的石径通向一片空白与寂静",
        "category": "landscape",
        "tags": ["landscape", "bamboo", "fog", "zen", "path", "minimal"],
        "style_keywords": ["tonal recession", "atmospheric perspective", "zen minimalism"],
        "difficulty": "beginner",
        "use_count": 1050,
        "like_count": 350,
        "favorite_count": 195,
    },
    {
        "prompt_text": (
            "The Milky Way core rising above a field of desert wildflowers after rare spring rains. "
            "The galactic center blazes in warm gold and cool violet tones overhead, "
            "while the foreground flowers — primarily purple phacelia and yellow desert sunflowers — "
            "are gently illuminated by a brief light-paint sweep. "
            "Joshua trees stand as dark sentinels in the middle distance. "
            "A 14mm ultra-wide perspective stretches the sky from horizon to horizon."
        ),
        "display_name_en": "Desert Bloom Galaxy",
        "display_name_zh": "沙漠花海银河",
        "description_en": "Rare desert superbloom under the Milky Way — light-painted wildflowers glow beneath the galactic core",
        "description_zh": "沙漠罕见花季遇上银河升起，紫色花海在星光与补光中与宇宙对话",
        "category": "landscape",
        "tags": ["landscape", "milky-way", "wildflowers", "desert", "night-sky", "astro"],
        "style_keywords": ["astrophotography", "light painting", "ultra-wide perspective"],
        "difficulty": "advanced",
        "use_count": 450,
        "like_count": 195,
        "favorite_count": 105,
    },
    {
        "prompt_text": (
            "Volcanic landscape at Laki fissure in Iceland — "
            "black lava fields covered in thick moss that transitions from bright lime green "
            "on the crests to deep olive in the crevices. "
            "Steam vents rise from cracks in the lava, caught by low-angle afternoon sun "
            "and backlit into white plumes against a dark overcast sky. "
            "A gravel trail meanders through the moss-covered mounds. "
            "The palette is almost entirely green-on-black with warm steam accents."
        ),
        "display_name_en": "Moss on Lava",
        "display_name_zh": "苔原熔岩",
        "description_en": "Icelandic lava fields blanketed in lime-to-olive moss, backlit steam rising from volcanic fissures",
        "description_zh": "冰岛熔岩原上青苔从亮绿渐变至深橄榄，逆光蒸汽从裂隙中升腾如白色羽毛",
        "category": "landscape",
        "tags": ["landscape", "iceland", "volcanic", "moss", "geothermal"],
        "style_keywords": ["green-on-black palette", "backlit steam", "geological texture"],
        "difficulty": "intermediate",
        "use_count": 530,
        "like_count": 185,
        "favorite_count": 98,
    },
    {
        "prompt_text": (
            "A frozen waterfall in the Canadian Rockies, ice columns colored in bands "
            "of pale blue, white, and occasional mineral-stained amber. "
            "An ice climber in a red jacket is mid-ascent on the left column, "
            "ice axes planted, legs kicked in, tiny against the frozen curtain. "
            "Spruce trees frame the scene on both sides, heavy with fresh snow. "
            "Late afternoon winter sun grazes the ice at a low angle, "
            "making the blue sections glow with inner translucence."
        ),
        "display_name_en": "Frozen Cascade Climb",
        "display_name_zh": "冰瀑攀登者",
        "description_en": "Ice climber ascending a frozen waterfall of blue and amber bands, dwarfed by the scale of frozen water",
        "description_zh": "攀冰者红色身影在蓝白琥珀色冰瀑上缓慢上升，人与冰冻瀑布的尺度对比震撼",
        "category": "landscape",
        "tags": ["landscape", "waterfall", "ice-climbing", "winter", "rockies"],
        "style_keywords": ["scale figure", "ice translucence", "adventure landscape"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 165,
        "favorite_count": 88,
    },
    {
        "prompt_text": (
            "Rain-soaked Tokyo intersection at night from an elevated crosswalk, "
            "umbrellas forming a pointillist canopy of black, clear, and occasional red. "
            "Crosswalk stripes reflect white against the wet asphalt. "
            "Taxi taillights and LED storefronts streak in long exposure at the frame edges, "
            "while the pedestrians in the center remain sharp from brief flash sync. "
            "Vertical neon signage in Japanese kanji provides splashes of pink and cyan. "
            "The scene reads as organized chaos, every element wet and luminous."
        ),
        "display_name_en": "Neon Rain Crossing",
        "display_name_zh": "雨夜交叉口",
        "description_en": "Elevated night view of a rain-soaked Tokyo crossing — umbrellas, neon, and wet reflections in organized chaos",
        "description_zh": "雨夜东京十字路口的高角度俯瞰，伞阵、霓虹与湿漉漉的反光构成有序的混沌",
        "category": "landscape",
        "tags": ["landscape", "urban", "tokyo", "rain", "neon", "night"],
        "style_keywords": ["flash-ambient blend", "wet reflection", "elevated angle"],
        "difficulty": "advanced",
        "use_count": 420,
        "like_count": 180,
        "favorite_count": 95,
    },
    {
        "prompt_text": (
            "A lighthouse on a rocky headland at the exact moment of sunset, "
            "its beam just becoming visible as a faint cone against the dimming sky. "
            "Crashing waves send spray upward that catches the orange sunset backlight. "
            "The lighthouse is whitewashed with a red lantern room, positioned at upper-right third. "
            "Foreground rocks are dark and wet, creating a natural leading line toward the structure. "
            "Sky transitions from deep orange at horizon through salmon to dusky blue overhead."
        ),
        "display_name_en": "Headland Lighthouse",
        "display_name_zh": "岬角灯塔",
        "description_en": "Whitewashed lighthouse catching its first beam at sunset, spray backlit in orange against the darkening headland",
        "description_zh": "日落时分灯塔初亮，浪花飞溅在逆光中化为金色，白塔红顶矗立于岬角之巅",
        "category": "landscape",
        "tags": ["landscape", "lighthouse", "sunset", "coastal", "spray"],
        "style_keywords": ["sunset backlight", "leading lines", "coastal drama"],
        "difficulty": "beginner",
        "use_count": 1200,
        "like_count": 395,
        "favorite_count": 215,
    },
    {
        "prompt_text": (
            "Cherry blossom petals falling over a quiet canal in Kyoto, "
            "the water surface carpeted in soft pink. "
            "A single red wooden bridge arcs over the canal in the mid-ground, "
            "its reflection forming a perfect circle with the real structure. "
            "Willow branches dip into the frame from above. "
            "The far bank is lined with stone lanterns and moss-covered walls. "
            "Overcast light renders everything in soft, even tones without harsh shadow — "
            "the palette is almost entirely pink, green, gray, and red."
        ),
        "display_name_en": "Petal-Covered Canal",
        "display_name_zh": "花筏运河",
        "description_en": "Kyoto canal carpeted in cherry blossoms — a red bridge reflected into a perfect circle under overcast spring light",
        "description_zh": "京都运河上漂满樱花瓣，红色木桥的倒影与桥身合成完美的圆，阴天柔光下一片粉绿",
        "category": "landscape",
        "tags": ["landscape", "cherry-blossom", "kyoto", "canal", "bridge", "spring"],
        "style_keywords": ["overcast even light", "reflection circle", "pink carpet composition"],
        "difficulty": "beginner",
        "use_count": 1150,
        "like_count": 380,
        "favorite_count": 210,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  ILLUSTRATION (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "A red fox curled up inside a hollow tree stump, reading a tiny book by lantern light. "
            "Outside the stump, autumn leaves drift past the entrance. "
            "Watercolor rendering with visible paper grain, "
            "wet-on-wet washes for the background forest and precise dry-brush detail on the fox's fur. "
            "Warm amber lantern glow spills across the fox and book pages. "
            "Color palette of burnt orange, forest green, and cream."
        ),
        "display_name_en": "Reading Fox",
        "display_name_zh": "树洞书狐",
        "description_en": "Watercolor storybook fox reading by lantern light in a hollow stump, autumn leaves drifting past the door",
        "description_zh": "水彩绘本风格的小狐狸蜷在树洞里借灯光读书，秋叶在洞口飘过",
        "category": "illustration",
        "tags": ["illustration", "watercolor", "fox", "storybook", "autumn", "cozy"],
        "style_keywords": ["wet-on-wet watercolor", "storybook warmth", "dry-brush detail"],
        "difficulty": "beginner",
        "use_count": 1280,
        "like_count": 425,
        "favorite_count": 240,
    },
    {
        "prompt_text": (
            "Detailed cross-section of a Victorian terraced house, "
            "each room revealing a different family member's activity — "
            "grandmother knitting in the attic, children playing in the nursery, "
            "father reading in the study, cat sleeping by the kitchen stove. "
            "Cutaway style with the exterior brick wall removed on the left side. "
            "Fine ink linework with watercolor fill. "
            "Warm interior yellows contrast with cool blue-gray exterior walls."
        ),
        "display_name_en": "House Cross-Section",
        "display_name_zh": "房屋剖面图",
        "description_en": "Ink-and-watercolor cutaway of a Victorian house buzzing with family life in every room",
        "description_zh": "维多利亚联排屋的剖面插画，墨线水彩间每个房间都有家庭生活的温暖场景",
        "category": "illustration",
        "tags": ["illustration", "cross-section", "architecture", "family", "ink-watercolor"],
        "style_keywords": ["cutaway illustration", "ink linework", "warm-cool contrast"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 165,
        "favorite_count": 88,
    },
    {
        "prompt_text": (
            "Isometric pixel art scene of a ramen shop at night — "
            "the tiny kitchen visible through the front counter, a cook tending steaming pots, "
            "three customers on bar stools, red paper lanterns hanging from the awning. "
            "Each tile is precisely placed in a limited 32-color palette. "
            "Steam rises in dithered pixel gradients. "
            "The shop glows warm against a cool dark-blue night background. "
            "Neighboring buildings are visible at the edges, unlit by comparison."
        ),
        "display_name_en": "Pixel Ramen Shop",
        "display_name_zh": "像素拉面馆",
        "description_en": "Isometric pixel art ramen shop glowing warm against a cool night, every tile hand-placed in a 32-color palette",
        "description_zh": "等轴像素风深夜拉面馆，32色限定调色板中蒸汽以抖动渐变升腾",
        "category": "illustration",
        "tags": ["illustration", "pixel-art", "isometric", "ramen", "night", "cozy"],
        "style_keywords": ["isometric pixel art", "limited palette", "dithered gradients"],
        "difficulty": "intermediate",
        "use_count": 850,
        "like_count": 285,
        "favorite_count": 155,
    },
    {
        "prompt_text": (
            "Botanical illustration of a pomegranate branch — "
            "one fruit whole, one cut open to reveal ruby-red arils, "
            "blossoms at different stages from bud to full flower. "
            "Rendered in the style of 18th-century scientific illustration "
            "with fine cross-hatching for shadow and delicate stippling for texture. "
            "Aged cream paper background with faint foxing marks. "
            "A handwritten Latin name in copperplate script sits below the specimen."
        ),
        "display_name_en": "Pomegranate Study",
        "display_name_zh": "石榴图谱",
        "description_en": "Scientific botanical plate of pomegranate in full lifecycle — bud, bloom, fruit, and ruby cross-section",
        "description_zh": "十八世纪科学图谱风格的石榴全生命周期——花蕾、盛放、果实与宝石红剖面",
        "category": "illustration",
        "tags": ["illustration", "botanical", "scientific", "pomegranate", "vintage"],
        "style_keywords": ["scientific illustration", "cross-hatching", "stipple technique"],
        "difficulty": "intermediate",
        "use_count": 620,
        "like_count": 210,
        "favorite_count": 115,
    },
    {
        "prompt_text": (
            "Bold pop art portrait of a woman in the style of Roy Lichtenstein — "
            "Ben-Day dots forming skin tones, thick black outlines, primary color palette "
            "of cadmium red, cobalt blue, and lemon yellow on white. "
            "A speech bubble emerges from the upper right reading '...' in bold typeface. "
            "The woman's expression is ambiguous — she could be about to speak or choosing silence. "
            "Halftone gradients replace traditional shading throughout."
        ),
        "display_name_en": "Pop Art Silence",
        "display_name_zh": "波普沉默",
        "description_en": "Lichtenstein-style pop art portrait with an empty speech bubble — the loudest silence in primary colors",
        "description_zh": "利希滕斯坦风格波普肖像，空白对话气泡比任何言语都响亮，原色中的沉默宣言",
        "category": "illustration",
        "tags": ["illustration", "pop-art", "lichtenstein", "comic", "primary-colors"],
        "style_keywords": ["Ben-Day dots", "pop art", "primary color palette"],
        "difficulty": "beginner",
        "use_count": 980,
        "like_count": 325,
        "favorite_count": 180,
    },
    {
        "prompt_text": (
            "Art nouveau poster of a woman emerging from swirling wisteria vines, "
            "her hair flowing upward and merging with the blossoms. "
            "An ornate gold leaf border frames the composition in geometric arcs. "
            "The figure occupies the center vertical axis, "
            "while vine tendrils create organic S-curves filling every corner. "
            "Palette of soft lilac, sage green, ivory, and antique gold. "
            "Typography placeholder at the bottom in a stylized serif font."
        ),
        "display_name_en": "Wisteria Nouveau",
        "display_name_zh": "紫藤新艺术",
        "description_en": "Art nouveau poster where a woman and wisteria become one, wrapped in gold-leaf borders and organic S-curves",
        "description_zh": "新艺术海报中女性与紫藤融为一体，金箔边框与有机曲线填满每个角落",
        "category": "illustration",
        "tags": ["illustration", "art-nouveau", "poster", "wisteria", "decorative"],
        "style_keywords": ["art nouveau", "organic S-curves", "gold leaf accents"],
        "difficulty": "intermediate",
        "use_count": 540,
        "like_count": 195,
        "favorite_count": 105,
    },
    {
        "prompt_text": (
            "Dark fantasy ink illustration of a knight standing before an enormous iron gate "
            "set into a cliff face, chains hanging from unseen mechanisms above. "
            "The knight is small in the frame, emphasizing the gate's oppressive scale. "
            "Rendered entirely in black ink with white highlights on scraperboard — "
            "no gray tones, only the interplay of ink-black and paper-white. "
            "Cross-hatching density increases toward the edges, creating a natural vignette. "
            "Ravens perch on the chains, rendered as simple sharp silhouettes."
        ),
        "display_name_en": "Iron Gate Knight",
        "display_name_zh": "铁门前的骑士",
        "description_en": "Black-and-white scraperboard illustration of a lone knight before a titanic gate, scale conveying dread",
        "description_zh": "刮板画风格的黑白插画，孤独骑士立于巨大铁门之前，尺度感传递出无声的压迫",
        "category": "illustration",
        "tags": ["illustration", "dark-fantasy", "ink", "knight", "scraperboard"],
        "style_keywords": ["scraperboard technique", "high contrast ink", "scale intimidation"],
        "difficulty": "advanced",
        "use_count": 340,
        "like_count": 150,
        "favorite_count": 80,
    },
    {
        "prompt_text": (
            "Flat-design illustration of a workspace desk from directly above — "
            "laptop, coffee cup, succulent plant, notebook with pen, phone showing a message. "
            "Each object is rendered in clean geometric shapes with no outlines, "
            "only flat color fills with one highlight tone per object. "
            "Long shadows extend uniformly to the lower-right at 45 degrees. "
            "Palette of dusty rose, sage, warm gray, and terracotta on white."
        ),
        "display_name_en": "Flat Desk View",
        "display_name_zh": "扁平桌面俯瞰",
        "description_en": "Clean flat-design overhead desk illustration with geometric objects casting uniform 45-degree shadows",
        "description_zh": "纯色几何图形构成的扁平化桌面俯视图，统一45度长影投射在白色背景上",
        "category": "illustration",
        "tags": ["illustration", "flat-design", "workspace", "overhead", "geometric"],
        "style_keywords": ["flat design", "long shadow", "geometric simplification"],
        "difficulty": "beginner",
        "use_count": 1100,
        "like_count": 360,
        "favorite_count": 200,
    },
    {
        "prompt_text": (
            "A Chinese ink wash painting of two cranes taking flight from a misty lake surface. "
            "Their wings are rendered in a single confident brushstroke each — "
            "wet ink feathering at the tips into the damp rice paper. "
            "The lake is suggested by three horizontal wash bands of increasing dilution. "
            "A cluster of reeds on the left is painted in sharp, calligraphic strokes. "
            "Vast empty space dominates the upper two-thirds, embodying 留白."
        ),
        "display_name_en": "Cranes in Mist",
        "display_name_zh": "烟波双鹤",
        "description_en": "Traditional Chinese ink wash of two cranes lifting from mist — bold brushstrokes breathing in empty space",
        "description_zh": "水墨画中双鹤从烟波中振翅，每片翅膀只用一笔写成，留白占据大片画面",
        "category": "illustration",
        "tags": ["illustration", "chinese-ink", "cranes", "traditional", "minimalist"],
        "style_keywords": ["ink wash", "留白 negative space", "calligraphic brushwork"],
        "difficulty": "intermediate",
        "use_count": 680,
        "like_count": 230,
        "favorite_count": 125,
    },
    {
        "prompt_text": (
            "Retro travel poster for a fictional moon colony, "
            "rendered in the style of 1960s airline advertisements. "
            "A family in mid-century attire gazes up at a domed lunar city through a shuttle window. "
            "Earth hangs large in the black sky visible through the dome. "
            "Limited four-color screen print aesthetic — navy, burnt orange, cream, and silver. "
            "Bold sans-serif headline at the top: 'VISIT LUNA CITY'. "
            "Slight registration offset between color layers for authentic print feel."
        ),
        "display_name_en": "Retro Moon Poster",
        "display_name_zh": "复古月球旅行",
        "description_en": "1960s-style travel poster for a fictional moon colony — screen-print aesthetic in four retro colors",
        "description_zh": "六十年代航空广告风格的月球殖民地旅行海报，四色丝网印刷的复古质感",
        "category": "illustration",
        "tags": ["illustration", "retro", "sci-fi", "travel-poster", "screen-print"],
        "style_keywords": ["retro travel poster", "limited palette screen print", "mid-century"],
        "difficulty": "beginner",
        "use_count": 920,
        "like_count": 305,
        "favorite_count": 170,
    },
    {
        "prompt_text": (
            "Gouache illustration of a Mediterranean village at siesta hour — "
            "terracotta rooftops, a church bell tower, laundry lines between buildings, "
            "a single cat asleep on a sun-drenched step. "
            "The paint application is visible and textured, with thick impasto on sunlit surfaces "
            "and thin washes in shadowed alleys. "
            "Shadows are painted in cool violet rather than black. "
            "Bougainvillea cascades down a white wall in magenta strokes."
        ),
        "display_name_en": "Mediterranean Siesta",
        "display_name_zh": "地中海午休",
        "description_en": "Gouache village scene at siesta hour — violet shadows, terracotta roofs, and a cat commanding the sunniest step",
        "description_zh": "水粉画地中海午休时分——紫罗兰色阴影、赭红屋顶，一只猫占据了最晒的台阶",
        "category": "illustration",
        "tags": ["illustration", "gouache", "mediterranean", "village", "siesta"],
        "style_keywords": ["gouache impasto", "violet shadows", "Mediterranean palette"],
        "difficulty": "intermediate",
        "use_count": 570,
        "like_count": 195,
        "favorite_count": 108,
    },
    {
        "prompt_text": (
            "A continuous line drawing of a jazz musician playing saxophone, "
            "the single unbroken line flowing from the bell of the instrument "
            "up through the player's fingers, body, and into musical notes "
            "that spiral off the top of the frame. "
            "The line varies in weight from hairline to bold depending on pressure. "
            "No fill, no shading — just one black line on white paper. "
            "The musician's pose conveys deep feeling through minimal means."
        ),
        "display_name_en": "One-Line Jazz",
        "display_name_zh": "一笔爵士",
        "description_en": "Single continuous line drawing of a saxophonist — instrument, body, and music all flowing as one stroke",
        "description_zh": "一条不断线画出萨克斯手——乐器、身体与音符在一笔之间流淌",
        "category": "illustration",
        "tags": ["illustration", "line-art", "jazz", "minimal", "continuous-line"],
        "style_keywords": ["continuous line", "variable weight", "gestural minimalism"],
        "difficulty": "advanced",
        "use_count": 290,
        "like_count": 130,
        "favorite_count": 70,
    },
    {
        "prompt_text": (
            "Children's book spread showing a girl and her dog walking through a forest "
            "where the trees gradually transform from realistic oaks into candy — "
            "trunks becoming peppermint sticks, leaves turning to gummy bears, "
            "mushrooms replaced by cupcakes. The transition is gradual left-to-right. "
            "Digital painting with soft edges and rounded shapes throughout. "
            "Cheerful palette of mint green, strawberry pink, lemon yellow, and chocolate brown."
        ),
        "display_name_en": "Candy Forest Walk",
        "display_name_zh": "糖果森林漫步",
        "description_en": "Whimsical children's book scene where a forest gradually transforms into candy, tree by tree from left to right",
        "description_zh": "童书场景中森林从左到右渐变为糖果——树干成了薄荷棒，蘑菇变成纸杯蛋糕",
        "category": "illustration",
        "tags": ["illustration", "children", "fantasy", "candy", "whimsical", "digital"],
        "style_keywords": ["children's book digital", "gradual transformation", "candy palette"],
        "difficulty": "beginner",
        "use_count": 1050,
        "like_count": 350,
        "favorite_count": 195,
    },
    {
        "prompt_text": (
            "Technical exploded-view illustration of a vintage mechanical pocket watch, "
            "all components separated along the central axis and floating in space — "
            "mainspring, escapement, balance wheel, gear train, dial, and case. "
            "Each part is rendered with precise mechanical drafting detail "
            "and subtle metallic shading in gold, brass, and steel tones. "
            "Thin numbered leader lines connect each component to labels in the margin. "
            "Clean white background with a subtle blue engineering grid."
        ),
        "display_name_en": "Watch Exploded View",
        "display_name_zh": "怀表拆解图",
        "description_en": "Technical exploded-view of a pocket watch revealing every gear and spring in precise mechanical beauty",
        "description_zh": "机械怀表的爆炸视图，主发条、擒纵机构与齿轮组在精密制图中悬浮排列",
        "category": "illustration",
        "tags": ["illustration", "technical", "exploded-view", "mechanical", "watch"],
        "style_keywords": ["exploded view", "technical drafting", "metallic rendering"],
        "difficulty": "advanced",
        "use_count": 310,
        "like_count": 140,
        "favorite_count": 78,
    },
    {
        "prompt_text": (
            "A map illustration in the style of a treasure chart — "
            "hand-drawn coastlines with tiny wave symbols, a compass rose in the corner, "
            "mountain ranges shown as rows of small triangles, forests as clusters of tree symbols. "
            "A dotted path winds from a ship icon at the coast to an X marking the treasure. "
            "Aged parchment background with coffee-stain rings and burned edges. "
            "Ink colors: sepia main lines, red for the dotted path, blue for water features. "
            "A sea serpent coils in the ocean corner with 'Here Be Dragons' in italic script."
        ),
        "display_name_en": "Treasure Map Chart",
        "display_name_zh": "藏宝图",
        "description_en": "Hand-drawn treasure map on aged parchment — wave symbols, triangle mountains, and a sea serpent guarding the corner",
        "description_zh": "羊皮纸上的手绘藏宝图——波浪符号、三角山脉与角落里守护的海蛇",
        "category": "illustration",
        "tags": ["illustration", "map", "treasure", "hand-drawn", "parchment", "adventure"],
        "style_keywords": ["cartographic symbols", "aged parchment", "adventure illustration"],
        "difficulty": "beginner",
        "use_count": 890,
        "like_count": 300,
        "favorite_count": 168,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  PRODUCT (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "A matte-black ceramic perfume bottle standing on a raw marble slab, "
            "a single drop of amber liquid suspended mid-drip from the glass stopper. "
            "Soft overhead strip light creates a clean highlight along the bottle's left edge "
            "while the right side falls into rich shadow. "
            "Background is a smooth dark-charcoal gradient. "
            "Foreground: scattered dried rose petals in muted blush pink. "
            "The composition is centered and symmetrical, conveying quiet luxury."
        ),
        "display_name_en": "Black Ceramic Perfume",
        "display_name_zh": "墨色瓷瓶香水",
        "description_en": "Minimalist perfume still life — amber drop suspended mid-fall, dried petals scattered on raw marble",
        "description_zh": "极简香水静物——琥珀液滴悬于半空，干玫瑰花瓣散落在粗糙大理石上",
        "category": "product",
        "tags": ["product", "perfume", "luxury", "minimal", "dark-mood"],
        "style_keywords": ["strip light edge", "dark gradient", "symmetrical luxury"],
        "difficulty": "beginner",
        "use_count": 980,
        "like_count": 325,
        "favorite_count": 180,
    },
    {
        "prompt_text": (
            "A pair of handmade leather boots floating at a slight tilt against a pure white void, "
            "no visible surface or shadow grounding them. "
            "Warm directional light from upper-left reveals the grain of the vegetable-tanned leather, "
            "hand-stitched welt, and brass eyelets. "
            "One boot faces forward, the other is rotated to show the sole profile. "
            "Fine scratches and patina marks are visible, conveying artisanal character. "
            "Color palette limited to cognac brown, brass, and ivory white."
        ),
        "display_name_en": "Artisan Boot Float",
        "display_name_zh": "手工靴悬浮",
        "description_en": "Floating leather boots revealing every hand-stitched detail against a pure white void — artisan craft on display",
        "description_zh": "手工皮靴悬浮在纯白虚空中，每一道手缝线迹与包浆痕迹都在诉说匠人故事",
        "category": "product",
        "tags": ["product", "boots", "leather", "artisan", "floating", "minimal"],
        "style_keywords": ["levitation shot", "texture reveal", "white void"],
        "difficulty": "intermediate",
        "use_count": 620,
        "like_count": 210,
        "favorite_count": 115,
    },
    {
        "prompt_text": (
            "Flat-lay arrangement of a complete pour-over coffee setup on a dark walnut table — "
            "Chemex brewer, hand grinder, gooseneck kettle, digital scale, "
            "and a small bag of beans with a kraft paper label. "
            "Morning window light enters from the top of the frame. "
            "Each item casts a soft shadow downward, "
            "and a thin steam wisp rises from the freshly brewed carafe. "
            "Earth-tone palette: walnut, cream ceramic, brushed steel, kraft brown."
        ),
        "display_name_en": "Pour-Over Flat Lay",
        "display_name_zh": "手冲咖啡全家福",
        "description_en": "Methodical flat-lay of a pour-over coffee ritual — Chemex, grinder, kettle, and beans on dark walnut",
        "description_zh": "深色胡桃木上手冲咖啡器具的有序排列——Chemex、手磨、鹅颈壶与咖啡豆",
        "category": "product",
        "tags": ["product", "coffee", "flat-lay", "lifestyle", "ritual"],
        "style_keywords": ["overhead flat lay", "earth-tone palette", "lifestyle ritual"],
        "difficulty": "beginner",
        "use_count": 1150,
        "like_count": 375,
        "favorite_count": 210,
    },
    {
        "prompt_text": (
            "A running shoe frozen in mid-explosion, its layers deconstructed and separated — "
            "outer mesh shell, foam midsole, carbon plate, and rubber outsole "
            "all floating apart in space with visible gaps between them. "
            "Each layer is lit individually with colored accent lights: "
            "white on mesh, electric blue on foam, orange on carbon plate. "
            "Black background with subtle radial gradient. "
            "Dynamic 3/4 angle showing both the interior engineering and exterior design."
        ),
        "display_name_en": "Shoe Deconstruction",
        "display_name_zh": "球鞋解构",
        "description_en": "Exploded-view sneaker photography with color-coded accent lights revealing each engineering layer",
        "description_zh": "球鞋爆炸视图——网面、中底、碳板、外底分层悬浮，彩色灯光逐层点亮",
        "category": "product",
        "tags": ["product", "sneaker", "exploded-view", "tech", "dynamic"],
        "style_keywords": ["exploded product shot", "colored accent lights", "dark background"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 165,
        "favorite_count": 88,
    },
    {
        "prompt_text": (
            "A handmade ceramic tea set arranged on a linen runner — "
            "a teapot with an organic, slightly asymmetric form and two matching cups "
            "in wabi-sabi style with visible kiln marks and glaze drips. "
            "Soft diffused daylight from a nearby window, no harsh shadows. "
            "A single camellia bloom lies beside the teapot as a color accent. "
            "The linen texture is visible and tactile. "
            "Palette of celadon green glaze, natural linen beige, and the deep pink of the camellia."
        ),
        "display_name_en": "Wabi-Sabi Tea Set",
        "display_name_zh": "侘寂茶器",
        "description_en": "Handmade ceramic tea set embracing imperfection — kiln marks, glaze drips, and a single camellia accent",
        "description_zh": "侘寂美学手作茶器——窑变痕迹与釉滴是不完美的完美，一朵山茶花旁衬",
        "category": "product",
        "tags": ["product", "ceramic", "tea", "wabi-sabi", "handmade"],
        "style_keywords": ["wabi-sabi aesthetic", "diffused daylight", "tactile texture"],
        "difficulty": "beginner",
        "use_count": 870,
        "like_count": 290,
        "favorite_count": 160,
    },
    {
        "prompt_text": (
            "A smartwatch displayed on a polished obsidian pedestal, "
            "its screen showing a minimalist watch face with a single complication. "
            "The watch band curves gracefully off the edge of the pedestal. "
            "Two-point lighting setup: cool blue key light from upper-left "
            "and warm accent light from lower-right, "
            "creating complementary reflections on the glass screen and metal case. "
            "Background is deep navy with a subtle horizontal gradient line suggesting a horizon."
        ),
        "display_name_en": "Smartwatch Showcase",
        "display_name_zh": "智能表展示",
        "description_en": "Smartwatch on obsidian pedestal under dual-temperature lighting, cool blue meets warm amber in glass reflections",
        "description_zh": "智能手表置于黑曜石底座上，冷蓝与暖琥珀双色光在表面玻璃上交汇",
        "category": "product",
        "tags": ["product", "smartwatch", "tech", "pedestal", "dual-light"],
        "style_keywords": ["dual-temperature lighting", "obsidian surface", "tech minimal"],
        "difficulty": "intermediate",
        "use_count": 540,
        "like_count": 185,
        "favorite_count": 98,
    },
    {
        "prompt_text": (
            "A collection of natural skincare bottles arranged in a sunlit bathroom shelf "
            "with morning light streaming through frosted glass, "
            "casting soft diffused shadows behind each bottle. "
            "Eucalyptus sprigs in a small vase sit at one end, connecting to the botanical branding. "
            "Bottles are amber glass with minimalist white labels. "
            "Water droplets on some bottles suggest recent shower humidity. "
            "Palette: amber glass, white labels, eucalyptus green, warm stone shelf."
        ),
        "display_name_en": "Botanical Shelfie",
        "display_name_zh": "植物系浴室陈列",
        "description_en": "Morning-lit bathroom shelf of amber-glass botanicals — water droplets, eucalyptus, and frosted window glow",
        "description_zh": "晨光穿过磨砂玻璃洒在浴室架上，琥珀色瓶身带着水珠，桉树枝呼应品牌理念",
        "category": "product",
        "tags": ["product", "skincare", "botanical", "lifestyle", "amber-glass"],
        "style_keywords": ["diffused window light", "lifestyle context", "botanical branding"],
        "difficulty": "beginner",
        "use_count": 1050,
        "like_count": 345,
        "favorite_count": 190,
    },
    {
        "prompt_text": (
            "A single hand-blown wine glass filled with ruby-red wine, "
            "tilted at 15 degrees and held in place by invisible means. "
            "The wine creates a thin film on the glass wall revealing legs. "
            "A hard spotlight from behind projects the glass's shadow forward as a long, "
            "distorted silhouette filled with refracted color. "
            "The wine itself glows translucent where the light passes through. "
            "Pure black background, no surface visible — the glass appears suspended in darkness."
        ),
        "display_name_en": "Wine Glass Light Study",
        "display_name_zh": "酒杯光影",
        "description_en": "Backlit wine glass study — ruby liquid glowing translucent, its colored shadow projected forward into darkness",
        "description_zh": "逆光红酒杯光影研究——酒液透光如红宝石，彩色投影在黑暗中拉长延伸",
        "category": "product",
        "tags": ["product", "wine-glass", "backlight", "shadow-play", "translucent"],
        "style_keywords": ["backlight translucence", "shadow projection", "pure black void"],
        "difficulty": "advanced",
        "use_count": 330,
        "like_count": 145,
        "favorite_count": 78,
    },
    {
        "prompt_text": (
            "A fountain pen resting on an open leather journal, nib pointing toward the viewer. "
            "A line of wet ink trails from the nib across the page, still glistening. "
            "The pen is midnight blue resin with gold trim. "
            "Macro-close framing focuses on the nib area, showing ink flow channels and the tipping. "
            "Shallow depth of field blurs the journal text into abstract texture. "
            "Warm desk lamp light from the left, dark wood desk visible at the edges."
        ),
        "display_name_en": "Fountain Pen Macro",
        "display_name_zh": "钢笔微距",
        "description_en": "Macro study of a fountain pen's wet nib on an open journal — ink still glistening on the page",
        "description_zh": "钢笔笔尖微距特写——墨水刚刚从笔尖流淌到纸面，尚未干透的光泽清晰可见",
        "category": "product",
        "tags": ["product", "fountain-pen", "macro", "stationery", "ink"],
        "style_keywords": ["macro close-up", "wet ink detail", "desk lamp warmth"],
        "difficulty": "intermediate",
        "use_count": 580,
        "like_count": 200,
        "favorite_count": 108,
    },
    {
        "prompt_text": (
            "A bicycle frame hanging on a white pegboard workshop wall, "
            "surrounded by organized tools — hex wrenches, tire levers, chain lube. "
            "The frame is bare titanium with visible weld beads and a brushed finish. "
            "Overhead fluorescent workshop light creates even illumination with no drama. "
            "The composition celebrates function over form, "
            "with the frame centered and tools arranged in neat rows on either side. "
            "Industrial palette: titanium gray, black rubber, chrome, white pegboard."
        ),
        "display_name_en": "Workshop Frame",
        "display_name_zh": "车间车架",
        "description_en": "Bare titanium bicycle frame displayed on a workshop pegboard — industrial craft celebrated without pretense",
        "description_zh": "钛合金自行车架悬挂在工具墙上，工业质感的焊缝与工具排列诉说着功能之美",
        "category": "product",
        "tags": ["product", "bicycle", "titanium", "workshop", "industrial"],
        "style_keywords": ["workshop documentary", "industrial palette", "functional display"],
        "difficulty": "intermediate",
        "use_count": 460,
        "like_count": 160,
        "favorite_count": 85,
    },
    {
        "prompt_text": (
            "Three bars of handmade soap stacked at alternating angles, "
            "each a different natural color — oatmeal beige, charcoal black, lavender purple. "
            "Dried lavender sprigs and oat grains are scattered around the base. "
            "Soft window light from the right, casting gentle directional shadows. "
            "The soap surfaces show swirl patterns from the cold-process pour. "
            "Background is a neutral warm-gray linen cloth. "
            "Tight crop at slight overhead angle, emphasizing texture and craft."
        ),
        "display_name_en": "Artisan Soap Stack",
        "display_name_zh": "手工皂叠放",
        "description_en": "Cold-process soap trio with visible swirl patterns — oatmeal, charcoal, and lavender stacked on linen",
        "description_zh": "三块冷制手工皂呈交错角度叠放，旋涡纹路清晰可见，散落薰衣草与燕麦点缀",
        "category": "product",
        "tags": ["product", "soap", "handmade", "natural", "texture"],
        "style_keywords": ["window sidelight", "texture close-up", "natural ingredients"],
        "difficulty": "beginner",
        "use_count": 790,
        "like_count": 265,
        "favorite_count": 145,
    },
    {
        "prompt_text": (
            "A high-end headphone displayed on a geometric concrete stand, "
            "ear cups rotated to show the driver mesh pattern inside. "
            "The headband arcs above, forming a graceful parabolic curve. "
            "Cool neutral lighting from a large overhead softbox, "
            "with a subtle warm fill from below reflecting off the concrete surface. "
            "Background is a seamless medium-gray. "
            "Material contrast between matte aluminum cups, leather pads, and woven cable."
        ),
        "display_name_en": "Headphone on Concrete",
        "display_name_zh": "混凝土上的耳机",
        "description_en": "Audiophile headphones on a geometric concrete stand — aluminum, leather, and woven cable catch neutral light",
        "description_zh": "发烧耳机陈列于几何混凝土底座，铝杯、皮垫与编织线材在中性光线中各展质感",
        "category": "product",
        "tags": ["product", "headphone", "audio", "concrete", "material-contrast"],
        "style_keywords": ["neutral studio light", "material contrast", "geometric display"],
        "difficulty": "beginner",
        "use_count": 830,
        "like_count": 275,
        "favorite_count": 150,
    },
    {
        "prompt_text": (
            "A chocolate truffle box opened to reveal nine truffles, "
            "each with a different artistic finish — gold leaf, cocoa dust, "
            "pistachio crumb, freeze-dried raspberry, white chocolate drizzle. "
            "The box is textured matte black with embossed gold logo. "
            "Shot at 45-degree angle to show both the open lid and the truffle grid. "
            "Soft ring light creates even illumination with a subtle circular catch-light "
            "on each glossy truffle surface. Dark wood table surface beneath."
        ),
        "display_name_en": "Truffle Box Gallery",
        "display_name_zh": "松露巧克力画廊",
        "description_en": "Nine artisan truffles in a matte-black box, each surface a different edible artwork under soft ring light",
        "description_zh": "九颗手工松露巧克力在黑色礼盒中排列，每颗表面都是不同的可食用艺术品",
        "category": "product",
        "tags": ["product", "chocolate", "luxury", "food-product", "artisan"],
        "style_keywords": ["ring light", "45-degree reveal", "luxury packaging"],
        "difficulty": "intermediate",
        "use_count": 510,
        "like_count": 180,
        "favorite_count": 98,
    },
    {
        "prompt_text": (
            "A vintage Leica camera disassembled into its major components — "
            "body, lens, viewfinder assembly, shutter mechanism — "
            "arranged in a precise knolling layout on a clean white surface. "
            "Each component is perfectly parallel or perpendicular to the frame edges. "
            "Even, shadowless overhead light emphasizes the machined metal surfaces. "
            "The chrome and black paint show authentic wear from decades of use. "
            "Strict top-down perspective with generous spacing between each piece."
        ),
        "display_name_en": "Leica Knolling",
        "display_name_zh": "徕卡拆解排列",
        "description_en": "Precision knolling of a vintage Leica — each machined component aligned on white, decades of wear visible",
        "description_zh": "经典徕卡相机的精准排列拆解，每个机加工组件在白色背景上整齐码放",
        "category": "product",
        "tags": ["product", "camera", "knolling", "vintage", "precision"],
        "style_keywords": ["knolling layout", "top-down precision", "machined patina"],
        "difficulty": "advanced",
        "use_count": 350,
        "like_count": 155,
        "favorite_count": 82,
    },
    {
        "prompt_text": (
            "A single houseplant — a mature monstera deliciosa — "
            "in a hand-thrown terracotta pot with visible throwing rings. "
            "Placed on a rattan plant stand in front of a white textured wall. "
            "A shaft of direct afternoon sun crosses the wall diagonally, "
            "and the monstera's split leaves cast intricate shadow patterns on the white surface. "
            "The light catches the glossy leaf surface, creating highlights that reveal the fenestration pattern. "
            "Earth-tone palette: terracotta, deep green, rattan honey, white wall."
        ),
        "display_name_en": "Monstera Shadow Play",
        "display_name_zh": "龟背竹光影戏",
        "description_en": "Monstera casting intricate leaf shadows on a white wall — a study in natural light, form, and fenestration",
        "description_zh": "龟背竹在午后斜阳中投射精致叶影于白墙上，天然孔洞光影如一幕剪影戏",
        "category": "product",
        "tags": ["product", "plant", "monstera", "shadow", "natural-light"],
        "style_keywords": ["shadow play", "direct sunlight", "botanical product"],
        "difficulty": "beginner",
        "use_count": 920,
        "like_count": 305,
        "favorite_count": 170,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  ARCHITECTURE (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Interior of a concrete brutalist church — raw board-formed concrete walls "
            "rising to a narrow skylight slit that pours a single blade of sunlight "
            "diagonally across the nave. "
            "Wooden pews cast parallel shadow lines across the floor. "
            "The light blade illuminates suspended dust particles, "
            "creating a solid-looking beam in an otherwise dim space. "
            "No decoration — only concrete, light, and geometry define the sacred."
        ),
        "display_name_en": "Brutalist Light Blade",
        "display_name_zh": "光刃教堂",
        "description_en": "A single skylight blade cuts through raw concrete brutalism — light itself becomes the only ornament",
        "description_zh": "一道天窗光刃划过清水混凝土教堂的中殿，光线本身成为唯一的装饰",
        "category": "architecture",
        "tags": ["architecture", "brutalist", "church", "concrete", "light-blade"],
        "style_keywords": ["board-formed concrete", "light as ornament", "sacred geometry"],
        "difficulty": "intermediate",
        "use_count": 620,
        "like_count": 215,
        "favorite_count": 115,
    },
    {
        "prompt_text": (
            "A traditional Kyoto machiya townhouse interior looking from the entrance "
            "through a series of sliding shoji screens toward a small courtyard garden at the back. "
            "Each layer of screens creates a frame-within-a-frame effect, "
            "light increasing with each threshold. "
            "Tatami floors, dark timber columns, and a single ikebana arrangement "
            "on a tokonoma alcove shelf at the midpoint. "
            "The garden at the far end glows with green reflected light."
        ),
        "display_name_en": "Machiya Threshold",
        "display_name_zh": "町屋深处",
        "description_en": "Kyoto machiya seen through layered shoji thresholds, each frame brighter than the last, pulling toward the garden",
        "description_zh": "从京都町屋入口望去，层层障子门框叠透，光线逐层递增直至尽头庭院的绿意",
        "category": "architecture",
        "tags": ["architecture", "japanese", "machiya", "interior", "threshold"],
        "style_keywords": ["frame-within-frame", "layered depth", "Japanese interior"],
        "difficulty": "beginner",
        "use_count": 850,
        "like_count": 285,
        "favorite_count": 155,
    },
    {
        "prompt_text": (
            "The spiral staircase of a Baroque library seen from directly below, "
            "looking up through the ornate iron balustrade to a painted ceiling fresco far above. "
            "The spiral creates a perfect logarithmic curve receding upward. "
            "Leather-bound books line every visible wall surface. "
            "Warm incandescent light from brass reading lamps on each landing. "
            "The perspective converges to a bright oculus at the center-top of the frame. "
            "Rich palette of mahogany, gold leaf, aged leather, and fresco pastels."
        ),
        "display_name_en": "Library Spiral Lookup",
        "display_name_zh": "藏书楼螺旋",
        "description_en": "Looking straight up through a Baroque library's spiral staircase to a painted ceiling — books lining every surface",
        "description_zh": "从巴洛克藏书楼底部仰望螺旋楼梯直达穹顶壁画，四壁皮装书籍环绕而上",
        "category": "architecture",
        "tags": ["architecture", "library", "spiral", "baroque", "lookup"],
        "style_keywords": ["worm's eye view", "logarithmic spiral", "Baroque grandeur"],
        "difficulty": "intermediate",
        "use_count": 580,
        "like_count": 200,
        "favorite_count": 108,
    },
    {
        "prompt_text": (
            "A glass-walled modernist pavilion set in a forest clearing, "
            "the reflection of trees on the glass exterior blending seamlessly "
            "with the actual trees visible through the interior. "
            "The effect erases the boundary between inside and outside. "
            "A single Barcelona chair sits inside, visible as a dark silhouette. "
            "Overcast sky provides perfectly even illumination without reflective hot-spots. "
            "Autumn leaves carpet the ground, some pressed against the glass base."
        ),
        "display_name_en": "Glass Pavilion Forest",
        "display_name_zh": "林间玻璃屋",
        "description_en": "Glass pavilion dissolving into forest — reflections and transparency erase the boundary between inside and out",
        "description_zh": "玻璃展馆在森林中消融，反射与透明模糊了内外的界限，秋叶贴上基座",
        "category": "architecture",
        "tags": ["architecture", "modernist", "glass", "pavilion", "forest"],
        "style_keywords": ["transparency reflection", "inside-outside blur", "modernist pavilion"],
        "difficulty": "beginner",
        "use_count": 920,
        "like_count": 310,
        "favorite_count": 170,
    },
    {
        "prompt_text": (
            "An abandoned Art Deco movie palace interior, seats removed but the ornate ceiling "
            "still intact — gilded plasterwork sunburst patterns, "
            "a massive crystal chandelier hanging slightly askew. "
            "Shafts of light enter through broken sections of the roof, "
            "illuminating floating dust and revealing patches of original turquoise and gold paint "
            "beneath decades of grime. "
            "The stage curtain hangs in tatters, revealing a bare brick back wall."
        ),
        "display_name_en": "Deco Palace Ruins",
        "display_name_zh": "装饰派影院遗迹",
        "description_en": "Abandoned Art Deco cinema — gilded sunbursts still gleam through decades of grime, chandelier listing to one side",
        "description_zh": "废弃的装饰艺术电影院——镀金日晕纹在积尘中依稀闪烁，水晶吊灯微微倾斜",
        "category": "architecture",
        "tags": ["architecture", "art-deco", "abandoned", "cinema", "ruins"],
        "style_keywords": ["ruin beauty", "Art Deco ornament", "shaft light through decay"],
        "difficulty": "intermediate",
        "use_count": 490,
        "like_count": 175,
        "favorite_count": 95,
    },
    {
        "prompt_text": (
            "A parametric architecture facade made of thousands of individually angled aluminum fins "
            "that create a dynamic moiré pattern when viewed from different angles. "
            "The photograph captures a moment where the fin angles align to reveal "
            "a hidden wave pattern across the entire building face. "
            "Late afternoon sun catches the fin edges, creating horizontal lines of golden light. "
            "Blue sky reflected in the glass behind the fins. "
            "Shot from street level looking up, perspective compression from a telephoto lens."
        ),
        "display_name_en": "Parametric Fin Facade",
        "display_name_zh": "参数化鳍片立面",
        "description_en": "Thousands of aluminum fins creating a moiré wave on a parametric facade, golden light catching each edge",
        "description_zh": "数千片铝鳍以参数化排列在建筑立面形成摩尔波纹，夕阳在每片边缘点亮金线",
        "category": "architecture",
        "tags": ["architecture", "parametric", "facade", "aluminum", "moire"],
        "style_keywords": ["parametric design", "moiré pattern", "telephoto compression"],
        "difficulty": "advanced",
        "use_count": 340,
        "like_count": 150,
        "favorite_count": 80,
    },
    {
        "prompt_text": (
            "A Scandinavian cabin living room in deep winter — "
            "floor-to-ceiling windows framing a snow-covered pine forest, "
            "a roaring stone fireplace casting warm flickering light on the left wall. "
            "Sheepskin throws on mid-century modern armchairs, a thick wool rug on pale oak floors. "
            "The color temperature splits the room: warm amber firelight on the left, "
            "cool blue-white snow-reflected daylight on the right. "
            "A stack of birch logs and a steaming mug complete the hygge tableau."
        ),
        "display_name_en": "Nordic Fireside Winter",
        "display_name_zh": "北欧冬日炉边",
        "description_en": "Scandinavian cabin split between firelight warmth and snow-blue window light — hygge distilled to one room",
        "description_zh": "北欧木屋被壁炉暖光与雪地冷光一分为二，温暖与凛冽在一个房间内共存",
        "category": "architecture",
        "tags": ["architecture", "scandinavian", "cabin", "winter", "hygge", "interior"],
        "style_keywords": ["warm-cool split", "hygge interior", "natural materials"],
        "difficulty": "beginner",
        "use_count": 1100,
        "like_count": 365,
        "favorite_count": 200,
    },
    {
        "prompt_text": (
            "The flying buttresses of a Gothic cathedral shot from the apse at dawn, "
            "stone ribs arcing outward like the skeleton of a massive creature. "
            "The lower walls are still in deep shadow while the upper flying arches "
            "catch the first pink-gold light of sunrise. "
            "Gargoyle silhouettes punctuate the skyline. "
            "Pigeons roost in the stone tracery. "
            "The stone itself shows centuries of weathering — dark streaks below water channels."
        ),
        "display_name_en": "Gothic Buttress Dawn",
        "display_name_zh": "哥特飞扶壁晨曦",
        "description_en": "Gothic flying buttresses catching first dawn light while the lower walls remain in deep shadow",
        "description_zh": "哥特飞扶壁在晨曦中被金粉色光线点亮，下方墙体仍沉于深影之中",
        "category": "architecture",
        "tags": ["architecture", "gothic", "cathedral", "buttress", "dawn"],
        "style_keywords": ["dawn gradient light", "structural skeleton", "Gothic verticality"],
        "difficulty": "intermediate",
        "use_count": 520,
        "like_count": 180,
        "favorite_count": 98,
    },
    {
        "prompt_text": (
            "Interior of a traditional Moroccan riad courtyard — "
            "a small central fountain surrounded by intricate zellige tilework in cobalt blue and white, "
            "four orange trees in ornate pots at the corners, "
            "and carved plaster arches on all four sides. "
            "Midday sun falls directly into the courtyard, creating hard shadows "
            "with razor-sharp edges on the tile patterns. "
            "Upper balcony with turned wood railings frames the sky above."
        ),
        "display_name_en": "Riad Courtyard Noon",
        "display_name_zh": "庭院正午",
        "description_en": "Moroccan riad courtyard at noon — zellige tiles blazing in cobalt blue under direct overhead sun",
        "description_zh": "摩洛哥庭院正午——钴蓝泽利吉瓷砖在直射阳光下灿烂，喷泉与橙树四角对称",
        "category": "architecture",
        "tags": ["architecture", "moroccan", "riad", "courtyard", "zellige"],
        "style_keywords": ["overhead noon light", "zellige pattern", "courtyard symmetry"],
        "difficulty": "beginner",
        "use_count": 750,
        "like_count": 250,
        "favorite_count": 135,
    },
    {
        "prompt_text": (
            "A cantilevered concrete house projecting over a waterfall, "
            "inspired by Fallingwater but reimagined in contemporary minimalism. "
            "Clean horizontal planes of white concrete extend over the rocky ledge, "
            "floor-to-ceiling glass revealing the interior living space. "
            "The waterfall drops directly beneath the main living area. "
            "Lush green forest surrounds the structure. "
            "Photographed from downstream at water level, the house framed by wet boulders."
        ),
        "display_name_en": "Waterfall Cantilever",
        "display_name_zh": "瀑布上的悬挑",
        "description_en": "Contemporary cantilever house over a waterfall — white concrete planes floating above rushing water and forest",
        "description_zh": "白色混凝土悬挑住宅凌驾于瀑布之上，从下游水面视角望去，建筑与瀑布融为一体",
        "category": "architecture",
        "tags": ["architecture", "cantilever", "waterfall", "contemporary", "nature"],
        "style_keywords": ["cantilever drama", "water-level perspective", "architecture-nature fusion"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 165,
        "favorite_count": 88,
    },
    {
        "prompt_text": (
            "A dense Hong Kong apartment tower photographed from directly below, "
            "looking straight up the narrow light well between buildings. "
            "Hundreds of identical windows, air conditioning units, and laundry poles "
            "recede upward in forced perspective toward a tiny rectangle of sky. "
            "The walls are painted in faded pastels — mint, peach, powder blue — "
            "creating an unexpected color palette in the urban density. "
            "A few windows glow warm from interior light despite daytime."
        ),
        "display_name_en": "Dense Tower Lookup",
        "display_name_zh": "密楼仰望",
        "description_en": "Worm's-eye view up a Hong Kong light well — hundreds of windows converging toward a postage-stamp sky",
        "description_zh": "从香港楼宇天井底部仰望——数百扇窗户向上汇聚，只剩一方邮票大小的天空",
        "category": "architecture",
        "tags": ["architecture", "hong-kong", "density", "lookup", "urban"],
        "style_keywords": ["worm's eye forced perspective", "pastel urban", "vertical density"],
        "difficulty": "beginner",
        "use_count": 780,
        "like_count": 260,
        "favorite_count": 140,
    },
    {
        "prompt_text": (
            "An infinity-edge swimming pool on a cliff-top villa at golden hour, "
            "the pool edge seamlessly merging with the Mediterranean Sea beyond. "
            "Underwater pool lights just beginning to glow aquamarine "
            "while the sky transitions to peach and lavender. "
            "A single lounge chair with a white towel sits at the pool's far end. "
            "The wet pool deck reflects the sky like a second mirror surface. "
            "Clean modernist architecture with white rendered walls and dark teak accents."
        ),
        "display_name_en": "Infinity Edge Sunset",
        "display_name_zh": "无边泳池日落",
        "description_en": "Cliff-top infinity pool merging with the Mediterranean at golden hour — water, sky, and sea becoming one surface",
        "description_zh": "悬崖上的无边泳池在黄金时刻与地中海融为一体——水面、天空与海面合为一面",
        "category": "architecture",
        "tags": ["architecture", "pool", "infinity-edge", "villa", "golden-hour"],
        "style_keywords": ["infinity edge merge", "golden hour warmth", "modernist villa"],
        "difficulty": "beginner",
        "use_count": 1200,
        "like_count": 395,
        "favorite_count": 215,
    },
    {
        "prompt_text": (
            "Cross-section rendering of a multi-level underground house built into a hillside — "
            "the roof is a living green meadow from above, "
            "while below ground three levels of rooms are carved into the earth. "
            "Skylights tunnel daylight down to the lowest level through light wells. "
            "Interior walls are a mix of exposed rock face and smooth white plaster. "
            "An underground stream runs through the lowest level behind a glass wall. "
            "The section cut reveals soil layers, root systems, and embedded boulders."
        ),
        "display_name_en": "Earth-Sheltered Section",
        "display_name_zh": "地下住宅剖面",
        "description_en": "Architectural section revealing three underground levels beneath a living meadow roof — light wells, rock, and stream",
        "description_zh": "建筑剖面图揭示草甸屋顶下的三层地下居所——光井、岩壁与暗溪清晰可见",
        "category": "architecture",
        "tags": ["architecture", "underground", "section", "earth-sheltered", "sustainable"],
        "style_keywords": ["architectural section", "earth-sheltered design", "geological layers"],
        "difficulty": "advanced",
        "use_count": 310,
        "like_count": 140,
        "favorite_count": 75,
    },
    {
        "prompt_text": (
            "A narrow Shanghai longtang alleyway after rain, "
            "brick walls on both sides darkened by water, "
            "electrical wires crisscrossing overhead forming a web against gray sky. "
            "A single red lantern hangs from a doorway halfway down the alley. "
            "Puddles on the stone-paved ground reflect the lantern and the sky. "
            "An old bicycle leans against one wall. "
            "The alley terminates in a bright opening where a modern glass tower is visible."
        ),
        "display_name_en": "Longtang After Rain",
        "display_name_zh": "弄堂雨后",
        "description_en": "Rain-soaked Shanghai longtang alley — one red lantern and its puddle reflection bridging old brick and new glass",
        "description_zh": "雨后上海弄堂——一盏红灯笼与水洼倒影在旧砖墙与远处玻璃塔楼之间架起桥梁",
        "category": "architecture",
        "tags": ["architecture", "shanghai", "longtang", "alley", "rain", "urban-contrast"],
        "style_keywords": ["rain-wet surfaces", "old-new juxtaposition", "red accent"],
        "difficulty": "intermediate",
        "use_count": 650,
        "like_count": 220,
        "favorite_count": 120,
    },
    {
        "prompt_text": (
            "A half-demolished concrete apartment block stands at the edge of a construction site, "
            "one wall completely removed to reveal twelve cross-section rooms still furnished — "
            "a kitchen with dishes in the rack, a child's bedroom with star stickers on the ceiling, "
            "a bathroom with a towel on the hook. Morning sun enters the exposed rooms from the east, "
            "casting long shadows across patterned wallpaper and cracked tile floors. "
            "A wrecking crane waits motionless to the left, its ball suspended mid-swing. "
            "Dust particles float in the sunbeams. The surrounding city continues indifferently behind."
        ),
        "display_name_en": "Cross-Section Lives",
        "display_name_zh": "剖面人生",
        "description_en": "A half-demolished building reveals twelve furnished rooms in cross-section — private lives laid open to morning sun and the waiting wrecking ball",
        "description_zh": "半拆公寓楼如剖面图般展露十二户人家的房间——晨光照进挂着毛巾的浴室和贴着星星的儿童房，铁球悬在半空",
        "category": "architecture",
        "tags": ["architecture", "demolition", "cross-section", "urban", "morning-light", "nostalgia"],
        "style_keywords": ["architectural cross-section", "frozen demolition", "private-to-public exposure"],
        "difficulty": "advanced",
        "use_count": 520,
        "like_count": 190,
        "favorite_count": 105,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  ANIME (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "A girl in a sailor uniform sits alone on the last train home, "
            "forehead resting against the rain-streaked window. "
            "The empty carriage stretches behind her in warm fluorescent light, "
            "while outside the glass, city lights streak into horizontal neon ribbons. "
            "Her reflection overlaps with the passing cityscape in a ghostly double exposure. "
            "Tight interior framing, shallow focus on raindrops, melancholic blue-orange palette."
        ),
        "display_name_en": "Last Train Reflection",
        "display_name_zh": "末班车独白",
        "description_en": "Intimate anime scene using window reflections to externalize a quiet emotional moment on the last train home",
        "description_zh": "车窗倒影与城市光影交融的末班列车独处瞬间，雨滴模糊了现实与内心的界限",
        "category": "anime",
        "tags": ["anime", "train", "melancholy", "night", "reflection", "slice-of-life"],
        "style_keywords": ["double exposure", "tight framing", "blue-orange palette"],
        "difficulty": "intermediate",
        "use_count": 1100,
        "like_count": 410,
        "favorite_count": 230,
    },
    {
        "prompt_text": (
            "A boy and his giant robot sitting on a hilltop overlooking a sunset sea, "
            "the robot's massive hand flat on the grass beside the boy. "
            "The robot is battle-scarred — dented armor plates, one dim eye, sparking joints — "
            "but its posture mirrors the boy's relaxed lean. "
            "Warm golden hour light paints them both. "
            "The sky graduates from deep orange at the horizon through coral to soft lavender. "
            "Wildflowers and tall grass soften the mechanical edges."
        ),
        "display_name_en": "Mecha Sunset Companion",
        "display_name_zh": "夕阳下的机甲伙伴",
        "description_en": "A battle-scarred mecha and its young pilot share a quiet hilltop sunset — gentle despite the scale and scars",
        "description_zh": "伤痕累累的机甲与少年并肩坐在山丘上看海上日落，温柔与壮阔并存",
        "category": "anime",
        "tags": ["anime", "mecha", "sunset", "companion", "gentle-giant"],
        "style_keywords": ["scale contrast", "golden hour anime", "emotional mecha"],
        "difficulty": "beginner",
        "use_count": 1350,
        "like_count": 450,
        "favorite_count": 250,
    },
    {
        "prompt_text": (
            "A floating marketplace in a canal city inspired by Southeast Asian stilt villages, "
            "colorful wooden boats laden with fruit and fabric, "
            "vendors calling to customers leaning from balconied houses. "
            "Paper lanterns string between buildings, glowing warm against a twilight sky. "
            "Water reflects all the color and light in broken, shimmering patterns. "
            "Wide establishing shot showing three blocks of the canal district. "
            "Studio Ghibli-inspired richness of detail in every window and awning."
        ),
        "display_name_en": "Floating Market Twilight",
        "display_name_zh": "水上集市黄昏",
        "description_en": "A canal market city at twilight brimming with Ghibli-level detail — boats, lanterns, and shimmering reflections",
        "description_zh": "黄昏中的水上集市充满吉卜力式的细节——彩船、灯笼与波光粼粼的倒影",
        "category": "anime",
        "tags": ["anime", "ghibli", "market", "canal", "twilight", "fantasy"],
        "style_keywords": ["Ghibli world-building", "twilight atmosphere", "water reflections"],
        "difficulty": "intermediate",
        "use_count": 780,
        "like_count": 280,
        "favorite_count": 155,
    },
    {
        "prompt_text": (
            "A lone samurai standing at the edge of a cliff in a snowstorm, "
            "his tattered haori whipping in the wind, katana drawn and held low. "
            "The snow is so thick that the background is reduced to white emptiness. "
            "Only the samurai, a gnarled pine tree clinging to the cliff edge, "
            "and the shadow of an approaching figure in the blizzard are visible. "
            "Ink-wash influenced anime style with limited color — black, white, and blood red sash."
        ),
        "display_name_en": "Blizzard Duel",
        "display_name_zh": "风雪对峙",
        "description_en": "Samurai at the cliff's edge in a white-out blizzard — ink-wash anime with only a blood-red sash breaking the void",
        "description_zh": "暴风雪中悬崖边的武士对峙，水墨动漫风格下只有血红腰带打破苍白虚空",
        "category": "anime",
        "tags": ["anime", "samurai", "blizzard", "ink-wash", "duel", "minimal"],
        "style_keywords": ["ink-wash anime", "white-out composition", "limited color accent"],
        "difficulty": "intermediate",
        "use_count": 670,
        "like_count": 245,
        "favorite_count": 135,
    },
    {
        "prompt_text": (
            "A chibi witch stirring an oversized cauldron that bubbles with pink and purple potion, "
            "sparkles floating upward. Her pointed hat is comically large, drooping over one eye. "
            "A fat cat familiar sits on a stack of spellbooks, unimpressed. "
            "The witch's cottage kitchen is cozy chaos — jars of ingredients, "
            "hanging herbs, a window showing a crescent moon. "
            "Warm amber interior light, pastel candy-color palette, round soft shapes throughout."
        ),
        "display_name_en": "Chibi Witch Brewing",
        "display_name_zh": "Q版魔女炼药",
        "description_en": "Adorable chibi witch brewing sparkly potion while her unimpressed cat judges from a stack of spellbooks",
        "description_zh": "Q版小魔女搅动冒泡的彩色药水，胖猫在咒语书堆上冷眼旁观",
        "category": "anime",
        "tags": ["anime", "chibi", "witch", "kawaii", "cozy", "potion"],
        "style_keywords": ["chibi proportions", "candy pastel palette", "cozy chaos"],
        "difficulty": "beginner",
        "use_count": 1250,
        "like_count": 420,
        "favorite_count": 235,
    },
    {
        "prompt_text": (
            "A cyberpunk hacker sitting cross-legged on the floor of a neon-lit server room, "
            "surrounded by floating holographic displays showing cascading code. "
            "She wears a cropped jacket over a bodysuit, cables plugged into her neck port. "
            "The server racks behind her pulse with rhythmic blue lights. "
            "Her face is lit from below by the screens, eyes reflecting scrolling data. "
            "Color palette of deep indigo, electric cyan, and hot magenta accents."
        ),
        "display_name_en": "Neon Hacker Den",
        "display_name_zh": "霓虹黑客",
        "description_en": "Cyberpunk hacker immersed in holographic code, server racks pulsing behind her in an indigo-cyan-magenta glow",
        "description_zh": "赛博朋克黑客沉浸在全息代码中，服务器机架在身后以蓝紫节奏脉动",
        "category": "anime",
        "tags": ["anime", "cyberpunk", "hacker", "neon", "hologram", "sci-fi"],
        "style_keywords": ["cyberpunk neon", "under-lit face", "holographic interface"],
        "difficulty": "intermediate",
        "use_count": 730,
        "like_count": 265,
        "favorite_count": 145,
    },
    {
        "prompt_text": (
            "A school rooftop scene after class — two students sitting back to back "
            "against the chain-link fence, surrounded by scattered textbooks and empty juice boxes. "
            "Cherry blossom petals drift across the frame from a tree just out of view. "
            "The sky is a Makoto Shinkai gradient of cyan to deep blue with dramatic cumulus clouds. "
            "Late afternoon light casts long shadows from the fence across the concrete. "
            "The mood is bittersweet — the end of something, the beginning of something else."
        ),
        "display_name_en": "Rooftop Last Spring",
        "display_name_zh": "天台最后的春天",
        "description_en": "Two students back-to-back on a school rooftop as cherry blossoms drift by — Shinkai-sky nostalgia at its purest",
        "description_zh": "两人背靠背坐在校园天台栏杆前，樱花飘落在新海诚式的天空下，青春将散场",
        "category": "anime",
        "tags": ["anime", "school", "rooftop", "cherry-blossom", "nostalgia", "shinkai"],
        "style_keywords": ["Shinkai sky gradient", "cherry blossom drift", "bittersweet nostalgia"],
        "difficulty": "beginner",
        "use_count": 1450,
        "like_count": 480,
        "favorite_count": 270,
    },
    {
        "prompt_text": (
            "An underwater scene showing a girl in a flowing white dress sinking slowly, "
            "hair fanning upward like seaweed, eyes closed in peaceful expression. "
            "Rays of surface light penetrate the water in shifting columns around her. "
            "Small bioluminescent jellyfish drift past, trailing gentle light. "
            "Air bubbles rise from the folds of her dress. "
            "The water transitions from bright turquoise near the surface to deep navy below. "
            "The composition is vertical, her figure centered, descent implied by the upward hair."
        ),
        "display_name_en": "Sinking Serenity",
        "display_name_zh": "沉入深蓝",
        "description_en": "A girl sinking through illuminated water, hair fanning upward, bioluminescent jellyfish her only company",
        "description_zh": "少女在光柱穿透的水中缓缓下沉，发丝向上漂散，水母以微光相伴",
        "category": "anime",
        "tags": ["anime", "underwater", "ethereal", "jellyfish", "sinking", "serene"],
        "style_keywords": ["underwater light columns", "vertical descent", "bioluminescent accents"],
        "difficulty": "advanced",
        "use_count": 420,
        "like_count": 185,
        "favorite_count": 100,
    },
    {
        "prompt_text": (
            "A group of adventurers camping in a giant mushroom forest, "
            "their small campfire casting warm orange light upward "
            "onto the underside of spotted mushroom caps the size of houses. "
            "Each mushroom cap has a slightly different color — lavender, cream, coral. "
            "Fireflies mingle with floating spores in the air. "
            "A winding dirt path leads away into the luminous fungal canopy. "
            "Fantasy RPG party composition: warrior polishing a sword, "
            "mage reading a scroll, ranger keeping watch from a mushroom stem."
        ),
        "display_name_en": "Mushroom Camp",
        "display_name_zh": "蘑菇林营地",
        "description_en": "Fantasy RPG party camping beneath house-sized mushrooms, campfire light painting the spotted caps in warm orange",
        "description_zh": "奇幻冒险队在巨型蘑菇林中扎营，篝火将屋顶大的菇盖照成暖橙色",
        "category": "anime",
        "tags": ["anime", "fantasy-rpg", "mushroom", "campfire", "adventure", "party"],
        "style_keywords": ["upward campfire light", "fantasy flora", "RPG party composition"],
        "difficulty": "beginner",
        "use_count": 980,
        "like_count": 340,
        "favorite_count": 190,
    },
    {
        "prompt_text": (
            "A shrine maiden performing a kagura dance on a moonlit outdoor stage, "
            "white sleeves tracing arcs of motion blur in the air. "
            "A torii gate frames her from behind, its vermillion contrasting with the blue moonlight. "
            "Spirit foxes made of pale blue fire sit in a semicircle watching. "
            "Sakura petals frozen mid-fall around the stage. "
            "The ground is polished wood reflecting both dancer and moon. "
            "Composition places the dancer at the golden ratio point, torii behind, fox-fire below."
        ),
        "display_name_en": "Moonlit Kagura",
        "display_name_zh": "月下神乐",
        "description_en": "Shrine maiden dancing kagura under moonlight, spirit foxes of pale fire watching from their semicircle",
        "description_zh": "巫女在月光下舞神乐，青蓝色狐火围成半圆静观，袖间樱花凝固于空中",
        "category": "anime",
        "tags": ["anime", "shrine-maiden", "moonlight", "spirit-fox", "dance", "traditional"],
        "style_keywords": ["moonlit stage", "motion blur trails", "fox-fire supernatural"],
        "difficulty": "advanced",
        "use_count": 390,
        "like_count": 170,
        "favorite_count": 92,
    },
    {
        "prompt_text": (
            "A time-lapse anime scene showing the same park bench across four seasons "
            "in horizontal quadrants — spring cherry blossoms, summer green canopy, "
            "autumn red maple, winter bare branches with snow. "
            "The bench and lamp post remain constant anchors. "
            "A different girl sits on the bench in each season, "
            "wearing seasonal clothing. "
            "Each panel has its characteristic color temperature: "
            "pink-warm, green-bright, orange-golden, blue-cool."
        ),
        "display_name_en": "Four Seasons Bench",
        "display_name_zh": "四季长椅",
        "description_en": "One park bench across four anime seasons — cherry blossom, green canopy, red maple, and snowy branches",
        "description_zh": "同一张公园长椅的四季轮转——樱花、绿荫、红枫、白雪，四格画面流转时光",
        "category": "anime",
        "tags": ["anime", "four-seasons", "time-lapse", "park", "nostalgic", "split-panel"],
        "style_keywords": ["seasonal color temperature", "quadrant composition", "temporal narrative"],
        "difficulty": "intermediate",
        "use_count": 850,
        "like_count": 305,
        "favorite_count": 170,
    },
    {
        "prompt_text": (
            "A giant cat sleeping curled around a European clock tower in a small town, "
            "its fur blanketing several rooftops, tail curling down a cobblestone street. "
            "Townspeople go about their morning as if this is perfectly normal — "
            "a baker carries bread past the cat's paw, children play on its back. "
            "Morning light with long shadows. "
            "The cat's eye is half-open, lazily watching a bird on the clock hand. "
            "Warm, humorous, Ghibli-esque sense of wonder mixed with everyday life."
        ),
        "display_name_en": "Town Cat Nap",
        "display_name_zh": "小镇巨猫",
        "description_en": "A kaiju-sized cat napping around a clock tower while townspeople carry on — Ghibli wonder meets daily life",
        "description_zh": "一只巨猫蜷缩在钟楼周围打盹，镇民照常生活，吉卜力式的奇幻日常",
        "category": "anime",
        "tags": ["anime", "giant-cat", "ghibli", "whimsical", "town", "cozy"],
        "style_keywords": ["scale absurdity", "Ghibli everyday magic", "warm humor"],
        "difficulty": "beginner",
        "use_count": 1180,
        "like_count": 395,
        "favorite_count": 220,
    },
    {
        "prompt_text": (
            "A dark seinen-style scene in a rain-soaked back alley: "
            "a detective in a long coat crouches beside a chalk outline, "
            "cigarette smoke curling upward to mix with the rain. "
            "A single bare light bulb on a wire above casts harsh downward light "
            "and deep eye-socket shadows on his face. "
            "The alley walls are covered in peeling movie posters and rusted pipes. "
            "Puddles reflect the distorted light bulb as wobbling circles. "
            "Palette of gunmetal gray, nicotine yellow, and midnight blue."
        ),
        "display_name_en": "Noir Alley Detective",
        "display_name_zh": "暗巷侦探",
        "description_en": "Seinen noir detective in a rain-soaked alley — harsh bare-bulb light, chalk outline, and curling cigarette smoke",
        "description_zh": "青年漫画风格的雨夜暗巷侦探——裸灯泡的刺眼光线、粉笔轮廓与上升的烟雾",
        "category": "anime",
        "tags": ["anime", "noir", "detective", "seinen", "rain", "dark"],
        "style_keywords": ["seinen noir", "harsh bare-bulb lighting", "rain-soaked atmosphere"],
        "difficulty": "advanced",
        "use_count": 360,
        "like_count": 155,
        "favorite_count": 85,
    },
    {
        "prompt_text": (
            "A girl running across a field of sunflowers toward a distant train crossing, "
            "one arm outstretched as if trying to catch the departing train. "
            "The sunflowers are taller than her, creating a corridor of yellow. "
            "The train is already in motion, the crossing gate descending. "
            "Summer heat shimmer distorts the air above the rail tracks. "
            "A straw hat flies off her head, frozen mid-air behind her. "
            "Dazzling summer light, high saturation, the energy of a sprint captured mid-stride."
        ),
        "display_name_en": "Sunflower Sprint",
        "display_name_zh": "向日葵狂奔",
        "description_en": "A girl sprinting through sunflowers toward a departing train — summer energy crystallized in a single mid-stride frame",
        "description_zh": "少女穿过向日葵田奔向即将驶离的列车，草帽飞起，夏日的全部能量凝固在一步之间",
        "category": "anime",
        "tags": ["anime", "summer", "sunflower", "running", "train", "youth"],
        "style_keywords": ["frozen motion energy", "summer high-saturation", "corridor composition"],
        "difficulty": "beginner",
        "use_count": 1080,
        "like_count": 365,
        "favorite_count": 200,
    },
    {
        "prompt_text": (
            "A boy in a gakuran school uniform stands on a riverbank at golden hour, "
            "holding a letter he hasn't opened yet. Cherry blossom petals drift across the frame "
            "from right to left, some landing on the water's surface where they spin in slow eddies. "
            "Behind him, a concrete bridge carries a train across the river — warm window light "
            "visible in every carriage. His shadow stretches long on the grass. "
            "The letter's envelope is pale blue with a pressed-flower seal. "
            "The sky graduates from peach near the horizon to soft lavender above."
        ),
        "display_name_en": "Unopened Letter at Dusk",
        "display_name_zh": "黄昏未拆信",
        "description_en": "A boy holds an unopened letter on a cherry-blossom riverbank at golden hour — the last train crossing behind him, petals landing on still water",
        "description_zh": "少年站在河堤上握着一封未拆的淡蓝色信，樱花瓣落在水面缓缓旋转，身后末班电车正驶过铁桥",
        "category": "anime",
        "tags": ["anime", "golden-hour", "cherry-blossom", "letter", "riverbank", "nostalgia"],
        "style_keywords": ["golden-hour glow", "floating petal motion", "bittersweet stillness"],
        "difficulty": "intermediate",
        "use_count": 920,
        "like_count": 310,
        "favorite_count": 175,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  FANTASY (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "An enormous ancient tree grows through the collapsed roof of a forgotten cathedral, "
            "its roots splitting marble floors into mosaic fragments. "
            "Bioluminescent fungi climb the trunk in spiraling chains of soft cyan light, "
            "casting shifting patterns across crumbling stone arches and stained glass shards. "
            "A small figure in a hooded cloak stands at the nave entrance, "
            "lantern in hand, dwarfed by the scale of nature reclaiming sacred architecture. "
            "Deep greens and cool stone grays dominate, punctuated by warm lantern glow."
        ),
        "display_name_en": "Cathedral of Roots",
        "display_name_zh": "树根圣殿",
        "description_en": "Nature overtakes a ruined cathedral — bioluminescent fungi, massive roots, and a lone explorer with a lantern",
        "description_zh": "巨树穿破废弃教堂的穹顶，发光菌螺旋攀附，孤独探索者提灯而入",
        "category": "fantasy",
        "tags": ["fantasy", "ruins", "bioluminescent", "nature-reclaim", "cathedral", "explorer"],
        "style_keywords": ["scale contrast", "nature vs architecture", "bioluminescent lighting"],
        "difficulty": "beginner",
        "use_count": 1380,
        "like_count": 460,
        "favorite_count": 255,
    },
    {
        "prompt_text": (
            "A dragon made entirely of storm clouds coiling through a thunderhead, "
            "lightning flickering along its spine like a nervous system made visible. "
            "Rain falls from its belly. "
            "Below, a fishing village on stilts is lit by the last slice of golden sunset "
            "at the horizon, oblivious to the sky-dragon forming above. "
            "The dragon's eye is a dense knot of cloud with a lightning-flash pupil. "
            "Palette divided: warm gold below the horizon line, cold blue-gray-white above."
        ),
        "display_name_en": "Storm Dragon Rising",
        "display_name_zh": "风暴龙起",
        "description_en": "A dragon forged from thunderclouds with a lightning spine coils above an unsuspecting golden-lit fishing village",
        "description_zh": "雷暴云化为巨龙盘旋于天际，闪电沿脊椎闪烁，金色渔村浑然不知",
        "category": "fantasy",
        "tags": ["fantasy", "dragon", "storm", "lightning", "village", "epic"],
        "style_keywords": ["atmospheric dragon", "warm-cold horizon split", "lightning detail"],
        "difficulty": "intermediate",
        "use_count": 920,
        "like_count": 340,
        "favorite_count": 190,
    },
    {
        "prompt_text": (
            "An underground crystal cavern where geodes the size of rooms line the walls, "
            "their interiors glowing in amethyst purple, citrine gold, and rose quartz pink. "
            "A narrow wooden bridge spans a chasm in the center, "
            "and a robed scholar walks across it carrying a staff that resonates "
            "with the same violet frequency as the largest crystal cluster. "
            "The cavern ceiling is lost in darkness above. "
            "Reflections in a still underground pool below the bridge double the crystal light."
        ),
        "display_name_en": "Crystal Cavern Crossing",
        "display_name_zh": "水晶洞桥",
        "description_en": "Underground crystal cavern aglow in amethyst and citrine — a scholar's staff resonates with the largest geode",
        "description_zh": "地下水晶洞穴中紫晶与黄水晶交辉，学者的法杖与最大晶簇产生共鸣",
        "category": "fantasy",
        "tags": ["fantasy", "crystal", "cavern", "underground", "scholar", "geode"],
        "style_keywords": ["crystal interior glow", "resonance visual", "underground bridge"],
        "difficulty": "beginner",
        "use_count": 1050,
        "like_count": 355,
        "favorite_count": 195,
    },
    {
        "prompt_text": (
            "A floating library in the sky — bookshelves growing from the underside of a cloud island, "
            "books defying gravity, pages fluttering like pinned butterflies. "
            "Spiral staircases of living wood connect different levels. "
            "A librarian sits at a desk at the very edge, feet dangling over open sky, "
            "cataloguing with a quill that writes in glowing ink. "
            "Below, a patchwork of farmland and rivers stretches to the horizon. "
            "Warm afternoon sunlight catches the book spines in bands of gold and burgundy."
        ),
        "display_name_en": "Sky Library",
        "display_name_zh": "天空图书馆",
        "description_en": "A gravity-defying library growing from a cloud island — books flutter like butterflies, a librarian catalogues at the edge",
        "description_zh": "图书馆从云岛底部生长，书页如蝴蝶翻飞，图书管理员在云端悬崖边编目",
        "category": "fantasy",
        "tags": ["fantasy", "library", "floating-island", "books", "whimsical", "sky"],
        "style_keywords": ["gravity defiance", "cloud island", "whimsical world-building"],
        "difficulty": "beginner",
        "use_count": 1200,
        "like_count": 400,
        "favorite_count": 220,
    },
    {
        "prompt_text": (
            "A witch's apothecary built into the hollow of a massive baobab tree, "
            "shelves carved directly into the living wood, filled with jars of colored liquids "
            "that glow faintly in the dimness. "
            "Roots form the floor, twisted into natural channels that guide spilled potions. "
            "A cauldron hangs from a branch above a fire pit where the heartwood should be. "
            "Sunlight enters through a knothole, creating a spotlight on the witch's workbench. "
            "Earthy palette: bark brown, moss green, amber liquid, and purple potion accents."
        ),
        "display_name_en": "Baobab Apothecary",
        "display_name_zh": "猴面包树药铺",
        "description_en": "A witch's apothecary carved into a living baobab tree — glowing jars, root-channel floors, and knothole sunlight",
        "description_zh": "巫女的药铺开在活的猴面包树体内，发光药瓶嵌入木壁，树根形成地面的沟渠",
        "category": "fantasy",
        "tags": ["fantasy", "witch", "apothecary", "tree", "potion", "organic"],
        "style_keywords": ["organic architecture", "knothole spotlight", "earthy fantasy palette"],
        "difficulty": "intermediate",
        "use_count": 680,
        "like_count": 235,
        "favorite_count": 130,
    },
    {
        "prompt_text": (
            "A knight in tarnished silver armor kneeling before a sword embedded in a frozen lake, "
            "the ice around the blade cracked in a radial starburst pattern. "
            "The sword's pommel emits a faint pulse of white light visible through the ice below. "
            "A ring of dead winter trees surrounds the lake like silent witnesses. "
            "Heavy overcast sky presses low, with a single break in the clouds "
            "sending a shaft of pale light directly onto the sword. "
            "Desaturated palette of steel, ice-blue, and dead-wood gray with only the sword-glow as warmth."
        ),
        "display_name_en": "Sword in Frozen Lake",
        "display_name_zh": "冰湖圣剑",
        "description_en": "A knight kneels before a glowing sword frozen in a shattered lake — pale light from a single break in winter clouds",
        "description_zh": "骑士跪在冰冻湖面的发光圣剑前，冰面呈放射状碎裂，云层唯一的缺口投下光柱",
        "category": "fantasy",
        "tags": ["fantasy", "knight", "sword", "frozen-lake", "quest", "winter"],
        "style_keywords": ["radial crack pattern", "single cloud-break light", "desaturated with glow"],
        "difficulty": "intermediate",
        "use_count": 750,
        "like_count": 270,
        "favorite_count": 150,
    },
    {
        "prompt_text": (
            "A colossal stone golem slowly standing up from a hillside, "
            "trees and meadow grass still growing on its back and shoulders. "
            "As it rises, soil cascades from its joints and a waterfall "
            "that was flowing down the hill now pours from its elbow. "
            "A shepherd and flock scatter in the foreground, tiny against the golem's knee. "
            "Afternoon sun backlights the falling soil into a golden haze. "
            "The golem's face is barely distinguishable — two dark caves for eyes, "
            "a cliff-edge jaw covered in moss."
        ),
        "display_name_en": "Waking Golem",
        "display_name_zh": "苏醒的巨像",
        "description_en": "A hillside reveals itself as a colossal golem — trees on its back, a waterfall pouring from its elbow as it rises",
        "description_zh": "山丘竟是沉睡的巨石像，苏醒时树木仍长在背上，瀑布从肘关节倾泻而下",
        "category": "fantasy",
        "tags": ["fantasy", "golem", "colossal", "nature-creature", "awakening"],
        "style_keywords": ["scale revelation", "nature-camouflage creature", "backlit cascade"],
        "difficulty": "intermediate",
        "use_count": 620,
        "like_count": 225,
        "favorite_count": 125,
    },
    {
        "prompt_text": (
            "A celestial forge suspended in outer space, anvil floating among nebulae, "
            "a divine blacksmith hammering a new star into shape. "
            "Each hammer strike sends sparks that become smaller stars scattering outward. "
            "The forge's fire burns with the blue-white intensity of a supernova. "
            "The blacksmith is silhouetted — muscular form wreathed in star-fire. "
            "Surrounding nebula clouds glow in deep magenta and teal. "
            "Constellations are visible in the background, some incomplete, awaiting new stars."
        ),
        "display_name_en": "Celestial Forge",
        "display_name_zh": "星辰锻造",
        "description_en": "A divine blacksmith forging new stars on a cosmic anvil — each hammer-strike scatters sparks that become constellations",
        "description_zh": "神圣铁匠在宇宙铁砧上锻造新星，每一锤击散出的火花成为新的星座",
        "category": "fantasy",
        "tags": ["fantasy", "cosmic", "forge", "stars", "divine", "nebula"],
        "style_keywords": ["cosmic scale", "silhouette against fire", "star-birth sparks"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 170,
        "favorite_count": 92,
    },
    {
        "prompt_text": (
            "A steampunk airship docked at a cliff-side port, "
            "its brass hull gleaming in the setting sun, "
            "propellers still turning slowly as steam vents hiss from the engine nacelles. "
            "Dock workers in leather aprons haul crates on pulley systems. "
            "The port is a series of wooden platforms and rope bridges "
            "bolted into the cliff face with massive iron rivets. "
            "Below, clouds fill the valley floor like a cotton sea. "
            "Warm brass, weathered wood, and iron-gray against a coral sunset sky."
        ),
        "display_name_en": "Cliff Port Airship",
        "display_name_zh": "悬崖港飞艇",
        "description_en": "Steampunk airship at a cliff-side dock — brass hull, hissing steam, dock workers above a sea of valley clouds",
        "description_zh": "蒸汽朋克飞艇停靠悬崖港口，黄铜船体在夕阳中闪耀，脚下云海翻涌",
        "category": "fantasy",
        "tags": ["fantasy", "steampunk", "airship", "cliff-port", "dock", "sunset"],
        "style_keywords": ["steampunk industrial", "cliff-edge verticality", "cloud-sea below"],
        "difficulty": "beginner",
        "use_count": 980,
        "like_count": 335,
        "favorite_count": 185,
    },
    {
        "prompt_text": (
            "A haunted greenhouse at midnight — glass panes cracked and overgrown, "
            "spectral flowers blooming in impossible colors that no living plant produces: "
            "silver, deep black, translucent luminous white. "
            "A ghost gardener tends the plants with transparent hands, "
            "watering can pouring moonlight instead of water. "
            "The real moon is visible through the broken roof glass, full and cold. "
            "Palette of moonlight silver, glass-green, and deep shadow-black with spectral flower accents."
        ),
        "display_name_en": "Ghost Greenhouse",
        "display_name_zh": "幽灵温室",
        "description_en": "A spectral gardener tends impossible-colored flowers in a midnight greenhouse — watering can pours liquid moonlight",
        "description_zh": "幽灵园丁在午夜温室照料着现实中不存在的花色，洒水壶倒出的是液态月光",
        "category": "fantasy",
        "tags": ["fantasy", "ghost", "greenhouse", "moonlight", "spectral", "flowers"],
        "style_keywords": ["moonlight palette", "impossible colors", "spectral transparency"],
        "difficulty": "intermediate",
        "use_count": 560,
        "like_count": 200,
        "favorite_count": 110,
    },
    {
        "prompt_text": (
            "A map that is also a landscape — the parchment itself bends and folds into 3D terrain, "
            "ink-drawn mountain ranges rising as actual peaks, "
            "blue-ink rivers flowing with real water along their drawn channels. "
            "A miniature army marches along a marked road, "
            "each figure no larger than a chess piece. "
            "The map edges curl up to reveal the wooden table beneath. "
            "Quill and ink bottle sit at one corner, "
            "suggesting the cartographer's work has literally come to life."
        ),
        "display_name_en": "Living Map",
        "display_name_zh": "活地图",
        "description_en": "A map coming to life — ink mountains rise, drawn rivers flow, and miniature armies march along parchment roads",
        "description_zh": "地图活了过来——墨绘山脉隆起，蓝墨河流奔涌，微型军队沿着羊皮纸上的道路行军",
        "category": "fantasy",
        "tags": ["fantasy", "map", "miniature", "living-art", "cartography"],
        "style_keywords": ["2D-to-3D transition", "trompe l'oeil", "miniature scale"],
        "difficulty": "advanced",
        "use_count": 340,
        "like_count": 155,
        "favorite_count": 85,
    },
    {
        "prompt_text": (
            "A merfolk bazaar in a deep ocean trench, "
            "stalls built from coral and whale bones, lit by anglerfish lanterns "
            "and bioluminescent jellyfish strung like fairy lights. "
            "Merchants display pearl jewelry, seaweed textiles, and bottled currents. "
            "The trench walls rise on both sides, disappearing into dark water above. "
            "Bubbles rise from everywhere. "
            "A manta ray glides overhead like a living canopy. "
            "Cool deep-sea palette of indigo, teal, and pearl-white with anglerfish amber accents."
        ),
        "display_name_en": "Trench Bazaar",
        "display_name_zh": "深海集市",
        "description_en": "Deep-sea merfolk bazaar in an ocean trench — anglerfish lanterns, coral stalls, and a manta ray canopy overhead",
        "description_zh": "海沟中的人鱼集市——鮟鱇灯笼照亮珊瑚摊位，魔鬼鱼如穹顶般滑过头顶",
        "category": "fantasy",
        "tags": ["fantasy", "underwater", "merfolk", "bazaar", "deep-sea", "bioluminescent"],
        "style_keywords": ["deep-sea lighting", "bioluminescent market", "trench verticality"],
        "difficulty": "beginner",
        "use_count": 870,
        "like_count": 295,
        "favorite_count": 165,
    },
    {
        "prompt_text": (
            "A time-frozen battlefield where soldiers from different historical eras "
            "are caught mid-charge in a single frame — "
            "a Roman legionnaire, a medieval knight, a Napoleonic hussar, and a WWI soldier "
            "all suspended in motion, weapons raised, separated by visible temporal rifts "
            "that shimmer like heat haze with different color temperatures for each era. "
            "The ground itself shifts between cobblestone, mud, and grass across the rifts."
        ),
        "display_name_en": "Temporal Battlefield",
        "display_name_zh": "时间裂隙战场",
        "description_en": "A frozen battlefield where time rifts collide four eras — legionnaire, knight, hussar, and soldier in a single frame",
        "description_zh": "时间裂隙将四个时代的士兵定格在同一战场——罗马军团、中世纪骑士、拿破仑骑兵与一战步兵",
        "category": "fantasy",
        "tags": ["fantasy", "time-travel", "battlefield", "historical", "temporal-rift"],
        "style_keywords": ["temporal collage", "era-specific color temperature", "frozen motion"],
        "difficulty": "advanced",
        "use_count": 290,
        "like_count": 135,
        "favorite_count": 72,
    },
    {
        "prompt_text": (
            "A child stepping through a wardrobe into a snow-covered forest glade, "
            "one foot still on the bedroom carpet, the other sinking into fresh snow. "
            "Behind: warm yellow bedroom light, hanging coats, wooden hangers. "
            "Ahead: towering pines, softly falling snow, and a distant lamppost glowing warm. "
            "The wardrobe frame acts as a portal border between the two worlds. "
            "The child reaches forward, fingers just touching a snowflake. "
            "Color split: warm domestic amber behind, cool winter blue-white ahead."
        ),
        "display_name_en": "Wardrobe Threshold",
        "display_name_zh": "衣橱之门",
        "description_en": "A child steps through a wardrobe from warm bedroom into a snowy forest — one foot in each world",
        "description_zh": "孩子一脚踩在卧室地毯上，一脚踏入飘雪的森林，衣橱是两个世界的门框",
        "category": "fantasy",
        "tags": ["fantasy", "portal", "wardrobe", "snow", "childhood", "two-worlds"],
        "style_keywords": ["portal threshold", "warm-cold world split", "childhood wonder"],
        "difficulty": "beginner",
        "use_count": 1150,
        "like_count": 385,
        "favorite_count": 210,
    },
    {
        "prompt_text": (
            "A colossal stone golem kneels in a shallow lake at dawn, water reaching its waist, "
            "moss and wildflowers growing in every crack of its granite body. "
            "One massive hand rests palm-up on the surface, cradling a small wooden fishing boat "
            "where a lone fisherman casts his line as if nothing were unusual. "
            "Morning mist curls around the golem's shoulders and wraps through its hollow eye sockets "
            "where warm amber light glows faintly from within. "
            "Herons perch along its forearm. Mountains rise in blue-grey layers behind."
        ),
        "display_name_en": "The Gentle Colossus",
        "display_name_zh": "温柔巨像",
        "description_en": "A moss-covered stone golem kneels in a dawn lake, cradling a fisherman's boat in its open palm — herons on its arm, amber light in its hollow eyes",
        "description_zh": "苔藓覆盖的石像跪在晨雾弥漫的浅湖中，摊开的巨掌托着一叶渔舟，空洞的眼窝透出琥珀微光",
        "category": "fantasy",
        "tags": ["fantasy", "golem", "giant", "dawn-lake", "moss", "coexistence"],
        "style_keywords": ["monumental scale contrast", "nature-reclaimed stone", "misty dawn atmosphere"],
        "difficulty": "advanced",
        "use_count": 780,
        "like_count": 265,
        "favorite_count": 150,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  GRAPHIC DESIGN (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "A synthwave poster with a chrome-text title floating above a neon grid plane "
            "that stretches to a glowing sunset horizon of hot pink and electric purple. "
            "A DeLorean silhouette drives along the grid toward the sunset. "
            "Palm tree silhouettes flank the sides. "
            "VHS scan lines and chromatic aberration artifacts overlay the entire image. "
            "The grid squares glow brighter near the horizon line. "
            "Palette strictly limited to hot pink, electric purple, cyan, and chrome silver."
        ),
        "display_name_en": "Synthwave Grid Rider",
        "display_name_zh": "合成波骑行",
        "description_en": "Synthwave poster with chrome text, neon grid, and a DeLorean driving toward a hot-pink horizon",
        "description_zh": "合成波海报——铬字漂浮于霓虹网格上空，德劳瑞安驶向灼热粉色地平线",
        "category": "graphic-design",
        "tags": ["graphic-design", "synthwave", "retro", "neon", "80s", "poster"],
        "style_keywords": ["synthwave aesthetic", "neon grid", "VHS artifacts"],
        "difficulty": "beginner",
        "use_count": 1180,
        "like_count": 390,
        "favorite_count": 215,
    },
    {
        "prompt_text": (
            "Swiss international typographic poster — "
            "a strict 12-column grid with bold Akzidenz-Grotesk headlines flush left, "
            "a single red diagonal bar cutting across the lower third. "
            "Body text in a smaller weight, aligned to the fourth column baseline. "
            "The entire composition uses only black, white, and signal red. "
            "Generous white space around the type block. "
            "A small geometric circle in the upper-right corner acts as a visual counterweight."
        ),
        "display_name_en": "Swiss Grid Poster",
        "display_name_zh": "瑞士网格海报",
        "description_en": "Strict Swiss-style typographic poster — 12-column grid, flush-left Grotesk, and a single red diagonal slash",
        "description_zh": "严格的瑞士国际主义字体海报——12栏网格、左齐无衬线体与一道红色斜杠",
        "category": "graphic-design",
        "tags": ["graphic-design", "swiss-style", "typography", "grid", "modernist"],
        "style_keywords": ["Swiss International Style", "12-column grid", "signal red accent"],
        "difficulty": "intermediate",
        "use_count": 520,
        "like_count": 185,
        "favorite_count": 100,
    },
    {
        "prompt_text": (
            "A glassmorphism UI card floating over a blurred gradient background "
            "of soft purple and peach. "
            "The card has a frosted-glass effect with visible white border at 50% opacity, "
            "subtle inner shadow, and a slight drop shadow behind. "
            "Inside the card: a weather widget showing temperature, cloud icon, and location text "
            "in a clean sans-serif typeface. "
            "Two smaller frosted-glass pills float nearby showing secondary information. "
            "The overall feel is airy, modern, and translucent."
        ),
        "display_name_en": "Glassmorphism Weather",
        "display_name_zh": "玻璃态天气卡片",
        "description_en": "Frosted-glass UI weather card floating over a purple-peach gradient — airy glassmorphism at its most refined",
        "description_zh": "毛玻璃质感天气卡片悬浮于紫桃渐变背景上，通透的玻璃态设计",
        "category": "graphic-design",
        "tags": ["graphic-design", "glassmorphism", "UI", "weather", "modern"],
        "style_keywords": ["glassmorphism", "frosted blur", "gradient background"],
        "difficulty": "beginner",
        "use_count": 950,
        "like_count": 315,
        "favorite_count": 175,
    },
    {
        "prompt_text": (
            "A Bauhaus-inspired poster composed of three overlapping geometric shapes — "
            "a red circle, yellow triangle, and blue square — "
            "each printed with slight misregistration like a risograph print. "
            "Where shapes overlap, the colors mix additively. "
            "Background is off-white kraft paper with visible fiber texture. "
            "A single line of DIN typeface at the bottom in black. "
            "The composition follows the golden ratio for shape placement."
        ),
        "display_name_en": "Bauhaus Riso Print",
        "display_name_zh": "包豪斯印刷",
        "description_en": "Bauhaus primary shapes printed with risograph misregistration on kraft paper — circle, triangle, square overlapping",
        "description_zh": "包豪斯三原色几何图形以利索印刷的套色偏移效果叠印在牛皮纸上",
        "category": "graphic-design",
        "tags": ["graphic-design", "bauhaus", "risograph", "geometric", "primary-colors"],
        "style_keywords": ["Bauhaus geometry", "risograph offset", "kraft paper texture"],
        "difficulty": "beginner",
        "use_count": 780,
        "like_count": 260,
        "favorite_count": 145,
    },
    {
        "prompt_text": (
            "A concert poster for a fictional jazz quartet, "
            "rendered in torn-paper collage style with layered cutouts "
            "forming a saxophonist's silhouette from fragments of sheet music, "
            "old newspaper, and colored construction paper. "
            "The background is deep navy. "
            "Type is set in a hand-lettered brush script at the top, "
            "with venue details in a condensed sans-serif at the bottom. "
            "Color accents of mustard yellow and burnt sienna against the navy."
        ),
        "display_name_en": "Jazz Collage Poster",
        "display_name_zh": "爵士拼贴海报",
        "description_en": "Torn-paper collage jazz poster — a saxophonist's silhouette assembled from sheet music and newspaper fragments",
        "description_zh": "撕纸拼贴爵士海报——萨克斯手剪影由乐谱、旧报纸与彩色纸片拼合而成",
        "category": "graphic-design",
        "tags": ["graphic-design", "collage", "jazz", "poster", "torn-paper"],
        "style_keywords": ["torn-paper collage", "silhouette assembly", "hand-lettered type"],
        "difficulty": "intermediate",
        "use_count": 540,
        "like_count": 190,
        "favorite_count": 105,
    },
    {
        "prompt_text": (
            "A bold typographic composition where the word 'BREATHE' is set in an ultra-heavy sans-serif, "
            "each letter a different pastel color — lavender, mint, peach, sky blue, butter yellow. "
            "The letters are tightly kerned so they overlap slightly. "
            "A single green vine illustration weaves through the letter forms, "
            "entering the B and exiting the E with small leaves. "
            "Pure white background, generous margins. "
            "The overall effect is calming, intentional, and poster-ready."
        ),
        "display_name_en": "BREATHE Typography",
        "display_name_zh": "深呼吸字体艺术",
        "description_en": "The word BREATHE in pastel heavy type with a vine weaving through the letters — calming graphic minimalism",
        "description_zh": "BREATHE一词以柔和粉彩粗体排列，一根藤蔓穿梭于字母之间，宁静的图形极简",
        "category": "graphic-design",
        "tags": ["graphic-design", "typography", "pastel", "botanical", "poster", "calm"],
        "style_keywords": ["heavy type", "botanical integration", "pastel palette"],
        "difficulty": "beginner",
        "use_count": 870,
        "like_count": 290,
        "favorite_count": 160,
    },
    {
        "prompt_text": (
            "A vaporwave aesthetic composition — a Greek marble bust floating in a pink void, "
            "scanlines running horizontally across the image, "
            "a palm tree rendered in teal duotone behind the bust. "
            "Japanese katakana text runs vertically on the right margin in hot pink. "
            "A pixelated sunset gradient fills the background from magenta to cyan. "
            "Windows 95-era dialog boxes and error messages scatter across the lower portion. "
            "The overall palette is pink, teal, purple, and white."
        ),
        "display_name_en": "Vaporwave Bust",
        "display_name_zh": "蒸汽波石膏像",
        "description_en": "Classic vaporwave — Greek bust in pink void with scanlines, teal palm, and Windows 95 dialog artifacts",
        "description_zh": "经典蒸汽波——粉色虚空中的希腊石膏胸像，扫描线、青绿棕榈与Win95弹窗",
        "category": "graphic-design",
        "tags": ["graphic-design", "vaporwave", "retro", "aesthetic", "bust", "glitch"],
        "style_keywords": ["vaporwave aesthetic", "scanline overlay", "duotone palm"],
        "difficulty": "beginner",
        "use_count": 1050,
        "like_count": 345,
        "favorite_count": 190,
    },
    {
        "prompt_text": (
            "An editorial magazine spread layout — left page shows a full-bleed photograph "
            "of ocean waves in desaturated blue, right page has a large drop-cap 'T' "
            "in a bold serif typeface starting the body text. "
            "A thin rule separates the headline from the body. "
            "Pull quote in italic set in the right margin at one-third height. "
            "The overall design follows a strict baseline grid with 10pt leading. "
            "Color palette: ocean blue, charcoal text, cream paper stock."
        ),
        "display_name_en": "Editorial Ocean Spread",
        "display_name_zh": "海洋编辑版式",
        "description_en": "Editorial magazine spread — full-bleed ocean photograph facing a typographically precise text layout",
        "description_zh": "杂志编辑版式——全出血海浪照片对页精确排版的文字布局，严格基线网格",
        "category": "graphic-design",
        "tags": ["graphic-design", "editorial", "layout", "magazine", "typography"],
        "style_keywords": ["editorial layout", "baseline grid", "full-bleed photography"],
        "difficulty": "intermediate",
        "use_count": 430,
        "like_count": 155,
        "favorite_count": 85,
    },
    {
        "prompt_text": (
            "An abstract gradient poster where concentric circles radiate outward "
            "from the lower-left corner, each ring a slightly different hue "
            "shifting from deep violet in the center through magenta, coral, to warm amber "
            "at the outermost ring. "
            "The rings have varying thicknesses — some hairline, some bold. "
            "Subtle grain texture overlays the entire surface. "
            "No text, purely visual — the kind of poster that works as both art and design object."
        ),
        "display_name_en": "Gradient Ring Poster",
        "display_name_zh": "渐变光环海报",
        "description_en": "Abstract gradient poster — concentric rings shifting from violet through coral to amber, pure visual rhythm",
        "description_zh": "抽象渐变海报——同心圆环从紫罗兰经珊瑚色渐变至琥珀色，纯视觉节奏",
        "category": "graphic-design",
        "tags": ["graphic-design", "abstract", "gradient", "concentric", "poster-art"],
        "style_keywords": ["concentric gradient", "grain overlay", "chromatic shift"],
        "difficulty": "intermediate",
        "use_count": 580,
        "like_count": 200,
        "favorite_count": 110,
    },
    {
        "prompt_text": (
            "A paper-cut layered illustration of a forest scene with five visible layers of depth — "
            "foreground ferns in dark green, mid-ground tree trunks in medium green, "
            "background hills in pale sage, and a sky layer in soft apricot. "
            "Each layer casts a real shadow onto the layer behind, "
            "confirming the physical paper-cut construction. "
            "A deer silhouette stands on the third layer. "
            "The shadow gaps between layers create a sense of theatrical depth."
        ),
        "display_name_en": "Paper-Cut Forest Layers",
        "display_name_zh": "纸雕森林",
        "description_en": "Five-layer paper-cut forest with real shadows between each plane — theatrical depth from simple flat shapes",
        "description_zh": "五层纸雕森林，每层之间的真实阴影营造出舞台般的纵深感",
        "category": "graphic-design",
        "tags": ["graphic-design", "paper-cut", "layered", "forest", "shadow-depth"],
        "style_keywords": ["paper-cut layers", "shadow depth", "flat-to-3D illusion"],
        "difficulty": "intermediate",
        "use_count": 620,
        "like_count": 215,
        "favorite_count": 118,
    },
    {
        "prompt_text": (
            "A duotone portrait poster — a woman's face processed in high contrast, "
            "then printed in overlapping halftone dots of teal and magenta. "
            "Where the two inks overlap, a rich near-black forms. "
            "Where only one ink prints, the skin reads as either cool or warm. "
            "Headline text in a compressed grotesque typeface runs vertically along the right edge. "
            "The background is unprinted paper showing through in the highlights. "
            "Overall mood is bold, graphic, and distinctly print-culture."
        ),
        "display_name_en": "Duotone Halftone Portrait",
        "display_name_zh": "双色调半色调肖像",
        "description_en": "Duotone halftone portrait in teal and magenta — overlapping dots create a rich print-culture aesthetic",
        "description_zh": "青色与品红半色调网点叠印的肖像海报，两色交汇处形成浓郁的印刷文化美感",
        "category": "graphic-design",
        "tags": ["graphic-design", "duotone", "halftone", "portrait", "print-culture"],
        "style_keywords": ["duotone halftone", "teal-magenta ink", "print-culture aesthetic"],
        "difficulty": "advanced",
        "use_count": 350,
        "like_count": 150,
        "favorite_count": 82,
    },
    {
        "prompt_text": (
            "A brand identity mockup showing business cards, letterhead, and envelope "
            "arranged on a concrete surface with controlled overhead lighting. "
            "The brand uses a monogram logo — two overlapping geometric letters in a circle. "
            "Color system: charcoal, warm white, and a single accent of burnt copper. "
            "Business cards show front and back, one leaning against a small concrete block. "
            "The design is austere and confident, with generous white space. "
            "Embossed logo is visible catching side light on the letterhead."
        ),
        "display_name_en": "Copper Accent Identity",
        "display_name_zh": "铜色品牌识别",
        "description_en": "Minimalist brand identity mockup on concrete — charcoal and warm white with embossed copper-accent monogram",
        "description_zh": "混凝土面上的极简品牌识别样机——碳灰与暖白底色，压印铜色字母组合标志",
        "category": "graphic-design",
        "tags": ["graphic-design", "brand-identity", "mockup", "monogram", "copper"],
        "style_keywords": ["brand identity system", "emboss detail", "copper metallic accent"],
        "difficulty": "intermediate",
        "use_count": 490,
        "like_count": 175,
        "favorite_count": 95,
    },
    {
        "prompt_text": (
            "An infographic showing the water cycle as a vertical circular flow diagram. "
            "Icons for evaporation, condensation, precipitation, and collection "
            "are connected by curved arrows in a clockwise loop. "
            "Each stage uses a different shade of blue — from pale sky to deep ocean. "
            "Small illustrated vignettes inside each icon show the process in miniature. "
            "Clean sans-serif labels, left-aligned. "
            "Background is a subtle topographic contour pattern in very light gray."
        ),
        "display_name_en": "Water Cycle Infographic",
        "display_name_zh": "水循环信息图",
        "description_en": "Vertical circular infographic of the water cycle — four blue shades flow clockwise with illustrated vignettes",
        "description_zh": "水循环的纵向环形信息图——四种蓝色调顺时针流动，每个阶段配有微缩插画",
        "category": "graphic-design",
        "tags": ["graphic-design", "infographic", "water-cycle", "educational", "diagram"],
        "style_keywords": ["circular flow diagram", "blue shade progression", "icon vignettes"],
        "difficulty": "beginner",
        "use_count": 720,
        "like_count": 240,
        "favorite_count": 132,
    },
    {
        "prompt_text": (
            "A psychedelic concert poster with a central mandala pattern "
            "radiating outward in spiraling petals of orange, magenta, electric green, and violet. "
            "Band name lettering morphs into the pattern — "
            "the letters themselves are organic, flowing shapes that merge with the mandala. "
            "Background shifts from dark purple at the edges to bright center. "
            "Thick, uneven ink lines suggest screen-printed production. "
            "Small venue text in a contrasting geometric sans-serif at the bottom."
        ),
        "display_name_en": "Psychedelic Mandala Poster",
        "display_name_zh": "迷幻曼陀罗海报",
        "description_en": "Psychedelic concert poster where band lettering melts into a spiraling mandala of electric colors",
        "description_zh": "迷幻演唱会海报——乐队名字融入螺旋曼陀罗图案，荧光色系旋转绽放",
        "category": "graphic-design",
        "tags": ["graphic-design", "psychedelic", "mandala", "concert", "screen-print"],
        "style_keywords": ["psychedelic mandala", "organic lettering", "screen-print ink"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 165,
        "favorite_count": 90,
    },
    {
        "prompt_text": (
            "A set of four app icon concepts displayed on a soft gradient background, "
            "each icon occupying a rounded-square frame with distinct visual language — "
            "one uses negative space to form a bird, another is a gradient abstract wave, "
            "the third is a geometric monogram, the fourth a simple glyph. "
            "All four share a unified color system of coral, navy, and cream. "
            "Subtle long shadows on each icon. "
            "Clean grid alignment with equal spacing between all four icons."
        ),
        "display_name_en": "App Icon System",
        "display_name_zh": "应用图标体系",
        "description_en": "Four app icon concepts sharing a coral-navy-cream system — negative space, gradient, monogram, and glyph approaches",
        "description_zh": "四种应用图标概念共享珊瑚-海军蓝-奶油色体系——负空间、渐变、字母组合与符号",
        "category": "graphic-design",
        "tags": ["graphic-design", "app-icon", "UI", "icon-system", "branding"],
        "style_keywords": ["icon system", "unified color language", "rounded-square frames"],
        "difficulty": "beginner",
        "use_count": 830,
        "like_count": 275,
        "favorite_count": 152,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  FOOD (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "A single hand-pulled lamian noodle suspended in mid-air between two hands, "
            "flour dust frozen in motion against a dark kitchen background. "
            "The translucent dough catches backlight to reveal its thin, elastic structure. "
            "Below, a worn wooden counter dusted with flour anchors the frame. "
            "Shallow depth of field isolates the noodle strand "
            "while the cook's flour-covered forearms fade into soft focus on either side."
        ),
        "display_name_en": "Hand-Pulled Noodle Moment",
        "display_name_zh": "拉面的瞬间",
        "description_en": "Frozen-motion capture of hand-pulled noodle making with dramatic backlight revealing the dough's translucence",
        "description_zh": "逆光定格拉面瞬间，面条的弹性与面粉的飞扬凝固在空中",
        "category": "food",
        "tags": ["food", "noodle", "action-freeze", "craft", "backlight"],
        "style_keywords": ["frozen motion", "backlight translucency", "dark background"],
        "difficulty": "advanced",
        "use_count": 450,
        "like_count": 195,
        "favorite_count": 105,
    },
    {
        "prompt_text": (
            "Overhead shot of a rustic Italian Sunday lunch table — "
            "a large oval platter of hand-torn focaccia, bowls of olive oil with balsamic, "
            "a half-eaten caprese salad, scattered wine glasses with ruby remnants. "
            "Hands reach in from multiple sides of the frame, mid-gesture: pouring, tearing, gesturing. "
            "White linen tablecloth with natural creases and wine stains. "
            "Harsh afternoon sun from the upper-left casting sharp shadows of glasses and bottles. "
            "Colors: tomato red, basil green, olive gold, white linen, wine ruby."
        ),
        "display_name_en": "Italian Sunday Table",
        "display_name_zh": "意式周日午餐",
        "description_en": "Overhead Italian Sunday spread — reaching hands, torn focaccia, wine stains, and harsh afternoon sun",
        "description_zh": "意式周日午餐俯拍——伸入画面的手、撕裂的佛卡夏、酒渍与午后刺眼阳光",
        "category": "food",
        "tags": ["food", "italian", "overhead", "communal", "rustic", "sunday"],
        "style_keywords": ["communal hands-in", "harsh sunlight", "lived-in styling"],
        "difficulty": "beginner",
        "use_count": 1100,
        "like_count": 365,
        "favorite_count": 200,
    },
    {
        "prompt_text": (
            "A single perfect macaron cut in half, revealing the filling layer — "
            "the cut surface showing the delicate shell, thin feet, and ganache center. "
            "Shot at eye level on a marble slab. "
            "One half leans against the other. "
            "Soft diffused light from above with a subtle warm gradient. "
            "A light dusting of powdered sugar on the marble around the base. "
            "Background is a smooth dove-gray gradient. "
            "The macaron shell is pistachio green with a dark chocolate ganache filling."
        ),
        "display_name_en": "Macaron Cross-Section",
        "display_name_zh": "马卡龙剖面",
        "description_en": "A pistachio macaron split to reveal its architecture — shell, feet, and ganache in exquisite cross-section",
        "description_zh": "开心果马卡龙一分为二，酥壳、裙边与甘纳许内馅的精致剖面",
        "category": "food",
        "tags": ["food", "macaron", "cross-section", "pastry", "detail"],
        "style_keywords": ["cross-section reveal", "eye-level macro", "diffused top light"],
        "difficulty": "beginner",
        "use_count": 950,
        "like_count": 320,
        "favorite_count": 175,
    },
    {
        "prompt_text": (
            "Dark moody still life of aged cheese wheels on a slate board — "
            "a wedge cut from the largest wheel reveals amber paste and blue veining. "
            "Accompaniments arranged deliberately: fig halves, honeycomb with dripping honey, "
            "walnuts, and dried apricots. "
            "A single overhead spot creates a pool of light on the cheese, "
            "leaving the surrounding table in deep shadow. "
            "Rembrandt-inspired chiaroscuro food styling. "
            "Palette of amber, slate gray, fig purple, and honey gold."
        ),
        "display_name_en": "Cheese Board Chiaroscuro",
        "display_name_zh": "奶酪板明暗法",
        "description_en": "Dark moody cheese board in Rembrandt lighting — amber paste, blue veins, and honey catching a single spotlight",
        "description_zh": "伦勃朗式光影下的奶酪拼盘——琥珀色酪体、蓝色脉纹与蜂蜜在聚光灯下闪耀",
        "category": "food",
        "tags": ["food", "cheese", "dark-mood", "chiaroscuro", "still-life"],
        "style_keywords": ["Rembrandt food lighting", "dark mood", "deliberate styling"],
        "difficulty": "intermediate",
        "use_count": 680,
        "like_count": 235,
        "favorite_count": 128,
    },
    {
        "prompt_text": (
            "A street food vendor's cart in Bangkok at dusk, shot at customer's-eye-level. "
            "A wok flames high over a charcoal burner, pad thai noodles tossed mid-air. "
            "The vendor's face is partially lit by the wok fire from below. "
            "String lights and hand-painted signage frame the cart. "
            "Steam and smoke diffuse the background into warm haze. "
            "A plate of finished pad thai sits on the narrow counter in the foreground. "
            "Colors: wok-fire orange, noodle gold, lime green garnish, warm night haze."
        ),
        "display_name_en": "Wok Fire Street Cart",
        "display_name_zh": "锅气夜市",
        "description_en": "Bangkok street wok at dusk — noodles tossed mid-air above flames, vendor's face lit from the fire below",
        "description_zh": "曼谷黄昏街头铁锅——面条在火焰上方翻飞，锅下火光映照摊主的面庞",
        "category": "food",
        "tags": ["food", "street-food", "bangkok", "wok", "action", "night"],
        "style_keywords": ["wok-fire under-light", "tossed food action", "street atmosphere"],
        "difficulty": "intermediate",
        "use_count": 590,
        "like_count": 210,
        "favorite_count": 115,
    },
    {
        "prompt_text": (
            "A line of five cocktails arranged in chromatic order from clear to deep red — "
            "gin rickey, french 75, aperol spritz, negroni, and boulevardier. "
            "Each glass is a different classic shape matching its cocktail. "
            "Backlit against a warm amber bar-back with blurred bottle silhouettes. "
            "Condensation beads on each glass catch individual highlights. "
            "A long bar counter of dark walnut stretches beneath. "
            "The lighting is theatrical — each cocktail its own stage."
        ),
        "display_name_en": "Cocktail Chromatic Line",
        "display_name_zh": "鸡尾酒色谱",
        "description_en": "Five classic cocktails in chromatic order — clear to deep red — each glass backlit in its own theatrical spotlight",
        "description_zh": "五杯经典鸡尾酒按色谱排列——从透明到深红，逆光中每杯都是自己的舞台",
        "category": "food",
        "tags": ["food", "cocktail", "chromatic", "bar", "backlit", "lineup"],
        "style_keywords": ["chromatic gradient lineup", "bar backlight", "condensation detail"],
        "difficulty": "intermediate",
        "use_count": 520,
        "like_count": 185,
        "favorite_count": 100,
    },
    {
        "prompt_text": (
            "Japanese kaiseki course plated on a black lacquer tray — "
            "five small dishes arranged according to traditional placement rules. "
            "Sashimi on a leaf, tempura on handmade paper, "
            "a clear dashi soup in a covered bowl with the lid placed beside it. "
            "Each dish is a study in restraint — two or three elements, maximum. "
            "Soft diffused overhead light, no harsh shadows. "
            "The tray sits on a tatami surface. "
            "Palette: black lacquer, wasabi green, fish-pink, soup-gold, leaf-green, cream."
        ),
        "display_name_en": "Kaiseki Five Plates",
        "display_name_zh": "怀石五品",
        "description_en": "Kaiseki course on black lacquer — five restrained dishes arranged by tradition, each a study in elegant simplicity",
        "description_zh": "黑漆托盘上的怀石料理五品——每道菜仅两三种元素，极简中的极致讲究",
        "category": "food",
        "tags": ["food", "kaiseki", "japanese", "fine-dining", "minimal", "traditional"],
        "style_keywords": ["kaiseki restraint", "black lacquer contrast", "traditional placement"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 165,
        "favorite_count": 90,
    },
    {
        "prompt_text": (
            "A sourdough bread loaf just out of the oven, placed on a wire cooling rack. "
            "The crust is deeply caramelized with a pattern of ear scoring. "
            "A cloud of steam rises from a fresh cut revealing the open, airy crumb inside. "
            "Flour dust on the dark wooden counter catches raking window light. "
            "The cross-section shows large irregular holes — signs of proper fermentation. "
            "A linen bread cloth and a serrated knife sit nearby. "
            "Warm palette: crust mahogany, crumb cream, flour white, wood brown."
        ),
        "display_name_en": "Sourdough Crumb Reveal",
        "display_name_zh": "酸种面包切面",
        "description_en": "Fresh sourdough split open to reveal its airy crumb — steam rising, crust deeply caramelized, flour catching light",
        "description_zh": "新出炉酸种面包的切面——热气升腾，焦糖色外壳下是大气孔的松软内心",
        "category": "food",
        "tags": ["food", "sourdough", "bread", "crumb", "baking", "artisan"],
        "style_keywords": ["crumb reveal", "steam capture", "raking flour light"],
        "difficulty": "beginner",
        "use_count": 1050,
        "like_count": 350,
        "favorite_count": 195,
    },
    {
        "prompt_text": (
            "An ice cream cone at the exact moment of melting — "
            "a scoop of strawberry ice cream tilting dangerously on a waffle cone, "
            "a single pink drip running down the side. "
            "The background is a hot summer sky, pure cerulean blue. "
            "A child's hand holds the cone from below, fingers sticky. "
            "Bright direct sunlight creates harsh shadows and makes the ice cream glisten. "
            "Frozen in time: the drip, the tilt, the impending collapse. "
            "Saturated palette: strawberry pink, cone brown, sky blue, skin warmth."
        ),
        "display_name_en": "Melting Moment",
        "display_name_zh": "融化的瞬间",
        "description_en": "An ice cream cone frozen at the tipping point — one drip, one tilt, and a summer sky behind",
        "description_zh": "冰淇淋球在崩塌临界点的定格——一滴粉色融液、一个危险倾斜、一片夏日蓝天",
        "category": "food",
        "tags": ["food", "ice-cream", "summer", "melting", "frozen-moment"],
        "style_keywords": ["decisive moment", "harsh summer sun", "saturated primaries"],
        "difficulty": "beginner",
        "use_count": 1200,
        "like_count": 395,
        "favorite_count": 218,
    },
    {
        "prompt_text": (
            "Macro shot of chocolate being tempered — "
            "a palette knife spreading glossy melted dark chocolate across a marble slab, "
            "creating thin sheets that curl at the edges as they cool. "
            "The chocolate surface has a mirror-like sheen reflecting the overhead lights. "
            "Fine details: air bubbles, tempering lines, and the beginning of crystallization "
            "visible as a subtle matte bloom at the thinnest edges. "
            "Warm studio light from above, cool marble surface beneath."
        ),
        "display_name_en": "Chocolate Tempering",
        "display_name_zh": "巧克力调温",
        "description_en": "Macro tempering study — dark chocolate spreads mirror-glossy on marble, crystallization bloom at the thinnest edges",
        "description_zh": "巧克力调温微距——黑巧在大理石上展开镜面般的光泽，最薄处结晶的哑光初现",
        "category": "food",
        "tags": ["food", "chocolate", "tempering", "macro", "craft", "technique"],
        "style_keywords": ["macro texture", "mirror sheen", "crystallization detail"],
        "difficulty": "advanced",
        "use_count": 330,
        "like_count": 150,
        "favorite_count": 82,
    },
    {
        "prompt_text": (
            "An autumn harvest table seen from a low angle at one end — "
            "the table stretches into the distance under a canopy of string lights in a garden. "
            "Pumpkins, gourds, and autumn leaves serve as centerpieces. "
            "Place settings for twenty with linen napkins and rustic ceramic plates. "
            "Candles in glass holders provide warm pools of light along the length. "
            "The last light of dusk is visible in the sky above the garden wall. "
            "Earthy autumnal palette: pumpkin orange, burgundy, sage, cream, candlelight gold."
        ),
        "display_name_en": "Harvest Table Garden",
        "display_name_zh": "花园丰收长桌",
        "description_en": "Twenty-seat harvest table under garden string lights — pumpkins, candles, and dusk sky stretching to the vanishing point",
        "description_zh": "花园灯串下二十人的丰收长桌——南瓜、烛光与暮色天空延伸至消失点",
        "category": "food",
        "tags": ["food", "harvest", "table-setting", "autumn", "garden", "communal"],
        "style_keywords": ["low-angle vanishing point", "string light warmth", "autumnal styling"],
        "difficulty": "intermediate",
        "use_count": 620,
        "like_count": 215,
        "favorite_count": 118,
    },
    {
        "prompt_text": (
            "A tea ceremony moment — matcha being whisked in a chawan bowl, "
            "the bamboo chasen creating a spiral pattern of foam on the bright green surface. "
            "Shot from above at a slight angle. "
            "The chawan sits on a dark slate stone. "
            "A single wagashi sweet on a small plate sits to the side — "
            "pale pink, shaped like a cherry blossom. "
            "Steam rises in a gentle wisp. "
            "Muted palette: matcha green, slate gray, cherry-blossom pink, bamboo tan."
        ),
        "display_name_en": "Matcha Whisk Spiral",
        "display_name_zh": "茶筅旋涡",
        "description_en": "Matcha being whisked into a foam spiral — the bamboo chasen mid-motion, a pink wagashi waiting beside",
        "description_zh": "茶筅在抹茶中搅出泡沫旋涡，一旁的樱花和菓子静静等候",
        "category": "food",
        "tags": ["food", "matcha", "tea-ceremony", "japanese", "whisk", "zen"],
        "style_keywords": ["spiral foam pattern", "overhead angle", "zen simplicity"],
        "difficulty": "beginner",
        "use_count": 880,
        "like_count": 295,
        "favorite_count": 162,
    },
    {
        "prompt_text": (
            "A baker's hands shaping croissant dough — "
            "flour-dusted fingers rolling the triangular sheet into its crescent form, "
            "the lamination layers visible at the cut edge showing alternating butter and dough. "
            "The work surface is stainless steel, professional kitchen setting. "
            "A tray of finished unbaked croissants sits in soft focus behind. "
            "Overhead fluorescent light, clinical and honest. "
            "The hands tell the story: experienced, efficient, flour in every crease."
        ),
        "display_name_en": "Croissant Lamination",
        "display_name_zh": "可颂开酥",
        "description_en": "Baker's hands shaping croissant dough — lamination layers visible, flour in every crease, clinical kitchen light",
        "description_zh": "面包师双手将可颂面团卷成月牙形，切面处黄油与面团的层层叠叠清晰可见",
        "category": "food",
        "tags": ["food", "croissant", "lamination", "baking", "hands", "craft"],
        "style_keywords": ["hands-at-work", "lamination cross-section", "clinical light"],
        "difficulty": "intermediate",
        "use_count": 560,
        "like_count": 195,
        "favorite_count": 108,
    },
    {
        "prompt_text": (
            "A spice market stall viewed from above — "
            "dozens of open burlap sacks arranged in a grid, "
            "each containing a different ground spice in vivid color: "
            "turmeric yellow, paprika red, cumin brown, cinnamon rust, "
            "cardamom green, saffron orange, black pepper gray. "
            "A brass scoop rests in one sack. "
            "Afternoon sunlight rakes across the sacks at a low angle, "
            "catching floating spice dust in golden shafts. "
            "The chromatic density is the subject — pure color as composition."
        ),
        "display_name_en": "Spice Market Mosaic",
        "display_name_zh": "香料市场色谱",
        "description_en": "Overhead spice market — burlap sacks in a grid of turmeric, paprika, saffron, and cardamom create a color mosaic",
        "description_zh": "俯瞰香料市场——麻袋以网格排列，姜黄、辣椒粉、藏红花与豆蔻构成色彩马赛克",
        "category": "food",
        "tags": ["food", "spice-market", "overhead", "color-grid", "ingredients"],
        "style_keywords": ["color-as-composition", "spice chromatics", "raking sunlight"],
        "difficulty": "beginner",
        "use_count": 920,
        "like_count": 305,
        "favorite_count": 170,
    },
    {
        "prompt_text": (
            "A dim sum bamboo steamer stack — three tiers open and staggered "
            "to reveal different dumplings: har gow (translucent shrimp), "
            "siu mai (open-top pork), and char siu bao (fluffy white buns). "
            "Steam billows from between the tiers. "
            "The steamers sit on a round marble table in a traditional Hong Kong cha chaan teng. "
            "Natural window light from the side. "
            "Tea in a small white cup and a dish of chili oil accompany the spread. "
            "Warm bamboo, translucent dumpling skin, and white steam dominate."
        ),
        "display_name_en": "Dim Sum Tower",
        "display_name_zh": "蒸笼叠塔",
        "description_en": "Three-tier dim sum reveal — har gow, siu mai, and char siu bao cascading steam in a Hong Kong tea house",
        "description_zh": "三层竹蒸笼错落打开——虾饺、烧卖与叉烧包在茶餐厅里蒸汽缭绕",
        "category": "food",
        "tags": ["food", "dim-sum", "steamer", "hong-kong", "dumplings", "steam"],
        "style_keywords": ["stacked reveal", "steam atmosphere", "traditional tea-house setting"],
        "difficulty": "beginner",
        "use_count": 1080,
        "like_count": 355,
        "favorite_count": 195,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  ABSTRACT (15)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Fluid acrylic pour art — deep ocean blue, metallic gold, and titanium white "
            "swirling together in organic cell patterns. "
            "The gold pigment has separated into thousands of tiny cells "
            "that form lace-like networks against the blue. "
            "The white creates bold rivulets cutting through the blue-gold interplay. "
            "The surface is glossy with a visible resin topcoat. "
            "Macro-close framing reveals individual cell walls and pigment density variation."
        ),
        "display_name_en": "Blue Gold Pour Cells",
        "display_name_zh": "蓝金流体细胞",
        "description_en": "Acrylic pour art macro — metallic gold separating into lace cells against deep ocean blue, white rivulets cutting through",
        "description_zh": "丙烯流体画微距——金属金在深海蓝中分离成蕾丝般的细胞网络，白色激流穿越其间",
        "category": "abstract",
        "tags": ["abstract", "fluid-art", "pour", "cells", "metallic", "macro"],
        "style_keywords": ["acrylic pour cells", "metallic pigment separation", "resin gloss"],
        "difficulty": "beginner",
        "use_count": 980,
        "like_count": 325,
        "favorite_count": 180,
    },
    {
        "prompt_text": (
            "A Rothko-inspired color field painting — two horizontal rectangles of color "
            "stacked vertically with a thin breathing space between them. "
            "The upper field is a deep, saturated cadmium red that seems to pulse with heat. "
            "The lower field is a cooler maroon with hints of violet at the edges. "
            "Edges between the fields are soft and feathered, never hard. "
            "The canvas shows through at the margins. "
            "The painting invites contemplation — it is not a picture of something, it is the something."
        ),
        "display_name_en": "Red Field Contemplation",
        "display_name_zh": "红色冥想",
        "description_en": "Rothko-inspired dual color field — pulsing cadmium red over cool maroon, edges soft, canvas breathing at the margins",
        "description_zh": "致敬罗斯科的双色域——灼热的镉红悬于冷暗栗色之上，边缘柔和，画布在留白处呼吸",
        "category": "abstract",
        "tags": ["abstract", "color-field", "rothko", "contemplative", "red"],
        "style_keywords": ["color field painting", "soft edge feathering", "chromatic vibration"],
        "difficulty": "beginner",
        "use_count": 750,
        "like_count": 250,
        "favorite_count": 140,
    },
    {
        "prompt_text": (
            "Ink dropped into water — the moment of impact captured at high speed, "
            "a mushroom cloud of black ink expanding in a glass tank of clear water. "
            "Tendrils spiral downward in fractal branching patterns. "
            "Backlit by a white light panel, the ink ranges from jet-black at the center "
            "to translucent gray at the expanding edges. "
            "The water's surface shows ripples from the drop entry point. "
            "Pure black and white with infinite gradations between."
        ),
        "display_name_en": "Ink Cloud Expansion",
        "display_name_zh": "墨云扩散",
        "description_en": "High-speed ink-in-water capture — a mushroom cloud of black tendrils spiraling through illuminated clarity",
        "description_zh": "高速捕捉墨水入水的瞬间——黑色蘑菇云在透明水体中展开分形螺旋",
        "category": "abstract",
        "tags": ["abstract", "ink-in-water", "high-speed", "fractal", "monochrome"],
        "style_keywords": ["high-speed capture", "fractal tendrils", "backlit transparency"],
        "difficulty": "intermediate",
        "use_count": 680,
        "like_count": 235,
        "favorite_count": 128,
    },
    {
        "prompt_text": (
            "A minimalist zen rock garden viewed from directly above — "
            "carefully raked white gravel forming concentric circles around three dark stones. "
            "Each stone is a different size and sits at a different position in the frame "
            "according to asymmetric balance principles. "
            "The rake lines are perfectly parallel except where they curve around the stones. "
            "No other elements — just white gravel, dark stone, and the geometry of raking. "
            "The photograph is nearly abstract, the subject nearly invisible as garden."
        ),
        "display_name_en": "Zen Gravel Geometry",
        "display_name_zh": "枯山水纹理",
        "description_en": "Overhead zen garden so abstracted it becomes pure geometry — white gravel circles, dark stones, and rake-line rhythm",
        "description_zh": "极度抽象化的枯山水俯瞰——白砾石同心圆、暗石与耙纹节奏构成纯粹几何",
        "category": "abstract",
        "tags": ["abstract", "zen", "rock-garden", "minimal", "overhead", "geometry"],
        "style_keywords": ["zen abstraction", "concentric geometry", "asymmetric balance"],
        "difficulty": "beginner",
        "use_count": 880,
        "like_count": 295,
        "favorite_count": 165,
    },
    {
        "prompt_text": (
            "Digital glitch art — a corrupted photograph of a sunset "
            "where pixel rows have been displaced, duplicated, and color-shifted. "
            "Horizontal bands of the original image are recognizable but scrambled. "
            "Some bands are stretched to single-pixel-height lines of pure color. "
            "The original sunset's orange and purple survive in fractured, "
            "rearranged form alongside glitch artifacts of cyan and magenta. "
            "Data moshing effects create fluid areas where adjacent frames blend."
        ),
        "display_name_en": "Sunset Data Corruption",
        "display_name_zh": "日落数据损坏",
        "description_en": "Glitch-art sunset — pixel displacement, color-shift, and data-moshing transform nature into digital abstraction",
        "description_zh": "故障艺术日落——像素位移、色彩偏移与数据弯折将自然转化为数字抽象",
        "category": "abstract",
        "tags": ["abstract", "glitch", "digital", "sunset", "data-mosh", "corruption"],
        "style_keywords": ["pixel displacement", "data moshing", "chromatic glitch"],
        "difficulty": "intermediate",
        "use_count": 560,
        "like_count": 195,
        "favorite_count": 108,
    },
    {
        "prompt_text": (
            "Macro photograph of soap film showing thin-film interference patterns — "
            "iridescent bands of color flowing across a membrane surface "
            "that is only nanometers thick. "
            "The colors shift from magenta through green to gold in Newton's rings pattern. "
            "The film's edge where it meets the wire frame is visible as a dark line. "
            "A point of light reflected in the film surface creates a white starburst. "
            "The background is pure black, making the film float in space."
        ),
        "display_name_en": "Soap Film Iridescence",
        "display_name_zh": "皂膜虹彩",
        "description_en": "Macro soap-film interference — iridescent color bands flowing across a nanometer-thin membrane against black void",
        "description_zh": "皂膜薄膜干涉的微距——虹彩色带在纳米薄膜上流动，纯黑背景中漂浮",
        "category": "abstract",
        "tags": ["abstract", "soap-film", "iridescence", "macro", "thin-film", "physics"],
        "style_keywords": ["thin-film interference", "Newton's rings", "iridescent spectrum"],
        "difficulty": "intermediate",
        "use_count": 480,
        "like_count": 175,
        "favorite_count": 95,
    },
    {
        "prompt_text": (
            "An enormous Kandinsky-inspired composition — "
            "geometric shapes floating in dynamic tension on a cream ground: "
            "a large blue circle overlapping a red diagonal bar, "
            "small yellow triangles scattered like musical notes, "
            "black curves connecting elements like a conductor's gestures. "
            "Each shape has its own internal texture — the circle has concentric rings, "
            "the bar has parallel hatching, the triangles are solid flat. "
            "The arrangement implies movement from lower-left to upper-right."
        ),
        "display_name_en": "Kandinsky Tension",
        "display_name_zh": "康定斯基张力",
        "description_en": "Kandinsky-inspired geometric abstraction — shapes in dynamic tension, each with distinct internal texture",
        "description_zh": "致敬康定斯基的几何抽象——形状在动态张力中浮动，每个图形有独特的内部纹理",
        "category": "abstract",
        "tags": ["abstract", "kandinsky", "geometric", "dynamic", "bauhaus", "primary"],
        "style_keywords": ["dynamic geometric tension", "internal texture variety", "Kandinsky composition"],
        "difficulty": "intermediate",
        "use_count": 520,
        "like_count": 185,
        "favorite_count": 100,
    },
    {
        "prompt_text": (
            "Light painting photograph — long exposure capturing a dancer's movement "
            "traced with LED wands in a pitch-black studio. "
            "The dancer is invisible; only the light trails remain, "
            "forming a spiraling human figure of overlapping amber, "
            "violet, and white ribbons of light. "
            "The trails have variable thickness from the dancer's speed changes. "
            "Where ribbons cross, they brighten additively. "
            "The figure hovers in pure black space, ethereal and kinetic."
        ),
        "display_name_en": "Light Dance Trace",
        "display_name_zh": "光舞轨迹",
        "description_en": "Light-painted dance figure — LED trails form a spiraling human shape in amber, violet, and white against pure black",
        "description_zh": "光绘舞蹈——LED轨迹在纯黑中勾勒出旋转的人形，琥珀、紫罗兰与白色光带交织",
        "category": "abstract",
        "tags": ["abstract", "light-painting", "dance", "long-exposure", "kinetic"],
        "style_keywords": ["light painting", "kinetic trace", "additive brightness"],
        "difficulty": "advanced",
        "use_count": 380,
        "like_count": 165,
        "favorite_count": 90,
    },
    {
        "prompt_text": (
            "Aerial photograph of salt evaporation ponds — "
            "rectangular pools in a geometric grid, each a different color "
            "depending on salinity and algae concentration: "
            "deep crimson, rust orange, jade green, milky turquoise, and cream white. "
            "Narrow earthen dikes separate the pools into a Mondrian-like composition. "
            "No horizon visible — the frame is filled entirely with the color grid. "
            "Photographed from high altitude, shadows of clouds dapple some pools."
        ),
        "display_name_en": "Salt Pond Mondrian",
        "display_name_zh": "盐田蒙德里安",
        "description_en": "Aerial salt evaporation ponds forming an accidental Mondrian — each pool a different hue from algae and salinity",
        "description_zh": "航拍盐蒸发池形成偶然的蒙德里安构图——每个池塘因盐度与藻类呈现不同色调",
        "category": "abstract",
        "tags": ["abstract", "aerial", "salt-ponds", "color-grid", "mondrian", "natural"],
        "style_keywords": ["aerial abstraction", "natural color grid", "Mondrian accident"],
        "difficulty": "beginner",
        "use_count": 720,
        "like_count": 245,
        "favorite_count": 135,
    },
    {
        "prompt_text": (
            "Smoke trails from extinguished incense sticks — "
            "three thin streams of smoke rising in parallel, then intertwining "
            "into complex helical patterns before dissipating. "
            "Side-lit against a pure black background, "
            "the smoke appears luminous silver-white. "
            "Slow shutter speed captures the full trajectory from stick to dissolution. "
            "The smoke is the only element — no incense holder, no surface, "
            "just silver calligraphy written in air."
        ),
        "display_name_en": "Smoke Calligraphy",
        "display_name_zh": "烟之书法",
        "description_en": "Three incense smoke trails intertwining into helical calligraphy — silver writing on a black void",
        "description_zh": "三缕檀烟交织成螺旋的空中书法——银色笔迹书写在纯黑虚空之上",
        "category": "abstract",
        "tags": ["abstract", "smoke", "calligraphy", "minimal", "black-white", "ethereal"],
        "style_keywords": ["smoke photography", "side-lit silver", "helical pattern"],
        "difficulty": "intermediate",
        "use_count": 580,
        "like_count": 200,
        "favorite_count": 110,
    },
    {
        "prompt_text": (
            "A rust macro — extreme close-up of iron oxidation on a ship hull, "
            "the surface transformed into an abstract landscape of color and texture. "
            "Layers of paint peel back to reveal orange, brown, and deep red rust beneath, "
            "with patches of original teal paint still clinging. "
            "Bubble-like blisters of corroded metal create a three-dimensional topography. "
            "The scale is ambiguous — it could be a satellite photograph of Mars."
        ),
        "display_name_en": "Rust Landscape",
        "display_name_zh": "铁锈地貌",
        "description_en": "Macro rust abstraction — peeling ship paint reveals a landscape of orange, red, and teal that could be Mars from orbit",
        "description_zh": "船体铁锈微距——剥落的油漆下露出橙、红、青绿的抽象地貌，仿佛火星的卫星图",
        "category": "abstract",
        "tags": ["abstract", "rust", "macro", "texture", "decay", "found-abstract"],
        "style_keywords": ["found abstraction", "macro texture", "scale ambiguity"],
        "difficulty": "beginner",
        "use_count": 650,
        "like_count": 220,
        "favorite_count": 122,
    },
    {
        "prompt_text": (
            "Cymatics visualization — fine sand on a vibrating metal plate "
            "forming complex geometric patterns in response to a specific audio frequency. "
            "The sand has settled into a mandala-like arrangement of nodes and anti-nodes, "
            "with clean lines where the plate vibrates most and sand accumulation at the still points. "
            "The plate is circular, dark metallic. "
            "Overhead view, perfectly centered. "
            "The pattern is naturally symmetrical with six-fold rotational symmetry."
        ),
        "display_name_en": "Cymatics Mandala",
        "display_name_zh": "声波曼陀罗",
        "description_en": "Sand cymatics on a vibrating plate — audio frequency made visible as a six-fold symmetric mandala pattern",
        "description_zh": "振动金属板上的沙子形成声波图案——特定频率化为六重对称的曼陀罗",
        "category": "abstract",
        "tags": ["abstract", "cymatics", "sound", "sand", "symmetry", "physics"],
        "style_keywords": ["cymatics pattern", "six-fold symmetry", "sound visualization"],
        "difficulty": "advanced",
        "use_count": 340,
        "like_count": 155,
        "favorite_count": 85,
    },
    {
        "prompt_text": (
            "Oil and water photograph — a shallow dish of water with colored oil drops "
            "floating on the surface, each drop acting as a lens "
            "that magnifies and distorts the pattern beneath. "
            "The underlying pattern is a sheet of colorful confetti "
            "placed under the glass dish. "
            "Each oil circle shows a different warped version of the confetti. "
            "Backlit from below, the oil drops glow like stained glass windows. "
            "Palette determined by the confetti: primary colors softened by the liquid optics."
        ),
        "display_name_en": "Oil Drop Lenses",
        "display_name_zh": "油滴透镜",
        "description_en": "Oil drops on water acting as liquid lenses — each circle a unique distortion of the backlit confetti beneath",
        "description_zh": "水面上的油滴化身液态透镜——每个圆圈都是底部彩纸的独特折射变形",
        "category": "abstract",
        "tags": ["abstract", "oil-water", "macro", "lens-effect", "refraction", "colorful"],
        "style_keywords": ["liquid lens optics", "backlit refraction", "macro abstraction"],
        "difficulty": "intermediate",
        "use_count": 480,
        "like_count": 175,
        "favorite_count": 95,
    },
    {
        "prompt_text": (
            "A single sumi-e enso circle — one bold brushstroke of black ink on handmade washi paper. "
            "The stroke begins thick and wet at the seven-o'clock position, "
            "thins as the brush runs dry through the upper arc, "
            "and trails off with splattered whiskers at the end without closing the circle. "
            "The paper's texture — long fibers and uneven surface — is visible throughout. "
            "A small red seal stamp sits in the lower right corner. "
            "The circle is slightly off-center, human and imperfect."
        ),
        "display_name_en": "Enso Breath",
        "display_name_zh": "圆相一笔",
        "description_en": "A single enso brushstroke — thick to dry, open-ended, imperfect — the Zen circle as a breath made visible",
        "description_zh": "一笔圆相——从浓到枯、未合的圆，禅意中不完美的完美如一次呼吸的可见形式",
        "category": "abstract",
        "tags": ["abstract", "enso", "zen", "sumi-e", "brushstroke", "japanese"],
        "style_keywords": ["single brushstroke", "wabi-sabi imperfection", "wet-to-dry transition"],
        "difficulty": "beginner",
        "use_count": 830,
        "like_count": 280,
        "favorite_count": 155,
    },
    {
        "prompt_text": (
            "A dense field of translucent soap bubbles floats in front of a pure black background, "
            "each bubble a different size ranging from marble to basketball. "
            "Every bubble surface reflects a distorted miniature landscape — one shows mountains, "
            "another a cityscape, another an ocean wave, another a desert dune. "
            "The bubbles closest to the viewer are sharply focused with visible film interference "
            "patterns in rainbow iridescence, while distant bubbles dissolve into soft bokeh circles. "
            "A single bubble in the center has just popped, its fragments frozen mid-burst "
            "as a ring of tiny droplets expanding outward."
        ),
        "display_name_en": "Worlds in Foam",
        "display_name_zh": "泡影万象",
        "description_en": "Hundreds of soap bubbles against black, each reflecting a different miniature landscape — one pops mid-frame, its droplet ring frozen in expansion",
        "description_zh": "纯黑背景前漂浮着大小不一的肥皂泡，每个泡面映着不同的微缩风景，正中一个刚刚破裂，飞沫环凝固在扩散瞬间",
        "category": "abstract",
        "tags": ["abstract", "bubbles", "iridescence", "micro-worlds", "frozen-moment", "bokeh"],
        "style_keywords": ["film interference iridescence", "macro frozen burst", "contained world reflections"],
        "difficulty": "advanced",
        "use_count": 670,
        "like_count": 230,
        "favorite_count": 130,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VIDEO — LANDSCAPE (10)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Aerial drone shot slowly pushing forward over a glacial river delta in Iceland, "
            "braided turquoise streams weaving across volcanic black sand. The camera drifts "
            "from high altitude gradually descending toward the water surface, revealing intricate "
            "branching patterns. Wispy clouds cast moving shadows across the landscape. "
            "Late afternoon golden light rakes across the terrain at a low angle."
        ),
        "display_name_en": "Glacial Delta Flyover",
        "display_name_zh": "冰川三角洲飞越",
        "description_en": "Aerial push-in over Iceland's braided glacial rivers, descending from altitude to reveal turquoise streams on black volcanic sand",
        "description_zh": "航拍前推掠过冰岛辫状冰川河，从高空渐降揭示火山黑沙上的碧绿溪流",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "aerial", "drone", "iceland", "glacial", "timelapse"],
        "style_keywords": ["aerial push-in", "braided river pattern", "golden hour raking light"],
        "difficulty": "intermediate",
        "use_count": 580,
        "like_count": 210,
        "favorite_count": 120,
    },
    {
        "prompt_text": (
            "Time-lapse of a massive thunderstorm cell rolling across the Great Plains at dusk, "
            "mammatus clouds bulging beneath the anvil top. Lightning flickers inside the supercell "
            "in rhythmic pulses while the camera holds a wide static frame. The horizon transitions "
            "from amber to deep violet as day surrenders to night. Wheat fields in the foreground "
            "sway gently under increasing wind."
        ),
        "display_name_en": "Supercell at Dusk",
        "display_name_zh": "暮色超级单体",
        "description_en": "Time-lapse of a lightning-pulsing supercell rolling across wheat fields, day fading to violet night on the Great Plains",
        "description_zh": "大平原上超级单体雷暴延时摄影，闪电在砧状云中脉动，黄昏渐变为深紫夜色",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "storm", "timelapse", "lightning", "dramatic-sky", "plains"],
        "style_keywords": ["static wide frame", "mammatus texture", "day-to-night transition"],
        "difficulty": "advanced",
        "use_count": 720,
        "like_count": 260,
        "favorite_count": 145,
    },
    {
        "prompt_text": (
            "Slow dolly forward through a bamboo forest in Kyoto, morning mist drifting between "
            "towering green stalks. Shafts of sunlight pierce the canopy and shift as the camera "
            "advances, creating moving god rays. A narrow stone path leads the eye into the depth "
            "of the grove. Leaves rustle softly, and a few bamboo stalks creak in the breeze."
        ),
        "display_name_en": "Bamboo Forest Walk",
        "display_name_zh": "竹林漫行",
        "description_en": "Gentle dolly through misty Kyoto bamboo, god rays shifting as the camera glides along a stone path into green depth",
        "description_zh": "缓慢推进穿越京都竹林，晨雾中光束随镜头移动而变幻，石径通向幽深翠色",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "bamboo", "kyoto", "mist", "god-rays", "dolly"],
        "style_keywords": ["slow dolly forward", "volumetric god rays", "depth layering"],
        "difficulty": "beginner",
        "use_count": 890,
        "like_count": 320,
        "favorite_count": 180,
    },
    {
        "prompt_text": (
            "Sunrise time-lapse over Zhangjiajie sandstone pillars shrouded in a sea of clouds. "
            "The camera is fixed on a cliff edge looking across the valley. Clouds churn and flow "
            "between the pillars like slow rivers of cotton, occasionally revealing stone peaks. "
            "The sky transitions from deep rose through gold to pale blue as the sun climbs."
        ),
        "display_name_en": "Zhangjiajie Cloud Sea",
        "display_name_zh": "张家界云海日出",
        "description_en": "Fixed-frame sunrise time-lapse as clouds churn between Zhangjiajie's sandstone pillars, sky shifting rose-gold-blue",
        "description_zh": "固定机位拍摄张家界砂岩石柱间云海翻涌，天空从玫红渐变金色再到淡蓝",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "timelapse", "clouds", "sunrise", "zhangjiajie", "mountains"],
        "style_keywords": ["fixed tripod frame", "cloud river motion", "color gradient sky"],
        "difficulty": "intermediate",
        "use_count": 650,
        "like_count": 240,
        "favorite_count": 135,
    },
    {
        "prompt_text": (
            "Slow-motion ocean wave crashing against a rocky shore at golden hour, "
            "the camera positioned low at water level. Water explodes upward in a curtain of spray "
            "backlit by the setting sun, each droplet catching amber light like suspended jewels. "
            "The wave retreats in foaming sheets across textured basalt, "
            "pulling pebbles in a chattering cascade."
        ),
        "display_name_en": "Golden Wave Impact",
        "display_name_zh": "金浪撞岸",
        "description_en": "Low-angle slow-motion wave crash at golden hour, backlit spray suspended like amber jewels against the setting sun",
        "description_zh": "低机位慢动作拍摄金色时分海浪撞击礁石，逆光水雾如琥珀宝石悬浮空中",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "ocean", "slow-motion", "golden-hour", "waves", "backlit"],
        "style_keywords": ["low-angle water level", "backlit spray", "slow-motion impact"],
        "difficulty": "intermediate",
        "use_count": 760,
        "like_count": 280,
        "favorite_count": 155,
    },
    {
        "prompt_text": (
            "Hyperlapse along a winding mountain road in the Swiss Alps during autumn, "
            "the camera mounted to a vehicle moving steadily forward. Golden larch forests "
            "line the road on both sides, snow-capped peaks tower ahead. Clouds move quickly "
            "overhead in accelerated time while the road unspools like a ribbon through the valley."
        ),
        "display_name_en": "Alpine Road Hyperlapse",
        "display_name_zh": "阿尔卑斯公路穿行",
        "description_en": "Vehicle-mounted hyperlapse winding through golden larch forests toward snow peaks, fast clouds overhead",
        "description_zh": "车载超级延时沿蜿蜒山路穿越金色落叶松林，快速流云下雪峰在前方展开",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "hyperlapse", "alps", "autumn", "driving", "mountains"],
        "style_keywords": ["vehicle-mount hyperlapse", "winding road perspective", "accelerated clouds"],
        "difficulty": "advanced",
        "use_count": 540,
        "like_count": 195,
        "favorite_count": 110,
    },
    {
        "prompt_text": (
            "Northern lights dancing over a frozen lake in Norway, camera on a slow motorized pan "
            "from left to right. Green and violet aurora curtains ripple and fold across the sky, "
            "their reflections shimmering on the ice surface below. Scattered stars pierce through "
            "gaps in the aurora. A lone cabin with a warm window glow sits at the lake edge."
        ),
        "display_name_en": "Aurora over Frozen Lake",
        "display_name_zh": "冰湖极光",
        "description_en": "Slow pan across aurora curtains rippling over a Norwegian frozen lake, green and violet light reflected on ice",
        "description_zh": "缓慢水平摇摄挪威冰湖上空翻卷的极光帷幕，绿紫光芒倒映在冰面上",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "aurora", "night", "norway", "frozen-lake", "pan"],
        "style_keywords": ["motorized slow pan", "aurora curtain ripple", "ice reflection"],
        "difficulty": "beginner",
        "use_count": 920,
        "like_count": 350,
        "favorite_count": 200,
    },
    {
        "prompt_text": (
            "Time-lapse of cherry blossom petals falling like snow in a Tokyo park, "
            "the camera tilting slowly upward from a carpet of pink petals on the ground "
            "to the canopy of blossoming branches overhead. Pedestrians move as blurred ghosts "
            "through the frame. Afternoon light filters through translucent petals, "
            "creating a soft pink glow across the entire scene."
        ),
        "display_name_en": "Sakura Petal Rain",
        "display_name_zh": "樱吹雪",
        "description_en": "Tilt-up time-lapse from pink petal carpet to cherry blossom canopy, ghostly pedestrians drifting through soft pink light",
        "description_zh": "从地面粉色花瓣毯缓慢仰拍至樱花树冠，行人化作虚影穿过柔粉光晕",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "sakura", "timelapse", "tokyo", "spring", "petals"],
        "style_keywords": ["slow tilt up", "petal particle rain", "ghosted pedestrians"],
        "difficulty": "beginner",
        "use_count": 980,
        "like_count": 370,
        "favorite_count": 210,
    },
    {
        "prompt_text": (
            "Aerial orbit shot circling a volcanic crater lake in Indonesia, "
            "the water an otherworldly turquoise against charcoal slopes. Steam vents along the rim "
            "release plumes that drift across the frame as the drone completes a slow 180-degree arc. "
            "Morning light catches the mineral-stained shoreline in bands of yellow and white."
        ),
        "display_name_en": "Crater Lake Orbit",
        "display_name_zh": "火山口湖环绕",
        "description_en": "Aerial orbit around a turquoise volcanic crater lake, steam plumes drifting across mineral-stained slopes",
        "description_zh": "航拍环绕印尼碧绿火山口湖，蒸汽羽流飘过矿物质染色的焦炭色山坡",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "aerial", "volcano", "crater-lake", "orbit", "indonesia"],
        "style_keywords": ["aerial orbit 180°", "mineral color contrast", "steam drift"],
        "difficulty": "advanced",
        "use_count": 480,
        "like_count": 175,
        "favorite_count": 95,
    },
    {
        "prompt_text": (
            "Day-to-night time-lapse of the Sahara desert, camera fixed on a single crescent dune. "
            "Shadows sweep across rippled sand as the sun arcs overhead, then stars emerge in a "
            "deep indigo sky. The Milky Way rotates slowly above the dune crest. "
            "Wind subtly reshapes the sand ripple patterns throughout the sequence."
        ),
        "display_name_en": "Desert Day to Night",
        "display_name_zh": "沙漠昼夜轮转",
        "description_en": "Fixed-frame day-to-night time-lapse on a Sahara dune — sweeping shadows, emerging stars, Milky Way rotation",
        "description_zh": "固定机位撒哈拉沙丘昼夜延时，影子扫过波纹沙面，星空渐现，银河缓缓旋转",
        "category": "landscape",
        "media_type": "video",
        "tags": ["landscape", "desert", "timelapse", "milky-way", "day-to-night", "sahara"],
        "style_keywords": ["fixed frame holy grail", "shadow sweep", "star rotation"],
        "difficulty": "advanced",
        "use_count": 610,
        "like_count": 225,
        "favorite_count": 125,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VIDEO — ANIME (10)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Anime-style scene of a girl running through a field of sunflowers in summer, "
            "camera tracking alongside her at matching speed. Her straw hat flies off and tumbles "
            "behind her in slow motion. Sunflower heads bob as she brushes past them. "
            "Bright cel-shaded colors, lens flare from the high sun, wind rippling her white dress."
        ),
        "display_name_en": "Sunflower Sprint",
        "display_name_zh": "向日葵奔跑",
        "description_en": "Side-tracking shot of an anime girl sprinting through sunflowers, straw hat flying off in slow motion under bright summer sun",
        "description_zh": "动漫少女在向日葵花田中奔跑的侧面跟拍，草帽飞起慢动作，夏日阳光耀眼",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "running", "summer", "sunflower", "slow-motion", "tracking"],
        "style_keywords": ["side tracking shot", "cel-shaded bright", "slow-motion detail"],
        "difficulty": "beginner",
        "use_count": 850,
        "like_count": 310,
        "favorite_count": 175,
    },
    {
        "prompt_text": (
            "Anime warrior drawing a katana in a bamboo grove, the blade emerging inch by inch "
            "with a gleaming reflection sliding along the steel. Cherry blossom petals freeze "
            "in mid-air during the draw. Camera circles the character in a slow 360-degree orbit "
            "at waist height. Dramatic ink-wash style shadows and volumetric light shafts."
        ),
        "display_name_en": "Katana Unsheathed",
        "display_name_zh": "拔刀一瞬",
        "description_en": "360-degree orbit around an anime warrior drawing a katana, petals frozen mid-air, ink-wash shadows and light shafts",
        "description_zh": "动漫武士竹林拔刀的360度环绕镜头，樱花瓣凝固空中，水墨风光影交织",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "samurai", "katana", "cherry-blossom", "orbit-shot", "dramatic"],
        "style_keywords": ["360 orbit at waist", "frozen particle moment", "ink-wash volumetric"],
        "difficulty": "advanced",
        "use_count": 690,
        "like_count": 255,
        "favorite_count": 140,
    },
    {
        "prompt_text": (
            "Cozy anime scene of a cat curled up on a windowsill as rain streams down the glass, "
            "camera slowly zooming in from room interior toward the window. Raindrops trace paths "
            "on the pane, refracting blurred city lights outside. The cat's tail twitches gently "
            "in sleep. Warm indoor lamp light contrasts with the cool blue rain outside."
        ),
        "display_name_en": "Rainy Day Cat Nap",
        "display_name_zh": "雨天猫眠",
        "description_en": "Slow zoom toward a sleeping cat on a rainy windowsill, raindrops refracting city lights in warm-cool contrast",
        "description_zh": "缓慢推近窗台上酣睡的猫，雨滴在玻璃上折射城市灯光，暖冷色调对比",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "cat", "rain", "cozy", "lofi", "slow-zoom"],
        "style_keywords": ["slow zoom in", "rain refraction bokeh", "warm-cool contrast"],
        "difficulty": "beginner",
        "use_count": 1050,
        "like_count": 390,
        "favorite_count": 220,
    },
    {
        "prompt_text": (
            "Mecha anime battle sequence: a giant robot slides backward on a city street "
            "leaving sparking gouges in the asphalt, then plants its feet and launches forward. "
            "Camera follows from a low Dutch angle, buildings blurring past. "
            "Neon signs shatter from the shockwave. Cyberpunk color palette of teal and magenta."
        ),
        "display_name_en": "Mecha Street Clash",
        "display_name_zh": "机甲街头冲击",
        "description_en": "Low Dutch angle tracking a mecha sliding and launching on a city street, neon signs shattering from the shockwave",
        "description_zh": "低角度荷兰倾斜跟拍机甲在城市街道上滑行反击，霓虹招牌被冲击波震碎",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "mecha", "action", "cyberpunk", "dutch-angle", "shockwave"],
        "style_keywords": ["low Dutch angle tracking", "motion blur streaks", "teal-magenta palette"],
        "difficulty": "advanced",
        "use_count": 620,
        "like_count": 230,
        "favorite_count": 125,
    },
    {
        "prompt_text": (
            "Anime-style magical girl transformation sequence, the character spinning in mid-air "
            "as ribbons of light spiral around her forming an elaborate costume. Camera rotates "
            "around her in the opposite direction. Sparkle particles burst outward in concentric rings. "
            "Pastel gradient background shifts from pink to lavender to gold."
        ),
        "display_name_en": "Magical Transformation",
        "display_name_zh": "魔法变身",
        "description_en": "Counter-rotating camera around a magical girl mid-transformation, light ribbons spiraling, sparkles bursting in rings",
        "description_zh": "魔法少女变身中的反向旋转镜头，光带螺旋缠绕，闪光粒子同心圆绽放",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "magical-girl", "transformation", "sparkle", "rotation", "pastel"],
        "style_keywords": ["counter-rotation camera", "spiral light ribbons", "concentric particle burst"],
        "difficulty": "intermediate",
        "use_count": 770,
        "like_count": 285,
        "favorite_count": 160,
    },
    {
        "prompt_text": (
            "Anime train window scene: countryside scrolling past as viewed from inside a moving train, "
            "rice paddies and distant mountains reflected on the glass. A schoolgirl sits by the window, "
            "her hair gently swaying with the train's rhythm. Camera holds steady on her profile. "
            "Afternoon light creates moving shadow bars from window frames across her face."
        ),
        "display_name_en": "Train Window Daydream",
        "display_name_zh": "列车窗边遐想",
        "description_en": "Static profile shot of a schoolgirl by a moving train window, countryside scrolling past, light bars sweeping across her face",
        "description_zh": "少女靠列车窗边的侧面静止镜头，田园风景滚动流过，光影条纹掠过面庞",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "train", "slice-of-life", "countryside", "contemplative", "light-bars"],
        "style_keywords": ["static interior profile", "parallax scroll background", "moving window light"],
        "difficulty": "beginner",
        "use_count": 920,
        "like_count": 340,
        "favorite_count": 190,
    },
    {
        "prompt_text": (
            "Anime night market scene bustling with activity, camera on a slow crane-up from "
            "street level through hanging paper lanterns to reveal the full market stretching "
            "into the distance. Steam rises from food stalls, neon signage flickers, "
            "dozens of characters move through the crowd. Warm amber and red dominant palette."
        ),
        "display_name_en": "Night Market Reveal",
        "display_name_zh": "夜市灯火升起",
        "description_en": "Crane-up through paper lanterns revealing a bustling anime night market, steam and neon in warm amber tones",
        "description_zh": "从街道水平缓缓升起穿过灯笼，展现热闹动漫夜市全景，蒸汽与霓虹暖色交织",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "night-market", "crane-shot", "lanterns", "crowd", "neon"],
        "style_keywords": ["slow crane up reveal", "layered crowd motion", "warm ambient glow"],
        "difficulty": "intermediate",
        "use_count": 810,
        "like_count": 295,
        "favorite_count": 165,
    },
    {
        "prompt_text": (
            "Anime sword duel on a moonlit rooftop, two figures exchanging rapid strikes "
            "with motion-blur trails on each swing. Camera cuts between close-ups of clashing blades "
            "and a wide shot showing their silhouettes against a full moon. "
            "Sparks fly on each parry. Wind whips their cloaks. Dark blue and silver color scheme."
        ),
        "display_name_en": "Moonlit Blade Duel",
        "display_name_zh": "月下对剑",
        "description_en": "Rapid cuts between close blade clashes and wide moonlit silhouettes in a rooftop anime sword duel",
        "description_zh": "屋顶动漫剑斗的快速剪辑，近景刀锋碰撞与满月剪影交替，火花与风共舞",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "sword-fight", "moonlight", "rooftop", "action", "silhouette"],
        "style_keywords": ["rapid cut montage", "motion-blur blade trails", "moon silhouette wide"],
        "difficulty": "advanced",
        "use_count": 580,
        "like_count": 215,
        "favorite_count": 120,
    },
    {
        "prompt_text": (
            "Studio Ghibli-inspired scene of a child riding a giant fluffy creature flying above "
            "a patchwork countryside, camera pulling back to reveal the vast landscape below. "
            "Cotton-ball clouds drift past at eye level. The child's scarf flutters behind them. "
            "Watercolor-soft edges and dappled sunlight on rolling green hills."
        ),
        "display_name_en": "Sky Ride Adventure",
        "display_name_zh": "天空骑行",
        "description_en": "Pull-back reveal of a child riding a flying creature over Ghibli-style patchwork countryside, clouds drifting at eye level",
        "description_zh": "拉远镜头展现孩子骑巨大飞行生物飞越吉卜力风田园，棉花云在眼前飘过",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "ghibli", "flying", "countryside", "whimsical", "pull-back"],
        "style_keywords": ["pull-back reveal", "watercolor soft edges", "eye-level cloud layer"],
        "difficulty": "intermediate",
        "use_count": 870,
        "like_count": 325,
        "favorite_count": 185,
    },
    {
        "prompt_text": (
            "Anime cooking scene: close-up of a wok toss in a steaming kitchen, vegetables and "
            "shrimp arcing through the air in slow motion with flames licking underneath. "
            "Camera follows the food arc upward then back down. Oil droplets sparkle. "
            "The chef's confident hand flick is frozen at the peak of the toss."
        ),
        "display_name_en": "Wok Toss Spectacle",
        "display_name_zh": "颠锅瞬间",
        "description_en": "Slow-motion close-up of an anime wok toss, food arcing through flames, oil sparkles frozen at the peak",
        "description_zh": "动漫颠锅慢动作特写，食材在火焰上飞弧，油珠在最高点闪烁凝固",
        "category": "anime",
        "media_type": "video",
        "tags": ["anime", "cooking", "slow-motion", "food", "close-up", "flames"],
        "style_keywords": ["food arc tracking", "slow-motion sparkle", "flame underlighting"],
        "difficulty": "intermediate",
        "use_count": 740,
        "like_count": 270,
        "favorite_count": 150,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VIDEO — FANTASY (10)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "A dragon bursts through a cloud bank, wings fully extended, the camera matching its "
            "dive speed from above. Scales shimmer from emerald to gold as sunlight catches "
            "each ridge. Cloud vapor trails off the wingtips in spiraling vortices. "
            "Below, a mountain kingdom grows larger as the dragon descends."
        ),
        "display_name_en": "Dragon Dive",
        "display_name_zh": "龙之俯冲",
        "description_en": "Camera-matched dive alongside a dragon bursting through clouds, scales shimmering, mountain kingdom growing below",
        "description_zh": "跟随巨龙破云俯冲的同步镜头，鳞片在日光下闪烁变幻，山间王国在下方渐近",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "dragon", "dive", "clouds", "aerial", "epic"],
        "style_keywords": ["speed-matched aerial", "scale iridescence shift", "growing reveal below"],
        "difficulty": "advanced",
        "use_count": 780,
        "like_count": 290,
        "favorite_count": 160,
    },
    {
        "prompt_text": (
            "A wizard opens a portal in a dark stone chamber, the circular rift expanding from "
            "a pinpoint of light to a full doorway revealing a sunlit meadow on the other side. "
            "Camera pushes slowly through the portal threshold. Energy crackles along the rim. "
            "Dust and loose parchment pages are sucked toward the opening."
        ),
        "display_name_en": "Portal Opening",
        "display_name_zh": "传送门开启",
        "description_en": "Push-through shot as a portal expands from pinpoint to full doorway, energy crackling, debris drawn inward",
        "description_zh": "推进镜头穿过从光点扩展为大门的传送门，能量在边缘噼啪作响，碎片被吸入",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "portal", "magic", "push-through", "energy", "dimensional"],
        "style_keywords": ["push-through threshold", "expanding circle rift", "debris suction"],
        "difficulty": "intermediate",
        "use_count": 830,
        "like_count": 305,
        "favorite_count": 170,
    },
    {
        "prompt_text": (
            "An ancient tree awakens, its bark cracking and splitting as glowing amber veins of "
            "magic spread from roots to crown. Camera tilts upward following the light climbing "
            "the trunk. Branches begin to sway with purpose, leaves ignite in golden luminescence. "
            "Fireflies swarm around the tree in synchronized spirals."
        ),
        "display_name_en": "Treant Awakening",
        "display_name_zh": "古树苏醒",
        "description_en": "Tilt-up tracking golden magic veins climbing an ancient tree from roots to crown, bark splitting, leaves igniting",
        "description_zh": "仰拍跟踪金色魔力脉络从根部攀升至树冠，树皮开裂，叶片燃起金光",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "tree", "magic", "awakening", "tilt-up", "glow"],
        "style_keywords": ["tilt-up growth tracking", "spreading vein illumination", "synchronized fireflies"],
        "difficulty": "intermediate",
        "use_count": 710,
        "like_count": 260,
        "favorite_count": 145,
    },
    {
        "prompt_text": (
            "A phoenix erupts from a pile of ash, flames spiraling upward in a double helix pattern "
            "as the bird takes form. Camera holds a medium shot then slowly orbits as the phoenix "
            "spreads its wings, each feather trailing sparks. The surrounding darkness is pushed back "
            "by expanding waves of warm light. Ash particles rain down like inverse snow."
        ),
        "display_name_en": "Phoenix Rebirth",
        "display_name_zh": "凤凰涅槃",
        "description_en": "Medium shot orbiting a phoenix emerging from ash, double-helix flames, feather sparks pushing back darkness",
        "description_zh": "中景环绕凤凰从灰烬中重生，双螺旋火焰上升，羽毛火星驱退周围黑暗",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "phoenix", "fire", "rebirth", "orbit", "particles"],
        "style_keywords": ["medium orbit shot", "double helix flame spiral", "inverse particle rain"],
        "difficulty": "advanced",
        "use_count": 690,
        "like_count": 255,
        "favorite_count": 140,
    },
    {
        "prompt_text": (
            "A crystal ball sits on a velvet cloth, the camera slowly pushing in until the sphere "
            "fills the frame. Inside, swirling mist parts to reveal a miniature stormy ocean with "
            "tiny lightning bolts and waves. The reflection of the viewer's eye is visible on the "
            "glass surface. Candlelight flickers around the edges of the frame."
        ),
        "display_name_en": "Crystal Vision",
        "display_name_zh": "水晶预言",
        "description_en": "Slow push-in to a crystal ball revealing a miniature storm ocean inside, candlelight flickering, eye reflected on glass",
        "description_zh": "缓慢推近水晶球直至充满画面，球内迷雾散开露出微型风暴海洋，烛光摇曳",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "crystal-ball", "divination", "push-in", "miniature", "storm"],
        "style_keywords": ["macro push-in", "contained world reveal", "surface reflection layer"],
        "difficulty": "beginner",
        "use_count": 860,
        "like_count": 315,
        "favorite_count": 180,
    },
    {
        "prompt_text": (
            "An enchanted forge: a blacksmith hammers a glowing rune-inscribed blade, "
            "each strike sending showers of magical sparks that form brief runic symbols in the air "
            "before fading. Camera in close-up on the anvil, rack-focusing between the hammer strike "
            "and the floating runes. The forge fire burns an unnatural blue-white."
        ),
        "display_name_en": "Runic Forging",
        "display_name_zh": "符文铸剑",
        "description_en": "Close-up anvil view of a rune-blade being forged, sparks forming runic symbols, rack focus between hammer and floating glyphs",
        "description_zh": "铁砧特写拍摄符文剑锻造，火花在空中凝成符文字形，焦点在锤击与浮空符文间切换",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "forge", "runes", "sparks", "close-up", "rack-focus"],
        "style_keywords": ["close-up rack focus", "spark-to-symbol formation", "blue-white forge fire"],
        "difficulty": "intermediate",
        "use_count": 640,
        "like_count": 235,
        "favorite_count": 130,
    },
    {
        "prompt_text": (
            "An underwater elven city glimmers beneath a tropical sea, bioluminescent corals lining "
            "marble colonnades. Camera glides forward through an arched gateway as schools of fish "
            "scatter. Sunbeams lance through the water from above, creating moving caustic patterns "
            "on the white stone. Air bubble streams rise from hidden vents."
        ),
        "display_name_en": "Sunken Elven City",
        "display_name_zh": "沉没精灵城",
        "description_en": "Gliding forward through a bioluminescent underwater elven city, caustic light patterns dancing on marble, fish scattering",
        "description_zh": "镜头滑行穿过水下精灵城的拱门，焦散光纹在白色大理石上舞动，鱼群散开",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "underwater", "elven", "bioluminescent", "glide", "caustics"],
        "style_keywords": ["forward glide through arch", "caustic light dance", "bioluminescent coral glow"],
        "difficulty": "intermediate",
        "use_count": 720,
        "like_count": 265,
        "favorite_count": 148,
    },
    {
        "prompt_text": (
            "A spell book floats open in mid-air, pages turning by themselves as illustrated creatures "
            "leap off the pages and become three-dimensional. Camera watches from a reading-desk "
            "perspective. A tiny painted dragon flaps off the parchment, gaining color and depth "
            "as it transitions from 2D illustration to 3D creature. Ink trails behind it like smoke."
        ),
        "display_name_en": "Living Spell Book",
        "display_name_zh": "活页魔典",
        "description_en": "Desk-perspective view of a floating spell book whose illustrated creatures leap off pages into 3D life, trailing ink smoke",
        "description_zh": "书桌视角看浮空魔典中绘画生物跃出页面变为立体，身后拖曳墨烟",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "spell-book", "2d-to-3d", "creatures", "ink", "floating"],
        "style_keywords": ["desk POV static", "2D-to-3D transition", "trailing ink particle"],
        "difficulty": "advanced",
        "use_count": 560,
        "like_count": 205,
        "favorite_count": 115,
    },
    {
        "prompt_text": (
            "A frozen throne room with ice pillars thawing in real time: water trickles down carved "
            "surfaces, icicles drip, and frost recedes from stained glass windows revealing color beneath. "
            "Camera on a slow push-in toward the empty throne. "
            "Warm light gradually replaces cold blue as the thaw progresses."
        ),
        "display_name_en": "Thawing Throne",
        "display_name_zh": "冰殿融化",
        "description_en": "Slow push-in toward an ice throne room thawing in real time, frost receding from stained glass, cold blue warming",
        "description_zh": "缓慢推近正在融化的冰霜王座大厅，霜从彩色玻璃上退去，冷蓝渐变暖光",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "ice", "throne", "thawing", "push-in", "transformation"],
        "style_keywords": ["slow push-in reveal", "real-time thaw texture", "cold-to-warm transition"],
        "difficulty": "beginner",
        "use_count": 750,
        "like_count": 275,
        "favorite_count": 155,
    },
    {
        "prompt_text": (
            "A floating island drifts across a sunset sky, waterfalls pouring off its edges into "
            "misty nothingness below. Camera slowly pans around the island revealing a small village "
            "with glowing windows perched on top. Chains and roots dangle from the underside. "
            "Flocks of birds circle the island. Warm orange and purple sky gradient."
        ),
        "display_name_en": "Floating Island Village",
        "display_name_zh": "浮岛村落",
        "description_en": "Slow pan around a floating island at sunset, waterfalls spilling into void, a glowing village perched on top",
        "description_zh": "缓慢摇摄日落天空中的浮岛，瀑布倾泻入虚空，顶部小村落窗灯温暖",
        "category": "fantasy",
        "media_type": "video",
        "tags": ["fantasy", "floating-island", "sunset", "village", "waterfalls", "pan"],
        "style_keywords": ["slow orbit pan", "edge waterfall cascade", "sunset gradient sky"],
        "difficulty": "beginner",
        "use_count": 900,
        "like_count": 335,
        "favorite_count": 190,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VIDEO — PORTRAIT (10)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Close-up of a woman's face, a gentle breeze lifts strands of dark hair across her eyes. "
            "She reaches up slowly to brush the hair aside, revealing a half-smile. "
            "Soft golden-hour backlight creates a halo rim around her head. "
            "Camera holds steady in a tight frame, shallow depth of field blurs a lavender field behind her."
        ),
        "display_name_en": "Wind-Swept Portrait",
        "display_name_zh": "微风拂面",
        "description_en": "Tight static portrait as wind lifts hair across her face, golden-hour halo rim light, lavender field bokeh behind",
        "description_zh": "紧凑静止人像，微风将发丝吹过面颊，金色时分逆光光环，薰衣草田背景虚化",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "wind", "golden-hour", "close-up", "hair", "backlit"],
        "style_keywords": ["tight static frame", "rim light halo", "shallow DOF lavender"],
        "difficulty": "beginner",
        "use_count": 940,
        "like_count": 345,
        "favorite_count": 195,
    },
    {
        "prompt_text": (
            "An elderly man sits at a window in a dimly lit room, afternoon light painting "
            "half his face in warm amber while the other half falls into shadow. He slowly turns "
            "his head toward the camera, light sliding across his features revealing deep wrinkles "
            "and bright eyes. Dust motes drift in the light beam. Camera on a very slow push-in."
        ),
        "display_name_en": "Turning to Light",
        "display_name_zh": "转向光明",
        "description_en": "Slow push-in as an elderly man turns toward window light, illumination sliding across weathered features, dust motes floating",
        "description_zh": "老人缓缓转向窗光的慢推镜头，光线滑过沧桑面容，尘埃在光柱中飘浮",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "elderly", "window-light", "chiaroscuro", "push-in", "dust"],
        "style_keywords": ["slow push-in", "sliding chiaroscuro", "floating dust motes"],
        "difficulty": "intermediate",
        "use_count": 680,
        "like_count": 250,
        "favorite_count": 138,
    },
    {
        "prompt_text": (
            "A dancer spins in place under a single overhead spotlight on a dark stage, "
            "camera circling her in slow orbit. Her flowing red dress fans outward creating a "
            "disc of fabric. Captured at high frame rate so every fold and ripple is visible. "
            "The spotlight catches fabric texture and skin in stark contrast against pure black."
        ),
        "display_name_en": "Spinning Red Dress",
        "display_name_zh": "旋转红裙",
        "description_en": "Slow orbit around a spinning dancer under a spotlight, red dress fanning outward in high-frame-rate detail against black",
        "description_zh": "聚光灯下旋转舞者的慢速环绕镜头，红裙张开如盘，高帧率捕捉每一褶皱",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "dance", "spin", "spotlight", "red-dress", "slow-motion"],
        "style_keywords": ["slow orbit circle", "single spotlight isolation", "high-fps fabric detail"],
        "difficulty": "intermediate",
        "use_count": 810,
        "like_count": 300,
        "favorite_count": 168,
    },
    {
        "prompt_text": (
            "Split-screen portrait transitioning from a young woman applying traditional Japanese "
            "geisha makeup to the finished look. Time compresses as white foundation is applied, "
            "lips painted red, and wig secured. Camera fixed in a centered front-facing frame. "
            "The background remains static while only the face transforms."
        ),
        "display_name_en": "Geisha Transformation",
        "display_name_zh": "艺伎妆变",
        "description_en": "Fixed centered time-lapse of traditional geisha makeup application, face transforming while background stays static",
        "description_zh": "固定正面居中延时拍摄传统艺伎化妆过程，面容渐变而背景静止不动",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "geisha", "makeup", "timelapse", "transformation", "japanese"],
        "style_keywords": ["fixed centered frame", "time-lapse makeup", "static-dynamic contrast"],
        "difficulty": "beginner",
        "use_count": 870,
        "like_count": 320,
        "favorite_count": 180,
    },
    {
        "prompt_text": (
            "A street musician plays saxophone on a rainy sidewalk at night, camera slowly dollying "
            "in from across the street. Neon reflections shimmer in puddles around his feet. "
            "Rain catches the glow of a streetlamp directly above. His fingers move fluidly on the keys. "
            "Shallow depth of field isolates him from passing car headlight streaks."
        ),
        "display_name_en": "Rain Saxophone",
        "display_name_zh": "雨中萨克斯",
        "description_en": "Slow dolly-in toward a night saxophonist in the rain, neon puddle reflections, headlight streaks in bokeh",
        "description_zh": "雨夜缓慢推近街头萨克斯手，霓虹在积水中闪烁，车灯在虚化中划过",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "musician", "rain", "night", "neon", "dolly-in"],
        "style_keywords": ["slow dolly approach", "neon puddle reflection", "bokeh headlight streaks"],
        "difficulty": "intermediate",
        "use_count": 750,
        "like_count": 278,
        "favorite_count": 155,
    },
    {
        "prompt_text": (
            "Extreme close-up of an eye, the camera so close the iris fills the frame. "
            "The pupil dilates slowly as light changes. Reflected in the iris is a miniature scene "
            "of a sunset over the ocean. Tiny blood vessels are visible in the sclera. "
            "A single tear forms at the lower lid and rolls down in slow motion."
        ),
        "display_name_en": "Iris Landscape",
        "display_name_zh": "瞳中风景",
        "description_en": "Macro shot of a dilating iris reflecting a miniature ocean sunset, a slow-motion tear rolling from the lower lid",
        "description_zh": "瞳孔微距镜头映出微型海上日落，虹膜缓缓扩张，一滴泪从下眼睑慢速滑落",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "macro", "eye", "iris", "reflection", "tear"],
        "style_keywords": ["extreme macro iris", "reflected miniature scene", "slow-motion tear roll"],
        "difficulty": "advanced",
        "use_count": 590,
        "like_count": 220,
        "favorite_count": 122,
    },
    {
        "prompt_text": (
            "A blacksmith wipes sweat from his brow with a leather-gloved hand, forge fire glowing "
            "behind him. Camera holds a medium close-up as he exhales, breath visible in cool air "
            "contrasting the heat behind. Embers float past his face. He lifts his gaze directly "
            "into the lens with tired but satisfied eyes."
        ),
        "display_name_en": "Forge-Lit Craftsman",
        "display_name_zh": "炉火匠人",
        "description_en": "Medium close-up of a blacksmith pausing before his forge, visible breath mixing with floating embers, direct gaze into lens",
        "description_zh": "铁匠在锻炉前歇息的中近景，呼出的白气与飘浮火星交融，目光直视镜头",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "blacksmith", "forge", "embers", "gaze", "breath"],
        "style_keywords": ["medium close-up hold", "backlit forge glow", "direct lens address"],
        "difficulty": "intermediate",
        "use_count": 640,
        "like_count": 238,
        "favorite_count": 132,
    },
    {
        "prompt_text": (
            "Twin sisters stand back to back, the camera rotating around them as each turns to "
            "face the lens in sequence. One lit in cool blue from the left, the other in warm orange "
            "from the right. As the camera completes a full rotation, the lighting swaps between them. "
            "Minimal dark background, emphasis on symmetry and contrast."
        ),
        "display_name_en": "Twin Light Swap",
        "display_name_zh": "双子光影交换",
        "description_en": "Rotating camera around back-to-back twins, blue and orange lighting swapping between them over a full 360-degree orbit",
        "description_zh": "镜头环绕背靠背双胞胎旋转，蓝橙灯光在360度中互换，强调对称与对比",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "twins", "lighting", "rotation", "symmetry", "color-contrast"],
        "style_keywords": ["360 rotation orbit", "blue-orange swap lighting", "symmetry emphasis"],
        "difficulty": "advanced",
        "use_count": 520,
        "like_count": 195,
        "favorite_count": 108,
    },
    {
        "prompt_text": (
            "A child blows dandelion seeds toward the camera, the seeds drifting in extreme slow motion "
            "directly into the lens. Each seed parachute is individually visible, backlit by afternoon sun. "
            "The child's face goes out of focus as the seeds approach. Soft green meadow background. "
            "Warm, nostalgic color grading."
        ),
        "display_name_en": "Dandelion Wish",
        "display_name_zh": "蒲公英心愿",
        "description_en": "Slow-motion dandelion seeds floating toward the lens, backlit and individually sharp, child drifting out of focus behind",
        "description_zh": "蒲公英种子慢动作飘向镜头，逆光下每朵清晰可见，身后孩子渐渐失焦",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "child", "dandelion", "slow-motion", "backlit", "nostalgic"],
        "style_keywords": ["toward-lens slow motion", "backlit seed detail", "focus rack to particles"],
        "difficulty": "beginner",
        "use_count": 960,
        "like_count": 355,
        "favorite_count": 200,
    },
    {
        "prompt_text": (
            "A calligrapher writes a single Chinese character with a large brush on rice paper, "
            "camera positioned directly overhead looking down. The ink flows from the brush tip "
            "in confident strokes, bleeding slightly at the edges into the paper grain. "
            "The character completes stroke by stroke. Ink-stained fingers and a stone inkwell "
            "visible at the frame edges."
        ),
        "display_name_en": "Calligraphy Overhead",
        "display_name_zh": "俯瞰挥毫",
        "description_en": "Top-down view of a calligrapher completing a Chinese character stroke by stroke, ink bleeding into rice paper grain",
        "description_zh": "正上方俯拍书法家逐笔完成汉字，墨汁在宣纸纹理中晕染，墨手与砚台入画",
        "category": "portrait",
        "media_type": "video",
        "tags": ["portrait", "calligraphy", "overhead", "ink", "chinese", "process"],
        "style_keywords": ["top-down overhead", "ink bleed on grain", "stroke-by-stroke process"],
        "difficulty": "beginner",
        "use_count": 880,
        "like_count": 328,
        "favorite_count": 185,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VIDEO — FOOD (10)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Red wine poured into a crystal glass in extreme slow motion, the liquid hitting "
            "the bowl and splashing upward in a crown formation. Camera at glass-rim height. "
            "Deep ruby color catches overhead studio light. The splash settles into a swirling vortex "
            "as the glass fills. Black background, single key light."
        ),
        "display_name_en": "Wine Crown Splash",
        "display_name_zh": "红酒皇冠溅花",
        "description_en": "Extreme slow-motion red wine pour forming a crown splash inside a crystal glass, single key light on black",
        "description_zh": "极致慢动作红酒倒入水晶杯形成皇冠溅花，单一主光源映衬纯黑背景",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "wine", "slow-motion", "splash", "close-up", "studio"],
        "style_keywords": ["rim-height close-up", "crown splash formation", "single key light studio"],
        "difficulty": "intermediate",
        "use_count": 820,
        "like_count": 300,
        "favorite_count": 170,
    },
    {
        "prompt_text": (
            "A sharp knife slices through a ripe mango in one smooth motion, the blade revealing "
            "the bright orange flesh inside. Captured in slow motion at 240fps. "
            "Juice beads form instantly along the cut surface. The two halves separate and fall "
            "onto a marble cutting board. Soft side lighting from the left."
        ),
        "display_name_en": "Mango Slice Reveal",
        "display_name_zh": "芒果切开瞬间",
        "description_en": "240fps slow-motion knife slicing through a mango, juice beading on fresh orange flesh, halves falling onto marble",
        "description_zh": "240帧慢动作刀切芒果，鲜橙果肉上立即冒出汁珠，两半落在大理石案板上",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "fruit", "slow-motion", "knife", "cutting", "juice"],
        "style_keywords": ["240fps extreme slow-mo", "juice bead formation", "side-lit marble surface"],
        "difficulty": "beginner",
        "use_count": 910,
        "like_count": 335,
        "favorite_count": 188,
    },
    {
        "prompt_text": (
            "Steam rising from a freshly baked sourdough loaf as it's pulled from a Dutch oven, "
            "the crust crackling audibly. Camera tight on the bread surface showing ear expansion "
            "and caramelized crust texture. The baker's hands tilt the loaf to reveal the scoring "
            "pattern. Warm kitchen light from the oven interior. Flour dust in the air."
        ),
        "display_name_en": "Sourdough Steam Reveal",
        "display_name_zh": "酸面团出炉",
        "description_en": "Tight shot of sourdough pulled from a Dutch oven, steam pouring, crust crackling, scoring pattern revealed under warm oven light",
        "description_zh": "新出炉酸面包特写，蒸汽涌出铸铁锅，脆皮噼啪作响，划痕纹路在炉光下展现",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "bread", "baking", "steam", "close-up", "texture"],
        "style_keywords": ["tight surface detail", "steam pour reveal", "oven interior warm light"],
        "difficulty": "beginner",
        "use_count": 870,
        "like_count": 320,
        "favorite_count": 178,
    },
    {
        "prompt_text": (
            "Overhead time-lapse of a sushi chef assembling a platter: hands moving with precise "
            "speed placing nigiri pieces in a circular pattern on a wooden board. "
            "Each piece appears in its place almost magically as time compresses. "
            "Pickled ginger and wasabi are positioned last. The hands withdraw and the completed "
            "platter sits for a beat in the final frame."
        ),
        "display_name_en": "Sushi Assembly",
        "display_name_zh": "寿司拼盘成型",
        "description_en": "Top-down time-lapse of a sushi platter being assembled piece by piece, hands moving with compressed precision",
        "description_zh": "俯拍延时寿司拼盘逐件组装，双手在压缩时间中精确放置每一贯握寿司",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "sushi", "timelapse", "overhead", "assembly", "japanese"],
        "style_keywords": ["top-down timelapse", "precision hand choreography", "circular arrangement build"],
        "difficulty": "intermediate",
        "use_count": 780,
        "like_count": 288,
        "favorite_count": 160,
    },
    {
        "prompt_text": (
            "Chocolate ganache being poured over a layered cake, the dark glossy liquid cascading "
            "over the edges in thick rivulets. Camera orbits slowly around the cake on a turntable. "
            "The ganache coats the sides in a smooth curtain. Overhead diffused light catches the "
            "mirror-like surface. A few fresh raspberries garnish the top."
        ),
        "display_name_en": "Ganache Cascade",
        "display_name_zh": "巧克力瀑流",
        "description_en": "Orbiting shot of glossy ganache cascading over a cake on a turntable, mirror-like surface under diffused overhead light",
        "description_zh": "环绕拍摄旋转台上蛋糕的巧克力甘纳许淋面，亮泽如镜面在柔光下流淌",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "chocolate", "cake", "ganache", "orbit", "turntable"],
        "style_keywords": ["turntable orbit", "viscous cascade flow", "mirror-gloss surface"],
        "difficulty": "intermediate",
        "use_count": 750,
        "like_count": 276,
        "favorite_count": 154,
    },
    {
        "prompt_text": (
            "A bartender torches the surface of a crème brûlée, the sugar bubbling and caramelizing "
            "under the blue flame. Extreme close-up shows the sugar transitioning from white crystals "
            "to amber liquid to hardened caramel. Camera slowly pulls back to reveal the full ramekin. "
            "A spoon taps the surface and cracks through the glassy top."
        ),
        "display_name_en": "Brûlée Torch & Crack",
        "display_name_zh": "焦糖炙烤与敲裂",
        "description_en": "Macro view of sugar caramelizing under a torch, then pulling back as a spoon cracks through the glassy brûlée top",
        "description_zh": "微距拍摄焰枪下糖霜从白色结晶变为琥珀焦糖，拉远后汤匙敲裂玻璃般的表面",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "dessert", "brulee", "torch", "macro", "crack"],
        "style_keywords": ["macro caramelization", "pull-back reveal", "crack impact moment"],
        "difficulty": "intermediate",
        "use_count": 700,
        "like_count": 258,
        "favorite_count": 143,
    },
    {
        "prompt_text": (
            "A hand pulls a slice of pizza away from the pie, mozzarella stretching in long gooey "
            "strings that refuse to break. Slow motion captures the cheese stretch in detail. "
            "Camera positioned low at table level. Steam rises from the fresh slice. "
            "The cheese strings finally snap and recoil. Rustic wooden table, checkered tablecloth."
        ),
        "display_name_en": "Pizza Cheese Pull",
        "display_name_zh": "披萨拉丝",
        "description_en": "Low-angle slow-motion pizza slice pull with endless mozzarella stretch, strings snapping and recoiling over a rustic table",
        "description_zh": "低角度慢动作拉起披萨，马苏里拉长丝不断拉伸直到弹断回缩，质朴木桌背景",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "pizza", "cheese", "slow-motion", "stretch", "low-angle"],
        "style_keywords": ["table-level low angle", "cheese stretch slow-mo", "snap recoil moment"],
        "difficulty": "beginner",
        "use_count": 1020,
        "like_count": 380,
        "favorite_count": 215,
    },
    {
        "prompt_text": (
            "Espresso extraction from a bottomless portafilter, the camera positioned directly underneath "
            "looking up. Dark brown streams emerge, merge into a single flow, then develop tiger-stripe "
            "crema patterns. The liquid collects in a white ceramic cup below. "
            "Drops catch the light like caramel jewels. Entire shot lasts the 25-second extraction."
        ),
        "display_name_en": "Bottomless Espresso",
        "display_name_zh": "无底手柄萃取",
        "description_en": "Bottom-up view of espresso extraction through a naked portafilter, tiger-stripe crema forming, drops like caramel jewels",
        "description_zh": "从下方仰拍无底手柄咖啡萃取，虎纹油脂渐显，液滴如焦糖宝石闪耀",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "coffee", "espresso", "extraction", "close-up", "crema"],
        "style_keywords": ["bottom-up POV", "tiger-stripe crema flow", "real-time extraction"],
        "difficulty": "intermediate",
        "use_count": 840,
        "like_count": 310,
        "favorite_count": 172,
    },
    {
        "prompt_text": (
            "A hot pot bubbling vigorously at a round table, steam billowing upward. "
            "Camera starts overhead looking down into the churning red broth with visible chili peppers "
            "and Sichuan peppercorns, then slowly descends to table level showing chopsticks "
            "lowering thin-sliced beef into the roiling liquid. The meat curls instantly on contact."
        ),
        "display_name_en": "Hot Pot Plunge",
        "display_name_zh": "火锅涮肉",
        "description_en": "Overhead-to-table-level descent into a bubbling hot pot, chopsticks lowering beef that curls on contact with chili broth",
        "description_zh": "从俯拍降至桌面高度看翻滚的红汤火锅，筷子夹薄牛肉片入锅瞬间卷曲",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "hotpot", "sichuan", "steam", "descent-shot", "cooking"],
        "style_keywords": ["overhead-to-level descent", "rolling broth texture", "instant meat curl"],
        "difficulty": "beginner",
        "use_count": 930,
        "like_count": 342,
        "favorite_count": 192,
    },
    {
        "prompt_text": (
            "A waffle iron opens to reveal a perfectly golden Belgian waffle, steam escaping in a burst. "
            "Camera tight on the waffle surface showing deep grid indentations. "
            "Maple syrup is drizzled from above in a thin stream, filling each pocket. "
            "A pat of butter melts on top, spreading outward. Warm morning window light."
        ),
        "display_name_en": "Golden Waffle Morning",
        "display_name_zh": "金色华夫晨光",
        "description_en": "Tight shot of a waffle iron opening with a steam burst, syrup filling grid pockets, butter melting under morning light",
        "description_zh": "华夫饼机打开的特写，蒸汽涌出，枫糖浆注满每个格子，黄油在晨光中融化",
        "category": "food",
        "media_type": "video",
        "tags": ["food", "waffle", "breakfast", "syrup", "steam", "butter-melt"],
        "style_keywords": ["tight surface reveal", "syrup fill sequence", "butter melt spread"],
        "difficulty": "beginner",
        "use_count": 890,
        "like_count": 328,
        "favorite_count": 184,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VIDEO — ARCHITECTURE (10)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Drone flythrough of an abandoned Gothic cathedral, entering through a shattered "
            "rose window and descending into the nave. Shafts of colored light from remaining "
            "stained glass paint the stone floor. Pigeons scatter as the camera glides past "
            "crumbling pillars. Ivy creeps up the walls. Dust particles float in the light beams."
        ),
        "display_name_en": "Cathedral Flythrough",
        "display_name_zh": "哥特教堂穿越",
        "description_en": "FPV drone entering an abandoned Gothic cathedral through a shattered rose window, colored light shafts on crumbling stone",
        "description_zh": "FPV无人机穿过破碎玫瑰窗进入废弃哥特教堂，彩色光柱投射在碎裂石地上",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "gothic", "drone", "flythrough", "abandoned", "stained-glass"],
        "style_keywords": ["FPV flythrough entry", "colored light shaft painting", "decay texture detail"],
        "difficulty": "advanced",
        "use_count": 680,
        "like_count": 250,
        "favorite_count": 140,
    },
    {
        "prompt_text": (
            "Time-lapse of sunlight moving across a minimalist concrete interior throughout the day, "
            "a rectangular skylight casting a sharp geometric shadow that slowly tracks across the floor "
            "and up the opposite wall. The shadow shape warps as it climbs. "
            "Clean Tadao Ando-inspired space with smooth walls and water features."
        ),
        "display_name_en": "Concrete Light Clock",
        "display_name_zh": "混凝土光钟",
        "description_en": "Day-long time-lapse of a skylight shadow tracking across a minimalist concrete interior, warping as it climbs the wall",
        "description_zh": "全天延时拍摄天窗光影在极简混凝土空间中游移，投影攀上对面墙壁时变形",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "minimalist", "concrete", "timelapse", "shadow", "skylight"],
        "style_keywords": ["shadow tracking timelapse", "geometric warp progression", "Ando-inspired minimal"],
        "difficulty": "intermediate",
        "use_count": 620,
        "like_count": 228,
        "favorite_count": 128,
    },
    {
        "prompt_text": (
            "Steadicam walk through a traditional Moroccan riad, entering from a dark narrow corridor "
            "that opens into a sunlit courtyard with a central fountain. The camera follows the path "
            "of zellige tilework on the floor. Orange trees frame the courtyard. "
            "Water in the fountain catches sunlight. The transition from dark to bright is dramatic."
        ),
        "display_name_en": "Riad Courtyard Reveal",
        "display_name_zh": "摩洛哥庭院现身",
        "description_en": "Steadicam walk from dark corridor into a sunlit Moroccan riad courtyard, zellige tiles guiding the path to a fountain",
        "description_zh": "斯坦尼康从暗窄走廊走入阳光摩洛哥庭院，马赛克地砖引路至中央喷泉",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "moroccan", "riad", "steadicam", "courtyard", "reveal"],
        "style_keywords": ["dark-to-light steadicam", "tile-line path follow", "courtyard reveal"],
        "difficulty": "beginner",
        "use_count": 790,
        "like_count": 292,
        "favorite_count": 162,
    },
    {
        "prompt_text": (
            "Aerial descent along the exterior of a twisting parametric skyscraper, the camera hugging "
            "the glass facade as it spirals downward. Reflections of clouds and neighboring buildings "
            "warp on the curved surface. The twist of the structure creates an optical illusion. "
            "Sunset light turns the glass into panels of gold and copper."
        ),
        "display_name_en": "Twisted Tower Descent",
        "display_name_zh": "扭旋塔楼滑降",
        "description_en": "Aerial spiral descent along a parametric skyscraper facade, cloud reflections warping on twisted glass, sunset-gilded panels",
        "description_zh": "航拍沿参数化摩天楼立面螺旋下降，云的倒影在扭曲玻璃上变形，夕阳镀金",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "parametric", "skyscraper", "spiral", "descent", "sunset"],
        "style_keywords": ["facade-hugging spiral descent", "reflection warp on curve", "sunset glass gilding"],
        "difficulty": "advanced",
        "use_count": 540,
        "like_count": 198,
        "favorite_count": 110,
    },
    {
        "prompt_text": (
            "Camera walks slowly through a Japanese torii gate tunnel, hundreds of vermillion gates "
            "creating a rhythmic repeating corridor. Dappled forest light flickers between the gates. "
            "The perspective compression makes the tunnel seem infinite. "
            "A figure in the far distance walks ahead, barely visible."
        ),
        "display_name_en": "Torii Gate Passage",
        "display_name_zh": "千本鸟居穿行",
        "description_en": "Slow walk through a vermillion torii gate tunnel, flickering forest light, infinite perspective compression, distant lone figure",
        "description_zh": "缓慢穿行朱红千本鸟居隧道，树林光影闪烁，透视压缩似无尽延伸",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "torii", "japanese", "tunnel", "perspective", "walk-through"],
        "style_keywords": ["rhythmic gate repetition", "perspective compression infinity", "dappled flicker light"],
        "difficulty": "beginner",
        "use_count": 950,
        "like_count": 348,
        "favorite_count": 198,
    },
    {
        "prompt_text": (
            "A construction time-lapse showing a modern glass building rising floor by floor over months, "
            "cranes swinging, workers moving like ants. Clouds race overhead in accelerated time. "
            "The surrounding cityscape remains static while the building grows. "
            "Night and day cycle rapidly, the building skeleton lit by work lights at night."
        ),
        "display_name_en": "Building Rise Timelapse",
        "display_name_zh": "楼宇崛起",
        "description_en": "Months-compressed time-lapse of a glass building rising floor by floor, day-night cycling, cranes swinging",
        "description_zh": "数月压缩延时拍摄玻璃建筑逐层升起，昼夜快速交替，塔吊不停旋转",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "construction", "timelapse", "progress", "day-night", "crane"],
        "style_keywords": ["months-to-seconds compression", "day-night rapid cycle", "floor-by-floor growth"],
        "difficulty": "intermediate",
        "use_count": 660,
        "like_count": 242,
        "favorite_count": 135,
    },
    {
        "prompt_text": (
            "A slow elevator ride up a glass shaft inside a futuristic atrium, the camera looking "
            "outward through the glass at each floor passing by — gardens, offices, restaurants, "
            "a library, all visible in cross-section. The ride ends emerging through the roof "
            "onto a sky terrace with a panoramic city view."
        ),
        "display_name_en": "Atrium Elevator Rise",
        "display_name_zh": "中庭电梯升空",
        "description_en": "Glass elevator POV rising through a futuristic atrium, each floor visible in cross-section, emerging onto a sky terrace",
        "description_zh": "玻璃电梯视角穿越未来感中庭，每层横截面尽收眼底，最终升至天空露台",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "elevator", "atrium", "futuristic", "POV", "vertical"],
        "style_keywords": ["vertical POV ascent", "cross-section floor reveal", "rooftop emergence"],
        "difficulty": "intermediate",
        "use_count": 710,
        "like_count": 262,
        "favorite_count": 146,
    },
    {
        "prompt_text": (
            "FPV drone racing through a brutalist parking garage, swooping between concrete pillars "
            "and spiraling down ramps at speed. Fluorescent lights streak past. "
            "Tire marks and graffiti flash by on walls. The drone exits through an open barrier "
            "into bright daylight, the exposure blooming then adjusting."
        ),
        "display_name_en": "Brutalist Garage Sprint",
        "display_name_zh": "野兽派车库飞驰",
        "description_en": "FPV drone racing through a brutalist parking garage, spiraling ramps, fluorescent streaks, bursting into daylight",
        "description_zh": "FPV无人机穿越野兽派停车场，螺旋下坡道，荧光灯拉丝，冲出闸门迎接日光",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "brutalist", "FPV", "drone", "garage", "speed"],
        "style_keywords": ["FPV speed run", "fluorescent light streak", "dark-to-bright exposure bloom"],
        "difficulty": "advanced",
        "use_count": 580,
        "like_count": 215,
        "favorite_count": 120,
    },
    {
        "prompt_text": (
            "A traditional Chinese moon gate frames a Suzhou garden, camera positioned to look through "
            "the circular opening. A gentle rain falls, creating ripples in the pond beyond. "
            "Raindrops bead on lotus leaves. The scene through the moon gate is like a living painting "
            "that changes with each ripple. Muted green and grey palette."
        ),
        "display_name_en": "Moon Gate Rain Garden",
        "display_name_zh": "月洞门听雨",
        "description_en": "Static frame through a circular moon gate as rain falls on a Suzhou garden pond, ripples and lotus beads in muted greens",
        "description_zh": "透过月洞门的静止画面，雨落苏州园林池塘，涟漪与荷叶水珠在灰绿色中摇曳",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "chinese-garden", "moon-gate", "rain", "suzhou", "tranquil"],
        "style_keywords": ["circular frame composition", "rain ripple animation", "muted ink-wash palette"],
        "difficulty": "beginner",
        "use_count": 850,
        "like_count": 312,
        "favorite_count": 175,
    },
    {
        "prompt_text": (
            "Interior tracking shot through Frank Lloyd Wright's Fallingwater, following the horizontal "
            "concrete cantilevers as the camera moves from the living room over the waterfall. "
            "Through floor-to-ceiling windows, autumn foliage is visible. The sound of rushing water "
            "grows louder. Natural stone walls and warm wood tones inside."
        ),
        "display_name_en": "Fallingwater Flow",
        "display_name_zh": "流水别墅行走",
        "description_en": "Interior tracking through Fallingwater's cantilevered spaces, autumn trees through glass, waterfall presence growing",
        "description_zh": "室内跟拍穿越流水别墅悬挑空间，玻璃外秋叶可见，瀑布水声渐强",
        "category": "architecture",
        "media_type": "video",
        "tags": ["architecture", "fallingwater", "wright", "cantilever", "tracking", "autumn"],
        "style_keywords": ["horizontal tracking shot", "cantilever space flow", "nature-architecture fusion"],
        "difficulty": "intermediate",
        "use_count": 730,
        "like_count": 268,
        "favorite_count": 150,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VIDEO — PRODUCT (10)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "A luxury watch rotates on an invisible turntable, camera orbiting in the opposite direction "
            "for a double-rotation effect. The polished case catches studio lights in moving reflections. "
            "The second hand sweeps smoothly. Focus racks from the dial to the crown detail. "
            "Dark gradient background, two-tone warm and cool lighting."
        ),
        "display_name_en": "Watch Double Orbit",
        "display_name_zh": "腕表双向旋转",
        "description_en": "Counter-rotating camera and turntable showcasing a luxury watch, focus racking from dial to crown, two-tone studio lighting",
        "description_zh": "镜头与转台反向旋转展示奢华腕表，焦点从表盘切换至表冠，双色调影棚灯光",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "watch", "luxury", "rotation", "studio", "rack-focus"],
        "style_keywords": ["counter-rotation orbit", "moving reflection catch", "two-tone lighting"],
        "difficulty": "intermediate",
        "use_count": 740,
        "like_count": 272,
        "favorite_count": 152,
    },
    {
        "prompt_text": (
            "Unboxing sequence of a premium smartphone: hands lift the lid off a matte black box, "
            "revealing the device nestled in a molded insert. Camera positioned directly overhead. "
            "The phone is lifted out, plastic film peeled away in a satisfying strip revealing the glossy screen. "
            "Accessories are laid out one by one. Clean white desk, natural window light."
        ),
        "display_name_en": "Premium Unboxing",
        "display_name_zh": "旗舰开箱",
        "description_en": "Overhead unboxing of a premium smartphone, film peel reveal, accessories laid out on a clean white desk in natural light",
        "description_zh": "俯拍旗舰手机开箱，揭膜露出光亮屏幕，配件逐一摆放在白色桌面自然光下",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "unboxing", "smartphone", "overhead", "peel", "premium"],
        "style_keywords": ["overhead unboxing POV", "film peel satisfaction", "sequential layout"],
        "difficulty": "beginner",
        "use_count": 960,
        "like_count": 352,
        "favorite_count": 198,
    },
    {
        "prompt_text": (
            "A sneaker floats in mid-air and slowly disassembles into its component layers — outsole, "
            "midsole foam, insole, upper mesh, laces — each layer separating and spreading apart "
            "vertically. Camera orbits the exploded view. Each material texture is clearly visible. "
            "Neutral grey background, even studio lighting from all sides."
        ),
        "display_name_en": "Sneaker Exploded View",
        "display_name_zh": "运动鞋分解视图",
        "description_en": "Orbiting exploded-view animation of a sneaker, layers separating vertically, each material texture highlighted",
        "description_zh": "运动鞋爆炸分解视图环绕展示，各层材料垂直分离，每种材质纹理清晰可见",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "sneaker", "exploded-view", "materials", "orbit", "3D"],
        "style_keywords": ["vertical exploded separation", "material texture showcase", "neutral orbit studio"],
        "difficulty": "advanced",
        "use_count": 620,
        "like_count": 228,
        "favorite_count": 128,
    },
    {
        "prompt_text": (
            "A perfume bottle emerges from water in slow motion, droplets cascading off the glass surface. "
            "The camera follows the bottle as it rises, water sheeting away to reveal the label. "
            "Colored light refracts through the liquid inside — amber and rose tones. "
            "A single remaining droplet rolls down the bottle and falls off the base."
        ),
        "display_name_en": "Perfume Water Rise",
        "display_name_zh": "香水破水而出",
        "description_en": "Slow-motion perfume bottle rising from water, droplets cascading, colored light refracting through the liquid inside",
        "description_zh": "慢动作香水瓶从水中升起，水珠倾泻而下，琥珀玫瑰色光线穿透瓶中液体",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "perfume", "water", "slow-motion", "refraction", "luxury"],
        "style_keywords": ["water emergence slow-mo", "cascade droplet sheet", "colored light refraction"],
        "difficulty": "intermediate",
        "use_count": 810,
        "like_count": 298,
        "favorite_count": 166,
    },
    {
        "prompt_text": (
            "A laptop opens from closed to fully flat in one smooth motion, the screen illuminating "
            "as the lid passes 45 degrees. Camera positioned at hinge level, tracking the lid arc. "
            "The keyboard backlight fades on in sequence from center outward. "
            "A dark desk surface reflects the screen glow. Minimal, premium aesthetic."
        ),
        "display_name_en": "Laptop Open Sequence",
        "display_name_zh": "笔电开合仪式",
        "description_en": "Hinge-level tracking shot of a laptop opening, screen illuminating at 45 degrees, keyboard backlight cascading outward",
        "description_zh": "铰链高度跟拍笔记本电脑打开，屏幕在45度时亮起，键盘背光从中心向外扩散",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "laptop", "tech", "open-sequence", "backlight", "minimal"],
        "style_keywords": ["hinge-level arc tracking", "sequential backlight cascade", "screen illuminate reveal"],
        "difficulty": "beginner",
        "use_count": 880,
        "like_count": 324,
        "favorite_count": 182,
    },
    {
        "prompt_text": (
            "Macro shot of a fountain pen nib touching paper, ink flowing from the slit as the pen "
            "writes a cursive word in real time. Camera so close the paper fibers are visible. "
            "The ink spreads microscopically into the paper grain. A small ink pool forms at "
            "each pen lift. Warm desk lamp lighting from the upper left."
        ),
        "display_name_en": "Nib on Paper",
        "display_name_zh": "笔尖触纸",
        "description_en": "Extreme macro of a fountain pen nib writing on paper, ink flowing through the slit, spreading into visible paper fibers",
        "description_zh": "钢笔笔尖书写的极致微距，墨水从笔缝流出渗入可见的纸张纤维中",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "fountain-pen", "macro", "ink", "writing", "stationery"],
        "style_keywords": ["extreme macro nib", "ink capillary spread", "real-time writing"],
        "difficulty": "intermediate",
        "use_count": 700,
        "like_count": 258,
        "favorite_count": 144,
    },
    {
        "prompt_text": (
            "A pair of wireless earbuds levitates out of their charging case, the case lid opening "
            "on its own. The buds float to ear height and rotate to show all angles. "
            "A subtle LED pulse on the case indicates charging status. "
            "Camera starts on the case and tilts up to follow the floating buds. "
            "Clean white background, soft shadowless lighting."
        ),
        "display_name_en": "Earbuds Levitation",
        "display_name_zh": "耳机悬浮出仓",
        "description_en": "Case-to-float sequence of wireless earbuds levitating and rotating, LED pulse, camera tilting up on white shadowless background",
        "description_zh": "无线耳机从充电仓悬浮升起并旋转展示各角度，LED脉冲指示，无影白色背景",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "earbuds", "tech", "levitation", "tilt-up", "clean"],
        "style_keywords": ["levitation float reveal", "tilt-up follow", "shadowless white studio"],
        "difficulty": "beginner",
        "use_count": 850,
        "like_count": 312,
        "favorite_count": 175,
    },
    {
        "prompt_text": (
            "A ceramic mug being formed on a potter's wheel, hands shaping wet clay as it spins. "
            "Camera in close-up profile view. Water and slip fly off in centrifugal arcs. "
            "Fingers press and the clay walls rise. Time-lapse compresses the full forming process "
            "into ten seconds. Earthy warm tones, shallow depth of field on the hands."
        ),
        "display_name_en": "Pottery Wheel Creation",
        "display_name_zh": "陶轮塑形",
        "description_en": "Profile close-up time-lapse of hands shaping a mug on a potter's wheel, clay rising, water arcing, earthy warm tones",
        "description_zh": "侧面特写延时拍摄双手在陶轮上塑造杯子，陶土升起，水花飞溅，泥土暖色调",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "pottery", "ceramic", "timelapse", "hands", "craft"],
        "style_keywords": ["profile close-up timelapse", "centrifugal water arc", "clay wall rise"],
        "difficulty": "intermediate",
        "use_count": 720,
        "like_count": 265,
        "favorite_count": 148,
    },
    {
        "prompt_text": (
            "A sports car drives through a water curtain in slow motion, sheets of water parting "
            "over the aerodynamic body. Camera tracks alongside at wheel height. "
            "Water droplets bead on the waxed paint surface. The headlights cut through the spray. "
            "Dark tunnel environment with dramatic directional lighting from above."
        ),
        "display_name_en": "Car Water Curtain",
        "display_name_zh": "跑车破水帘",
        "description_en": "Wheel-height slow-motion tracking of a sports car slicing through a water curtain, droplets beading on waxed paint",
        "description_zh": "轮高慢动作跟拍跑车穿越水帘，水珠在蜡面车漆上凝结，前灯切开水雾",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "car", "automotive", "slow-motion", "water", "tracking"],
        "style_keywords": ["wheel-height tracking", "water curtain parting", "wax bead surface detail"],
        "difficulty": "advanced",
        "use_count": 670,
        "like_count": 248,
        "favorite_count": 138,
    },
    {
        "prompt_text": (
            "A leather bag is assembled in stop-motion: cut pieces fly into position, stitching "
            "appears thread by thread, hardware clasps click into place, and the final bag "
            "stands upright. Camera holds a fixed front-on studio frame throughout. "
            "Each component arrival is punctuated by a brief pause. "
            "Craft paper background, warm directional light."
        ),
        "display_name_en": "Bag Assembly Stop Motion",
        "display_name_zh": "皮包定格组装",
        "description_en": "Stop-motion assembly of a leather bag — pieces flying in, stitching appearing, hardware clicking — on a craft paper background",
        "description_zh": "皮包定格动画组装——皮片飞入就位、缝线逐针出现、五金扣合——牛皮纸背景",
        "category": "product",
        "media_type": "video",
        "tags": ["product", "leather-bag", "stop-motion", "assembly", "craft", "studio"],
        "style_keywords": ["stop-motion assembly", "fixed front-on frame", "component arrival rhythm"],
        "difficulty": "advanced",
        "use_count": 560,
        "like_count": 205,
        "favorite_count": 115,
    },
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    #  VIDEO — ABSTRACT (10)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    {
        "prompt_text": (
            "Thick streams of colored ink dropped into water, the camera capturing the underwater "
            "expansion in slow motion. Crimson, indigo, and gold plumes billow and intertwine "
            "like underwater auroras. The camera slowly rotates, shifting the orientation of gravity "
            "in the viewer's perception. Black background, backlit from behind the tank."
        ),
        "display_name_en": "Ink Aurora Underwater",
        "display_name_zh": "水中墨极光",
        "description_en": "Slow-motion ink plumes billowing underwater in crimson, indigo and gold, camera rotating to shift gravity perception",
        "description_zh": "慢动作墨水在水中扩散如极光，深红靛蓝与金色翻卷交织，镜头旋转颠覆重力感",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "ink", "underwater", "slow-motion", "rotation", "color"],
        "style_keywords": ["underwater ink billow", "gravity-shift rotation", "backlit tank silhouette"],
        "difficulty": "intermediate",
        "use_count": 780,
        "like_count": 288,
        "favorite_count": 160,
    },
    {
        "prompt_text": (
            "A kaleidoscope pattern generated from reflections of moving colored glass, "
            "the symmetry shifting and morphing in real time. The pattern breathes — expanding "
            "and contracting rhythmically. Colors cycle through warm to cool spectrums. "
            "Camera pushes slowly into the center of the pattern creating an infinite tunnel effect."
        ),
        "display_name_en": "Living Kaleidoscope",
        "display_name_zh": "活体万花筒",
        "description_en": "Morphing kaleidoscope of colored glass reflections breathing rhythmically, camera pushing into an infinite tunnel center",
        "description_zh": "彩色玻璃反射形成的万花筒图案有节奏地呼吸变幻，镜头推入中心形成无尽隧道",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "kaleidoscope", "symmetry", "tunnel", "color-cycle", "mesmerizing"],
        "style_keywords": ["breathing symmetry morph", "center push tunnel", "warm-cool color cycle"],
        "difficulty": "beginner",
        "use_count": 870,
        "like_count": 320,
        "favorite_count": 180,
    },
    {
        "prompt_text": (
            "Ferrofluid responding to a moving magnet beneath a glass surface, spikes forming "
            "and collapsing in organic wave patterns. Camera in extreme macro looking down. "
            "The magnetic liquid creates impossible-looking shapes that defy surface tension. "
            "Iridescent rainbow sheen on the black fluid. The magnet traces a slow circle."
        ),
        "display_name_en": "Ferrofluid Dance",
        "display_name_zh": "磁流体之舞",
        "description_en": "Macro top-down view of ferrofluid spiking and flowing in response to a circling magnet, iridescent sheen on black liquid",
        "description_zh": "俯拍微距磁流体随圆形磁场运动尖刺涌动，黑色液面上虹彩光泽闪烁",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "ferrofluid", "magnetic", "macro", "iridescent", "organic"],
        "style_keywords": ["macro top-down", "spike-collapse organic wave", "iridescent surface sheen"],
        "difficulty": "intermediate",
        "use_count": 720,
        "like_count": 265,
        "favorite_count": 148,
    },
    {
        "prompt_text": (
            "Particles simulating a murmuration of starlings, thousands of white dots swirling "
            "in coordinated patterns against a black void. The swarm compresses into a tight sphere, "
            "then explodes outward, then reforms into a flowing ribbon. "
            "Camera slowly pulls back to reveal the full scale of the formation."
        ),
        "display_name_en": "Digital Murmuration",
        "display_name_zh": "数字椋鸟风暴",
        "description_en": "Particle swarm murmuration — compress, explode, reform into ribbon — camera pulling back to reveal full scale against black",
        "description_zh": "粒子群模拟椋鸟风暴——压缩、爆散、重组为飘带——拉远镜头展现完整规模",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "particles", "murmuration", "swarm", "pull-back", "formation"],
        "style_keywords": ["swarm behavior simulation", "compress-explode-reform cycle", "scale reveal pull-back"],
        "difficulty": "advanced",
        "use_count": 640,
        "like_count": 235,
        "favorite_count": 132,
    },
    {
        "prompt_text": (
            "A single drop of water falls onto a vibrating speaker surface covered in cornstarch mixture, "
            "creating concentric ripple patterns that interact with standing wave nodes. "
            "The non-Newtonian fluid dances between liquid and solid states. "
            "High-speed camera captures the moment of impact. Colored LED lighting from below."
        ),
        "display_name_en": "Cymatics Drop Impact",
        "display_name_zh": "声波水滴冲击",
        "description_en": "High-speed capture of a water drop hitting a vibrating non-Newtonian surface, cymatics patterns forming under colored LEDs",
        "description_zh": "高速拍摄水滴击中振动非牛顿流体表面，声波图案在彩色LED底光下成形",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "cymatics", "high-speed", "non-newtonian", "vibration", "impact"],
        "style_keywords": ["high-speed impact capture", "standing wave interaction", "LED underlighting"],
        "difficulty": "advanced",
        "use_count": 560,
        "like_count": 208,
        "favorite_count": 115,
    },
    {
        "prompt_text": (
            "A gradient color field that slowly morphs and breathes, transitioning from deep ocean blue "
            "through emerald green to sunset orange over 10 seconds. The colors blend in organic, "
            "cloud-like formations rather than linear gradients. Subtle grain texture overlays the "
            "smooth color. Meditative and hypnotic in its simplicity."
        ),
        "display_name_en": "Breathing Color Field",
        "display_name_zh": "呼吸色域",
        "description_en": "Slowly morphing color field breathing from ocean blue through emerald to sunset orange in organic cloud formations",
        "description_zh": "缓慢变幻的色域从深海蓝经翡翠绿到日落橙，以有机云状形态呼吸流动",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "color-field", "gradient", "meditative", "minimal", "breathing"],
        "style_keywords": ["organic gradient morph", "cloud-form color blend", "meditative simplicity"],
        "difficulty": "beginner",
        "use_count": 940,
        "like_count": 345,
        "favorite_count": 195,
    },
    {
        "prompt_text": (
            "Macro footage of ice crystals forming on a glass surface in real time, fractal branches "
            "extending outward from nucleation points. The camera holds still as the frost pattern "
            "grows to fill the frame. Backlit from behind the glass, each crystal edge glows. "
            "Time is slightly accelerated to make the growth visible."
        ),
        "display_name_en": "Frost Crystal Growth",
        "display_name_zh": "霜晶生长",
        "description_en": "Real-time macro of ice crystals branching across glass, backlit edges glowing, fractal pattern filling the frame",
        "description_zh": "微距实时拍摄冰晶在玻璃上分枝生长，逆光边缘发光，分形图案逐渐填满画面",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "ice", "crystal", "macro", "growth", "fractal"],
        "style_keywords": ["macro static growth", "backlit edge glow", "fractal branch expansion"],
        "difficulty": "beginner",
        "use_count": 830,
        "like_count": 305,
        "favorite_count": 172,
    },
    {
        "prompt_text": (
            "Two high-viscosity paint colors — electric blue and hot pink — colliding in mid-air "
            "in extreme slow motion. The collision creates a mushroom-cloud shape as the paints merge "
            "and spiral around each other. Individual paint ligaments stretch and snap. "
            "Camera captures from the side, dark background, studio strobe frozen lighting."
        ),
        "display_name_en": "Paint Collision",
        "display_name_zh": "颜料对撞",
        "description_en": "Extreme slow-motion mid-air collision of blue and pink paint forming a mushroom cloud, ligaments stretching and snapping",
        "description_zh": "极致慢动作蓝色与粉色颜料在空中对撞形成蘑菇云，颜料丝拉伸断裂",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "paint", "collision", "slow-motion", "color", "strobe"],
        "style_keywords": ["mid-air collision capture", "mushroom cloud formation", "strobe freeze lighting"],
        "difficulty": "advanced",
        "use_count": 610,
        "like_count": 225,
        "favorite_count": 125,
    },
    {
        "prompt_text": (
            "A Möbius strip made of translucent material rotating slowly in space, "
            "the camera following an ant-like particle traveling along its surface to demonstrate "
            "the single-sided topology. Light refracts through the strip creating rainbow caustics "
            "on the surrounding dark space. The strip breathes — slightly flexing as it turns."
        ),
        "display_name_en": "Möbius Light Loop",
        "display_name_zh": "莫比乌斯光环",
        "description_en": "Slowly rotating translucent Möbius strip with a particle tracing its surface, rainbow caustics refracting into dark space",
        "description_zh": "半透明莫比乌斯带缓缓旋转，粒子沿单面拓扑行走，彩虹焦散投射到暗空间",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "mobius", "topology", "refraction", "rotation", "particle"],
        "style_keywords": ["topology surface trace", "translucent caustic refraction", "breathing flex rotation"],
        "difficulty": "intermediate",
        "use_count": 690,
        "like_count": 254,
        "favorite_count": 142,
    },
    {
        "prompt_text": (
            "Soap film stretched across a wire frame, iridescent colors flowing and swirling "
            "across the thin membrane as air currents disturb it. Camera in macro, the film "
            "occupies the entire frame. Thickness variations create moving bands of color — "
            "magenta, cyan, gold. The film thins at one edge, and a hole opens, "
            "expanding rapidly as the film retracts and snaps."
        ),
        "display_name_en": "Soap Film Burst",
        "display_name_zh": "皂膜虹彩破裂",
        "description_en": "Macro view of iridescent soap film swirling with color bands, thinning at one edge, then rupturing and snapping shut",
        "description_zh": "微距拍摄虹彩皂膜上色带流转，薄膜在一侧变薄后破裂，迅速收缩消失",
        "category": "abstract",
        "media_type": "video",
        "tags": ["abstract", "soap-film", "iridescence", "macro", "burst", "thin-film"],
        "style_keywords": ["full-frame macro film", "thin-film interference color", "rupture propagation"],
        "difficulty": "intermediate",
        "use_count": 750,
        "like_count": 276,
        "favorite_count": 154,
    },
]


# ═══════════════════════════════════════════════════════════════
#  DATABASE OPERATIONS
# ═══════════════════════════════════════════════════════════════


async def clear_templates(session) -> int:
    """Delete all existing templates (cascades to likes/favorites/usages).

    WARNING: This destroys preview_image_url and engagement data.
    Only use with --force-reset flag.
    """
    result = await session.execute(delete(PromptTemplate))
    count = result.rowcount
    await session.flush()
    logger.info("Cleared %d existing templates", count)
    return count


async def seed_data(session) -> int:
    """Incremental seed: only insert templates that don't already exist.

    Uses display_name_en as the dedup key. Existing templates (and their
    preview_image_url, engagement metrics, etc.) are preserved.
    """
    # Build set of existing display_name_en for fast lookup
    result = await session.execute(
        select(PromptTemplate.display_name_en).where(PromptTemplate.deleted_at.is_(None))
    )
    existing_names: set[str] = {row[0] for row in result.all()}
    logger.info("Found %d existing templates in DB", len(existing_names))

    now = datetime.now(UTC)
    total = len(TEMPLATES)
    inserted = 0
    skipped = 0

    for i, tpl in enumerate(TEMPLATES):
        if tpl["display_name_en"] in existing_names:
            skipped += 1
            continue

        tpl_data = dict(tpl)

        # Spread creation times over last 30 days
        hours_ago = (total - i) * (30 * 24 / total)
        created_at = now - timedelta(hours=hours_ago)

        use_count: int = tpl_data.pop("use_count", 0)
        like_count: int = tpl_data.pop("like_count", 0)
        favorite_count: int = tpl_data.pop("favorite_count", 0)

        trending = compute_trending(like_count, use_count, favorite_count, hours_ago)

        template = PromptTemplate(
            id=uuid4(),
            **tpl_data,
            parameters={},
            language="bilingual",
            source="curated",
            use_count=use_count,
            like_count=like_count,
            favorite_count=favorite_count,
            trending_score=round(trending, 6),
            is_active=True,
            created_at=created_at,
        )
        session.add(template)
        inserted += 1

    await session.flush()
    logger.info("Inserted %d new templates, skipped %d existing", inserted, skipped)
    return inserted


async def generate_preview_images(session, *, delay: float = 5.0) -> tuple[int, int]:
    """Generate preview images for templates with NULL preview_image_url.

    Delegates to the shared PreviewGenerator service (services/preview_generator.py).
    """
    from services.preview_generator import PreviewGenerator

    generator = PreviewGenerator()
    return await generator.run(session, delay=delay)


# ═══════════════════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════════════════


async def main(args) -> None:
    """Main entry point.

    Default mode is incremental: insert only new templates, preserve existing data.
    Use --force-reset to wipe and re-seed from scratch (destroys preview URLs!).
    """
    await init_database()

    async for session in get_session():
        if not args.images_only:
            if args.force_reset:
                cleared = await clear_templates(session)
                if cleared:
                    print(f"Force-reset: cleared {cleared} existing templates.")

            inserted = await seed_data(session)
            print(f"Seeded {inserted} new prompt templates (incremental).")

        if not args.data_only:
            # Generate preview images
            print("\nStarting preview image generation...")
            success, fail = await generate_preview_images(session, delay=args.delay)
            print(f"\nPreview images: {success} generated, {fail} failed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed prompt templates (image + video)")
    parser.add_argument(
        "--data-only",
        action="store_true",
        help="Only insert data, skip image generation",
    )
    parser.add_argument(
        "--images-only",
        action="store_true",
        help="Only generate images for templates with NULL preview_image_url",
    )
    parser.add_argument(
        "--force-reset",
        action="store_true",
        help="WARNING: Clear ALL templates before seeding (destroys preview URLs and engagement data)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=5.0,
        help="Seconds between API requests (default 5, increase if rate-limited)",
    )
    args = parser.parse_args()

    if args.data_only and args.images_only:
        print("ERROR: --data-only and --images-only are mutually exclusive")
        sys.exit(1)

    asyncio.run(main(args))
