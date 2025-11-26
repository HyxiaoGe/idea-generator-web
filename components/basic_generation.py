"""
Basic image generation component.
"""
import asyncio
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import ImageGenerator, get_storage


def render_basic_generation(t: Translator, settings: dict, generator: ImageGenerator):
    """
    Render the basic image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        generator: ImageGenerator instance
    """
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

    # Generate button
    col1, col2 = st.columns([1, 4])
    with col1:
        generate_clicked = st.button(
            t("basic.generate_btn"),
            type="primary",
            use_container_width=True,
            disabled=not prompt.strip()
        )

    # Handle generation
    if generate_clicked and prompt.strip():
        with st.spinner(t("basic.generating")):
            # Run async generation
            result = asyncio.run(generator.generate(
                prompt=prompt,
                aspect_ratio=settings["aspect_ratio"],
                resolution=settings["resolution"],
                enable_thinking=settings["enable_thinking"],
                enable_search=settings["enable_search"],
            ))

        if result.error:
            st.error(f"{t('basic.error')}: {result.error}")
        elif result.image:
            # Save to disk
            storage = get_storage()
            filename = storage.save_image(
                image=result.image,
                prompt=prompt,
                settings=settings,
                duration=result.duration,
                mode="basic",
                text_response=result.text,
                thinking=result.thinking,
            )

            # Store in session for history
            if "history" not in st.session_state:
                st.session_state.history = []

            st.session_state.history.insert(0, {
                "prompt": prompt,
                "image": result.image,
                "text": result.text,
                "thinking": result.thinking,
                "duration": result.duration,
                "settings": settings.copy(),
                "filename": filename,
            })

            # Display result
            st.subheader(t("basic.result"))

            # Show thinking if available
            if result.thinking:
                with st.expander(t("basic.thinking_label"), expanded=False):
                    st.write(result.thinking)

            # Show image
            st.image(result.image, use_container_width=True)

            # Show text response
            if result.text:
                with st.expander(t("basic.response_label"), expanded=True):
                    st.write(result.text)

            # Show timing and download
            col1, col2, col3 = st.columns([2, 2, 1])
            with col1:
                st.caption(f"{t('basic.time_label')}: {result.duration:.2f} {t('basic.seconds')}")

            with col3:
                # Download button
                buf = BytesIO()
                result.image.save(buf, format="PNG")
                st.download_button(
                    t("basic.download_btn"),
                    data=buf.getvalue(),
                    file_name="generated_image.png",
                    mime="image/png"
                )
        else:
            st.warning(t("basic.no_image"))

    # Show last generated image if exists
    elif "history" in st.session_state and st.session_state.history:
        last = st.session_state.history[0]
        st.subheader(t("basic.result"))

        if last.get("thinking"):
            with st.expander(t("basic.thinking_label"), expanded=False):
                st.write(last["thinking"])

        st.image(last["image"], use_container_width=True)

        if last.get("text"):
            with st.expander(t("basic.response_label"), expanded=True):
                st.write(last["text"])

        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            st.caption(f"{t('basic.time_label')}: {last['duration']:.2f} {t('basic.seconds')}")

        with col3:
            buf = BytesIO()
            last["image"].save(buf, format="PNG")
            st.download_button(
                t("basic.download_btn"),
                data=buf.getvalue(),
                file_name="generated_image.png",
                mime="image/png"
            )
