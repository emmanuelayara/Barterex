"""Private identity-document storage and explicit legacy-file relocation."""

import os
from pathlib import Path

from flask import current_app


def document_path(filename):
    if not filename or Path(filename).name != filename or '/' in filename or '\\' in filename:
        raise ValueError('Invalid identity document name.')
    root = Path(current_app.config['IDENTITY_DOCUMENT_FOLDER']).resolve()
    path = root / filename
    if path.is_symlink() or path.resolve().parent != root:
        raise ValueError('Invalid identity document path.')
    return path


def relocate_legacy_documents():
    from models import User

    legacy = Path(current_app.root_path) / 'static' / 'uploads' / 'verification'
    moved = 0
    for user in User.query.filter(User.government_id_document.isnot(None)).all():
        target = document_path(user.government_id_document)
        source = legacy / user.government_id_document
        if source.is_symlink():
            raise ValueError('Refusing to relocate a symlinked identity document.')
        if source.is_file():
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                raise ValueError('Both public and private copies exist; reconcile them before retrying.')
            os.replace(source, target)
            moved += 1
        elif not target.is_file():
            raise ValueError(f'Identity document missing for user {user.id}.')
    return moved
