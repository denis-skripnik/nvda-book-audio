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
from dataclasses import dataclass


@dataclass
class Document:
    text: str
    sections: list[tuple[str, str]]
    annotation: str = ''
    kind: str = 'txt'

MAX_DOCUMENT_BYTES = 128 * 1024 * 1024

# Input-language vocabulary is data, not UI text: never translate these tokens.
_HEADING_PREFIXES = ('глава', 'часть', 'chapter', 'part')
_HEADING_RU_WORDS = ('первая вторая третья четвёртая четвертая пятая шестая седьмая восьмая '
                     'девятая десятая одиннадцатая двенадцатая тринадцатая четырнадцатая '
                     'пятнадцатая шестнадцатая семнадцатая восемнадцатая девятнадцатая '
                     'двадцатая тридцатая сороковая пятидесятая шестидесятая семидесятая '
                     'восьмидесятая девяностая сотая')
_HEADING_RU_TENS = ('двадцать', 'тридцать', 'сорок', 'пятьдесят', 'шестьдесят', 'семьдесят', 'восемьдесят', 'девяносто')


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


def plan_chapters(book: Document, separator: str, mode='auto', include_annotation=True) -> list[tuple[str, str]]:
    """Plan speech tracks without treating narrative FB2 paragraphs as headings."""
    if mode not in ('auto', 'structure', 'phrase', 'none'):
        raise ValueError(_('Неизвестный режим разбиения книги.'))
    if type(include_annotation) is not bool:
        raise ValueError(_('Параметр озвучивания аннотации должен быть логическим значением.'))
    whole = [(_('Книга'), book.text.strip())] if book.text.strip() else []
    annotation = book.annotation.strip() if include_annotation else ''
    if mode == 'none':
        text = '\n\n'.join(part for part in (annotation, book.text.strip()) if part)
        return [(_('Книга'), text)] if text else []
    if mode == 'phrase':
        chapters = split_chapters(book.text, separator)
    elif mode == 'auto':
        chapters = list(book.sections) or _numbered_chapters(book.text)
    else:
        chapters = list(book.sections) or whole
    return ([(_('Аннотация'), annotation)] if annotation else []) + chapters


def _numbered_chapters(text, separator=None):
    """Conservative fallback: fixed-prefix numbered headings, at most 120 chars.

    Narrative and freely titled lines are not guessed. The optional legacy
    separator argument is ignored: persisted custom prefixes cannot affect auto.
    """
    text = text.replace('\r\n', '\n').replace('\r', '\n').strip()
    whole = [(_('Книга'), text)] if text else []

    ru = _HEADING_RU_WORDS.split()
    en = ('one two three four five six seven eight nine ten eleven twelve thirteen '
          'fourteen fifteen sixteen seventeen eighteen nineteen twenty thirty forty '
          'fifty sixty seventy eighty ninety hundred first second third fourth fifth '
          'sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth '
          'fifteenth sixteenth seventeenth eighteenth nineteenth twentieth thirtieth').split()
    words = set(ru + en)
    for tens in _HEADING_RU_TENS:
        words.update(tens + ' ' + unit for unit in ru[:10])
    for tens in ('twenty', 'thirty', 'forty', 'fifty', 'sixty', 'seventy', 'eighty', 'ninety'):
        words.update(tens + joiner + unit for joiner in (' ', '-') for unit in en[:9])
    prefix = re.compile(r'^[^\S\n]*(?:' + '|'.join(map(re.escape, _HEADING_PREFIXES))
                        + r')[^\S\n]+(.+?)[^\S\n]*$', re.IGNORECASE)
    roman = re.compile(r'M{0,3}(CM|CD|D?C{0,3})(XC|XL|L?X{0,3})(IX|IV|V?I{0,3})', re.IGNORECASE)
    starts = []
    for match in re.finditer(r'^.*$', text, re.MULTILINE):
        line = match.group()
        heading = prefix.fullmatch(line) if len(line) <= 120 else None
        if heading:
            number = heading.group(1).removesuffix('.').casefold()
            if number in words or re.fullmatch(r'[0-9]+', number) or (number and roman.fullmatch(number)):
                starts.append(match.start())
    if not starts:
        return whole
    chapters = []
    if text[:starts[0]].strip():
        chapters.append((_('Предисловие'), text[:starts[0]].removesuffix('\n')))
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(text)
        # Remove just the boundary newline, not indentation, blank paragraphs,
        # or literal trailing spaces within a section.
        body = text[start:end].removesuffix('\n')
        chapters.append((body.split('\n', 1)[0].strip(), body))
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
    return _fb2_document(root)


def _fb2_document(root):
    lines = []
    headings = []

    def collect(element, parent_tag=''):
        start = len(lines)
        tag = element.tag.rsplit('}', 1)[-1]
        is_heading = tag == 'title' and parent_tag == 'section'
        collect_text(element)
        if is_heading:
            title = '\n'.join(lines[start:]).strip()
            if title:
                headings.append((start, len(lines), title))

    def collect_text(element):
        tag = element.tag.rsplit("}", 1)[-1]
        if tag == "empty-line":
            lines.append("")
        elif tag in ("p", "subtitle", "v", "text-author", "date", "td", "th") or (tag == "title" and not list(element)):
            lines.append("".join(element.itertext()).strip())
        elif tag not in ("binary", "description", "image"):
            for child in element:
                collect(child, tag)

    for body in root:
        if body.tag.rsplit("}", 1)[-1] == "body":
            collect(body)
    text = '\n'.join(lines).strip()
    sections = []
    if headings:
        preface = '\n'.join(lines[:headings[0][0]]).strip()
        if preface:
            sections.append((_('Предисловие'), preface))
        pending = headings[0][0]
        for index, (start, title_end, title) in enumerate(headings):
            end = headings[index + 1][0] if index + 1 < len(headings) else len(lines)
            # A heading-only container belongs to its first nonempty child.
            if index + 1 < len(headings) and not any(line.strip() for line in lines[title_end:end]):
                continue
            section = '\n'.join(lines[pending:end]).strip()
            if section:
                sections.append((title, section))
            pending = end
    # Only the primary title-info contributes an annotation, never src-title-info.
    annotation = ''
    primary = root
    for tag in ('description', 'title-info', 'annotation'):
        primary = next((child for child in primary
                        if child.tag.rsplit('}', 1)[-1] == tag), None)
        if primary is None:
            break
    if primary is not None:
        lines = []
        collect(primary)
        annotation = '\n'.join(lines).strip()
    return Document(text, sections, annotation, kind='fb2')


class _PasswordProtectedPDF(ValueError):
    """Route password errors by type, never by translated message text."""


def _read_pdf(data, structured=False):
    from io import BytesIO
    try:
        if __package__:
            from .vendor.pypdf import PdfReader
        else:
            from pypdf import PdfReader
        reader = PdfReader(BytesIO(data), strict=True)
        if reader.is_encrypted and not reader.decrypt(""):
            raise _PasswordProtectedPDF(_("PDF защищён паролем. Сначала снимите защиту документа."))
        pages = [page.extract_text() or "" for page in reader.pages]
        text = "\n\n".join(pages).strip()
    except _PasswordProtectedPDF:
        raise
    except Exception as error:
        raise ValueError(_("Не удалось прочитать PDF: файл повреждён или не поддерживается.")) from error
    if not text:
        raise ValueError(_("В PDF нет доступного текста. Выполните распознавание текста (OCR) и повторите попытку."))
    if not structured:
        return text
    starts = {}

    def bookmarks(items):
        if not isinstance(items, list):
            return
        for item in items:
            if isinstance(item, list):
                bookmarks(item)
                continue
            try:
                page = reader.get_destination_page_number(item)
                title = str(item.get('/Title', '')).strip()
            except Exception:
                continue  # Unresolvable/nonlocal metadata is not a text error.
            if type(page) is int and 0 <= page < len(pages) and title:
                starts.setdefault(page, title)  # First title on each page wins.

    try:
        bookmarks(reader.outline)
    except Exception:
        starts.clear()  # Malformed optional outlines must not lose page text.
    sections = []
    ordered = sorted(starts)
    if ordered:
        preface = '\n\n'.join(pages[:ordered[0]]).strip()
        if preface:
            sections.append((_('Предисловие'), preface))
        for index, start in enumerate(ordered):
            end = ordered[index + 1] if index + 1 < len(ordered) else len(pages)
            body = '\n\n'.join(pages[start:end]).strip()
            if body:
                sections.append((starts[start], body))
    return Document(text, sections, kind='pdf')


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
    """Compatibility API: return body text only, without annotation."""
    return read_book(path).text


def read_book(path) -> Document:
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
        return _read_pdf(data, structured=True)
    if suffix == ".fb2":
        return _read_fb2(data)
    try:
        if data.startswith((b"\xff\xfe", b"\xfe\xff")):
            return Document(data.decode("utf-16"), [])
        try:
            return Document(data.decode("utf-8-sig"), [])
        except UnicodeDecodeError:
            return Document(data.decode("cp1251"), [])
    except UnicodeDecodeError as error:
        raise ValueError(_("Не удалось определить кодировку TXT. Сохраните файл в UTF-8 или UTF-16.")) from error
