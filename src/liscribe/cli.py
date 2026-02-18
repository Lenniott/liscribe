"""CLI entry point — rec command with -f, -s, --mic flags and subcommands."""

from __future__ import annotations

import sys

import click

from liscribe import __version__
from liscribe.config import init_config_if_missing, load_config, CONFIG_PATH
from liscribe.logging_setup import setup_logging


@click.group(invoke_without_command=True)
@click.option(
    "-f", "--folder",
    type=click.Path(),
    help="Folder to save recordings and transcripts.",
)
@click.option(
    "-s", "--speaker",
    is_flag=True,
    default=False,
    help="Also record system audio (requires BlackHole + Multi-Output Device).",
)
@click.option(
    "--mic",
    type=str,
    default=None,
    help="Input device name or index to use for recording.",
)
@click.option(
    "--debug",
    is_flag=True,
    default=False,
    help="Enable debug logging.",
)
@click.version_option(__version__, prog_name="liscribe")
@click.pass_context
def main(ctx: click.Context, folder: str | None, speaker: bool, mic: str | None, debug: bool) -> None:
    """Liscribe — 100% offline terminal recorder and transcriber."""
    setup_logging(debug=debug)
    ctx.ensure_object(dict)
    ctx.obj["folder"] = folder
    ctx.obj["speaker"] = speaker
    ctx.obj["mic"] = mic

    if ctx.invoked_subcommand is not None:
        return

    if folder is None:
        cfg = load_config()
        folder = cfg.get("save_folder")
        if folder is None:
            click.echo("Error: --folder / -f is required (or set save_folder in config).", err=True)
            click.echo(f"Config: {CONFIG_PATH}", err=True)
            sys.exit(1)
        ctx.obj["folder"] = folder

    # Start recording via TUI
    from liscribe.app import RecordingApp
    app = RecordingApp(folder=folder, speaker=speaker, mic=mic)
    wav_path = app.run()

    if not wav_path:
        click.echo("Recording cancelled.")
        return

    click.echo(f"Audio saved: {wav_path}")
    timestamped_notes = app.notes

    # Transcribe
    click.echo("Transcribing...")
    from liscribe.transcriber import transcribe
    from liscribe.output import save_transcript, copy_to_clipboard, cleanup_audio

    def show_progress(progress: float) -> None:
        bar_len = 30
        filled = int(bar_len * progress)
        bar = "█" * filled + "░" * (bar_len - filled)
        click.echo(f"\r  [{bar}] {progress*100:.0f}%", nl=False)

    try:
        result = transcribe(wav_path, on_progress=show_progress)
        click.echo()
    except Exception as exc:
        click.echo(f"\nTranscription failed: {exc}", err=True)
        click.echo(f"Audio file kept at: {wav_path}")
        return

    # Save transcript
    mic_name = mic or "system default"
    md_path = save_transcript(
        result=result,
        wav_path=wav_path,
        notes=timestamped_notes if timestamped_notes else None,
        mic_name=mic_name,
        speaker_mode=speaker,
    )
    click.echo(f"Transcript saved: {md_path}")

    # Clipboard
    cfg = load_config()
    if cfg.get("auto_clipboard", True):
        if copy_to_clipboard(result.text):
            click.echo("Transcript copied to clipboard.")

    # Remove audio only after transcript is confirmed saved
    if cleanup_audio(wav_path, md_path):
        click.echo("Audio file removed (transcript saved).")
    else:
        click.echo(f"Audio file kept at: {wav_path}")


@main.command()
def setup() -> None:
    """Check dependencies and initialise config."""
    from liscribe.platform_setup import run_all_checks

    created = init_config_if_missing()
    if created:
        click.echo(f"Created default config at {CONFIG_PATH}")
    else:
        click.echo(f"Config already exists at {CONFIG_PATH}")

    click.echo()
    results = run_all_checks(include_speaker=True)
    all_ok = True
    for name, ok, msg in results:
        icon = "OK" if ok else "MISSING"
        click.echo(f"  [{icon}] {name}: {msg}")
        if not ok:
            all_ok = False

    click.echo()
    if all_ok:
        click.echo("All checks passed.")
    else:
        click.echo("Some checks failed. See above for install instructions.")

    # Offer to download whisper model
    click.echo()
    cfg = load_config()
    model_size = cfg.get("whisper_model", "base")
    click.echo(f"Whisper model: {model_size}")
    if click.confirm(f"Download/verify the '{model_size}' model now?", default=True):
        click.echo(f"Loading model '{model_size}' (downloads on first use)...")
        from liscribe.transcriber import load_model
        try:
            load_model(model_size)
            click.echo("Model ready.")
        except Exception as exc:
            click.echo(f"Error loading model: {exc}", err=True)


@main.command()
@click.option("--show", is_flag=True, help="Show current config values.")
def config(show: bool) -> None:
    """Show or edit configuration."""
    if show:
        cfg = load_config()
        for key, val in cfg.items():
            click.echo(f"  {key}: {val}")
    else:
        click.echo(f"Config file: {CONFIG_PATH}")
        click.echo("Edit it directly, or use 'rec config --show' to view current values.")


@main.command()
def devices() -> None:
    """List available audio input devices."""
    try:
        import sounddevice as sd
    except OSError:
        click.echo("Error: PortAudio not found. Run 'rec setup' for instructions.", err=True)
        sys.exit(1)

    devs = sd.query_devices()
    click.echo("Available input devices:\n")
    for i, d in enumerate(devs):
        if d["max_input_channels"] > 0:
            default_marker = " (default)" if i == sd.default.device[0] else ""
            click.echo(
                f"  [{i}] {d['name']}"
                f"  ({d['max_input_channels']}ch, {int(d['default_samplerate'])}Hz)"
                f"{default_marker}"
            )
