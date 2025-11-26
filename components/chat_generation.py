"""
Chat-based image generation component for iterative refinement.
"""
import asyncio
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import ChatSession


def render_chat_generation(t: Translator, settings: dict, chat_session: ChatSession):
    """
    Render the chat-based image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        chat_session: ChatSession instance
    """
    st.header(t("chat.title"))
    st.caption(t("chat.description"))

    # Initialize chat messages in session state
    if "chat_messages" not in st.session_state:
        st.session_state.chat_messages = []

    # Control buttons
    col1, col2, col3 = st.columns([1, 1, 3])
    with col1:
        if st.button(t("chat.start_btn"), use_container_width=True):
            chat_session.clear_session()
            chat_session.start_session(aspect_ratio=settings["aspect_ratio"])
            st.session_state.chat_messages = [{
                "role": "assistant",
                "content": t("chat.welcome"),
                "image": None
            }]
            st.rerun()

    with col2:
        if st.button(t("chat.clear_btn"), use_container_width=True):
            chat_session.clear_session()
            st.session_state.chat_messages = []
            st.rerun()

    st.divider()

    # Show refinement tips if no messages yet
    if not st.session_state.chat_messages:
        st.info(t("chat.new_session_tip"))

        with st.expander(t("chat.refine_tips.title"), expanded=True):
            tips = t("chat.refine_tips.items")
            if isinstance(tips, list):
                for tip in tips:
                    st.write(f"- {tip}")
        return

    # Display chat messages
    for idx, message in enumerate(st.session_state.chat_messages):
        role = message["role"]
        avatar = "🤖" if role == "assistant" else "👤"

        with st.chat_message(role, avatar=avatar):
            # Show text content
            if message.get("content"):
                st.write(message["content"])

            # Show thinking if available
            if message.get("thinking"):
                with st.expander(t("chat.thinking_label"), expanded=False):
                    st.write(message["thinking"])

            # Show image if available
            if message.get("image"):
                st.image(message["image"], use_container_width=True)

                # Download button
                buf = BytesIO()
                message["image"].save(buf, format="PNG")
                st.download_button(
                    t("history.download_btn"),
                    data=buf.getvalue(),
                    file_name=f"chat_image_{idx}.png",
                    mime="image/png",
                    key=f"download_chat_{idx}"
                )

    # Chat input
    if prompt := st.chat_input(t("chat.input_placeholder")):
        # Add user message
        st.session_state.chat_messages.append({
            "role": "user",
            "content": prompt,
            "image": None
        })

        # Display user message immediately
        with st.chat_message("user", avatar="👤"):
            st.write(prompt)

        # Generate response
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner(t("basic.generating")):
                # Ensure session is started
                if not chat_session.is_active():
                    chat_session.start_session(aspect_ratio=settings["aspect_ratio"])

                # Send message
                response = asyncio.run(chat_session.send_message(
                    message=prompt,
                    aspect_ratio=settings["aspect_ratio"]
                ))

            if response.error:
                st.error(f"{t('basic.error')}: {response.error}")
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": f"Error: {response.error}",
                    "image": None
                })
            else:
                # Show response
                if response.text:
                    st.write(response.text)

                if response.thinking:
                    with st.expander(t("chat.thinking_label"), expanded=False):
                        st.write(response.thinking)

                if response.image:
                    st.image(response.image, use_container_width=True)

                    # Download button
                    buf = BytesIO()
                    response.image.save(buf, format="PNG")
                    st.download_button(
                        t("history.download_btn"),
                        data=buf.getvalue(),
                        file_name=f"chat_image_{len(st.session_state.chat_messages)}.png",
                        mime="image/png",
                        key=f"download_chat_new"
                    )

                # Store in history
                if "history" not in st.session_state:
                    st.session_state.history = []

                if response.image:
                    st.session_state.history.insert(0, {
                        "prompt": prompt,
                        "image": response.image,
                        "text": response.text,
                        "thinking": response.thinking,
                        "duration": response.duration,
                        "settings": settings.copy(),
                    })

                # Add to chat messages
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": response.text or "",
                    "image": response.image,
                    "thinking": response.thinking
                })

        st.rerun()
