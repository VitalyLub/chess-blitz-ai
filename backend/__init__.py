"""Chess Blitz AI backend package.

Loads a local .env (if present) so API keys are available no matter how the
backend is launched (terminal, uvicorn --reload, or PyCharm). Real shell
environment variables take precedence over .env values.
"""

try:
    from dotenv import load_dotenv

    load_dotenv()  # searches cwd and parents for a .env file
except ImportError:  # dotenv is optional; mock games don't need it
    pass
