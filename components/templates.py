"""
Prompt templates library component.
"""
import asyncio
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import ImageGenerator


# Template categories with example prompts
TEMPLATES = {
    "portrait": {
        "icon": "👤",
        "prompts": [
            "professional headshot photo",
            "artistic portrait with dramatic lighting",
            "vintage style portrait photo",
        ]
    },
    "product": {
        "icon": "📦",
        "prompts": [
            "product photography on white background",
            "lifestyle product shot with natural lighting",
            "minimalist product display",
        ]
    },
    "landscape": {
        "icon": "🏞️",
        "prompts": [
            "breathtaking mountain landscape at golden hour",
            "serene beach sunset with palm trees",
            "misty forest morning scene",
        ]
    },
    "art": {
        "icon": "🎨",
        "prompts": [
            "abstract oil painting with vibrant colors",
            "watercolor illustration in soft tones",
            "digital art in cyberpunk style",
        ]
    },
    "food": {
        "icon": "🍕",
        "prompts": [
            "gourmet food photography with garnish",
            "rustic homemade dish on wooden table",
            "colorful healthy breakfast spread",
        ]
    },
    "architecture": {
        "icon": "🏛️",
        "prompts": [
            "modern minimalist building exterior",
            "cozy interior design with warm lighting",
            "futuristic architecture concept",
        ]
    }
}


def render_templates(t: Translator, settings: dict, generator: ImageGenerator):
    """
    Render the prompt templates library interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        generator: ImageGenerator instance
    """
    st.header(t("templates.title"))
    st.caption(t("templates.description"))

    # Category tabs
    categories = list(TEMPLATES.keys())
    category_labels = [f"{TEMPLATES[c]['icon']} {t(f'templates.categories.{c}')}" for c in categories]

    selected_tab = st.radio(
        t("templates.select_category"),
        options=categories,
        format_func=lambda x: f"{TEMPLATES[x]['icon']} {t(f'templates.categories.{x}')}",
        horizontal=True,
        label_visibility="collapsed"
    )

    st.divider()

    # Show templates for selected category
    if selected_tab:
        prompts = t(f"templates.prompts.{selected_tab}")
        if not isinstance(prompts, list):
            # Fallback to English prompts
            prompts = TEMPLATES[selected_tab]["prompts"]

        # Create columns for template cards
        cols = st.columns(len(prompts))

        for idx, (col, prompt) in enumerate(zip(cols, prompts)):
            with col:
                with st.container(border=True):
                    st.write(f"**{t('templates.template')} {idx + 1}**")
                    st.caption(prompt[:50] + "..." if len(prompt) > 50 else prompt)
                    if st.button(t("templates.use_btn"), key=f"template_{selected_tab}_{idx}", use_container_width=True):
                        st.session_state.template_prompt = prompt
                        st.session_state.selected_template = f"{selected_tab}_{idx}"

    st.divider()

    # Prompt customization area
    st.subheader(t("templates.customize"))

    # Get base prompt from template or user input
    base_prompt = st.session_state.get("template_prompt", "")

    prompt = st.text_area(
        t("templates.prompt_label"),
        value=base_prompt,
        placeholder=t("templates.prompt_placeholder"),
        height=100,
        key="template_prompt_input"
    )

    # Subject/object input
    subject = st.text_input(
        t("templates.subject_label"),
        placeholder=t("templates.subject_placeholder"),
        key="template_subject"
    )

    # Build final prompt
    final_prompt = prompt
    if subject:
        final_prompt = f"{subject}, {prompt}"

    if final_prompt:
        with st.expander(t("templates.preview_label"), expanded=True):
            st.code(final_prompt, language=None)

    # Generate button
    if st.button(t("basic.generate_btn"), type="primary", disabled=not final_prompt.strip()):
        if final_prompt.strip():
            with st.spinner(t("basic.generating")):
                result = asyncio.run(generator.generate(
                    prompt=final_prompt,
                    aspect_ratio=settings["aspect_ratio"],
                    resolution=settings["resolution"],
                    enable_thinking=settings["enable_thinking"],
                    enable_search=settings["enable_search"],
                ))

            if result.error:
                st.error(f"{t('basic.error')}: {result.error}")
            elif result.image:
                st.subheader(t("basic.result"))

                if result.thinking:
                    with st.expander(t("basic.thinking_label"), expanded=False):
                        st.write(result.thinking)

                st.image(result.image, use_container_width=True)

                if result.text:
                    with st.expander(t("basic.response_label"), expanded=True):
                        st.write(result.text)

                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"{t('basic.time_label')}: {result.duration:.2f} {t('basic.seconds')}")
                with col2:
                    buf = BytesIO()
                    result.image.save(buf, format="PNG")
                    st.download_button(
                        t("basic.download_btn"),
                        data=buf.getvalue(),
                        file_name="template_generated.png",
                        mime="image/png"
                    )

                # Add to history
                if "history" not in st.session_state:
                    st.session_state.history = []
                st.session_state.history.insert(0, {
                    "prompt": final_prompt,
                    "image": result.image,
                    "text": result.text,
                    "thinking": result.thinking,
                    "duration": result.duration,
                    "settings": settings.copy(),
                })
            else:
                st.warning(t("basic.no_image"))
