def create_hello_file():
    """Create hello.txt with "Hello, world!" content."""
    with open("hello.txt", "w") as f:
        f.write("Hello, world!")
    return True