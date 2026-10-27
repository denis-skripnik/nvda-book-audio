"""Ordered book conversion with no-clobber output directories."""

if __package__:
    from .i18n import _
else:
    from i18n import _
from pathlib import Path


def unique_directory(output, name):
    root = Path(output)
    if not root.is_dir():
        raise ValueError(_('Выберите существующую папку для сохранения.'))
    for number in range(1, 10000):
        path = root / (name if number == 1 else f'{name} ({number})')
        try:
            path.mkdir()
            return path
        except FileExistsError:
            continue
    raise RuntimeError(_('Не удалось подобрать свободное имя папки.'))


def convert(request, read, split, safe, render, encode, emit):
    completed = 0
    for file_index, source in enumerate(request['files'], 1):
        source = Path(source)
        emit('status', message=_('Чтение файла {file_index} из {files}: {name}').format(file_index=file_index, files=len(request['files']), name=source.name))
        chapters = split(read(source), request['separator'])
        if not chapters:
            raise ValueError(_('В файле «{name}» нет текста для озвучивания.').format(name=source.name))
        book_name = source.name[:-8] if source.name.lower().endswith('.fb2.zip') else source.stem
        directory = unique_directory(request['output'], safe(book_name))
        for index, (title, text) in enumerate(chapters, 1):
            target = directory / f'{index:03d} - {safe(title)}.mp3'
            wav = Path(request['config']) / 'chapter.wav'
            emit('chapter', file=file_index, files=len(request['files']), chapter=index,
                 chapters=len(chapters), output=str(target),
                 message=_('{name}: часть {index} из {chapters}. {title}').format(name=source.name, index=index, chapters=len(chapters), title=title))
            try:
                render(text, wav)
                encode(wav, target)
            finally:
                wav.unlink(missing_ok=True)
            completed += 1
            emit('saved', output=str(target), count=completed)
    return completed
