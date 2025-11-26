"""
Image viewer utilities with zoom functionality.
"""
import base64
from io import BytesIO
from PIL import Image
import streamlit as st


def image_to_base64(image: Image.Image, format: str = "PNG") -> str:
    """Convert PIL Image to base64 string."""
    buffer = BytesIO()
    image.save(buffer, format=format)
    return base64.b64encode(buffer.getvalue()).decode()


def display_image_with_zoom(
    image: Image.Image,
    caption: str = None,
    key: str = None,
    use_container_width: bool = True
):
    """
    Display an image with hover zoom and click-to-fullscreen functionality.

    Args:
        image: PIL Image to display
        caption: Optional caption for the image
        key: Unique key for the component
        use_container_width: Whether to use full container width
    """
    if key is None:
        key = f"img_{id(image)}"

    img_base64 = image_to_base64(image)

    # CSS for zoom effect
    zoom_css = """
    <style>
    .zoom-container {
        position: relative;
        overflow: hidden;
        cursor: zoom-in;
        border-radius: 8px;
    }
    .zoom-container img {
        width: 100%;
        transition: transform 0.3s ease;
    }
    .zoom-container:hover img {
        transform: scale(1.05);
    }
    .zoom-hint {
        position: absolute;
        top: 8px;
        right: 8px;
        background: rgba(0, 0, 0, 0.6);
        color: white;
        padding: 4px 8px;
        border-radius: 4px;
        font-size: 12px;
        opacity: 0;
        transition: opacity 0.3s ease;
    }
    .zoom-container:hover .zoom-hint {
        opacity: 1;
    }

    /* Fullscreen modal */
    .fullscreen-modal {
        display: none;
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0, 0, 0, 0.9);
        z-index: 9999;
        justify-content: center;
        align-items: center;
        cursor: zoom-out;
    }
    .fullscreen-modal.active {
        display: flex;
    }
    .fullscreen-modal img {
        max-width: 95vw;
        max-height: 95vh;
        object-fit: contain;
    }
    .fullscreen-close {
        position: absolute;
        top: 20px;
        right: 30px;
        color: white;
        font-size: 30px;
        cursor: pointer;
        z-index: 10000;
    }
    </style>
    """

    # HTML for the image with zoom
    img_html = f"""
    {zoom_css}
    <div class="zoom-container" onclick="openFullscreen_{key}()">
        <img src="data:image/png;base64,{img_base64}" alt="{caption or 'Generated image'}">
        <span class="zoom-hint">🔍 Click to enlarge</span>
    </div>

    <div id="modal_{key}" class="fullscreen-modal" onclick="closeFullscreen_{key}()">
        <span class="fullscreen-close" onclick="closeFullscreen_{key}()">&times;</span>
        <img src="data:image/png;base64,{img_base64}" alt="{caption or 'Generated image'}">
    </div>

    <script>
    function openFullscreen_{key}() {{
        document.getElementById('modal_{key}').classList.add('active');
        document.body.style.overflow = 'hidden';
    }}
    function closeFullscreen_{key}() {{
        document.getElementById('modal_{key}').classList.remove('active');
        document.body.style.overflow = 'auto';
    }}
    // Close on Escape key
    document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            closeFullscreen_{key}();
        }}
    }});
    </script>
    """

    # Render the HTML
    st.components.v1.html(img_html, height=500 if use_container_width else 400)

    # Show caption if provided
    if caption:
        st.caption(caption)


def display_image_simple_zoom(
    image: Image.Image,
    key: str = None,
):
    """
    Display image with a simple magnifier button.
    Opens fullscreen view when clicked.

    Args:
        image: PIL Image to display
        key: Unique key for the component
    """
    if key is None:
        key = f"simple_img_{id(image)}"

    # Initialize session state for fullscreen
    fullscreen_key = f"fullscreen_{key}"
    if fullscreen_key not in st.session_state:
        st.session_state[fullscreen_key] = False

    # Display regular image
    st.image(image, use_container_width=True)

    # Magnifier button
    col1, col2, col3 = st.columns([3, 1, 1])
    with col2:
        if st.button("🔍", key=f"zoom_btn_{key}", help="View fullscreen"):
            st.session_state[fullscreen_key] = True
            st.rerun()

    # Show fullscreen modal if active
    if st.session_state.get(fullscreen_key, False):
        _show_fullscreen_modal(image, key, fullscreen_key)


def _show_fullscreen_modal(image: Image.Image, key: str, fullscreen_key: str):
    """Show fullscreen modal for image."""
    img_base64 = image_to_base64(image)

    modal_html = f"""
    <style>
    .st-fullscreen-overlay {{
        position: fixed;
        top: 0;
        left: 0;
        width: 100vw;
        height: 100vh;
        background: rgba(0, 0, 0, 0.95);
        z-index: 999999;
        display: flex;
        justify-content: center;
        align-items: center;
    }}
    .st-fullscreen-image {{
        max-width: 95vw;
        max-height: 95vh;
        object-fit: contain;
    }}
    .st-fullscreen-close {{
        position: fixed;
        top: 20px;
        right: 30px;
        color: white;
        font-size: 40px;
        cursor: pointer;
        z-index: 1000000;
        font-weight: bold;
    }}
    .st-fullscreen-hint {{
        position: fixed;
        bottom: 20px;
        left: 50%;
        transform: translateX(-50%);
        color: white;
        font-size: 14px;
        opacity: 0.7;
    }}
    </style>
    <div class="st-fullscreen-overlay" id="overlay_{key}">
        <span class="st-fullscreen-close" onclick="closeModal()">×</span>
        <img class="st-fullscreen-image" src="data:image/png;base64,{img_base64}">
        <div class="st-fullscreen-hint">Press ESC or click × to close</div>
    </div>
    <script>
    function closeModal() {{
        document.getElementById('overlay_{key}').style.display = 'none';
    }}
    document.addEventListener('keydown', function(e) {{
        if (e.key === 'Escape') {{
            closeModal();
        }}
    }});
    </script>
    """

    st.components.v1.html(modal_html, height=0)

    # Add close button in Streamlit
    if st.button("Close fullscreen", key=f"close_fullscreen_{key}"):
        st.session_state[fullscreen_key] = False
        st.rerun()
