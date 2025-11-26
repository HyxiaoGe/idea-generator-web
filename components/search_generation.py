"""
Search-grounded image generation component.
"""
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import (
    ImageGenerator,
    GenerationStateManager,
    get_history_sync,
)
from utils import run_async


def render_search_generation(t: Translator, settings: dict, generator: ImageGenerator):
    """
    Render the search-grounded image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        generator: ImageGenerator instance
    """
    # Initialize generation state
    GenerationStateManager.init_session_state()

    st.header(t("search.title"))
    st.caption(t("search.description"))

    # Example prompts that benefit from real-time data
    with st.expander(t("search.examples.title"), expanded=False):
        examples = t("search.examples.items")
        if isinstance(examples, list):
            for example in examples:
                if st.button(example, key=f"search_example_{hash(example)}", use_container_width=True):
                    st.session_state.search_prompt = example
                    st.rerun()

    # Prompt input
    prompt = st.text_area(
        t("search.prompt_label"),
        placeholder=t("search.prompt_placeholder"),
        height=100,
        key="search_prompt",
        value=st.session_state.get("search_prompt", "")
    )

    # Info about search grounding
    st.info(t("search.info"))

    # Check generation state
    is_generating = GenerationStateManager.is_generating()
    can_generate, block_reason = GenerationStateManager.can_start_generation()

    # Generate button
    button_disabled = not prompt.strip() or not can_generate
    if st.button(t("basic.generate_btn"), type="primary", disabled=button_disabled):
        if prompt.strip() and can_generate:
            # Start generation task
            task = GenerationStateManager.start_generation(
                prompt=prompt,
                mode="search",
                resolution=settings.get("resolution", "1K")
            )

            with st.spinner(t("basic.generating")):
                try:
                    result = run_async(generator.generate_with_search(
                        prompt=prompt,
                        aspect_ratio=settings["aspect_ratio"],
                        safety_level=settings.get("safety_level", "moderate"),
                    ))
                    GenerationStateManager.complete_generation(result=result)
                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.error(f"❌ {t('basic.error')}: {str(e)}")
                    return

            if result.error:
                icon = "🛡️" if result.safety_blocked else "❌"
                st.error(f"{icon} {t('basic.error')}: {result.error}")
            elif result.image:
                st.subheader(t("basic.result"))
                st.image(result.image, use_container_width=True)

                # Show text response
                if result.text:
                    with st.expander(t("basic.response_label"), expanded=True):
                        st.write(result.text)

                # Show search sources
                if result.search_sources:
                    with st.expander(t("search.sources_label"), expanded=False):
                        st.markdown(result.search_sources, unsafe_allow_html=True)

                # Timing and download
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"⏱️ {t('basic.time_label')}: {result.duration:.2f} {t('basic.seconds')}")
                with col2:
                    buf = BytesIO()
                    result.image.save(buf, format="PNG")
                    st.download_button(
                        f"⬇️ {t('basic.download_btn')}",
                        data=buf.getvalue(),
                        file_name="search_generated.png",
                        mime="image/png",
                        use_container_width=True
                    )

                # Save to history using sync manager
                history_sync = get_history_sync()
                filename = history_sync.save_to_history(
                    image=result.image,
                    prompt=prompt,
                    settings=settings,
                    duration=result.duration,
                    mode="search",
                    text_response=result.text,
                )

                # Toast notification for save success
                if filename:
                    st.toast(t("toast.image_saved", filename=filename), icon="✅")
            else:
                st.warning(f"⚠️ {t('basic.no_image')}")
