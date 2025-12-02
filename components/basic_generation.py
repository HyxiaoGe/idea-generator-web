"""
Basic image generation component.
"""
import time
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import (
    ImageGenerator,
    GenerationStateManager,
    get_current_user_history_sync,
    get_friendly_error_message,
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
                if st.button(example, key=f"example_{hash(example)}", width="stretch"):
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

    # Show tips when prompt is empty
    if not prompt.strip():
        st.caption(f"💡 {t('basic.empty_hint')}")
        with st.expander(t("basic.tip_title"), expanded=False):
            tips = t("basic.tips")
            if isinstance(tips, list):
                for tip in tips:
                    st.markdown(f"- {tip}")

    # Check generation state
    is_generating = GenerationStateManager.is_generating()
    can_generate, block_reason = GenerationStateManager.can_start_generation()

    # Generate button
    button_disabled = not prompt.strip() or not can_generate

    generate_clicked = st.button(
        t("basic.generate_btn") if not is_generating else t("basic.generating"),
        type="primary",
        disabled=button_disabled
    )

    # Handle generation button click - start task and rerun to update UI
    if generate_clicked and prompt.strip() and can_generate:
        # Save generation params to session state for use after rerun
        st.session_state._pending_generation = {
            "prompt": prompt,
            "settings": settings.copy(),
        }
        # Start generation task (sets is_generating = True)
        GenerationStateManager.start_generation(
            prompt=prompt,
            mode="basic",
            resolution=settings["resolution"]
        )
        # Rerun immediately to update button state (disable it)
        st.rerun()

    # Execute generation when is_generating is True
    if is_generating and "_pending_generation" in st.session_state:
        pending = st.session_state._pending_generation
        gen_prompt = pending["prompt"]
        gen_settings = pending["settings"]

        # Create a placeholder for progress
        progress_container = st.empty()
        status_container = st.empty()

        result = None
        with status_container.container():
            # Show progress indicator
            estimated_time = GenerationStateManager.ESTIMATED_TIMES.get(
                gen_settings["resolution"], 10.0
            )
            st.info(f"🎨 {t('generation.in_progress')} ({t('generation.estimated_time', seconds=f'{estimated_time:.0f}')})")

            # Progress bar
            progress_bar = st.progress(0, text=t("basic.generating"))

            try:
                # Run sync generation
                result = generator.generate(
                    prompt=gen_prompt,
                    aspect_ratio=gen_settings["aspect_ratio"],
                    resolution=gen_settings["resolution"],
                    enable_thinking=gen_settings["enable_thinking"],
                    enable_search=gen_settings["enable_search"],
                    safety_level=gen_settings.get("safety_level", "moderate"),
                )

                # Update progress to 100%
                progress_bar.progress(1.0, text=t("generation.complete"))

                # Complete the generation task
                GenerationStateManager.complete_generation(
                    result=result,
                    error=result.error if result.error else None
                )

            except Exception as e:
                GenerationStateManager.complete_generation(error=str(e))
                del st.session_state._pending_generation
                st.error(f"❌ {t('basic.error')}: {get_friendly_error_message(str(e), t)}")
                return

        # Clean up pending generation
        del st.session_state._pending_generation

        # Clear progress containers
        progress_container.empty()
        status_container.empty()

        # Handle result
        if result.error:
            icon = "🛡️" if result.safety_blocked else "❌"
            st.error(f"{icon} {t('basic.error')}: {get_friendly_error_message(result.error, t)}")
        elif result.image:
            # Save using history sync manager (user-specific)
            history_sync = get_current_user_history_sync()
            filename = history_sync.save_to_history(
                image=result.image,
                prompt=gen_prompt,
                settings=gen_settings,
                duration=result.duration,
                mode="basic",
                text_response=result.text,
                thinking=result.thinking,
            )

            # Toast notification for save success
            if filename:
                st.toast(t("toast.image_saved", filename=filename), icon="✅")

            # Store as last result for this mode
            st.session_state.basic_last_result = {
                "image": result.image,
                "text": result.text,
                "thinking": result.thinking,
                "duration": result.duration,
                "filename": filename,
            }

            # Display result
            _display_result(t, result.image, result.text, result.thinking,
                           result.duration, filename)
        else:
            st.warning(f"⚠️ {t('basic.no_image')}")

    # Show last generated image from current session (only for basic mode)
    elif not is_generating and "basic_last_result" in st.session_state and st.session_state.basic_last_result:
        _display_history_item(t, st.session_state.basic_last_result)


def _display_result(t: Translator, image, text: str, thinking: str,
                   duration: float, filename: str):
    """Display the generation result."""
    st.subheader(t("basic.result"))

    # Show thinking if available
    if thinking:
        with st.expander(t("basic.thinking_label"), expanded=False):
            st.write(thinking)

    # Show image
    st.image(image, width="stretch")

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
            width="stretch"
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

    # Show image
    st.image(item["image"], width="stretch")

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
            width="stretch"
        )

    if item.get("text"):
        with st.expander(t("basic.response_label"), expanded=False):
            st.write(item["text"])
