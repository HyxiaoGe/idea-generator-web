"""
Unit tests for GoogleProvider inpaint/outpaint/describe methods.

Tests the provider layer directly with real PIL images and mocked Google SDK calls.
"""

from io import BytesIO
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from services.providers.base import GenerationRequest
from services.providers.google import GoogleProvider

# ============ Fixtures ============


@pytest.fixture
def provider():
    """Create a GoogleProvider with a mocked client."""
    with patch("services.providers.google.genai") as mock_genai:
        mock_client = MagicMock()
        mock_genai.Client.return_value = mock_client

        p = GoogleProvider()
        # Force inject the mock client (bypass API key check)
        p._api_key = "test-api-key"
        p._client = mock_client
        return p


@pytest.fixture
def source_image():
    """Create a realistic RGB source image."""
    img = Image.new("RGB", (512, 512), color="red")
    # Draw some variation to make it realistic
    pixels = img.load()
    for x in range(0, 512, 2):
        for y in range(0, 512, 2):
            pixels[x, y] = (x % 256, y % 256, 128)
    return img


@pytest.fixture
def mask_image():
    """Create a grayscale mask image (white = masked area)."""
    mask = Image.new("L", (512, 512), color=0)
    # Draw a white rectangle in the center (mask area)
    pixels = mask.load()
    for x in range(128, 384):
        for y in range(128, 384):
            pixels[x, y] = 255
    return mask


def _make_edit_response(width=512, height=512):
    """Build a mock edit_image response with a real PNG image."""
    # Generate a real PNG image bytes
    img = Image.new("RGB", (width, height), color="blue")
    buf = BytesIO()
    img.save(buf, format="PNG")
    image_bytes = buf.getvalue()

    mock_image = MagicMock()
    mock_image.image_bytes = image_bytes

    mock_generated = MagicMock()
    mock_generated.image = mock_image

    mock_response = MagicMock()
    mock_response.generated_images = [mock_generated]
    return mock_response


def _make_content_response(text="A beautiful image of a sunset.", has_image=False):
    """Build a mock generate_content response."""
    parts = []

    # Text part
    text_part = MagicMock()
    text_part.thought = False
    text_part.text = text
    text_part.inline_data = None
    parts.append(text_part)

    # Image part (optional)
    if has_image:
        img = Image.new("RGB", (256, 256), color="green")
        buf = BytesIO()
        img.save(buf, format="PNG")

        inline_data = MagicMock()
        inline_data.data = buf.getvalue()

        img_part = MagicMock()
        img_part.thought = False
        img_part.text = None
        img_part.inline_data = inline_data
        parts.append(img_part)

    content = MagicMock()
    content.parts = parts

    candidate = MagicMock()
    candidate.content = content
    candidate.safety_ratings = None
    candidate.finish_reason = "STOP"

    response = MagicMock()
    response.candidates = [candidate]
    return response


# ============ _pil_to_genai_image tests ============


class TestPilToGenaiImage:
    """Test the PIL → genai Image conversion helper."""

    def test_converts_rgb_image(self):
        """Converts an RGB PIL image to genai Image with PNG bytes."""
        img = Image.new("RGB", (100, 100), color="red")
        result = GoogleProvider._pil_to_genai_image(img)

        assert result.mime_type == "image/png"
        assert isinstance(result.image_bytes, bytes)
        assert len(result.image_bytes) > 0

        # Verify the bytes are valid PNG
        reconstructed = Image.open(BytesIO(result.image_bytes))
        assert reconstructed.size == (100, 100)

    def test_converts_grayscale_image(self):
        """Converts a grayscale (L mode) image to genai Image."""
        img = Image.new("L", (64, 64), color=128)
        result = GoogleProvider._pil_to_genai_image(img)

        assert result.mime_type == "image/png"
        assert len(result.image_bytes) > 0

    def test_converts_rgba_image(self):
        """Converts an RGBA image (with transparency) to genai Image."""
        img = Image.new("RGBA", (200, 200), color=(255, 0, 0, 128))
        result = GoogleProvider._pil_to_genai_image(img)

        assert result.mime_type == "image/png"
        reconstructed = Image.open(BytesIO(result.image_bytes))
        assert reconstructed.size == (200, 200)

    def test_preserves_image_content(self):
        """Verifies pixel data round-trips through the conversion."""
        img = Image.new("RGB", (10, 10), color=(42, 128, 200))
        result = GoogleProvider._pil_to_genai_image(img)

        reconstructed = Image.open(BytesIO(result.image_bytes)).convert("RGB")
        pixel = reconstructed.getpixel((5, 5))
        assert pixel == (42, 128, 200)


# ============ generate() routing tests ============


class TestGenerateRouting:
    """Test that generate() routes edit_mode to the correct method."""

    async def test_routes_inpaint_insert(self, provider, source_image, mask_image):
        """edit_mode=inpaint_insert routes to _generate_inpaint."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Add a flower",
            edit_mode="inpaint_insert",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.model == "imagen-3.0-capability-001"
        provider._client.models.edit_image.assert_called_once()

    async def test_routes_inpaint_remove(self, provider, source_image, mask_image):
        """edit_mode=inpaint_remove routes to _generate_inpaint."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Remove the object",
            edit_mode="inpaint_remove",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.model == "imagen-3.0-capability-001"
        provider._client.models.edit_image.assert_called_once()

    async def test_routes_outpaint(self, provider, source_image, mask_image):
        """edit_mode=outpaint routes to _generate_outpaint."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Extend the scene",
            edit_mode="outpaint",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.model == "imagen-3.0-capability-001"
        provider._client.models.edit_image.assert_called_once()

    async def test_routes_describe(self, provider, source_image):
        """edit_mode=describe routes to _describe_image."""
        provider._client.models.generate_content.return_value = _make_content_response()

        request = GenerationRequest(
            prompt="Describe this image",
            edit_mode="describe",
            reference_images=[source_image],
        )

        result = await provider.generate(request)

        assert result.model == "gemini-3-pro-image-preview"  # default model
        provider._client.models.generate_content.assert_called_once()

    async def test_no_edit_mode_routes_to_basic(self, provider):
        """No edit_mode uses standard routing (basic generation)."""
        provider._client.models.generate_content.return_value = _make_content_response(
            has_image=True
        )

        request = GenerationRequest(prompt="A sunset")

        result = await provider.generate(request)

        assert result.model == "gemini-3-pro-image-preview"
        provider._client.models.generate_content.assert_called_once()


# ============ _generate_inpaint tests ============


class TestGenerateInpaint:
    """Test _generate_inpaint with real images and mocked SDK."""

    async def test_inpaint_insert_success(self, provider, source_image, mask_image):
        """Inpaint insertion returns a valid result with PIL image."""
        provider._client.models.edit_image.return_value = _make_edit_response(512, 512)

        request = GenerationRequest(
            prompt="Add a red flower",
            edit_mode="inpaint_insert",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
            mask_dilation=0.05,
        )

        result = await provider.generate(request)

        assert result.success is True
        assert result.image is not None
        assert result.image.size == (512, 512)
        assert result.error is None
        assert result.provider == "google"
        assert result.model == "imagen-3.0-capability-001"
        assert result.duration > 0

    async def test_inpaint_remove_success(self, provider, source_image, mask_image):
        """Inpaint removal mode works correctly."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Remove the object",
            edit_mode="inpaint_remove",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.success is True
        assert result.image is not None

        # Verify the SDK was called with INPAINT_REMOVAL mode
        call_args = provider._client.models.edit_image.call_args
        config = call_args.kwargs.get("config") or call_args[1].get("config")
        assert config.edit_mode == "EDIT_MODE_INPAINT_REMOVAL"

    async def test_inpaint_foreground_mode(self, provider, source_image):
        """Inpaint with foreground auto-detection (no mask image)."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Replace foreground",
            edit_mode="inpaint_insert",
            mask_mode="foreground",
            reference_images=[source_image],
            # No mask_image — auto-detect foreground
        )

        result = await provider.generate(request)

        assert result.success is True
        assert result.image is not None

    async def test_inpaint_background_mode(self, provider, source_image):
        """Inpaint with background auto-detection."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Replace background",
            edit_mode="inpaint_insert",
            mask_mode="background",
            reference_images=[source_image],
        )

        result = await provider.generate(request)

        assert result.success is True

    async def test_inpaint_semantic_mode(self, provider, source_image):
        """Inpaint with semantic segmentation mode."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Change the sky",
            edit_mode="inpaint_insert",
            mask_mode="semantic",
            reference_images=[source_image],
        )

        result = await provider.generate(request)

        assert result.success is True

    async def test_inpaint_no_source_image_error(self, provider):
        """Inpaint without source image returns error."""
        request = GenerationRequest(
            prompt="Add flower",
            edit_mode="inpaint_insert",
            mask_mode="foreground",
            reference_images=None,
        )

        result = await provider.generate(request)

        assert result.success is False
        assert "source image" in result.error.lower()

    async def test_inpaint_user_provided_no_mask_error(self, provider, source_image):
        """Inpaint with user_provided mode but no mask returns error."""
        request = GenerationRequest(
            prompt="Add flower",
            edit_mode="inpaint_insert",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=None,
        )

        result = await provider.generate(request)

        assert result.success is False
        assert "mask" in result.error.lower()

    async def test_inpaint_sdk_error(self, provider, source_image, mask_image):
        """Inpaint handles SDK exceptions gracefully."""
        provider._client.models.edit_image.side_effect = Exception("API quota exceeded")

        request = GenerationRequest(
            prompt="Add flower",
            edit_mode="inpaint_insert",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.success is False
        assert result.error is not None

    async def test_inpaint_safety_blocked(self, provider, source_image, mask_image):
        """Inpaint handles safety-blocked responses."""
        provider._client.models.edit_image.side_effect = Exception(
            "Content blocked by safety filter"
        )

        request = GenerationRequest(
            prompt="Something unsafe",
            edit_mode="inpaint_insert",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.safety_blocked is True

    async def test_inpaint_empty_response(self, provider, source_image, mask_image):
        """Inpaint handles empty generated_images list."""
        mock_response = MagicMock()
        mock_response.generated_images = []
        provider._client.models.edit_image.return_value = mock_response

        request = GenerationRequest(
            prompt="Add flower",
            edit_mode="inpaint_insert",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.success is False
        assert "no images" in result.error.lower()

    async def test_inpaint_verifies_sdk_call_args(self, provider, source_image, mask_image):
        """Verify exact arguments passed to edit_image SDK."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Add a tree",
            edit_mode="inpaint_insert",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
            mask_dilation=0.1,
        )

        await provider.generate(request)

        call_kwargs = provider._client.models.edit_image.call_args.kwargs
        assert call_kwargs["model"] == "imagen-3.0-capability-001"
        assert call_kwargs["prompt"] == "Add a tree"
        assert len(call_kwargs["reference_images"]) == 2  # raw + mask
        assert call_kwargs["config"].edit_mode == "EDIT_MODE_INPAINT_INSERTION"
        assert call_kwargs["config"].number_of_images == 1


# ============ _generate_outpaint tests ============


class TestGenerateOutpaint:
    """Test _generate_outpaint with real images and mocked SDK."""

    async def test_outpaint_success(self, provider, source_image, mask_image):
        """Outpaint returns a valid result with extended PIL image."""
        provider._client.models.edit_image.return_value = _make_edit_response(768, 512)

        request = GenerationRequest(
            prompt="Extend with a beach scene",
            edit_mode="outpaint",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.success is True
        assert result.image is not None
        assert result.image.size == (768, 512)
        assert result.provider == "google"
        assert result.model == "imagen-3.0-capability-001"

    async def test_outpaint_no_source_error(self, provider, mask_image):
        """Outpaint without source image returns error."""
        request = GenerationRequest(
            prompt="Extend",
            edit_mode="outpaint",
            reference_images=None,
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.success is False
        assert "source image" in result.error.lower()

    async def test_outpaint_no_mask_error(self, provider, source_image):
        """Outpaint without mask image returns error."""
        request = GenerationRequest(
            prompt="Extend",
            edit_mode="outpaint",
            reference_images=[source_image],
            mask_image=None,
        )

        result = await provider.generate(request)

        assert result.success is False
        assert "mask" in result.error.lower()

    async def test_outpaint_sdk_call_uses_outpaint_mode(self, provider, source_image, mask_image):
        """Verify SDK is called with EDIT_MODE_OUTPAINT."""
        provider._client.models.edit_image.return_value = _make_edit_response()

        request = GenerationRequest(
            prompt="Extend",
            edit_mode="outpaint",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        await provider.generate(request)

        call_kwargs = provider._client.models.edit_image.call_args.kwargs
        assert call_kwargs["config"].edit_mode == "EDIT_MODE_OUTPAINT"

    async def test_outpaint_sdk_error(self, provider, source_image, mask_image):
        """Outpaint handles SDK exceptions gracefully."""
        provider._client.models.edit_image.side_effect = Exception("Server disconnected")

        request = GenerationRequest(
            prompt="Extend",
            edit_mode="outpaint",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.success is False
        assert result.error is not None


# ============ _describe_image tests ============


class TestDescribeImage:
    """Test _describe_image with real images and mocked SDK."""

    async def test_describe_success(self, provider, source_image):
        """Describe returns text description of the image."""
        provider._client.models.generate_content.return_value = _make_content_response(
            text="A colorful abstract pattern with red and blue tones."
        )

        request = GenerationRequest(
            prompt="Describe this image in detail",
            edit_mode="describe",
            reference_images=[source_image],
        )

        result = await provider.generate(request)

        assert result.success is True
        assert result.text_response is not None
        assert "colorful" in result.text_response.lower()
        assert result.image is None  # describe produces no image
        assert result.provider == "google"
        assert result.duration > 0

    async def test_describe_no_image_error(self, provider):
        """Describe without reference image returns error."""
        request = GenerationRequest(
            prompt="Describe this image",
            edit_mode="describe",
            reference_images=None,
        )

        result = await provider.generate(request)

        assert result.success is False
        assert "image is required" in result.error.lower()

    async def test_describe_passes_image_to_sdk(self, provider, source_image):
        """Verify the image is passed to generate_content as contents."""
        provider._client.models.generate_content.return_value = _make_content_response()

        request = GenerationRequest(
            prompt="Describe this",
            edit_mode="describe",
            reference_images=[source_image],
        )

        await provider.generate(request)

        call_kwargs = provider._client.models.generate_content.call_args.kwargs
        contents = call_kwargs["contents"]
        assert len(contents) == 2  # [prompt, image]
        assert contents[0] == "Describe this"
        assert contents[1] is source_image  # PIL image passed directly

    async def test_describe_uses_text_only_modality(self, provider, source_image):
        """Verify response_modalities is Text only (no image output)."""
        provider._client.models.generate_content.return_value = _make_content_response()

        request = GenerationRequest(
            prompt="Describe this",
            edit_mode="describe",
            reference_images=[source_image],
        )

        await provider.generate(request)

        call_kwargs = provider._client.models.generate_content.call_args.kwargs
        config = call_kwargs["config"]
        assert config.response_modalities == ["Text"]

    async def test_describe_sdk_error(self, provider, source_image):
        """Describe handles SDK exceptions gracefully."""
        provider._client.models.generate_content.side_effect = Exception("Model overloaded 503")

        request = GenerationRequest(
            prompt="Describe this",
            edit_mode="describe",
            reference_images=[source_image],
        )

        result = await provider.generate(request)

        assert result.success is False
        assert result.error is not None

    async def test_describe_safety_blocked(self, provider, source_image):
        """Describe handles safety-blocked content."""
        response = _make_content_response()
        response.candidates[0].finish_reason = "SAFETY"

        provider._client.models.generate_content.return_value = response

        request = GenerationRequest(
            prompt="Describe this",
            edit_mode="describe",
            reference_images=[source_image],
        )

        result = await provider.generate(request)

        assert result.safety_blocked is True


# ============ Image round-trip tests ============


class TestImageRoundTrip:
    """Test that real image data survives the full pipeline."""

    async def test_inpaint_image_bytes_roundtrip(self, provider, source_image, mask_image):
        """The output image from inpaint is a valid PIL image with correct data."""
        # Create a recognizable output image
        output_img = Image.new("RGB", (512, 512), color=(42, 128, 200))
        buf = BytesIO()
        output_img.save(buf, format="PNG")

        mock_image = MagicMock()
        mock_image.image_bytes = buf.getvalue()
        mock_generated = MagicMock()
        mock_generated.image = mock_image
        mock_response = MagicMock()
        mock_response.generated_images = [mock_generated]

        provider._client.models.edit_image.return_value = mock_response

        request = GenerationRequest(
            prompt="Test",
            edit_mode="inpaint_insert",
            mask_mode="user_provided",
            reference_images=[source_image],
            mask_image=mask_image,
        )

        result = await provider.generate(request)

        assert result.success is True
        assert result.image.size == (512, 512)
        # Verify pixel color matches what we put in
        pixel = result.image.getpixel((256, 256))
        assert pixel == (42, 128, 200)

    async def test_mask_image_conversion(self, mask_image):
        """Verify mask image (grayscale L mode) converts to valid PNG bytes."""
        genai_img = GoogleProvider._pil_to_genai_image(mask_image)

        # Reconstruct and verify
        reconstructed = Image.open(BytesIO(genai_img.image_bytes))
        assert reconstructed.size == (512, 512)
        # Center pixel should be white (255)
        center = reconstructed.convert("L").getpixel((256, 256))
        assert center == 255
        # Corner pixel should be black (0)
        corner = reconstructed.convert("L").getpixel((0, 0))
        assert corner == 0
