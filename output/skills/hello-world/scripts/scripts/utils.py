def create_text_file(path, content):
    with open(path, 'w') as f:
        f.write(content)