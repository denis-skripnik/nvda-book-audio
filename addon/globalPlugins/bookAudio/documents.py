"""Document input and chapter utilities without NVDA dependencies."""

if __package__:
    from .i18n import _
else:
    from i18n import _
from pathlib import Path
import re
from io import BytesIO
import zipfile
from copy import copy

MAX_DOCUMENT_BYTES = 128 * 1024 * 1024


def safe_name(name: str) -> str:
    """Return a non-reserved Windows filename component (at most 100 chars)."""
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    name = name[:100].rstrip(" .") or _("Книга")
    stem = name.split(".", 1)[0].rstrip(" ").upper()
    reserved = {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
    reserved.update(prefix + digit for prefix in ("COM", "LPT") for digit in "123456789¹²³")
    if stem in reserved:
        name = ("_" + name)[:100].rstrip(" .")
    return name


def split_chapters(text: str, separator: str) -> list[tuple[str, str]]:
    """Split at literal, case-insensitive line-start phrases; retain headings."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").strip()
    if not text:
        return []
    if not separator:
        return [(_("Книга"), text)]
    boundary = r"(?!\w)" if separator[-1].isalnum() or separator[-1] == "_" else ""
    pattern = re.compile(r"^" + re.escape(separator) + boundary, re.IGNORECASE | re.MULTILINE)
    starts = list(pattern.finditer(text))
    if not starts:
        return [(_("Книга"), text)]
    chapters = []
    preface = text[:starts[0].start()].strip()
    if preface:
        chapters.append((_("Предисловие"), preface))
    for index, match in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        body = text[match.start():end].strip()
        chapters.append((body.split("\n", 1)[0].strip(), body))
    return chapters


def _read_fb2(data):
    try:
        if __package__:
            from .vendor.defusedxml import ElementTree
        else:
            from defusedxml import ElementTree
        root = ElementTree.fromstring(data, forbid_dtd=True, forbid_entities=True, forbid_external=True)
    except Exception as error:
        raise ValueError(_("Не удалось прочитать FB2: повреждённый или небезопасный XML.")) from error
    lines = []

    def collect(element):
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "empty-line":
            lines.append("")
        elif tag in ("p", "subtitle", "v", "text-author", "date", "td", "th") or (tag == "title" and not list(element)):
            lines.append("".join(element.itertext()).strip())
        elif tag not in ("binary", "description", "image"):
            for child in element:
                collect(child)

    for body in root:
        if body.tag.rsplit("}", 1)[-1] == "body":
            collect(body)
    return "\n".join(lines).strip()


class _PasswordProtectedPDF(ValueError):
    """Route password errors by type, never by translated message text."""


def _read_pdf(data):
    from io import BytesIO
    try:
        if __package__:
            from .vendor.pypdf import PdfReader
        else:
            from pypdf import PdfReader
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted and not reader.decrypt(""):
            raise _PasswordProtectedPDF(_("PDF защищён паролем. Сначала снимите защиту документа."))
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    except _PasswordProtectedPDF:
        raise
    except Exception as error:
        raise ValueError(_("Не удалось прочитать PDF: файл повреждён или не поддерживается.")) from error
    if not text:
        raise ValueError(_("В PDF нет доступного текста. Выполните распознавание текста (OCR) и повторите попытку."))
    return text


def _read_fb2_zip(data):
    try:
        with zipfile.ZipFile(BytesIO(data)) as archive:
            for info in archive.infolist():
                name = info.filename.replace("\\", "/")
                if name.startswith("/") or ".." in name.split("/") or re.match(r"^[A-Za-z]:", name):
                    raise ValueError(_("Архив FB2.ZIP содержит небезопасное имя файла."))
                if info.flag_bits & 1:
                    raise ValueError(_("Архив FB2.ZIP зашифрован. Сначала снимите защиту архива."))
            payloads = [info for info in archive.infolist()
                        if not info.is_dir() and info.filename.lower().endswith(".fb2")]
            if len(payloads) != 1:
                raise ValueError(_("Архив FB2.ZIP должен содержать ровно один файл FB2."))
            payload = payloads[0]
            if payload.file_size > MAX_DOCUMENT_BYTES:
                raise ValueError(_("FB2 в архиве слишком большой: допустимо не более 128 МиБ."))
            # ZipExtFile normally truncates at the untrusted declared file_size.
            # Give a copy a bounded ceiling instead, so forged sizes/CRCs cannot
            # hide trailing expansion. Keep the archive's own metadata unchanged.
            bounded = copy(payload)
            bounded.file_size = MAX_DOCUMENT_BYTES + 1
            with archive.open(bounded) as stream:
                content = stream.read(MAX_DOCUMENT_BYTES + 1)
            if len(content) > MAX_DOCUMENT_BYTES:
                raise ValueError(_("FB2 в архиве слишком большой: допустимо не более 128 МиБ."))
            if len(content) != payload.file_size:
                raise ValueError(_("Архив FB2.ZIP повреждён: неверный размер файла FB2."))
            return _read_fb2(content)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(_("Не удалось прочитать архив FB2.ZIP: архив повреждён или не поддерживается.")) from error


def read_document(path) -> str:
    """Read FB2, FB2.ZIP, TXT or PDF; expose localized user-facing errors."""
    path = Path(path)
    suffix = path.suffix.lower()
    zipped_fb2 = path.name.lower().endswith(".fb2.zip")
    if suffix not in (".txt", ".fb2", ".pdf") and not zipped_fb2:
        raise ValueError(_("Неподдерживаемый формат. Выберите файл FB2, FB2.ZIP, TXT или PDF."))
    limit = MAX_DOCUMENT_BYTES
    try:
        if path.stat().st_size > limit:
            raise ValueError(_("Документ слишком большой: допустимо не более 128 МиБ."))
        with path.open("rb") as stream:
            data = stream.read(limit + 1)
    except OSError as error:
        raise ValueError(_("Не удалось прочитать файл. Проверьте путь и права доступа.")) from error
    if len(data) > limit:
        raise ValueError(_("Документ слишком большой: допустимо не более 128 МиБ."))
    if zipped_fb2:
        return _read_fb2_zip(data)
    if suffix == ".pdf":
        return _read_pdf(data)
    if suffix == ".fb2":
        return _read_fb2(data)
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return data.decode("utf-16")
        try:
            return data.decode("utf-8-sig")
        except UnicodeDecodeError:
            return data.decode("cp1251")
    except UnicodeDecodeError as error:
        raise ValueError(_("Не удалось определить кодировку TXT. Сохраните файл в UTF-8 или UTF-16.")) from error
