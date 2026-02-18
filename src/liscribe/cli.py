"""CLI entry point — placeholder for Phase 2."""

import click


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx):
    """Liscribe — 100% offline terminal recorder and transcriber."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
