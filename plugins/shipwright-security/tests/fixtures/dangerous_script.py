"""Fixture: Python script with dangerous patterns for testing."""

import os
import subprocess
import pickle


def do_the_thing(user_input: str) -> None:
    # Dangerous: eval on user input
    result = eval(user_input)
    print(result)

    # Dangerous: exec on dynamic code
    exec("print('hello')")

    # Dangerous: os.system
    os.system("ls -la")

    # Dangerous: subprocess with shell=True
    subprocess.run("echo hi", shell=True)

    # Dangerous: unpickling untrusted data
    data = pickle.loads(b"\x80\x04N.")

    # Dangerous: dynamic import
    mod = __import__("os")


# This line is fine — just a normal function call
def safe_function() -> int:
    return 42
