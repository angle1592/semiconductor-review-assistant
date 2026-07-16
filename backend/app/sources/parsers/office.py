from collections.abc import Callable
from pathlib import Path
import platform
import re
import shutil

from app.shared.errors import AppError


class OfficeConversionUnavailable(AppError):
    def __init__(self):
        super().__init__(
            code="OFFICE_CONVERSION_UNAVAILABLE",
            message=(
                "此电脑未检测到可用的 Microsoft Office，无法解析旧版 .doc/.ppt。"
                "请另存为 .docx/.pptx 后重试。"
            ),
            status_code=422,
            action="convert_to_modern_format",
        )


def _registered(prog_id: str) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        import winreg

        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, f"{prog_id}\\CLSID"):
            return True
    except OSError:
        return False


def _convert_doc(source: Path, target: Path) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = win32com.client.DispatchEx("Word.Application")
    word.Visible = False
    document = None
    try:
        document = word.Documents.Open(str(source.resolve()), ReadOnly=True)
        document.SaveAs2(str(target.resolve()), FileFormat=16)
    finally:
        if document is not None:
            document.Close(False)
        word.Quit()
        pythoncom.CoUninitialize()


def _convert_ppt(source: Path, target: Path) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
    presentation = None
    try:
        presentation = powerpoint.Presentations.Open(str(source.resolve()), WithWindow=False)
        presentation.SaveAs(str(target.resolve()), 24)
    finally:
        if presentation is not None:
            presentation.Close()
        powerpoint.Quit()
        pythoncom.CoUninitialize()


def convert_legacy_office(
    source: Path,
    output_dir: Path,
    *,
    office_available: Callable[[], bool] | None = None,
) -> Path:
    extension = source.suffix.lower()
    prog_id = "Word.Application" if extension == ".doc" else "PowerPoint.Application"
    available = office_available() if office_available else _registered(prog_id)
    if not available:
        raise OfficeConversionUnavailable()
    output_dir.mkdir(parents=True, exist_ok=True)
    target = output_dir / f"{source.stem}{'.docx' if extension == '.doc' else '.pptx'}"
    if extension == ".doc":
        _convert_doc(source, target)
    else:
        _convert_ppt(source, target)
    return target


def _export_with_powerpoint(source: Path, export_dir: Path) -> None:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    powerpoint = win32com.client.DispatchEx("PowerPoint.Application")
    presentation = None
    try:
        presentation = powerpoint.Presentations.Open(str(source.resolve()), WithWindow=False)
        presentation.Export(str(export_dir.resolve()), "PNG")
    finally:
        if presentation is not None:
            presentation.Close()
        powerpoint.Quit()
        pythoncom.CoUninitialize()


def render_pptx_previews(
    source: Path,
    output_dir: Path,
    *,
    exporter: Callable[[Path, Path], None] | None = None,
) -> tuple[str, ...]:
    if exporter is None and not _registered("PowerPoint.Application"):
        return ()
    render_dir = output_dir / "slides"
    render_dir.mkdir(parents=True, exist_ok=True)
    export_dir = output_dir / "powerpoint-render"
    if export_dir.exists():
        shutil.rmtree(export_dir)
    export_dir.mkdir(parents=True)
    (exporter or _export_with_powerpoint)(source, export_dir)

    def slide_number(path: Path) -> tuple[int, str]:
        match = re.search(r"(\d+)(?=\.[^.]+$)", path.name)
        return (int(match.group(1)) if match else 0, path.name)

    rendered: list[str] = []
    images = sorted(
        (path for path in export_dir.iterdir() if path.suffix.lower() == ".png"),
        key=slide_number,
    )
    for index, image in enumerate(images, start=1):
        relative = f"slides/slide-{index:04d}.png"
        image.replace(output_dir / relative)
        rendered.append(relative)
    shutil.rmtree(export_dir)
    return tuple(rendered)
