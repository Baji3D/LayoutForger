"""
LayoutForger — Custom hotkey manager for Maya animators.
By Baji N | baji.digital
"""

VERSION = '0.0.1'

import os
import maya.cmds as cmds
import maya.mel as mel
import ctypes
import ctypes.wintypes

# optionVar to persist the selected camera across reloads
_CAM_OPTVAR = 'layoutForger_selectedCamera'

# Tracks whether hotkeys are currently registered
_hotkeys_enabled = False

# Hotkey command prefix: always reload module before running so edits take effect
_RELOAD_PREFIX = 'import importlib; import layout_forger; importlib.reload(layout_forger); '

# Hotkey definitions: label -> (key, commandName, pythonCommand)
# All bound to Ctrl+Shift+<key>
HOTKEYS = {
    'Graph Editor':    ('g', 'LayoutForger_GraphEditor',
                        _RELOAD_PREFIX + 'layout_forger.maximize_graph_editor()'),
    'Shot Camera':     ('c', 'LayoutForger_Camera',
                        _RELOAD_PREFIX + 'layout_forger.maximize_camera()'),
    'Dope Sheet':      ('d', 'LayoutForger_DopeSheet',
                        _RELOAD_PREFIX + 'layout_forger.maximize_dope_sheet()'),
    'Floating Cam':    ('f', 'LayoutForger_FloatingCam',
                        _RELOAD_PREFIX + 'layout_forger.floating_shot_cam()'),
    'Cam + Graph':     ('s', 'LayoutForger_StackedView',
                        _RELOAD_PREFIX + 'layout_forger.stacked_cam_graph()'),
    'Toggle Panels':  ('h', 'LayoutForger_TogglePanels',
                        _RELOAD_PREFIX + 'layout_forger.toggle_panels()'),
}

# ---------------------------------------------------------------------------
# Hotkey registration
# ---------------------------------------------------------------------------

def _ensure_editable_hotkeyset():
    """Switch to our custom hotkey set, creating it if needed."""
    current_set = cmds.hotkeySet(query=True, current=True)
    if current_set == 'Maya_Default':
        custom_set = 'LayoutForger_Set'
        try:
            cmds.hotkeySet(custom_set, edit=True, current=True)
        except Exception:
            cmds.hotkeySet(custom_set, source='Maya_Default', current=True)


def register_hotkey(key, name, cmd_str):
    _ensure_editable_hotkeyset()
    rtc = name + 'RTC'
    nc  = name + 'NC'
    if cmds.runTimeCommand(rtc, exists=True):
        cmds.runTimeCommand(rtc, edit=True, delete=True)
    cmds.runTimeCommand(rtc, annotation=name, command=cmd_str, commandLanguage='python')
    cmds.nameCommand(nc, annotation=name, command=rtc)
    cmds.hotkey(keyShortcut=key, ctrlModifier=True, shiftModifier=True, name=nc)


def unregister_hotkey(key):
    _ensure_editable_hotkeyset()
    cmds.hotkey(keyShortcut=key, ctrlModifier=True, shiftModifier=True, name='')


def enable_all_hotkeys():
    """Enable all custom hotkeys. Called on startup and by the shelf button."""
    global _hotkeys_enabled
    for _label, (key, cmd_name, cmd_str) in HOTKEYS.items():
        register_hotkey(key, cmd_name, cmd_str)
    _hotkeys_enabled = True


def disable_all_hotkeys():
    """Disable all custom hotkeys."""
    global _hotkeys_enabled
    for _label, (key, _cmd_name, _cmd_str) in HOTKEYS.items():
        unregister_hotkey(key)
    _hotkeys_enabled = False

# ---------------------------------------------------------------------------
# Monitor detection (Windows)
# ---------------------------------------------------------------------------

def _get_monitors():
    """Return a list of (x, y, width, height) for each monitor."""
    monitors = []
    MONITORENUMPROC = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_double)

    def callback(hMonitor, hdcMonitor, lprcMonitor, dwData):
        r = lprcMonitor.contents
        monitors.append((r.left, r.top, r.right - r.left, r.bottom - r.top))
        return True

    ctypes.windll.user32.EnumDisplayMonitors(0, None, MONITORENUMPROC(callback), 0)
    return monitors


def _get_second_monitor():
    monitors = _get_monitors()
    return monitors[1] if len(monitors) >= 2 else None

# ---------------------------------------------------------------------------
# Camera helpers
# ---------------------------------------------------------------------------

def get_scene_cameras():
    """Return all camera transform full paths (avoids name clashes with namespaces/groups)."""
    cam_shapes = cmds.ls(type='camera', long=True) or []
    transforms = []
    for shape in cam_shapes:
        parent = cmds.listRelatives(shape, parent=True, fullPath=True)
        if parent:
            transforms.append(parent[0])
    return sorted(set(transforms))


def get_selected_camera():
    """Return the stored camera name, falling back to 'persp'."""
    if cmds.optionVar(exists=_CAM_OPTVAR):
        cam = cmds.optionVar(query=_CAM_OPTVAR)
        if cmds.objExists(cam):
            return cam
    return 'persp'


def set_selected_camera(cam_name):
    cmds.optionVar(stringValue=(_CAM_OPTVAR, cam_name))

# ---------------------------------------------------------------------------
# Layout switching
# ---------------------------------------------------------------------------

def maximize_graph_editor():
    """Full-screen Graph Editor."""
    mel.eval('setNamedPanelLayout "Single Perspective View"')
    panel = cmds.getPanel(withFocus=True)
    if panel:
        try:
            cmds.scriptedPanel('graphEditor1', edit=True, replacePanel=panel)
        except Exception as e:
            cmds.warning('Could not switch to Graph Editor: ' + str(e))


def maximize_dope_sheet():
    """Full-screen Dope Sheet."""
    mel.eval('setNamedPanelLayout "Single Perspective View"')
    panel = cmds.getPanel(withFocus=True)
    if panel:
        try:
            cmds.scriptedPanel('dopeSheetPanel1', edit=True, replacePanel=panel)
        except Exception as e:
            cmds.warning('Could not switch to Dope Sheet: ' + str(e))


def maximize_camera():
    """Full-screen shot-camera viewport.

    Captures whatever camera is currently visible (respects stacked / quad
    views) before switching the layout so the panel reset does not drop you
    back to persp.
    """
    # 1. Remember the active camera before any layout change
    current_cam = None
    focused = cmds.getPanel(withFocus=True)
    if focused and cmds.getPanel(typeOf=focused) == 'modelPanel':
        current_cam = cmds.modelPanel(focused, query=True, camera=True)
    if not current_cam:
        for p in (cmds.getPanel(visiblePanels=True) or []):
            if cmds.getPanel(typeOf=p) == 'modelPanel':
                current_cam = cmds.modelPanel(p, query=True, camera=True)
                break

    # 2. Switch to single-panel layout (no Four View detour — that resets cams)
    mel.eval('setNamedPanelLayout "Single Perspective View"')

    # 3. Restore the camera we were looking through
    if current_cam:
        panel = cmds.getPanel(withFocus=True)
        if not panel or cmds.getPanel(typeOf=panel) != 'modelPanel':
            # focus may have shifted after layout swap — grab first visible
            for p in (cmds.getPanel(visiblePanels=True) or []):
                if cmds.getPanel(typeOf=p) == 'modelPanel':
                    panel = p
                    break
        if panel:
            try:
                cmds.modelPanel(panel, edit=True, camera=current_cam)
            except Exception as e:
                cmds.warning('LayoutForger: Could not restore camera — ' + str(e))


def stacked_cam_graph():
    """Persp/Graph stacked layout, retaining the current active camera."""
    # Capture current camera before switching
    current_cam = None
    panel = cmds.getPanel(withFocus=True)
    if panel and cmds.getPanel(typeOf=panel) == 'modelPanel':
        current_cam = cmds.modelPanel(panel, query=True, camera=True)
    else:
        for p in (cmds.getPanel(visiblePanels=True) or []):
            if cmds.getPanel(typeOf=p) == 'modelPanel':
                current_cam = cmds.modelPanel(p, query=True, camera=True)
                break

    mel.eval('setNamedPanelLayout "Persp/Graph"')

    # Restore camera to the top viewport
    if current_cam:
        for p in (cmds.getPanel(visiblePanels=True) or []):
            if cmds.getPanel(typeOf=p) == 'modelPanel':
                try:
                    cmds.modelPanel(p, edit=True, camera=current_cam)
                except Exception:
                    pass
                break


# All right-side workspace panels hidden by Ctrl+Shift+H.
_SIDE_PANELS = [
    'outlinerPanel1WorkspaceControl',   # Outliner
    'ChannelBoxLayerEditor',            # Channel Box / Layer Editor
    'AttributeEditor',                  # Attribute Editor
    'ToolSettings',                     # Tool Settings
    'NEXDockControl',                   # Modelling Toolkit (Maya 2022+)
    'CharacterControls',                # Character Controls
]


def toggle_panels():
    """Ctrl+Shift+H: hide all right-side panels, or restore only the Outliner.

    Any panel visible  -> hide ALL panels.
    All panels hidden  -> show Outliner only.
    """
    any_visible = False
    for ctrl in _SIDE_PANELS:
        try:
            if cmds.workspaceControl(ctrl, query=True, exists=True):
                if cmds.workspaceControl(ctrl, query=True, visible=True):
                    any_visible = True
                    break
        except Exception:
            pass

    if any_visible:
        # Hide everything
        for ctrl in _SIDE_PANELS:
            try:
                if cmds.workspaceControl(ctrl, query=True, exists=True):
                    cmds.workspaceControl(ctrl, edit=True, visible=False)
            except Exception:
                pass
    else:
        # Restore Outliner only
        mel.eval('ToggleOutliner')


def floating_shot_cam():
    """Open the shot camera full-screen on the second monitor (polygons + image planes only)."""
    if cmds.window('AnimFloatingCamWin', exists=True):
        cmds.deleteUI('AnimFloatingCamWin')

    shot_cam = get_selected_camera()

    second_mon = _get_second_monitor()
    if second_mon:
        x, y, w, h = second_mon
    else:
        x, y, w, h = 100, 100, 800, 600
        cmds.warning('No second monitor detected — opening windowed.')

    win = cmds.window('AnimFloatingCamWin',
                      title='Shot Cam: {}'.format(shot_cam),
                      widthHeight=(w, h),
                      topLeftCorner=(y, x),
                      sizeable=True,
                      titleBar=True)
    layout = cmds.paneLayout()
    panel  = cmds.modelPanel(parent=layout)
    cmds.showWindow(win)

    # Resolve the camera shape (handles namespaces + group hierarchies)
    cam_shape = shot_cam
    if cmds.objExists(shot_cam):
        resolved = cmds.ls(shot_cam, long=True)
        if resolved:
            shapes = cmds.listRelatives(resolved[0], shapes=True, type='camera', fullPath=True) or []
            if shapes:
                cam_shape = shapes[0]

    # Turn on resolution gate on the camera itself
    if cmds.objExists(cam_shape):
        try:
            cmds.camera(cam_shape, edit=True, displayResolution=True)
        except Exception:
            pass

    # Point the panel at the camera
    try:
        cmds.modelPanel(panel, edit=True, camera=cam_shape)
    except Exception:
        try:
            cmds.lookThroughModelPanel(shot_cam, panel)
        except Exception:
            cmds.warning('Could not look through camera: ' + shot_cam)

    # Viewport cleanup: polygons + image planes, shaded+textured, no wireframe
    try:
        cmds.modelEditor(panel, edit=True, allObjects=False)
        cmds.modelEditor(panel, edit=True,
                         polymeshes=True,
                         nurbsSurfaces=True,
                         subdivSurfaces=True,
                         pluginShapes=True,
                         imagePlane=True)
        cmds.setFocus(panel)
        try:
            mel.eval('DisplayShadedAndTextured')
        except Exception:
            pass
        cmds.modelEditor(panel, edit=True, wireframeOnShaded=False)
    except Exception as e:
        cmds.warning('Could not set display options: ' + str(e))

# ---------------------------------------------------------------------------
# UI
# ---------------------------------------------------------------------------

class ShortcutManagerUI(object):
    def __init__(self):
        self.win_name  = 'LayoutForgerWin'
        self.checkboxes = {}
        self.cam_menu  = None
        self.cam_label = None

    def create_ui(self):
        if cmds.window(self.win_name, exists=True):
            cmds.deleteUI(self.win_name)

        self.win = cmds.window(self.win_name, title='LayoutForger',
                               widthHeight=(280, 380))
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                          columnAttach=('both', 10))

        # Header row: title + info button
        cmds.rowLayout(numberOfColumns=2,
                       columnWidth2=(240, 30),
                       columnAttach2=('left', 'right'),
                       adjustableColumn=1)
        cmds.text(label='LayoutForger  —  Layout Hotkeys',
                  font='boldLabelFont', align='left', height=30)
        cmds.button(label='?', height=26, width=26,
                    command=lambda *_: show_about(),
                    annotation='About LayoutForger')
        cmds.setParent('..')

        # Read current hotkey state
        try:
            _ensure_editable_hotkeyset()
        except Exception:
            pass

        for label_name, (key, cmd_name, _cmd_str) in HOTKEYS.items():
            cb = cmds.checkBox(label='{} (Ctrl+Shift+{})'.format(label_name, key.upper()),
                               value=_hotkeys_enabled)
            cmds.checkBox(cb, edit=True,
                          changeCommand=lambda val, l=label_name: self._on_toggle(l, val))
            self.checkboxes[label_name] = cb

        cmds.separator(height=10, style='in')

        # Camera selector for Floating Cam
        cmds.text(label='Floating Cam Camera:', align='left')
        self.cam_menu = cmds.optionMenu(changeCommand=lambda val: self._on_camera_changed(val))
        self._populate_cameras()

        self.cam_label = cmds.text(label='  Active: {}'.format(get_selected_camera()),
                                   align='left', font='obliqueLabelFont')

        cmds.button(label='Refresh Cameras',
                    command=lambda *a: self._populate_cameras(),
                    height=22)

        cmds.separator(height=10, style='in')

        cmds.rowLayout(numberOfColumns=2, columnWidth2=(120, 120),
                       columnAttach2=('both', 'both'))
        cmds.button(label='Enable All',  command=self._enable_all,
                    backgroundColor=(0.2, 0.4, 0.2))
        cmds.button(label='Disable All', command=self._disable_all,
                    backgroundColor=(0.4, 0.2, 0.2))
        cmds.setParent('..')

        cmds.separator(height=6, style='none')
        cmds.button(label='Uninstall Plugin', command=self._uninstall,
                    backgroundColor=(0.25, 0.25, 0.25), height=20)

        cmds.showWindow(self.win)

    # --- Camera dropdown ---

    def _populate_cameras(self):
        existing = cmds.optionMenu(self.cam_menu, query=True, itemListLong=True) or []
        for item in existing:
            cmds.deleteUI(item)

        cameras = get_scene_cameras()
        saved   = get_selected_camera()
        for cam in cameras:
            cmds.menuItem(label=cam, parent=self.cam_menu)
        if saved in cameras:
            cmds.optionMenu(self.cam_menu, edit=True, value=saved)

    def _on_camera_changed(self, cam_name):
        set_selected_camera(cam_name)
        if self.cam_label:
            cmds.text(self.cam_label, edit=True, label='  Active: {}'.format(cam_name))

    # --- Hotkey toggles ---

    def _on_toggle(self, label_name, val):
        key, cmd_name, cmd_str = HOTKEYS[label_name]
        if val:
            register_hotkey(key, cmd_name, cmd_str)
            cmds.inViewMessage(amg='<hl>Enabled:</hl> {} (Shift+{})'.format(label_name, key),
                               pos='midCenterTop', fade=True)
        else:
            unregister_hotkey(key)
            cmds.inViewMessage(amg='<hl>Disabled:</hl> {} (Shift+{})'.format(label_name, key),
                               pos='midCenterTop', fade=True)

    def _enable_all(self, *_):
        for label_name, cb in self.checkboxes.items():
            cmds.checkBox(cb, edit=True, value=True)
            self._on_toggle(label_name, True)

    def _disable_all(self, *_):
        for _label, cb in self.checkboxes.items():
            cmds.checkBox(cb, edit=True, value=False)
        disable_all_hotkeys()

    # --- About ---

    def _show_about(self, *_):
        show_about()

    # --- Uninstall ---

    def _uninstall(self, *_):
        res = cmds.confirmDialog(
            title='Uninstall',
            message='Permanently uninstall Anim Shortcuts?',
            button=['Yes', 'Cancel'],
            defaultButton='Cancel', cancelButton='Cancel', dismissString='Cancel')
        if res != 'Yes':
            return

        # 1. Disable hotkeys
        self._disable_all()

        # 2. Remove shelf button(s)
        try:
            gShelfTopLevel = mel.eval('$tmpVar=$gShelfTopLevel')
            shelves = cmds.tabLayout(gShelfTopLevel, query=True, childArray=True) or []
            for shelf in shelves:
                buttons = cmds.shelfLayout(shelf, query=True, childArray=True) or []
                for btn in buttons:
                    try:
                        if cmds.objectTypeUI(btn) != 'shelfButton':
                            continue
                        cmd  = cmds.shelfButton(btn, query=True, command=True)     or ''
                        ann  = cmds.shelfButton(btn, query=True, annotation=True)  or ''
                        if ('layout_forger' in cmd or
                                'anim_shortcuts' in cmd or
                                'LayoutForger' in ann):
                            cmds.deleteUI(btn)
                    except Exception:
                        pass
        except Exception:
            pass

        # 3. Clean userSetup.py
        user_app_dir = cmds.internalVar(userAppDir=True)
        scripts_dir  = os.path.join(user_app_dir, 'scripts')
        setup_file   = os.path.join(scripts_dir, 'userSetup.py')
        if os.path.exists(setup_file):
            try:
                with open(setup_file, 'r') as f:
                    lines = f.readlines()
                skip = False
                with open(setup_file, 'w') as f:
                    for line in lines:
                        if '# --- Anim Shortcuts Auto-Start ---' in line:
                            skip = True
                        if not skip:
                            f.write(line)
                        if '# ---------------------------------' in line:
                            skip = False
            except Exception:
                pass

        # 4. Close UI
        if cmds.window(self.win_name, exists=True):
            cmds.deleteUI(self.win_name)

        # 5. Delete installed files
        for f in [
            os.path.join(scripts_dir, 'layout_forger.py'),
            os.path.join(user_app_dir, 'prefs', 'icons', 'anim_shortcuts_icon.png'),
        ]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        cmds.confirmDialog(title='Uninstalled',
                           message='LayoutForger has been removed successfully.')


def show_ui():
    ui = ShortcutManagerUI()
    ui.create_ui()


def show_about():
    """Display the LayoutForger About window."""
    win_name = 'LayoutForgerAboutWin'
    if cmds.window(win_name, exists=True):
        cmds.deleteUI(win_name)

    win  = cmds.window(win_name, title='About LayoutForger', sizeable=False)
    form = cmds.formLayout(numberOfDivisions=100)
    pos  = 14

    # --- Tool name (big, bold) ---
    title = cmds.text(label='LayoutForger', font='boldLabelFont', align='left')
    cmds.formLayout(form, edit=True, attachForm=[(title, 'top', pos), (title, 'left', 14)])

    pos += 22
    sub = cmds.text(label='Custom layout hotkey manager for Maya animators.',
                    align='left', font='obliqueLabelFont')
    cmds.formLayout(form, edit=True, attachForm=[(sub, 'top', pos), (sub, 'left', 14)])

    pos += 28
    sep = cmds.separator(style='in', height=1)
    cmds.formLayout(form, edit=True,
                    attachForm=[(sep, 'top', pos), (sep, 'left', 14), (sep, 'right', 14)])

    pos += 14

    def _row(label_text, value_text, is_link=False):
        lbl = cmds.text(label=label_text + ':', align='right', font='smallBoldLabelFont')
        cmds.formLayout(form, edit=True, attachForm=[(lbl, 'top', pos), (lbl, 'left', 14)],
                        attachPosition=[(lbl, 'right', 6, 38)])
        if is_link:
            val = cmds.text(label='<a href="http://{}">{}</a>'.format(value_text, value_text),
                            hyperlink=True, align='left')
        else:
            val = cmds.text(label=value_text, align='left')
        cmds.formLayout(form, edit=True, attachForm=[(val, 'top', pos), (val, 'left', 160)])
        return val

    _row('Tool',    'LayoutForger')
    pos += 18
    _row('Version', VERSION)
    pos += 18
    _row('Author',  'Baji N')
    pos += 18
    _row('Website', 'baji.digital', is_link=True)

    pos += 30
    sep2 = cmds.separator(style='in', height=1)
    cmds.formLayout(form, edit=True,
                    attachForm=[(sep2, 'top', pos), (sep2, 'left', 14), (sep2, 'right', 14)])

    pos += 14
    sign = cmds.text(label='Enjoy the flow.  — Baji N', align='left', font='obliqueLabelFont')
    cmds.formLayout(form, edit=True, attachForm=[(sign, 'top', pos), (sign, 'left', 14)])

    pos += 30
    close_btn = cmds.button(label='Close', height=26,
                            command=lambda *_: cmds.deleteUI(win_name))
    cmds.formLayout(form, edit=True,
                    attachForm=[(close_btn, 'top', pos),
                                (close_btn, 'left', 14),
                                (close_btn, 'right', 14)])

    pos += 40
    cmds.showWindow(win)
    cmds.window(win_name, edit=True, widthHeight=(340, pos))
