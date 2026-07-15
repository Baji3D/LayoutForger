"""
LayoutForger — Drag-and-drop installer for Maya.
Drag this file into the Maya viewport to install.

By Baji N | baji.digital
"""
import maya.cmds as cmds
import maya.mel as mel
import os
import sys
import base64

# ---------------------------------------------------------------------------
# Icon embedded as base64 (32x32 PNG)
# ---------------------------------------------------------------------------
_ICON_B64 = (
    "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"
)


def onMayaDroppedPythonFile(*args, **kwargs):
    """Called automatically by Maya when this file is dragged into the viewport."""

    # --- 1. Resolve source directory ---
    try:
        install_file = args[0]
    except (IndexError, TypeError):
        try:
            install_file = __file__
        except NameError:
            cmds.warning('Anim Shortcuts: Could not determine install path.')
            return

    install_dir = os.path.dirname(os.path.abspath(install_file))

    # --- 2. Write icon to Documents/maya/prefs/icons (hardcoded, AYON-proof) ---
    # We always use the real Windows Documents folder, never a pipeline override.
    docs_maya = os.path.join(
        os.environ.get('USERPROFILE', os.path.expanduser('~')),
        'Documents', 'maya')
    icon_name = 'anim_shortcuts_icon.png'
    icon_written = False
    for icons_candidate in [
        os.path.join(docs_maya, 'prefs', 'icons'),
        # also try version-specific
        os.path.join(docs_maya, cmds.about(version=True).split()[0], 'prefs', 'icons'),
    ]:
        try:
            if not os.path.exists(icons_candidate):
                os.makedirs(icons_candidate)
            with open(os.path.join(icons_candidate, icon_name), 'wb') as f:
                f.write(base64.b64decode(_ICON_B64))
            icon_written = True
        except Exception:
            pass

    if not icon_written:
        icon_name = 'commandButton.png'

    # --- 3. Create shelf button ---
    # No file copying needed — point shelf button straight at the source folder.
    try:
        gShelfTopLevel = mel.eval('$tmpVar=$gShelfTopLevel')
        current_shelf  = cmds.tabLayout(gShelfTopLevel, query=True, selectTab=True)
    except Exception as e:
        cmds.warning('Anim Shortcuts: Could not find active shelf — ' + str(e))
        return

    button_code = (
        'import sys, importlib\n'
        'script_path = r"{src}"\n'
        'if script_path not in sys.path:\n'
        '    sys.path.insert(0, script_path)\n'
        'import layout_forger\n'
        'importlib.reload(layout_forger)\n'
        'layout_forger.enable_all_hotkeys()\n'
        'layout_forger.show_ui()\n'
    ).format(src=install_dir)

    cmds.shelfButton(
        command=button_code,
        annotation='LayoutForger by Baji N',
        sourceType='python',
        imageOverlayLabel='',
        image=icon_name,
        parent=current_shelf,
    )

    # --- 4. Write userSetup.py (into real Documents/maya/scripts, AYON-proof) ---
    scripts_dir = os.path.join(docs_maya, 'scripts')
    try:
        if not os.path.exists(scripts_dir):
            os.makedirs(scripts_dir)
    except Exception:
        pass

    setup_file = os.path.join(scripts_dir, 'userSetup.py')
    marker     = '# --- LayoutForger Auto-Start ---'
    content    = ''
    if os.path.exists(setup_file):
        with open(setup_file, 'r') as f:
            content = f.read()

    if marker not in content:
        startup_block = (
            '\n'
            + marker + '\n'
            'import sys, maya.cmds as cmds\n'
            'def _init_layout_forger():\n'
            '    try:\n'
            '        script_path = r"{src}"\n'
            '        if script_path not in sys.path:\n'
            '            sys.path.insert(0, script_path)\n'
            '        import layout_forger\n'
            '        layout_forger.enable_all_hotkeys()\n'
            '    except Exception as e:\n'
            '        print("LayoutForger startup error: " + str(e))\n'
            'cmds.evalDeferred(_init_layout_forger)\n'
            '# ---------------------------------\n'
        ).format(src=install_dir)
        try:
            with open(setup_file, 'a') as f:
                f.write(startup_block)
        except Exception:
            pass

    # --- 5. Enable hotkeys right now ---
    if install_dir not in sys.path:
        sys.path.insert(0, install_dir)
    try:
        import importlib
        import layout_forger
        importlib.reload(layout_forger)
        layout_forger.enable_all_hotkeys()
    except Exception as e:
        cmds.warning('Anim Shortcuts: Could not activate hotkeys — ' + str(e))

    # --- 6. Done — show the About window as a welcome screen ---
    try:
        import layout_forger
        layout_forger.show_about()
    except Exception:
        cmds.confirmDialog(
            title='LayoutForger Installed',
            message='Installed successfully!\n\nBy Baji N\nbaji.digital',
            button=['Got it'],
            defaultButton='Got it',
        )
