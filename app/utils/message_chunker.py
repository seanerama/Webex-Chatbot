"""Utility for chunking long messages for Webex."""

import re


def chunk_message(content: str, max_length: int = 7439) -> list[str]:
    """
    Split a long message into chunks that fit within Webex's message limit.

    Attempts to split at natural boundaries (paragraphs, sentences, words)
    to maintain readability.

    Args:
        content: The message content to chunk
        max_length: Maximum length per chunk (default: Webex limit)

    Returns:
        List of message chunks
    """
    if not content:
        return [""]

    if len(content) <= max_length:
        return [content]

    chunks = []
    remaining = content

    while remaining:
        if len(remaining) <= max_length:
            chunks.append(remaining)
            break

        # Find best split point
        split_at = find_split_point(remaining, max_length)
        chunk = remaining[:split_at].rstrip()
        remaining = remaining[split_at:].lstrip()

        if chunk:
            chunks.append(chunk)

    return chunks if chunks else [""]


def find_split_point(text: str, max_length: int) -> int:
    """
    Find the best point to split text within max_length.

    Priority:
    1. Double newline (paragraph break)
    2. Single newline
    3. Sentence end (. ! ?)
    4. Comma or semicolon
    5. Space (word boundary)
    6. Hard cut at max_length

    Args:
        text: Text to find split point in
        max_length: Maximum position to split at

    Returns:
        Position to split at
    """
    search_text = text[:max_length]

    # Try to split at paragraph break (double newline)
    last_para = search_text.rfind("\n\n")
    if last_para > max_length // 2:
        return last_para + 2

    # Try to split at single newline
    last_newline = search_text.rfind("\n")
    if last_newline > max_length // 2:
        return last_newline + 1

    # Try to split at sentence end
    # Look for . ! ? followed by space or end
    sentence_ends = list(re.finditer(r"[.!?](?:\s|$)", search_text))
    if sentence_ends:
        last_sentence = sentence_ends[-1]
        if last_sentence.end() > max_length // 2:
            return last_sentence.end()

    # Try to split at comma or semicolon
    for sep in ["; ", ", "]:
        last_sep = search_text.rfind(sep)
        if last_sep > max_length // 2:
            return last_sep + len(sep)

    # Try to split at space (word boundary)
    last_space = search_text.rfind(" ")
    if last_space > max_length // 2:
        return last_space + 1

    # Hard cut as last resort
    return max_length


def chunk_code_block(content: str, max_length: int = 7439) -> list[str]:
    """
    Chunk content while preserving code blocks.

    Attempts to keep code blocks intact when possible.

    Args:
        content: Content that may contain code blocks
        max_length: Maximum length per chunk

    Returns:
        List of chunks with preserved code block formatting
    """
    # Pattern for fenced code blocks
    code_block_pattern = re.compile(r"```[\s\S]*?```", re.MULTILINE)

    chunks = []
    current_chunk = ""
    last_end = 0

    for match in code_block_pattern.finditer(content):
        # Add text before code block
        text_before = content[last_end:match.start()]

        if text_before:
            # Check if adding text would exceed limit
            if len(current_chunk) + len(text_before) > max_length:
                if current_chunk:
                    chunks.append(current_chunk.rstrip())
                # Chunk the text before
                for text_chunk in chunk_message(text_before, max_length):
                    if len(current_chunk) + len(text_chunk) > max_length:
                        if current_chunk:
                            chunks.append(current_chunk.rstrip())
                        current_chunk = text_chunk
                    else:
                        current_chunk += text_chunk
            else:
                current_chunk += text_before

        # Handle the code block
        code_block = match.group()
        if len(code_block) > max_length:
            # Code block too large - split it
            if current_chunk:
                chunks.append(current_chunk.rstrip())
                current_chunk = ""
            # Split the code block (try to preserve structure)
            chunks.extend(chunk_code_block_content(code_block, max_length))
        elif len(current_chunk) + len(code_block) > max_length:
            # Start new chunk for code block
            if current_chunk:
                chunks.append(current_chunk.rstrip())
            current_chunk = code_block
        else:
            current_chunk += code_block

        last_end = match.end()

    # Add remaining content
    remaining = content[last_end:]
    if remaining:
        if len(current_chunk) + len(remaining) > max_length:
            if current_chunk:
                chunks.append(current_chunk.rstrip())
            chunks.extend(chunk_message(remaining, max_length))
        else:
            current_chunk += remaining

    if current_chunk:
        chunks.append(current_chunk.rstrip())

    return chunks if chunks else [""]


def chunk_code_block_content(code_block: str, max_length: int) -> list[str]:
    """Split a large code block across multiple chunks."""
    # Extract language identifier if present
    match = re.match(r"```(\w*)\n", code_block)
    lang = match.group(1) if match else ""
    prefix = f"```{lang}\n" if lang else "```\n"
    suffix = "\n```"

    # Get the code content
    content = code_block[len(prefix):-len(suffix)] if code_block.endswith("```") else code_block[len(prefix):]

    # Calculate available space for code per chunk
    overhead = len(prefix) + len(suffix) + len("\n(continued...)")
    code_max = max_length - overhead

    chunks = []
    lines = content.split("\n")
    current_lines: list[str] = []
    current_len = 0

    for line in lines:
        line_len = len(line) + 1  # +1 for newline

        if current_len + line_len > code_max and current_lines:
            # Emit current chunk
            code_content = "\n".join(current_lines)
            chunk = f"{prefix}{code_content}\n(continued...){suffix}"
            chunks.append(chunk)
            current_lines = [line]
            current_len = line_len
        else:
            current_lines.append(line)
            current_len += line_len

    # Final chunk
    if current_lines:
        code_content = "\n".join(current_lines)
        chunk = f"{prefix}{code_content}{suffix}"
        chunks.append(chunk)

    return chunks
