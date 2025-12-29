"""Main CLI entry point."""

from pathlib import Path

import click
from dotenv import load_dotenv

from stache_tools import __version__

# Load .env from cwd
_env_file = Path.cwd() / ".env"
if _env_file.exists():
    load_dotenv(_env_file)


@click.group()
@click.version_option(version=__version__, prog_name="stache")
def cli():
    """Stache CLI - Interact with your knowledge base."""
    pass


def setup_cli():
    """Register all commands."""
    from .documents import doc
    from .health import health
    from .ingest import ingest
    from .models import models
    from .namespaces import namespace
    from .search import search

    cli.add_command(search)
    cli.add_command(ingest)
    cli.add_command(namespace)
    cli.add_command(doc)
    cli.add_command(health)
    cli.add_command(models)


setup_cli()


def main():
    """Entry point for stache CLI."""
    cli()


if __name__ == "__main__":
    main()
