"""
Batch image generation component.
Generate multiple image variations from a single prompt.
"""
import asyncio
from io import BytesIO
from typing import List
import streamlit as st
from PIL import Image
from i18n import Translator
from services import ImageGenerator, get_storage
from services.cost_estimator import estimate_cost, format_cost


async def generate_batch(
    generator: ImageGenerator,
    prompt: str,
    count: int,
    aspect_ratio: str,
    resolution: str,
    safety_level: str = "moderate",
    progress_callback=None
) -> List:
    """Generate multiple images asynchronously."""
    results = []

    for i in range(count):
        result = await generator.generate(
            prompt=prompt,
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            enable_thinking=False,
            enable_search=False,
            safety_level=safety_level,
        )
        results.append(result)

        if progress_callback:
            progress_callback(i + 1, count)

    return results


def render_batch_generation(t: Translator, settings: dict, generator: ImageGenerator):
    """
    Render the batch image generation interface.

    Args:
        t: Translator instance
        settings: Current settings from sidebar
        generator: ImageGenerator instance
    """
    st.header(t("batch.title"))
    st.caption(t("batch.description"))

    # Prompt input
    prompt = st.text_area(
        t("batch.prompt_label"),
        placeholder=t("batch.prompt_placeholder"),
        height=100,
        key="batch_prompt"
    )

    # Batch settings
    col1, col2 = st.columns(2)

    with col1:
        count = st.slider(
            t("batch.count_label"),
            min_value=2,
            max_value=8,
            value=4,
            step=1,
            key="batch_count"
        )

    with col2:
        # Show cost estimate
        estimate = estimate_cost(settings["resolution"], count)
        st.metric(
            t("batch.cost_label"),
            f"${estimate.total_cost:.2f}",
            delta=f"{count} {t('batch.images')}",
            delta_color="off"
        )

    # Variation mode hint
    st.info(t("batch.variation_hint"))

    # Generate button
    can_generate = prompt.strip() != ""

    if st.button(t("basic.generate_btn"), type="primary", disabled=not can_generate):
        if can_generate:
            # Create status container for progress
            with st.status(t("batch.generating"), expanded=True) as status:
                progress_bar = st.progress(0, text=t("batch.progress_text", current=0, total=count))
                results_container = st.empty()

                # Progress callback
                def update_progress(current, total):
                    progress = current / total
                    progress_bar.progress(progress, text=t("batch.progress_text", current=current, total=total))

                # Run batch generation
                results = asyncio.run(generate_batch(
                    generator=generator,
                    prompt=prompt,
                    count=count,
                    aspect_ratio=settings["aspect_ratio"],
                    resolution=settings["resolution"],
                    safety_level=settings.get("safety_level", "moderate"),
                    progress_callback=update_progress
                ))

                status.update(label=t("batch.complete"), state="complete", expanded=True)

            # Display results
            st.subheader(t("batch.results"))

            # Calculate statistics
            successful = [r for r in results if r.image is not None]
            failed = [r for r in results if r.error is not None]
            total_time = sum(r.duration for r in results)

            # Show stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric(t("batch.successful"), len(successful))
            with col2:
                st.metric(t("batch.failed"), len(failed))
            with col3:
                st.metric(t("batch.total_time"), f"{total_time:.1f}s")

            st.divider()

            # Display images in grid
            if successful:
                cols = st.columns(min(len(successful), 4))

                for idx, result in enumerate(successful):
                    col_idx = idx % 4
                    with cols[col_idx]:
                        st.image(result.image, use_container_width=True)

                        # Download button
                        buf = BytesIO()
                        result.image.save(buf, format="PNG")
                        st.download_button(
                            f"{t('basic.download_btn')} {idx + 1}",
                            data=buf.getvalue(),
                            file_name=f"batch_{idx + 1}.png",
                            mime="image/png",
                            key=f"download_batch_{idx}",
                            use_container_width=True
                        )

                # Add to history and save to disk
                if "history" not in st.session_state:
                    st.session_state.history = []

                storage = get_storage()
                for idx, result in enumerate(successful):
                    # Save to disk
                    filename = storage.save_image(
                        image=result.image,
                        prompt=f"[Batch {idx + 1}/{len(successful)}] {prompt}",
                        settings=settings,
                        duration=result.duration,
                        mode="batch",
                        text_response=result.text,
                    )

                    st.session_state.history.insert(0, {
                        "prompt": f"[Batch {idx + 1}/{len(successful)}] {prompt}",
                        "image": result.image,
                        "text": result.text,
                        "duration": result.duration,
                        "settings": settings.copy(),
                        "filename": filename,
                    })

                # Toast notification for batch save success
                st.toast(t("toast.batch_saved", count=len(successful)), icon="✅")

            # Show errors if any
            if failed:
                st.toast(t("toast.batch_failed", count=len(failed)), icon="⚠️")
                with st.expander(t("batch.errors"), expanded=False):
                    for idx, result in enumerate(failed):
                        st.write(f"Image {idx + 1}: {result.error}")

            # Download all as ZIP - direct download without extra button
            if len(successful) > 1:
                st.divider()
                import zipfile
                import io
                from datetime import datetime

                zip_buffer = io.BytesIO()
                with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
                    for idx, result in enumerate(successful):
                        img_buffer = BytesIO()
                        result.image.save(img_buffer, format="PNG")
                        # Use descriptive filename in ZIP
                        prompt_slug = "".join(c if c.isalnum() or c == " " else "" for c in prompt[:20])
                        prompt_slug = "_".join(prompt_slug.split())
                        zip_file.writestr(f"batch_{idx + 1}_{prompt_slug}.png", img_buffer.getvalue())

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                st.download_button(
                    f"📦 {t('batch.download_all')} ({len(successful)} {t('batch.images')})",
                    data=zip_buffer.getvalue(),
                    file_name=f"batch_{timestamp}.zip",
                    mime="application/zip",
                    key="download_batch_zip",
                    use_container_width=True
                )
