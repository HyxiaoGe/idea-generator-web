"""
Style transfer and image blending component.
"""
import asyncio
from io import BytesIO
import streamlit as st
from PIL import Image
from i18n import Translator
from services import (
    ImageGenerator,
    GenerationStateManager,
    get_throttle_remaining,
    get_history_sync,
)


def render_style_transfer(t: Translator, settings: dict, generator: ImageGenerator):
    """
    Render the style transfer and image blending interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        generator: ImageGenerator instance
    """
    # Initialize generation state
    GenerationStateManager.init_session_state()

    st.header(t("blend.title"))
    st.caption(t("blend.description"))

    # Check generation state
    is_generating = GenerationStateManager.is_generating()
    can_generate_state, block_reason = GenerationStateManager.can_start_generation()

    # Show throttle warning
    throttle_remaining = get_throttle_remaining()
    if throttle_remaining > 0 and not is_generating:
        st.caption(f"⏳ {t('generation.throttle_wait', seconds=f'{throttle_remaining:.1f}')}")

    # Tabs for different blend modes
    tab1, tab2 = st.tabs([t("blend.tab_style"), t("blend.tab_blend")])

    with tab1:
        render_style_transfer_mode(t, settings, generator)

    with tab2:
        render_blend_mode(t, settings, generator)


def render_style_transfer_mode(t: Translator, settings: dict, generator: ImageGenerator):
    """Style transfer: apply style from one image to another."""
    st.subheader(t("blend.style.title"))
    st.write(t("blend.style.description"))

    col1, col2 = st.columns(2)

    with col1:
        st.write(f"**{t('blend.style.content_image')}**")
        content_file = st.file_uploader(
            t("blend.style.upload_content"),
            type=["png", "jpg", "jpeg"],
            key="style_content_upload"
        )
        if content_file:
            content_image = Image.open(content_file)
            st.image(content_image, use_container_width=True)

    with col2:
        st.write(f"**{t('blend.style.style_image')}**")
        style_file = st.file_uploader(
            t("blend.style.upload_style"),
            type=["png", "jpg", "jpeg"],
            key="style_style_upload"
        )
        if style_file:
            style_image = Image.open(style_file)
            st.image(style_image, use_container_width=True)

    # Custom prompt
    prompt = st.text_input(
        t("blend.style.prompt_label"),
        value=t("blend.style.default_prompt"),
        key="style_transfer_prompt"
    )

    # Generate button
    can_generate = content_file is not None and style_file is not None and can_generate_state
    if st.button(t("blend.generate_btn"), type="primary", disabled=not can_generate, key="style_transfer_btn"):
        if can_generate:
            # Start generation task
            task = GenerationStateManager.start_generation(
                prompt=prompt,
                mode="style",
                resolution=settings.get("resolution", "1K")
            )

            with st.spinner(t("basic.generating")):
                content_img = Image.open(content_file)
                style_img = Image.open(style_file)

                try:
                    result = asyncio.run(generator.blend_images(
                        prompt=prompt,
                        images=[content_img, style_img],
                        aspect_ratio=settings["aspect_ratio"],
                        safety_level=settings.get("safety_level", "moderate"),
                    ))
                    GenerationStateManager.complete_generation(result=result)
                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.toast(f"{t('basic.error')}: {str(e)}", icon="❌")
                    return

            if result.error:
                icon = "🛡️" if result.safety_blocked else "❌"
                st.toast(f"{t('basic.error')}: {result.error}", icon=icon)
            elif result.image:
                st.subheader(t("basic.result"))
                st.image(result.image, use_container_width=True)

                if result.text:
                    st.write(result.text)

                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"⏱️ {t('basic.time_label')}: {result.duration:.2f} {t('basic.seconds')}")
                with col2:
                    buf = BytesIO()
                    result.image.save(buf, format="PNG")
                    st.download_button(
                        f"⬇️ {t('basic.download_btn')}",
                        data=buf.getvalue(),
                        file_name="style_transfer.png",
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
                    mode="style",
                    text_response=result.text,
                )

                # Toast notification for save success
                if filename:
                    st.toast(t("toast.image_saved", filename=filename), icon="✅")


def render_blend_mode(t: Translator, settings: dict, generator: ImageGenerator):
    """Multi-image blending mode."""
    # Check generation state (already initialized in parent)
    is_generating = GenerationStateManager.is_generating()
    can_generate_state, block_reason = GenerationStateManager.can_start_generation()

    st.subheader(t("blend.multi.title"))
    st.write(t("blend.multi.description"))

    # Multi-file uploader
    uploaded_files = st.file_uploader(
        t("blend.multi.upload"),
        type=["png", "jpg", "jpeg"],
        accept_multiple_files=True,
        key="blend_multi_upload"
    )

    # Show uploaded images
    if uploaded_files:
        st.write(f"{t('blend.multi.count')}: {len(uploaded_files)}")
        cols = st.columns(min(len(uploaded_files), 4))
        for idx, file in enumerate(uploaded_files[:4]):
            with cols[idx]:
                img = Image.open(file)
                st.image(img, use_container_width=True)
        if len(uploaded_files) > 4:
            st.caption(f"... {t('blend.multi.more', count=len(uploaded_files) - 4)}")

    # Prompt for blending
    prompt = st.text_area(
        t("blend.multi.prompt_label"),
        placeholder=t("blend.multi.prompt_placeholder"),
        height=100,
        key="blend_prompt"
    )

    # Generate button
    can_generate = uploaded_files and len(uploaded_files) >= 2 and prompt.strip() and can_generate_state
    if st.button(t("blend.generate_btn"), type="primary", disabled=not can_generate, key="blend_multi_btn"):
        if can_generate:
            # Start generation task
            task = GenerationStateManager.start_generation(
                prompt=prompt,
                mode="blend",
                resolution=settings.get("resolution", "1K")
            )

            with st.spinner(t("basic.generating")):
                images = [Image.open(f) for f in uploaded_files]

                try:
                    result = asyncio.run(generator.blend_images(
                        prompt=prompt,
                        images=images,
                        aspect_ratio=settings["aspect_ratio"],
                        safety_level=settings.get("safety_level", "moderate"),
                    ))
                    GenerationStateManager.complete_generation(result=result)
                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.toast(f"{t('basic.error')}: {str(e)}", icon="❌")
                    return

            if result.error:
                icon = "🛡️" if result.safety_blocked else "❌"
                st.toast(f"{t('basic.error')}: {result.error}", icon=icon)
            elif result.image:
                st.subheader(t("basic.result"))
                st.image(result.image, use_container_width=True)

                if result.text:
                    st.write(result.text)

                col1, col2 = st.columns([3, 1])
                with col1:
                    st.caption(f"⏱️ {t('basic.time_label')}: {result.duration:.2f} {t('basic.seconds')}")
                with col2:
                    buf = BytesIO()
                    result.image.save(buf, format="PNG")
                    st.download_button(
                        f"⬇️ {t('basic.download_btn')}",
                        data=buf.getvalue(),
                        file_name="blended_image.png",
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
                    mode="blend",
                    text_response=result.text,
                )

                # Toast notification for save success
                if filename:
                    st.toast(t("toast.image_saved", filename=filename), icon="✅")
