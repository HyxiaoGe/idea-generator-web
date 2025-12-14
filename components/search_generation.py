"""
Search-grounded image generation component.
"""
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import (
    ImageGenerator,
    GenerationStateManager,
    get_current_user_history_sync,
    get_friendly_error_message,
    is_trial_mode,
    get_content_filter,
)
from .trial_quota_display import check_and_show_quota_warning, consume_quota_after_generation


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
    
    # Consume quota if needed (after rerun)
    if "_quota_to_consume" in st.session_state:
        quota_info = st.session_state._quota_to_consume
        consume_quota_after_generation(
            quota_info["mode"],
            quota_info["resolution"],
            quota_info["count"],
            True
        )
        del st.session_state._quota_to_consume
        # Rerun to update quota display in sidebar
        st.rerun()

    st.header(t("search.title"))
    st.caption(t("search.description"))

    # Example prompts that benefit from real-time data
    with st.expander(t("search.examples.title"), expanded=False):
        examples = t("search.examples.items")
        if isinstance(examples, list):
            for example in examples:
                if st.button(example, key=f"search_example_{hash(example)}", width="stretch"):
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
            # Check content safety first (two-layer: keywords + AI)
            content_filter = get_content_filter()
            is_safe, blocked_reason = content_filter.is_safe(prompt)
            if not is_safe:
                st.error(content_filter.get_blocked_message(t.language, blocked_reason))
                if blocked_reason.startswith("keyword:"):
                    keyword = blocked_reason.split(":", 1)[1]
                    st.caption(f"🚫 {t('errors.blocked_keyword')}: `{keyword}`")
                return  # Blocked, stop here

            # Check trial quota if in trial mode
            if is_trial_mode():
                if not check_and_show_quota_warning(t, "search", settings.get("resolution", "1K"), 1):
                    return  # Quota exceeded, stop here
            # Start generation task
            task = GenerationStateManager.start_generation(
                prompt=prompt,
                mode="search",
                resolution=settings.get("resolution", "1K")
            )

            with st.spinner(t("basic.generating")):
                try:
                    result = generator.generate_with_search(
                        prompt=prompt,
                        aspect_ratio=settings["aspect_ratio"],
                        safety_level=settings.get("safety_level", "moderate"),
                    )
                    GenerationStateManager.complete_generation(result=result)
                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.error(f"❌ {t('basic.error')}: {get_friendly_error_message(str(e), t)}")
                    return

            if result.error:
                icon = "🛡️" if result.safety_blocked else "❌"
                st.error(f"{icon} {t('basic.error')}: {get_friendly_error_message(result.error, t)}")
            elif result.image:
                # Mark quota consumption needed (will be consumed after rerun)
                st.session_state._quota_to_consume = {
                    "mode": "search",
                    "resolution": settings.get("resolution", "1K"),
                    "count": 1
                }
                # Save to history using sync manager
                history_sync = get_current_user_history_sync()
                filename = history_sync.save_to_history(
                    image=result.image,
                    prompt=prompt,
                    settings=settings,
                    duration=result.duration,
                    mode="search",
                    text_response=result.text,
                )

                # Store as last result for this mode
                st.session_state.search_last_result = {
                    "image": result.image,
                    "text": result.text,
                    "search_sources": result.search_sources,
                    "duration": result.duration,
                    "filename": filename,
                    "prompt": prompt,
                }

                # Toast notification for save success
                if filename:
                    st.toast(t("toast.image_saved", filename=filename), icon="✅")

                # Display result
                _display_search_result(t, st.session_state.search_last_result)
            else:
                st.warning(f"⚠️ {t('basic.no_image')}")

    # Show last generated result from current session
    elif not is_generating and "search_last_result" in st.session_state and st.session_state.search_last_result:
        _display_search_result(t, st.session_state.search_last_result)


def _display_search_result(t: Translator, item: dict):
    """Display a search generation result."""
    st.subheader(t("basic.result"))
    st.image(item["image"], width="stretch")

    # Show text response
    if item.get("text"):
        with st.expander(t("basic.response_label"), expanded=True):
            st.write(item["text"])

    # Show search sources
    if item.get("search_sources"):
        with st.expander(t("search.sources_label"), expanded=False):
            st.markdown(item["search_sources"], unsafe_allow_html=True)

    # Timing and download
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"⏱️ {t('basic.time_label')}: {item['duration']:.2f} {t('basic.seconds')}")
    with col2:
        buf = BytesIO()
        item["image"].save(buf, format="PNG")
        filename = item.get("filename", "search_generated.png")
        if "/" in filename:
            filename = filename.split("/")[-1]
        st.download_button(
            f"⬇️ {t('basic.download_btn')}",
            data=buf.getvalue(),
            file_name=filename,
            mime="image/png",
            width="stretch"
        )
