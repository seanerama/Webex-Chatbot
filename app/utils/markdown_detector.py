"""Utilities for detecting and handling markdown content."""

import re


def detect_markdown(text: str) -> bool:
    """
    Detect if text contains markdown formatting.

    Checks for common markdown patterns:
    - Headers (#, ##, etc.)
    - Bold/italic (**text**, *text*, __text__, _text_)
    - Code blocks (``` or `)
    - Lists (-, *, numbered)
    - Links [text](url)
    - Images ![alt](url)
    - Blockquotes (>)
    - Tables (|)

    Args:
        text: Text to check for markdown

    Returns:
        True if markdown is detected
    """
    if not text:
        return False

    # Patterns that indicate markdown
    markdown_patterns = [
        r"^#{1,6}\s",  # Headers
        r"\*\*[^*]+\*\*",  # Bold
        r"\*[^*]+\*",  # Italic
        r"__[^_]+__",  # Bold (underscore)
        r"_[^_]+_",  # Italic (underscore)
        r"```[\s\S]*```",  # Fenced code blocks
        r"`[^`]+`",  # Inline code
        r"^\s*[-*+]\s",  # Unordered lists
        r"^\s*\d+\.\s",  # Ordered lists
        r"\[.+\]\(.+\)",  # Links
        r"!\[.*\]\(.+\)",  # Images
        r"^\s*>",  # Blockquotes
        r"\|.*\|",  # Tables
        r"^\s*---+\s*$",  # Horizontal rules
        r"^\s*\*\*\*+\s*$",  # Horizontal rules (asterisks)
    ]

    for pattern in markdown_patterns:
        if re.search(pattern, text, re.MULTILINE):
            return True

    return False


def should_use_markdown(text: str) -> bool:
    """
    Determine if a message should be sent as markdown.

    Uses heuristics to decide if markdown formatting
    would improve the message presentation.

    Args:
        text: Message text to analyze

    Returns:
        True if markdown should be used
    """
    # Always use markdown if it's already formatted
    if detect_markdown(text):
        return True

    # Use markdown for longer messages (likely to benefit from formatting)
    if len(text) > 500:
        return True

    # Use markdown if text contains code-like patterns
    code_patterns = [
        r"\b(function|def|class|import|from|const|let|var)\b",
        r"[{}\[\]()]",  # Brackets common in code
        r"=>",  # Arrow functions
        r"::",  # Scope resolution
        r"\w+\(\)",  # Function calls
    ]

    for pattern in code_patterns:
        if re.search(pattern, text):
            return True

    return False


def escape_markdown(text: str) -> str:
    """
    Escape markdown special characters in text.

    Useful when you want to include literal characters
    that would otherwise be interpreted as markdown.

    Args:
        text: Text to escape

    Returns:
        Text with markdown characters escaped
    """
    # Characters that have special meaning in markdown
    special_chars = ["\\", "`", "*", "_", "{", "}", "[", "]", "(", ")", "#", "+", "-", ".", "!", "|"]

    result = text
    for char in special_chars:
        result = result.replace(char, f"\\{char}")

    return result


def strip_markdown(text: str) -> str:
    """
    Remove markdown formatting from text.

    Converts markdown to plain text by removing formatting.

    Args:
        text: Markdown text

    Returns:
        Plain text without markdown formatting
    """
    if not text:
        return ""

    result = text

    # Remove code blocks (keep content)
    result = re.sub(r"```[\w]*\n([\s\S]*?)```", r"\1", result)

    # Remove inline code (keep content)
    result = re.sub(r"`([^`]+)`", r"\1", result)

    # Remove bold/italic
    result = re.sub(r"\*\*([^*]+)\*\*", r"\1", result)
    result = re.sub(r"\*([^*]+)\*", r"\1", result)
    result = re.sub(r"__([^_]+)__", r"\1", result)
    result = re.sub(r"_([^_]+)_", r"\1", result)

    # Remove headers (keep text)
    result = re.sub(r"^#{1,6}\s*", "", result, flags=re.MULTILINE)

    # Remove links (keep text)
    result = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", result)

    # Remove images
    result = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", result)

    # Remove blockquote markers
    result = re.sub(r"^\s*>\s*", "", result, flags=re.MULTILINE)

    # Remove horizontal rules
    result = re.sub(r"^\s*[-*_]{3,}\s*$", "", result, flags=re.MULTILINE)

    # Clean up extra whitespace
    result = re.sub(r"\n{3,}", "\n\n", result)

    return result.strip()


def format_as_code_block(code: str, language: str = "") -> str:
    """
    Format code as a markdown code block.

    Args:
        code: Code to format
        language: Optional language for syntax highlighting

    Returns:
        Markdown-formatted code block
    """
    return f"```{language}\n{code}\n```"


def format_as_inline_code(text: str) -> str:
    """
    Format text as inline code.

    Args:
        text: Text to format

    Returns:
        Markdown inline code
    """
    # Handle text that contains backticks
    if "`" in text:
        return f"`` {text} ``"
    return f"`{text}`"
