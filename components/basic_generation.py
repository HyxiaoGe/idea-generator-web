"""
Basic image generation component.
"""
import asyncio
import time
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import (
    ImageGenerator,
    GenerationStateManager,
    get_throttle_remaining,
    get_history_sync,
)


def render_basic_generation(t: Translator, settings: dict, generator: ImageGenerator):
    """
    Render the basic image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        generator: ImageGenerator instance
    """
    # Initialize generation state
    GenerationStateManager.init_session_state()

    st.header(t("basic.title"))

    # Example prompts
    with st.expander(t("basic.examples.title"), expanded=False):
        examples = t("basic.examples.items")
        if isinstance(examples, list):
            for example in examples:
                if st.button(example, key=f"example_{hash(example)}", use_container_width=True):
                    st.session_state.prompt_input = example
                    st.rerun()

    # Prompt input
    prompt = st.text_area(
        t("basic.prompt_label"),
        placeholder=t("basic.prompt_placeholder"),
        height=100,
        key="prompt_input",
        value=st.session_state.get("prompt_input", "")
    )

    # Check generation state
    is_generating = GenerationStateManager.is_generating()
    can_generate, block_reason = GenerationStateManager.can_start_generation()

    # Generate button row
    col1, col2, col3 = st.columns([1, 1, 3])

    with col1:
        # Disable button if generating or throttled
        button_disabled = not prompt.strip() or not can_generate

        generate_clicked = st.button(
            t("basic.generate_btn") if not is_generating else t("basic.generating"),
            type="primary",
            use_container_width=True,
            disabled=button_disabled
        )

    with col2:
        # Show cancel button when generating
        if is_generating:
            if st.button(t("generation.cancel_btn"), use_container_width=True):
                GenerationStateManager.cancel_generation()
                st.toast(t("generation.cancelled"), icon="⚠️")
                st.rerun()

    # Show throttle warning
    throttle_remaining = get_throttle_remaining()
    if throttle_remaining > 0 and not is_generating:
        st.caption(f"⏳ {t('generation.throttle_wait', seconds=f'{throttle_remaining:.1f}')}")

    # Handle generation
    if generate_clicked and prompt.strip() and can_generate:
        # Start generation task
        task = GenerationStateManager.start_generation(
            prompt=prompt,
            mode="basic",
            resolution=settings["resolution"]
        )

        if task:
            # Create a placeholder for progress
            progress_container = st.empty()
            status_container = st.empty()

            with status_container.container():
                # Show progress indicator
                estimated_time = GenerationStateManager.ESTIMATED_TIMES.get(
                    settings["resolution"], 10.0
                )
                st.info(f"🎨 {t('generation.in_progress')} ({t('generation.estimated_time', seconds=f'{estimated_time:.0f}')})")

                # Progress bar
                progress_bar = st.progress(0, text=t("basic.generating"))

                # Simulate progress while waiting for API
                start_time = time.time()

                try:
                    # Check for cancellation
                    if GenerationStateManager.is_cancelled():
                        GenerationStateManager.complete_generation(error="Cancelled by user")
                        st.rerun()

                    # Run async generation
                    result = asyncio.run(generator.generate(
                        prompt=prompt,
                        aspect_ratio=settings["aspect_ratio"],
                        resolution=settings["resolution"],
                        enable_thinking=settings["enable_thinking"],
                        enable_search=settings["enable_search"],
                        safety_level=settings.get("safety_level", "moderate"),
                    ))

                    # Update progress to 100%
                    progress_bar.progress(1.0, text=t("generation.complete"))

                    # Complete the generation task
                    GenerationStateManager.complete_generation(
                        result=result,
                        error=result.error if result.error else None
                    )

                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.toast(f"{t('basic.error')}: {str(e)}", icon="❌")
                    st.rerun()

            # Clear progress containers
            progress_container.empty()
            status_container.empty()

            # Handle result
            if result.error:
                icon = "🛡️" if result.safety_blocked else "❌"
                st.toast(f"{t('basic.error')}: {result.error}", icon=icon)
            elif result.image:
                # Save using history sync manager
                history_sync = get_history_sync()
                filename = history_sync.save_to_history(
                    image=result.image,
                    prompt=prompt,
                    settings=settings,
                    duration=result.duration,
                    mode="basic",
                    text_response=result.text,
                    thinking=result.thinking,
                )

                # Toast notification for save success
                if filename:
                    st.toast(t("toast.image_saved", filename=filename), icon="✅")

                # Display result
                _display_result(t, result.image, result.text, result.thinking,
                               result.duration, filename)
            else:
                st.toast(t("basic.no_image"), icon="⚠️")

    # Show last generated image if exists (when not generating)
    elif not is_generating and "history" in st.session_state and st.session_state.history:
        last = st.session_state.history[0]
        _display_history_item(t, last)


def _display_result(t: Translator, image, text: str, thinking: str,
                   duration: float, filename: str):
    """Display the generation result."""
    st.subheader(t("basic.result"))

    # Show thinking if available
    if thinking:
        with st.expander(t("basic.thinking_label"), expanded=False):
            st.write(thinking)

    # Show image
    st.image(image, use_container_width=True)

    # Action bar: timing info and download button
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"⏱️ {t('basic.time_label')}: {duration:.2f} {t('basic.seconds')}")
    with col2:
        buf = BytesIO()
        image.save(buf, format="PNG")
        download_name = filename.split("/")[-1] if "/" in filename else filename
        st.download_button(
            f"⬇️ {t('basic.download_btn')}",
            data=buf.getvalue(),
            file_name=download_name,
            mime="image/png",
            use_container_width=True
        )

    # Show text response
    if text:
        with st.expander(t("basic.response_label"), expanded=False):
            st.write(text)


def _display_history_item(t: Translator, item: dict):
    """Display a history item."""
    st.subheader(t("basic.result"))

    if item.get("thinking"):
        with st.expander(t("basic.thinking_label"), expanded=False):
            st.write(item["thinking"])

    st.image(item["image"], use_container_width=True)

    # Action bar
    col1, col2 = st.columns([3, 1])
    with col1:
        st.caption(f"⏱️ {t('basic.time_label')}: {item['duration']:.2f} {t('basic.seconds')}")
    with col2:
        buf = BytesIO()
        item["image"].save(buf, format="PNG")
        download_name = item.get("filename", "generated_image.png")
        if "/" in download_name:
            download_name = download_name.split("/")[-1]
        st.download_button(
            f"⬇️ {t('basic.download_btn')}",
            data=buf.getvalue(),
            file_name=download_name,
            mime="image/png",
            use_container_width=True
        )

    if item.get("text"):
        with st.expander(t("basic.response_label"), expanded=False):
            st.write(item["text"])
