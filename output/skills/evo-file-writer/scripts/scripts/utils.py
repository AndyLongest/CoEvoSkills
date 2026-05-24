def create_text_file(filepath: str, content: str) -> str:
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)
    return f"Successfully created {filepath}"