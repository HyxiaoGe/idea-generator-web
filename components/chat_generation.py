"""
Chat-based image generation component for iterative refinement.
"""
from io import BytesIO
import streamlit as st
from i18n import Translator
from services import (
    ChatSession,
    GenerationStateManager,
    get_history_sync,
    get_friendly_error_message,
)
from utils import run_async


def render_chat_generation(t: Translator, settings: dict, chat_session: ChatSession):
    """
    Render the chat-based image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        chat_session: ChatSession instance
    """
    # Initialize generation state
    GenerationStateManager.init_session_state()

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

                # Download button - compact style
                buf = BytesIO()
                message["image"].save(buf, format="PNG")
                st.download_button(
                    f"⬇️ {t('history.download_btn')}",
                    data=buf.getvalue(),
                    file_name=f"chat_{idx + 1}.png",
                    mime="image/png",
                    key=f"download_chat_{idx}",
                    use_container_width=False
                )

    # Check generation state
    is_generating = GenerationStateManager.is_generating()
    can_generate, block_reason = GenerationStateManager.can_start_generation()

    # Chat input (disabled during generation)
    if prompt := st.chat_input(t("chat.input_placeholder"), disabled=is_generating):
        if not can_generate:
            st.warning(f"⚠️ {block_reason}")
            return

        # Add user message
        st.session_state.chat_messages.append({
            "role": "user",
            "content": prompt,
            "image": None
        })

        # Display user message immediately
        with st.chat_message("user", avatar="👤"):
            st.write(prompt)

        # Start generation task
        task = GenerationStateManager.start_generation(
            prompt=prompt,
            mode="chat",
            resolution=settings.get("resolution", "1K")
        )

        # Generate response
        with st.chat_message("assistant", avatar="🤖"):
            with st.spinner(t("basic.generating")):
                # Ensure session is started
                if not chat_session.is_active():
                    chat_session.start_session(aspect_ratio=settings["aspect_ratio"])

                try:
                    # Send message
                    response = run_async(chat_session.send_message(
                        message=prompt,
                        aspect_ratio=settings["aspect_ratio"],
                        safety_level=settings.get("safety_level", "moderate"),
                    ))
                    GenerationStateManager.complete_generation(result=response)
                except Exception as e:
                    GenerationStateManager.complete_generation(error=str(e))
                    st.error(f"❌ {t('basic.error')}: {get_friendly_error_message(str(e))}")
                    st.rerun()

            if response.error:
                icon = "🛡️" if response.safety_blocked else "❌"
                friendly_error = get_friendly_error_message(response.error)
                st.error(f"{icon} {t('basic.error')}: {friendly_error}")
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": f"Error: {friendly_error}",
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

                    # Download button - compact style
                    buf = BytesIO()
                    response.image.save(buf, format="PNG")
                    st.download_button(
                        f"⬇️ {t('history.download_btn')}",
                        data=buf.getvalue(),
                        file_name=f"chat_{len(st.session_state.chat_messages) + 1}.png",
                        mime="image/png",
                        key=f"download_chat_new",
                        use_container_width=False
                    )

                # Store in history using sync manager
                if response.image:
                    history_sync = get_history_sync()
                    filename = history_sync.save_to_history(
                        image=response.image,
                        prompt=prompt,
                        settings=settings,
                        duration=response.duration,
                        mode="chat",
                        text_response=response.text,
                        thinking=response.thinking,
                    )

                    # Toast notification for save success
                    if filename:
                        st.toast(t("toast.image_saved", filename=filename), icon="✅")

                # Add to chat messages
                st.session_state.chat_messages.append({
                    "role": "assistant",
                    "content": response.text or "",
                    "image": response.image,
                    "thinking": response.thinking
                })

        st.rerun()
