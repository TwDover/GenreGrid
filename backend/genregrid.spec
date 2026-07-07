# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for GenreGrid backend.
# Build with:  pyinstaller genregrid.spec
# Output:      dist/genregrid-backend/   (onedir bundle)

block_cipher = None

a = Analysis(
    ['run.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        # Bundle all style JSON files so they're available at app/styles/ inside the bundle
        ('app/styles', 'app/styles'),
    ],
    hiddenimports=[
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
        'anyio',
        'anyio._backends._asyncio',
        'starlette.routing',
        'starlette.middleware.cors',
        'fastapi.routing',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'httpx', 'pytest_asyncio'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='genregrid-backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,   # windowed: no blank terminal behind the app on Windows.
                     # The Electron shell captures stdout/stderr into
                     # <userData>/logs/backend.log, so errors stay visible.
                     # For standalone debugging run the dev server instead
                     # (uvicorn app.main:app --reload).
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='genregrid-backend',
)
