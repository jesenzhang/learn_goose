"""
Test image support in goose-system providers
"""

import base64
import asyncio
import sys
import io

# 设置 Windows 控制台输出编码
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, 'F:/Workspace/learn_goose/goose-system/src')

from goose.conversation.message import (
    Message,
    Role,
    TextContent,
    ImageContent,
    ToolRequestContent,
)


def test_image_content():
    """Test ImageContent creation and serialization."""
    print("=== Test ImageContent ===")

    # Test with URL
    img_url = ImageContent.create(
        data="",
        url="https://example.com/image.png",
        mime_type="image/png",
        detail="high"
    )
    print(f"Image URL: {img_url}")
    print(f"To dict: {img_url.to_dict()}")

    # Test with base64
    img_base64 = ImageContent.create(
        data="iVBORw0KGgoAAAANSUhEUgAA...",
        mime_type="image/png",
        detail="auto"
    )
    print(f"Image base64: {img_base64}")
    print(f"To dict: {img_base64.to_dict()}")


def test_message_with_images():
    """Test creating messages with image content."""
    print("\n=== Test Message with Images ===")

    # Text only message
    text_msg = Message.user("Hello, world!")
    print(f"Text message: {text_msg.as_concat_text()}")

    # Text + Image message (URL)
    img_msg_url = Message(
        role=Role.USER,
        content=[
            TextContent(text="What's in this image?"),
            ImageContent.create(
                data="",
                url="https://example.com/cat.jpg",
                detail="high"
            )
        ]
    )
    print(f"Image message text: {img_msg_url.as_concat_text()}")

    # Text + Image message (base64)
    sample_b64 = "R0lGODlhAAANSUhEUgAAAA..."
    img_msg_base64 = Message(
        role=Role.USER,
        content=[
            TextContent(text="Describe this:"),
            ImageContent.create(
                data=sample_b64,
                mime_type="image/png"
            )
        ]
    )
    print(f"Base64 message text: {img_msg_base64.as_concat_text()}")

    # Multiple images
    multi_img_msg = Message(
        role=Role.USER,
        content=[
            TextContent(text="What animals are these?"),
            ImageContent.create(
                data="",
                url="https://example.com/dog.jpg"
            ),
            ImageContent.create(
                data="",
                url="https://example.com/cat.jpg"
            )
        ]
    )
    print(f"Multi-image message text: {multi_img_msg.as_concat_text()}")


def test_message_serialization():
    """Test message to_dict() with images."""
    print("\n=== Test Message Serialization ===")

    msg = Message(
        role=Role.USER,
        content=[
            TextContent(text="Look at this:"),
            ImageContent.create(
                data="",
                url="https://example.com/image.png"
            )
        ]
    )

    msg_dict = msg.to_dict()
    print(f"Message dict: {msg_dict}")

    # Verify structure
    assert msg_dict["role"] == "user"
    assert len(msg_dict["content"]) == 2
    assert msg_dict["content"][0]["type"] == "text"
    assert msg_dict["content"][1]["type"] == "image"
    # Check URL in source
    assert "source" in msg_dict["content"][1]
    assert msg_dict["content"][1]["source"]["type"] == "url"
    assert msg_dict["content"][1]["source"]["url"] == "https://example.com/image.png"
    print("Serialization correct!")


def test_mixed_content():
    """Test message with text, images, and tools."""
    print("\n=== Test Mixed Content ===")

    msg = Message(
        role=Role.ASSISTANT,
        content=[
            TextContent(text="I found 2 items in the image"),
            ToolRequestContent.create(
                tool_id="tool123",
                name="count_items",
                arguments={"count": 2}
            )
        ]
    )

    print(f"Text: {msg.as_concat_text()}")
    print(f"Content types: {[type(c).__name__ for c in msg.content]}")


async def test_provider_with_openai():
    """Test OpenAI provider with image content."""
    print("\n=== Test OpenAI Provider ===")

    try:
        from goose.providers.openai import OpenAIProvider
        from goose.providers.model_config import ModelConfig

        config = {
            "provider": "openai",
            "model_name": "gpt-4o",
            "api_key": "test-key"
        }

        provider = OpenAIProvider(config)

        # Create message with image
        msg = Message(
            role=Role.USER,
            content=[
                TextContent(text="What do you see?"),
                ImageContent.create(
                    data="",
                    url="https://example.com/test.jpg"
                )
            ]
        )

        print("✓ OpenAI provider can be initialized!")
        print(f"Message content: {[type(c).__name__ for c in msg.content]}")

    except ImportError as e:
        print(f"⚠ OpenAI not available: {e}")
    except Exception as e:
        print(f"⚠ Error: {e}")


async def test_provider_with_anthropic():
    """Test Anthropic provider with image content."""
    print("\n=== Test Anthropic Provider ===")

    try:
        from goose.providers.anthropic import AnthropicProvider

        config = {
            "provider": "anthropic",
            "model_name": "claude-3-5-sonnet-20241022",
            "api_key": "test-key"
        }

        provider = AnthropicProvider(config)

        # Create message with image
        msg = Message(
            role=Role.USER,
            content=[
                TextContent(text="What's in this image?"),
                ImageContent.create(
                    data="",
                    url="https://example.com/test.jpg"
                )
            ]
        )

        print("✓ Anthropic provider can be initialized!")
        print(f"Message content: {[type(c).__name__ for c in msg.content]}")

    except ImportError as e:
        print(f"⚠ Anthropic not available: {e}")
    except Exception as e:
        print(f"⚠ Error: {e}")


def load_image_as_base64(image_path):
    """Helper to load image and convert to base64."""
    try:
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except FileNotFoundError:
        print(f"Image not found: {image_path}")
        return None


async def main():
    """Run all tests."""
    print("Testing Goose-System Image Support\n")

    # Basic content tests
    test_image_content()
    test_message_with_images()
    test_message_serialization()
    test_mixed_content()

    # Provider tests (these need API keys or will use dummy)
    await test_provider_with_openai()
    await test_provider_with_anthropic()

    print("\n✓ All basic tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
