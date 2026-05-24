def write_hello():
    """Write "Hello, world!" to /root/hello.txt."""
    with open('/root/hello.txt', 'w') as f:
        f.write('Hello, world!')
