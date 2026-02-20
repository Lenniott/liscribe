"""CLI entry point — rec command with rich output, multi-model support, and transcribe subcommand."""

from __future__ import annotations

import json
import os
import sys
import wave
from pathlib import Path

import click

from liscribe.shell_alias import ALIAS_MARKER, get_shell_rc_path as _get_shell_rc_path, update_shell_alias as _update_shell_alias
from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)

from liscribe import __version__
from liscribe.config import init_config_if_missing, load_config, CONFIG_PATH
from liscribe.logging_setup import setup_logging

console = Console(highlight=False)

MODEL_QUALITY_ORDER = ["tiny", "base", "small", "medium", "large"]

# Map multi-character short options to long options
_SHORT_MODEL_OPTS = {
    "-xxs": "--tiny",
    "-xs": "--base",
    "-sm": "--small",
    "-md": "--medium",
    "-lg": "--large",
}


def _preprocess_model_args():
    """Convert multi-character short options like -xxs to --tiny before Click parses."""
    if len(sys.argv) < 2:
        return
    new_argv = [sys.argv[0]]
    i = 1
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg in _SHORT_MODEL_OPTS:
            # Replace -xxs with --tiny, etc.
            new_argv.append(_SHORT_MODEL_OPTS[arg])
        else:
            new_argv.append(arg)
        i += 1
    sys.argv = new_argv

WHISPER_MODELS = [
    ("tiny",   "~75 MB,  fastest, least accurate"),
    ("base",   "~150 MB, good balance for short recordings"),
    ("small",  "~500 MB, higher accuracy"),
    ("medium", "~1.5 GB, near-best accuracy, slower"),
    ("large",  "~3 GB,   best accuracy, slowest"),
]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _model_options(func):
    """Decorator adding whisper model selection flags to a Click command."""
    options = [
        click.option("--tiny", "--xxs", "model_tiny", is_flag=True, default=False,
                      help="Use tiny model (~75 MB, fastest)"),
        click.option("--base", "--xs", "model_base", is_flag=True, default=False,
                      help="Use base model (~150 MB)"),
        click.option("--small", "--sm", "model_small", is_flag=True, default=False,
                      help="Use small model (~500 MB)"),
        click.option("--medium", "--md", "model_medium", is_flag=True, default=False,
                      help="Use medium model (~1.5 GB)"),
        click.option("--large", "--lg", "model_large", is_flag=True, default=False,
                      help="Use large model (~3 GB, best accuracy)"),
    ]
    for option in reversed(options):
        func = option(func)
    return func


def _collect_models(model_tiny, model_base, model_small, model_medium, model_large) -> list[str]:
    """Gather selected model flags into quality-ordered list."""
    selected = []
    if model_tiny:
        selected.append("tiny")
    if model_base:
        selected.append("base")
    if model_small:
        selected.append("small")
    if model_medium:
        selected.append("medium")
    if model_large:
        selected.append("large")
    return selected


def _resolve_folder(folder: str | None, here: bool) -> str:
    """Determine save folder from flags and config.

    Priority: -f > --here > config save_folder > ~/transcripts
    """
    if folder:
        return folder
    if here:
        return str(Path.cwd() / "docs" / "transcripts")
    cfg = load_config()
    return cfg.get("save_folder", "~/transcripts")


def _get_command_name(ctx: click.Context | None = None) -> str:
    """Get the command name/alias from config or Click context.
    
    Priority: config command_alias > ctx.info_name > "rec"
    """
    cfg = load_config()
    alias = cfg.get("command_alias")
    if alias:
        return alias
    if ctx and ctx.info_name:
        return ctx.info_name
    return "rec"


def _audio_description(audio_path: Path) -> str:
    """Brief human-readable description of an audio file (duration or size)."""
    try:
        if audio_path.suffix.lower() == ".wav":
            with wave.open(str(audio_path), "rb") as wf:
                duration = wf.getnframes() / wf.getframerate()
            if duration >= 60:
                mins, secs = divmod(int(duration), 60)
                return f"{mins}m {secs}s audio"
            return f"{int(duration)}s audio"
    except Exception:
        pass
    try:
        size = audio_path.stat().st_size
        if size > 1_000_000:
            return f"{size / 1_000_000:.1f} MB"
        return f"{size / 1_000:.0f} KB"
    except Exception:
        return audio_path.suffix.lstrip(".").upper()


def _load_dual_source_session(audio_path: Path) -> dict | None:
    """Return dual-source session details when *audio_path* points to session mic.wav."""
    if audio_path.name.lower() != "mic.wav":
        return None
    session_dir = audio_path.parent
    speaker_path = session_dir / "speaker.wav"
    session_json_path = session_dir / "session.json"
    if not speaker_path.exists() or not session_json_path.exists():
        return None

    offset = 0.0
    try:
        session_meta = json.loads(session_json_path.read_text(encoding="utf-8"))
        offset = float(session_meta.get("offset_correction_seconds", 0.0))
    except Exception:
        offset = 0.0

    return {
        "session_dir": session_dir,
        "session_json_path": session_json_path,
        "mic_audio_path": audio_path,
        "speaker_audio_path": speaker_path,
        "speaker_offset_seconds": offset,
    }


def _transcribe_with_progress(audio_path: str, model_size: str, label: str):
    """Load model (spinner), then transcribe with segment-based progress and ETA."""
    from liscribe.transcriber import load_model, transcribe

    with console.status(f"  Loading [bold]{model_size}[/bold] model..."):
        model = load_model(model_size)

    progress = Progress(
        TextColumn(label),
        BarColumn(bar_width=26),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )

    # Start with placeholder total; transcriber will pass total_estimated in first callback.
    task = progress.add_task("", total=1000, completed=0)
    task_initialized: list[bool] = [False]
    total_estimated_ref: list[int] = [1000]

    def on_progress(p: float, info: dict | None = None) -> None:
        if info is not None:
            seg_i = info.get("segment_index", 0)
            total_n = info.get("total_estimated", 1)
            total_estimated_ref[0] = total_n
            if not task_initialized[0] and total_n is not None:
                progress.update(task, total=total_n, completed=seg_i)
                task_initialized[0] = True
            else:
                progress.update(task, completed=seg_i)
        else:
            progress.update(task, completed=int(p * 1000))

    progress.start()

    try:
        result = transcribe(audio_path, model=model, model_size=model_size, on_progress=on_progress)
        if task_initialized[0]:
            progress.update(task, completed=total_estimated_ref[0])
        else:
            progress.update(task, completed=1000)
    except Exception:
        raise
    finally:
        progress.stop()

    return result


def _transcribe_dual_with_progress(
    mic_audio_path: str,
    speaker_audio_path: str,
    model_size: str,
    label: str,
    speaker_offset_seconds: float = 0.0,
    group_consecutive: bool = False,
    suppress_mic_bleed_duplicates: bool = False,
    bleed_similarity_threshold: float = 0.82,
):
    """Transcribe mic and speaker tracks independently, then merge chronologically."""
    from liscribe.transcriber import load_model, transcribe, build_merged_transcription_result

    with console.status(f"  Loading [bold]{model_size}[/bold] model..."):
        model = load_model(model_size)

    progress = Progress(
        TextColumn(label),
        BarColumn(bar_width=26),
        TaskProgressColumn(),
        TimeElapsedColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=False,
    )
    task = progress.add_task("", total=1000, completed=0)

    def mic_progress(p: float, info: dict | None = None) -> None:
        progress.update(task, completed=min(500, int(p * 500)))

    def speaker_progress(p: float, info: dict | None = None) -> None:
        progress.update(task, completed=min(1000, 500 + int(p * 500)))

    progress.start()
    try:
        mic_result = transcribe(mic_audio_path, model=model, model_size=model_size, on_progress=mic_progress)
        speaker_result = transcribe(
            speaker_audio_path,
            model=model,
            model_size=model_size,
            on_progress=speaker_progress,
        )
        merged_result = build_merged_transcription_result(
            mic_result=mic_result,
            speaker_result=speaker_result,
            speaker_offset_seconds=speaker_offset_seconds,
            group_consecutive=group_consecutive,
            suppress_mic_bleed_duplicates=suppress_mic_bleed_duplicates,
            bleed_similarity_threshold=bleed_similarity_threshold,
            model_name=model_size,
        )
        progress.update(task, completed=1000)
        return merged_result
    finally:
        progress.stop()


def _run_transcription_pipeline(
    audio_path: str | Path,
    models: list[str],
    notes=None,
    mic_name: str = "system default",
    speaker_mode: bool = False,
    output_dir: str | Path | None = None,
    ctx: click.Context | None = None,
) -> None:
    """Transcribe with one or more models, save outputs, clipboard, cleanup."""
    from liscribe.transcriber import is_model_available
    from liscribe.output import save_transcript, copy_to_clipboard, cleanup_audio

    audio_path = Path(audio_path)
    dual_session = _load_dual_source_session(audio_path)
    is_dual_source = dual_session is not None
    cfg = load_config()
    multi_model = len(models) > 1
    cmd_name = _get_command_name(ctx)

    available = [m for m in models if is_model_available(m)]
    skipped = [m for m in models if m not in available]

    for m in skipped:
        console.print(
            f"  [dim]\\[skip][/dim]  [bold]{m:<8}[/bold] "
            f"not installed [dim](run '{cmd_name} setup' to download)[/dim]"
        )
    if skipped:
        console.print(f"  [dim]Tip: run [bold]{cmd_name} setup[/bold] to install more models.[/dim]")

    if not available:
        console.print()
        console.print("  [red bold]Error:[/red bold] None of the requested models are installed.")
        console.print(f"  Run [bold]'{cmd_name} setup'[/bold] to download models.")
        console.print(f"  Audio file kept at: [dim]{audio_path}[/dim]")
        return

    n = len(available)
    desc = _audio_description(dual_session["mic_audio_path"] if is_dual_source else audio_path)
    if multi_model or skipped:
        console.print(f"  [bold]Transcribing[/bold]  {n} model{'s' if n != 1 else ''} | {desc}")
    else:
        console.print(f"  [bold]Transcribing[/bold]  {available[0]} model | {desc}")
    if is_dual_source:
        console.print("  [dim]Mode: source-based merge (YOU=mic, THEM=speaker)[/dim]")
        console.print(
            f"  [dim]Offset correction: {dual_session['speaker_offset_seconds']:+.3f}s[/dim]"
        )

    results: list[tuple[str, object, Path]] = []
    group_consecutive = bool(cfg.get("group_consecutive_speaker_lines", False))
    suppress_mic_bleed = bool(cfg.get("suppress_mic_bleed_duplicates", True))
    bleed_similarity_threshold = float(cfg.get("mic_bleed_similarity_threshold", 0.62))
    filename_stem = dual_session["session_dir"].name if is_dual_source else None

    for i, model_size in enumerate(available):
        if n > 1:
            label = f"  \\[{i+1}/{n}] [bold]{model_size:<8}[/bold]"
        else:
            label = f"  [bold]{model_size:<8}[/bold]        "

        try:
            if is_dual_source:
                result = _transcribe_dual_with_progress(
                    mic_audio_path=str(dual_session["mic_audio_path"]),
                    speaker_audio_path=str(dual_session["speaker_audio_path"]),
                    model_size=model_size,
                    label=label,
                    speaker_offset_seconds=float(dual_session["speaker_offset_seconds"]),
                    group_consecutive=group_consecutive,
                    suppress_mic_bleed_duplicates=suppress_mic_bleed,
                    bleed_similarity_threshold=bleed_similarity_threshold,
                )
            else:
                result = _transcribe_with_progress(str(audio_path), model_size, label)
        except Exception as exc:
            console.print(f"  [red]\\[fail][/red] [bold]{model_size}[/bold]: {exc}")
            continue

        md_path = save_transcript(
            result=result,
            audio_path=dual_session["mic_audio_path"] if is_dual_source else audio_path,
            notes=notes,
            mic_name=mic_name,
            speaker_mode=speaker_mode or is_dual_source,
            model_name=model_size,
            include_model_in_filename=multi_model,
            output_dir=output_dir,
            filename_stem=filename_stem,
        )
        results.append((model_size, result, md_path))

    if not results:
        console.print()
        console.print("  [red bold]All transcriptions failed.[/red bold]")
        console.print(f"  Audio file kept at: [dim]{audio_path}[/dim]")
        return

    # -- Saved files --
    console.print()
    for i, (_, _, p) in enumerate(results):
        prefix = "  [green]Saved[/green]         " if i == 0 else "                  "
        console.print(f"{prefix}[dim]{Path(p).name}[/dim]")
    first_md = results[0][2]
    console.print(f"  [dim]Transcript: {first_md.resolve()}[/dim]")

    # -- Clipboard: pick highest-quality model --
    if cfg.get("auto_clipboard", False):
        def _quality(name: str) -> int:
            try:
                return MODEL_QUALITY_ORDER.index(name)
            except ValueError:
                return -1

        best_model, best_result, _ = max(results, key=lambda x: _quality(x[0]))
        if copy_to_clipboard(best_result.text):
            quality_note = f" [dim]({best_model})[/dim]" if multi_model else ""
            console.print(f"  [green]Clipboard[/green]     copied{quality_note}")

    # -- Cleanup: only after ALL transcripts confirmed on disk --
    all_md_paths = [p for _, _, p in results]
    cleanup_targets = [audio_path]
    if is_dual_source:
        cleanup_targets = [
            dual_session["mic_audio_path"],
            dual_session["speaker_audio_path"],
        ]

    removed_all = True
    for target in cleanup_targets:
        if not cleanup_audio(target, all_md_paths):
            removed_all = False

    if removed_all and is_dual_source:
        session_json = dual_session["session_json_path"]
        try:
            session_json.unlink(missing_ok=True)
        except OSError:
            pass

    if removed_all:
        label = "audio sources removed" if is_dual_source else "audio removed"
        console.print(f"  [green]Cleanup[/green]       {label}")
    else:
        for target in cleanup_targets:
            console.print(f"  [dim]Audio kept at: {target}[/dim]")


# ---------------------------------------------------------------------------
# Main command group
# ---------------------------------------------------------------------------

def _launch_tui(
    land_on: str = "home",
    folder: str | None = None,
    speaker: bool = False,
    mic: str | None = None,
    prog_name: str = "rec",
) -> None:
    """Launch the Textual TUI app and run until quit."""
    from liscribe.app import LiscribeApp
    app = LiscribeApp(
        land_on=land_on,
        folder=folder,
        speaker=speaker,
        mic=mic,
        prog_name=prog_name or "rec",
    )
    app.run()


@click.group(invoke_without_command=True)
@click.option(
    "-f", "--folder",
    type=click.Path(),
    help="Folder to save recordings and transcripts.",
)
@click.option(
    "-h", "--here",
    "here",
    is_flag=True,
    default=False,
    help="Save to ./docs/transcripts in current directory.",
)
@click.option(
    "-o", "--output",
    "speaker",
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
    "-s", "--start",
    is_flag=True,
    default=False,
    help="Go straight to Record screen (skip Home).",
)
@click.option("--debug", is_flag=True, default=False, help="Enable debug logging.")
@_model_options
@click.version_option(__version__, prog_name="liscribe")
@click.pass_context
def main(
    ctx: click.Context,
    folder: str | None,
    here: bool,
    speaker: bool,
    mic: str | None,
    start: bool,
    debug: bool,
    model_tiny: bool,
    model_base: bool,
    model_small: bool,
    model_medium: bool,
    model_large: bool,
) -> None:
    """Liscribe — 100% offline terminal recorder and transcriber."""
    setup_logging(debug=debug)
    ctx.ensure_object(dict)
    ctx.obj["folder"] = folder
    ctx.obj["here"] = here
    ctx.obj["speaker"] = speaker
    ctx.obj["mic"] = mic
    ctx.obj["models_selected"] = _collect_models(
        model_tiny, model_base, model_small, model_medium, model_large,
    )

    if ctx.invoked_subcommand is not None:
        return

    # -- Launch TUI: Home or Record (when --start) --
    land_on = "record" if start else "home"
    resolved_folder: str | None = None
    if land_on == "record":
        resolved_folder = _resolve_folder(folder, here)
        Path(resolved_folder).expanduser().resolve().mkdir(parents=True, exist_ok=True)
    _launch_tui(
        land_on=land_on,
        folder=resolved_folder,
        speaker=speaker,
        mic=mic,
        prog_name=ctx.info_name or "rec",
    )


# ---------------------------------------------------------------------------
# transcribe subcommand  (alias: t)
# ---------------------------------------------------------------------------

@main.command(name="transcribe")
@click.argument("audio_files", nargs=-1, type=click.Path(exists=True), required=True)
@_model_options
@click.pass_context
def transcribe_cmd(
    ctx: click.Context,
    audio_files: tuple[str, ...],
    model_tiny: bool,
    model_base: bool,
    model_small: bool,
    model_medium: bool,
    model_large: bool,
) -> None:
    """Transcribe existing audio files (WAV, MP3, M4A, OGG, etc.)."""
    models = _collect_models(model_tiny, model_base, model_small, model_medium, model_large)
    if not models:
        parent_models = ctx.obj.get("models_selected", [])
        if parent_models:
            models = parent_models
    if not models:
        cfg = load_config()
        models = [cfg.get("whisper_model", "base")]

    folder = ctx.obj.get("folder")
    here = ctx.obj.get("here", False)

    output_dir = None
    if folder or here:
        output_dir = str(Path(_resolve_folder(folder, here)).expanduser().resolve())
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        console.print(f"  [dim]Saving transcripts to {output_dir}[/dim]")

    for audio_file in audio_files:
        audio_path = Path(audio_file).resolve()
        console.print(f"\n  [bold]{audio_path.name}[/bold]")

        _run_transcription_pipeline(
            audio_path=str(audio_path),
            models=models,
            output_dir=output_dir,
            ctx=ctx,
        )


main.add_command(transcribe_cmd, "t")


# ---------------------------------------------------------------------------
# setup subcommand
# ---------------------------------------------------------------------------

def _setup_configure_only(cfg: dict) -> None:
    """Prompt for default model, language, and command alias; save config. No model download."""
    from liscribe.config import save_config
    from liscribe.transcriber import is_model_available

    current_model = cfg.get("whisper_model", "base")
    model_names = [name for name, _ in WHISPER_MODELS]

    console.print()
    console.print("  [bold]Default model[/bold]")
    for i, (name, desc) in enumerate(WHISPER_MODELS, 1):
        installed = " [green]✓[/green]" if is_model_available(name) else ""
        current = " [dim](current default)[/dim]" if name == current_model else ""
        console.print(f"    {i}. [bold]{name:<8}[/bold] {desc}{installed}{current}")
    default_idx = model_names.index(current_model) + 1 if current_model in model_names else 2
    default_choice = click.prompt(
        "  Default model for recordings (number)",
        type=click.IntRange(1, len(WHISPER_MODELS)),
        default=default_idx,
    )
    default_model = model_names[default_choice - 1]

    current_lang = cfg.get("language", "en")
    console.print()
    lang = click.prompt(
        "  Transcription language (ISO 639-1 code, e.g. en, fr, de, or 'auto')",
        default=current_lang,
    ).strip().lower()

    current_alias = cfg.get("command_alias", "rec")
    console.print()
    alias = click.prompt(
        "  Command alias/name for help messages (e.g., rec, scrib)",
        default=current_alias,
    ).strip()

    cfg["whisper_model"] = default_model
    cfg["language"] = lang
    cfg["command_alias"] = alias
    save_config(cfg)
    console.print(f"\n  Config saved: default=[bold]{default_model}[/bold], language=[bold]{lang}[/bold], alias=[bold]{alias}[/bold]")

    rc_updated = _update_shell_alias(alias)
    if rc_updated:
        console.print(f"  Shell alias updated in [dim]{rc_updated}[/dim]")
        console.print(f"  Run: [bold]source {rc_updated}[/bold]  to use [bold]{alias}[/bold] in this terminal.")


def _setup_download_models(cfg: dict) -> None:
    """Prompt for which models to download and download them."""
    from liscribe.transcriber import is_model_available, load_model

    current_model = cfg.get("whisper_model", "base")
    model_names = [name for name, _ in WHISPER_MODELS]

    console.print()
    console.print("  Available whisper models:")
    for i, (name, desc) in enumerate(WHISPER_MODELS, 1):
        installed = " [green]✓[/green]" if is_model_available(name) else ""
        current = " [dim](default)[/dim]" if name == current_model else ""
        console.print(f"    {i}. [bold]{name:<8}[/bold] {desc}{installed}{current}")

    console.print()
    console.print("  [dim]Enter numbers to download (e.g. 2,4,5 or 2-5 or all), or leave empty to skip[/dim]")
    raw = click.prompt(
        "  Models to download",
        default="",
        show_default=False,
    ).strip().lower()

    if not raw:
        console.print("  [dim]Skipping model download.[/dim]")
        return

    indices: set[int] = set()
    if raw == "all":
        indices = set(range(1, len(WHISPER_MODELS) + 1))
    else:
        for part in raw.replace(",", " ").split():
            if "-" in part:
                a, b = part.split("-", 1)
                try:
                    lo, hi = int(a.strip()), int(b.strip())
                    indices.update(range(lo, hi + 1))
                except ValueError:
                    pass
            else:
                try:
                    indices.add(int(part))
                except ValueError:
                    pass

    to_download = [model_names[i - 1] for i in sorted(indices) if 1 <= i <= len(WHISPER_MODELS)]
    if not to_download:
        console.print("  [dim]No models selected.[/dim]")
        return

    for model_size in to_download:
        if is_model_available(model_size):
            console.print(f"  [dim]Skipping [bold]{model_size}[/bold] (already installed)[/dim]")
            continue
        with console.status(f"  Downloading [bold]{model_size}[/bold]..."):
            try:
                load_model(model_size)
                console.print(f"  [green]Ready:[/green] {model_size}")
            except Exception as exc:
                console.print(f"  [red]Error [bold]{model_size}[/bold]:[/red] {exc}")


@main.command()
def setup() -> None:
    """Check dependencies and configure liscribe."""
    from liscribe.config import save_config
    from liscribe.platform_setup import run_all_checks

    created = init_config_if_missing()
    if created:
        console.print(f"  Created default config at [dim]{CONFIG_PATH}[/dim]")
    else:
        console.print(f"  Config already exists at [dim]{CONFIG_PATH}[/dim]")

    console.print()
    results = run_all_checks(include_speaker=True)
    all_ok = True
    for name, ok, msg in results:
        icon = "[green]OK[/green]" if ok else "[red]MISSING[/red]"
        console.print(f"  [{icon}] {name}: {msg}")
        if not ok:
            all_ok = False

    console.print()
    if all_ok:
        console.print("  [green]All checks passed.[/green]")
    else:
        console.print("  [yellow]Some checks failed.[/yellow] See above for install instructions.")

    cfg = load_config()

    console.print()
    console.print("  [bold]What would you like to do?[/bold]")
    console.print("    1. [dim]Exit[/dim] (dependency check done)")
    console.print("    2. Configure settings only (alias, language, default model)")
    console.print("    3. Download whisper models")
    console.print("    4. Configure settings, then download models")
    choice = click.prompt(
        "  Choice",
        type=click.IntRange(1, 4),
        default=1,
    )

    if choice == 1:
        return
    if choice == 2:
        _setup_configure_only(cfg)
        return
    if choice == 3:
        _setup_download_models(cfg)
        return
    # choice == 4
    _setup_configure_only(load_config())
    _setup_download_models(load_config())


# ---------------------------------------------------------------------------
# config subcommand
# ---------------------------------------------------------------------------

@main.command()
@click.option("--show", is_flag=True, help="Show current config values.")
@click.pass_context
def config(ctx: click.Context, show: bool) -> None:
    """Show or edit configuration."""
    if show:
        cfg = load_config()
        for key, val in cfg.items():
            console.print(f"  [bold]{key}:[/bold] {val}")
        console.print(f"  [dim]See config.example.json or README for all options and descriptions.[/dim]")
    else:
        console.print(f"  Config file: [dim]{CONFIG_PATH}[/dim]")
        cmd_name = _get_command_name(ctx)
        console.print(
            f"  Edit it directly, or use [bold]'{cmd_name} config --show'[/bold] to view current values."
        )
        console.print(f"  [dim]See config.example.json or README for all options and descriptions.[/dim]")


# ---------------------------------------------------------------------------
# preferences / help / devices — launch TUI on that screen
# ---------------------------------------------------------------------------

@main.command()
@click.pass_context
def preferences(ctx: click.Context) -> None:
    """Open Preferences in the TUI."""
    _launch_tui(land_on="preferences", prog_name=_get_command_name(ctx))


@main.command(name="help")
@click.pass_context
def help_cmd(ctx: click.Context) -> None:
    """Open Help in the TUI."""
    _launch_tui(land_on="help", prog_name=_get_command_name(ctx))


@main.command()
@click.pass_context
def devices(ctx: click.Context) -> None:
    """List available audio input devices (in TUI)."""
    _launch_tui(land_on="devices", prog_name=_get_command_name(ctx))


def get_help_text(prog_name: str = "rec") -> str:
    """Return the same help text as rec --help (for Help TUI screen)."""
    ctx = click.Context(main, info_name=prog_name)
    return ctx.get_help()


# Wrapper for entry point scripts (converts -xxs to --tiny before Click parses)
def main_wrapper():
    """Entry point wrapper that preprocesses arguments before calling main()."""
    _preprocess_model_args()
    # Click will parse the modified sys.argv when main() is invoked
    main()
