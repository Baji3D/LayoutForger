"""
LayoutForger — Create custom panel layouts and switch between them instantly using custom hotkeys. Streamline your animation workflow by eliminating tedious menus and keeping your workspace perfectly organized.
By Baji N | baji.digital

Copyright 2026 Baji N

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

VERSION = '0.0.2'

import os
import json
import uuid
import maya.cmds as cmds
import maya.mel as mel
import ctypes
import ctypes.wintypes

# optionVar to persist the selected camera across reloads
_CAM_OPTVAR = 'layoutForger_selectedCamera'

# Hotkey command prefix: always reload module before running so edits take effect
_RELOAD_PREFIX = 'import importlib; import layout_forger; importlib.reload(layout_forger); '

_DEFAULT_HOTKEYS = [
    {
        'id': 'builtin_graph',
        'label': 'Graph Editor',
        'key': 'g',
        'command_name': 'LayoutForger_GraphEditor',
        'python_cmd': _RELOAD_PREFIX + 'layout_forger.maximize_graph_editor()',
        'enabled': True,
        'builtin': True
    },
    {
        'id': 'builtin_cam',
        'label': 'Shot Camera',
        'key': 'c',
        'command_name': 'LayoutForger_Camera',
        'python_cmd': _RELOAD_PREFIX + 'layout_forger.maximize_camera()',
        'enabled': True,
        'builtin': True
    },
    {
        'id': 'builtin_dope',
        'label': 'Dope Sheet',
        'key': 'd',
        'command_name': 'LayoutForger_DopeSheet',
        'python_cmd': _RELOAD_PREFIX + 'layout_forger.maximize_dope_sheet()',
        'enabled': True,
        'builtin': True
    },
    {
        'id': 'builtin_float',
        'label': 'Floating Cam',
        'key': 'f',
        'command_name': 'LayoutForger_FloatingCam',
        'python_cmd': _RELOAD_PREFIX + 'layout_forger.floating_shot_cam()',
        'enabled': True,
        'builtin': True
    },
    {
        'id': 'builtin_stack',
        'label': 'Cam + Graph',
        'key': 's',
        'command_name': 'LayoutForger_StackedView',
        'python_cmd': _RELOAD_PREFIX + 'layout_forger.stacked_cam_graph()',
        'enabled': True,
        'builtin': True
    },
    {
        'id': 'builtin_toggle',
        'label': 'Toggle Panels',
        'key': 'h',
        'command_name': 'LayoutForger_TogglePanels',
        'python_cmd': _RELOAD_PREFIX + 'layout_forger.toggle_panels()',
        'enabled': True,
        'builtin': True
    }
]

def _get_config_path():
    try:
        user_app_dir = cmds.internalVar(userAppDir=True)
        return os.path.join(user_app_dir, 'scripts', 'layoutforger_config.json')
    except Exception:
        # Fallback if maya.cmds fails (e.g. testing outside maya)
        return 'layoutforger_config.json'

def load_config():
    path = _get_config_path()
    if os.path.exists(path):
        try:
            with open(path, 'r') as f:
                data = json.load(f)
                return data.get('hotkeys', [])
        except Exception as e:
            try: cmds.warning('LayoutForger: Failed to load config - ' + str(e))
            except: pass
    return [dict(h) for h in _DEFAULT_HOTKEYS]

def save_config(hotkeys):
    path = _get_config_path()
    try:
        with open(path, 'w') as f:
            json.dump({'hotkeys': hotkeys}, f, indent=4)
    except Exception as e:
        try: cmds.warning('LayoutForger: Failed to save config - ' + str(e))
        except: pass

_config = load_config()

# Tracks whether hotkeys are currently registered
_hotkeys_enabled = False

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
    for entry in _config:
        if entry.get('enabled', True):
            register_hotkey(entry['key'], entry['command_name'], entry['python_cmd'])
    _hotkeys_enabled = True


def disable_all_hotkeys():
    """Disable all custom hotkeys."""
    global _hotkeys_enabled
    for entry in _config:
        unregister_hotkey(entry['key'])
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

    Sets the base layout to Four View, restores the active camera,
    and then maximizes that specific panel so Spacebar returns to the 4-stack view.
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

    # 2. Switch to Four View as the base layout
    mel.eval('setNamedPanelLayout "Four View"')
    
    # Maya bug: sometimes switching from a 3-pane layout to Four View fails to update the paneLayout style.
    # We forcefully ensure the main pane is a 4-stack (quad) before proceeding.
    mel.eval('string $tmp = $gMainPane; if (`paneLayout -ex $tmp`) { paneLayout -e -configuration "quad" $tmp; }')

    # 3. Find a model panel, set its camera, and maximize it
    target_panel = None
    for p in (cmds.getPanel(visiblePanels=True) or []):
        if cmds.getPanel(typeOf=p) == 'modelPanel':
            target_panel = p
            if current_cam:
                try:
                    cmds.modelPanel(p, edit=True, camera=current_cam)
                except Exception as e:
                    cmds.warning('LayoutForger: Could not restore camera — ' + str(e))
            break
            
    if target_panel:
        cmds.setFocus(target_panel)
        # Emulate hitting Spacebar to maximize the active pane without ruining the Four View base
        mel.eval('string $tmp = $gMainPane; if (`paneLayout -ex $tmp`) { string $cfg = `paneLayout -q -configuration $tmp`; if ($cfg != "single") { paneLayout -e -configuration "single" $tmp; } }')


def stacked_cam_graph():
    """Left: Persp View. Right: Saved Camera. Bottom: Graph Editor.

    Uses the user's custom 3-pane layout snapshot.
    """
    # 1. Capture the active camera before changing layouts
    saved_cam = None
    focused = cmds.getPanel(withFocus=True)
    if focused and cmds.getPanel(typeOf=focused) == 'modelPanel':
        saved_cam = cmds.modelPanel(focused, query=True, camera=True)
    if not saved_cam:
        for p in (cmds.getPanel(visiblePanels=True) or []):
            if cmds.getPanel(typeOf=p) == 'modelPanel':
                saved_cam = cmds.modelPanel(p, query=True, camera=True)
                break
                
    if not saved_cam:
        saved_cam = get_selected_camera()
    if not saved_cam:
        saved_cam = 'persp'

    # 2. Switch to a clean single-panel layout first
    mel.eval('setNamedPanelLayout "Single Perspective View"')

    # 3. Build the exact layout the user requested, modifying pane 1/2 labels
    layout_name = 'LF_Cam_Graph_Layout_V2'
    if not cmds.panelConfiguration(layout_name, exists=True):
        cmds.panelConfiguration(layout_name, sceneConfig=False, configString='global string $gMainPane; paneLayout -e -cn "top3" -ps 1 50 50 -ps 2 50 50 -ps 3 100 50 $gMainPane;')
        # Left Panel (Pane 1)
        pane1_str = 'modelPanel -edit -l (localizedPanelLabel("Persp View")) -mbv $menusOkayInPanels  $panelName; $editorName = $panelName; modelEditor -e      -camera "|persp"      -useInteractiveMode 0     -displayLights "default"      -displayAppearance "smoothShaded"      -activeOnly 0     -ignorePanZoom 0     -wireframeOnShaded 0     -headsUpDisplay 1     -holdOuts 1     -selectionHiliteDisplay 1     -useDefaultMaterial 0     -bufferMode "double"      -twoSidedLighting 0     -backfaceCulling 0     -xray 0     -jointXray 0     -activeComponentsXray 0     -displayTextures 0     -smoothWireframe 0     -lineWidth 1     -textureAnisotropic 0     -textureHilight 1     -textureSampling 2     -textureDisplay "modulate"      -textureMaxSize 32768     -fogging 0     -fogSource "fragment"      -fogMode "linear"      -fogStart 0     -fogEnd 100     -fogDensity 0.1     -fogColor 0.5 0.5 0.5 1      -depthOfFieldPreview 1     -maxConstantTransparency 1     -rendererName "vp2Renderer"      -objectFilterShowInHUD 1     -isFiltered 0     -colorResolution 256 256      -bumpResolution 512 512      -textureCompression 0     -transparencyAlgorithm "frontAndBackCull"      -transpInShadows 0     -cullingOverride "none"      -lowQualityLighting 0     -maximumNumHardwareLights 1     -occlusionCulling 0     -shadingModel 0     -useBaseRenderer 0     -useReducedRenderer 0     -smallObjectCulling 0     -smallObjectThreshold -1      -interactiveDisableShadows 0     -interactiveBackFaceCull 0     -sortTransparent 1     -controllers 1     -nurbsCurves 1     -nurbsSurfaces 1     -polymeshes 1     -subdivSurfaces 1     -planes 1     -lights 1     -cameras 1     -controlVertices 1     -hulls 1     -grid 1     -imagePlane 1     -joints 1     -ikHandles 1     -deformers 1     -dynamics 1     -particleInstancers 1     -fluids 1     -hairSystems 1     -follicles 1     -nCloths 1     -nParticles 1     -nRigids 1     -dynamicConstraints 1     -locators 1     -manipulators 1     -pluginShapes 1     -dimensions 1     -handles 1     -pivots 1     -textures 1     -strokes 1     -motionTrails 1     -clipGhosts 1     -bluePencil 1     -greasePencils 0     -excludeObjectPreset "All"      -shadows 0     -captureSequenceNumber -1     -width 994     -height 325     -sceneRenderFilter 0     $editorName; modelEditor -e -viewSelected 0 $editorName; modelEditor -e      -pluginObjects "gpuCacheDisplayFilter" 1      $editorName'.replace('"', '\\"')
        mel.eval('panelConfiguration -edit -addPanel false "{}" "{}"'.format(pane1_str, layout_name))
        
        # Right Panel (Pane 2)
        pane2_str = 'modelPanel -edit -l (localizedPanelLabel("Shot Cam")) -mbv $menusOkayInPanels  $panelName; $editorName = $panelName; modelEditor -e      -cam `findStartUpCamera persp`      -useInteractiveMode 0     -displayLights "default"      -displayAppearance "smoothShaded"      -activeOnly 0     -ignorePanZoom 0     -wireframeOnShaded 0     -headsUpDisplay 1     -holdOuts 1     -selectionHiliteDisplay 1     -useDefaultMaterial 0     -bufferMode "double"      -twoSidedLighting 0     -backfaceCulling 0     -xray 0     -jointXray 0     -activeComponentsXray 0     -displayTextures 0     -smoothWireframe 0     -lineWidth 1     -textureAnisotropic 0     -textureHilight 1     -textureSampling 2     -textureDisplay "modulate"      -textureMaxSize 32768     -fogging 0     -fogSource "fragment"      -fogMode "linear"      -fogStart 0     -fogEnd 100     -fogDensity 0.1     -fogColor 0.5 0.5 0.5 1      -depthOfFieldPreview 1     -maxConstantTransparency 1     -rendererName "vp2Renderer"      -objectFilterShowInHUD 1     -isFiltered 0     -colorResolution 256 256      -bumpResolution 512 512      -textureCompression 0     -transparencyAlgorithm "frontAndBackCull"      -transpInShadows 0     -cullingOverride "none"      -lowQualityLighting 0     -maximumNumHardwareLights 1     -occlusionCulling 0     -shadingModel 0     -useBaseRenderer 0     -useReducedRenderer 0     -smallObjectCulling 0     -smallObjectThreshold -1      -interactiveDisableShadows 0     -interactiveBackFaceCull 0     -sortTransparent 1     -controllers 1     -nurbsCurves 1     -nurbsSurfaces 1     -polymeshes 1     -subdivSurfaces 1     -planes 1     -lights 1     -cameras 1     -controlVertices 1     -hulls 1     -grid 1     -imagePlane 1     -joints 1     -ikHandles 1     -deformers 1     -dynamics 1     -particleInstancers 1     -fluids 1     -hairSystems 1     -follicles 1     -nCloths 1     -nParticles 1     -nRigids 1     -dynamicConstraints 1     -locators 1     -manipulators 1     -pluginShapes 1     -dimensions 1     -handles 1     -pivots 1     -textures 1     -strokes 1     -motionTrails 1     -clipGhosts 1     -bluePencil 1     -greasePencils 0     -excludeObjectPreset "All"      -shadows 0     -captureSequenceNumber -1     -width 993     -height 325     -sceneRenderFilter 0     $editorName; modelEditor -e -viewSelected 0 $editorName; modelEditor -e      -pluginObjects "gpuCacheDisplayFilter" 1      $editorName'.replace('"', '\\"')
        mel.eval('panelConfiguration -edit -addPanel false "{}" "{}"'.format(pane2_str, layout_name))
        
        # Bottom Panel (Pane 3)
        pane3_str = 'scriptedPanel -edit -l (localizedPanelLabel("Graph Editor")) -mbv $menusOkayInPanels  $panelName;  			$editorName = ($panelName+"OutlineEd");             outlinerEditor -e                  -showShapes 1                 -showAssignedMaterials 0                 -showTimeEditor 1                 -showReferenceNodes 0                 -showReferenceMembers 0                 -showAttributes 1                 -showConnected 1                 -showAnimCurvesOnly 1                 -showMuteInfo 0                 -organizeByLayer 1                 -organizeByClip 1                 -showAnimLayerWeight 1                 -autoExpandLayers 1                 -autoExpand 1                 -showDagOnly 0                 -showAssets 1                 -showContainedOnly 0                 -showPublishedAsConnected 0                 -showParentContainers 0                 -showContainerContents 0                 -ignoreDagHierarchy 0                 -expandConnections 1                 -showUpstreamCurves 1                 -showUnitlessCurves 1                 -showCompounds 0                 -showLeafs 1                 -showNumericAttrsOnly 1                 -highlightActive 0                 -autoSelectNewObjects 1                 -doNotSelectNewObjects 0                 -dropIsParent 1                 -transmitFilters 1                 -setFilter "0"                  -showSetMembers 0                 -allowMultiSelection 1                 -alwaysToggleSelect 0                 -directSelect 0                 -isSet 0                 -isSetMember 0                 -showUfeItems 1                 -displayMode "DAG"                  -expandObjects 0                 -setsIgnoreFilters 1                 -containersIgnoreFilters 0                 -editAttrName 0                 -showAttrValues 0                 -highlightSecondary 0                 -showUVAttrsOnly 0                 -showTextureNodesOnly 0                 -attrAlphaOrder "default"                  -animLayerFilterOptions "allAffecting"                  -sortOrder "none"                  -longNames 0                 -niceNames 1                 -showNamespace 1                 -showPinIcons 1                 -mapMotionTrails 1                 -ignoreHiddenAttribute 0                 -ignoreOutlinerColor 0                 -renderFilterVisible 0                 -selectionOrder "display"                  -expandAttribute 1                 -ufeFilter "USD" "InactivePrims" -ufeFilterValue 1                 $editorName;  			$editorName = ($panelName+"GraphEd");             animCurveEditor -e                  -displayValues 0                 -snapTime "integer"                  -snapValue "none"                  -showPlayRangeShades "on"                  -lockPlayRangeShades "off"                  -smoothness "fine"                  -resultSamples 1.041667                 -resultScreenSamples 0                 -resultUpdate "delayed"                  -showUpstreamCurves 1                 -tangentScale 1                 -tangentLineThickness 1                 -keyMinScale 1                 -stackedCurvesMin -1                 -stackedCurvesMax 1                 -stackedCurvesSpace 0.2                 -preSelectionHighlight 0                 -limitToSelectedCurves 0                 -constrainDrag 1                 -valueLinesToggle 0                 -outliner "graphEditor1OutlineEd"                  -highlightAffectedCurves 0                 $editorName'.replace('"', '\\"')
        mel.eval('panelConfiguration -edit -addPanel false "{}" "{}"'.format(pane3_str, layout_name))
    mel.eval('setNamedPanelLayout "{}"'.format(layout_name))
    
    # 4. Force the Graph Editor to always be in the bottom pane (Pane 3)
    try:
        main_layout = mel.eval('$_tmp = $gMainPane')
        bottom_panel = cmds.paneLayout(main_layout, query=True, pane3=True)
        if bottom_panel and cmds.getPanel(typeOf=bottom_panel) != 'scriptedPanel':
            cmds.scriptedPanel('graphEditor1', edit=True, replacePanel=bottom_panel)
    except Exception as e:
        cmds.warning("LayoutForger: Could not force Graph Editor into bottom pane - " + str(e))

    # 5. Restore the saved camera to the right viewport (Pane 2) with clean settings
    try:
        right_panel = cmds.paneLayout(main_layout, query=True, pane2=True)
        if right_panel and cmds.getPanel(typeOf=right_panel) == 'modelPanel':
            # Resolve camera shape
            cam_shape = saved_cam
            if cmds.objExists(saved_cam):
                resolved = cmds.ls(saved_cam, long=True)
                if resolved:
                    shapes = cmds.listRelatives(resolved[0], shapes=True, type='camera', fullPath=True) or []
                    if shapes:
                        cam_shape = shapes[0]

            # Turn on resolution gate on the camera itself
            if cmds.objExists(cam_shape):
                try: cmds.camera(cam_shape, edit=True, displayResolution=True)
                except Exception: pass

            # Set camera
            cmds.modelPanel(right_panel, edit=True, camera=cam_shape)
            cmds.setFocus(right_panel)

            # Viewport cleanup (same as Ctrl+Shift+F)
            try:
                cmds.modelEditor(right_panel, edit=True, allObjects=False)
                cmds.modelEditor(right_panel, edit=True,
                                 polymeshes=True,
                                 nurbsSurfaces=True,
                                 subdivSurfaces=True,
                                 pluginShapes=True,
                                 imagePlane=True,
                                 displayAppearance='smoothShaded',
                                 displayTextures=True,
                                 wireframeOnShaded=False)
            except Exception:
                pass
    except Exception as e:
        cmds.warning("LayoutForger: Could not set camera on right panel - " + str(e))


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
        self.cam_menu  = None
        self.cam_label = None
        self.hotkeys_layout = None

    def create_ui(self):
        if cmds.window(self.win_name, exists=True):
            cmds.deleteUI(self.win_name)

        self.win = cmds.window(self.win_name, title='LayoutForger',
                               widthHeight=(420, 560), sizeable=True)

        self.main_layout = cmds.scrollLayout(childResizable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=8,
                          columnAttach=('both', 10), parent=self.main_layout)

        # Header row: title + info button
        cmds.rowLayout(numberOfColumns=2,
                       columnWidth2=(350, 30),
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

        # Hotkeys List Container
        self.hotkeys_layout = cmds.columnLayout(adjustableColumn=True, rowSpacing=4)
        self._build_hotkey_rows()
        cmds.setParent('..')

        cmds.separator(height=10, style='in')
        
        cmds.button(label='+ Add Custom Shortcut', command=self._show_add_custom_ui, height=30)

        cmds.separator(height=10, style='in')

        # Camera selector for Floating Cam
        cmds.text(label='Floating Cam Camera:', align='left')
        cmds.rowLayout(numberOfColumns=2, adjustableColumn=1, columnWidth2=(220, 100))
        self.cam_menu = cmds.optionMenu(changeCommand=lambda val: self._on_camera_changed(val))
        self._populate_cameras()
        cmds.button(label='Refresh', command=lambda *a: self._populate_cameras(), height=22)
        cmds.setParent('..')

        self.cam_label = cmds.text(label='  Active: {}'.format(get_selected_camera()),
                                   align='left', font='obliqueLabelFont')

        cmds.separator(height=10, style='in')

        cmds.rowLayout(numberOfColumns=3, columnWidth3=(120, 120, 120),
                       columnAttach3=('both', 'both', 'both'))
        cmds.button(label='Enable All',  command=self._enable_all,
                    backgroundColor=(0.2, 0.4, 0.2))
        cmds.button(label='Disable All', command=self._disable_all,
                    backgroundColor=(0.4, 0.2, 0.2))
        cmds.button(label='Reset Defaults', command=self._reset_defaults,
                    backgroundColor=(0.4, 0.3, 0.1))
        cmds.setParent('..')

        cmds.separator(height=10, style='in')
        
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 180), columnAttach2=('both', 'both'))
        cmds.button(label='Export Config', command=self._export_config, backgroundColor=(0.2, 0.3, 0.4))
        cmds.button(label='Import Config', command=self._import_config, backgroundColor=(0.3, 0.2, 0.4))
        cmds.setParent('..')

        cmds.separator(height=6, style='none')
        cmds.frameLayout(label='Danger Zone', collapsable=True, collapse=True,
                         bgc=(0.2, 0.1, 0.1), marginWidth=10, marginHeight=10)
        cmds.button(label='Uninstall Plugin', command=self._uninstall,
                    backgroundColor=(0.5, 0.2, 0.2), height=24)
        cmds.setParent('..')

        cmds.separator(height=8, style='none')

        cmds.showWindow(self.win)

    def _build_hotkey_rows(self):
        # Clear existing rows
        if not self.hotkeys_layout: return
        for child in cmds.columnLayout(self.hotkeys_layout, query=True, childArray=True) or []:
            cmds.deleteUI(child)

        cmds.setParent(self.hotkeys_layout)
        
        # Build header for columns
        cmds.rowLayout(numberOfColumns=5, columnWidth5=(20, 130, 80, 50, 40), 
                       columnAttach5=('both', 'both', 'both', 'both', 'both'))
        cmds.text(label='On', font='smallBoldLabelFont')
        cmds.text(label='Label', font='smallBoldLabelFont', align='left')
        cmds.text(label='Ctrl+Shift+', font='smallBoldLabelFont')
        cmds.text(label='Cmd', font='smallBoldLabelFont')
        cmds.text(label='Del', font='smallBoldLabelFont')
        cmds.setParent('..')
        
        cmds.separator(height=2, style='in')

        for i, entry in enumerate(_config):
            row = cmds.rowLayout(numberOfColumns=5, columnWidth5=(20, 130, 80, 50, 40),
                                 columnAttach5=('both', 'both', 'both', 'both', 'both'))
            
            # Checkbox
            cb = cmds.checkBox(label='', value=entry.get('enabled', True))
            cmds.checkBox(cb, edit=True, changeCommand=lambda val, idx=i: self._on_toggle(idx, val))
            
            # Label
            label_field = cmds.textField(text=entry['label'])
            cmds.textField(label_field, edit=True, changeCommand=lambda val, idx=i: self._on_label_changed(idx, val))
            
            # Key Picker
            key_menu = cmds.optionMenu(changeCommand=lambda val, idx=i: self._on_key_changed(idx, val))
            # A-Z
            for char in 'abcdefghijklmnopqrstuvwxyz':
                cmds.menuItem(label=char, parent=key_menu)
            
            # Set the current key
            current_key = entry['key'].lower()
            items = cmds.optionMenu(key_menu, query=True, itemListLong=True) or []
            for item in items:
                if cmds.menuItem(item, query=True, label=True) == current_key:
                    cmds.optionMenu(key_menu, edit=True, value=current_key)
                    break
                    
            # Cmd Edit button
            cmds.button(label='Edit', command=lambda *a, idx=i: self._show_edit_cmd_ui(idx))
            
            # Delete button (now available for all entries)
            cmds.button(label='X', backgroundColor=(0.5, 0.2, 0.2), 
                        command=lambda *a, idx=i: self._delete_entry(idx))
                
            cmds.setParent('..')

    def _on_label_changed(self, idx, val):
        _config[idx]['label'] = val
        save_config(_config)

    def _on_key_changed(self, idx, val):
        old_key = _config[idx]['key']
        
        # Check for conflicts
        conflict_idx = None
        for i, entry in enumerate(_config):
            if i != idx and entry['key'] == val:
                conflict_idx = i
                break
                
        if conflict_idx is not None:
            cmds.warning("Key '{}' is already in use by '{}'. Stealing it!".format(val, _config[conflict_idx]['label']))
            _config[conflict_idx]['key'] = old_key # Swap keys
            
            if _config[conflict_idx].get('enabled', True) and _hotkeys_enabled:
                unregister_hotkey(val)
                register_hotkey(old_key, _config[conflict_idx]['command_name'], _config[conflict_idx]['python_cmd'])

        _config[idx]['key'] = val
        save_config(_config)
        
        if _config[idx].get('enabled', True) and _hotkeys_enabled:
            unregister_hotkey(old_key)
            register_hotkey(val, _config[idx]['command_name'], _config[idx]['python_cmd'])
            
        self._build_hotkey_rows() # Rebuild to reflect swap if any

    def _show_add_custom_ui(self, *_):
        prompt_win = 'LayoutForgerAddCustomWin'
        if cmds.window(prompt_win, exists=True):
            cmds.deleteUI(prompt_win)
            
        cmds.window(prompt_win, title='Add Custom Shortcut', widthHeight=(400, 320), sizeable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAttach=('both', 10))
        
        cmds.text(label='Label:', align='left')
        label_fld = cmds.textField(text='New Action')
        
        cmds.text(label='Key (Ctrl+Shift+):', align='left')
        key_menu = cmds.optionMenu()
        for char in 'abcdefghijklmnopqrstuvwxyz':
            cmds.menuItem(label=char, parent=key_menu)
            
        cmds.text(label='Action Type:', align='left')
        type_menu = cmds.optionMenu()
        cmds.menuItem(label='Load Saved Layout', parent=type_menu)
        cmds.menuItem(label='Snapshot Current Workspace', parent=type_menu)
        cmds.menuItem(label='Custom Python Script', parent=type_menu)
        
        layout_container = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        cmds.text(label='Select Saved Layout:', align='left')
        layout_menu = cmds.optionMenu()
        for config_node in (cmds.getPanel(allConfigs=True) or []):
            try:
                lbl = cmds.panelConfiguration(config_node, query=True, label=True)
                if lbl:
                    cmds.menuItem(label=lbl, parent=layout_menu)
            except Exception: pass
        cmds.setParent('..')

        snapshot_container = cmds.columnLayout(adjustableColumn=True, rowSpacing=5, visible=False)
        cmds.text(label='This will capture your exact current Maya window setup\ninto a portable script that works on any PC.', align='left')
        cmds.setParent('..')
        
        script_container = cmds.columnLayout(adjustableColumn=True, rowSpacing=5, visible=False)
        cmds.text(label='Python Command:', align='left')
        cmd_fld = cmds.scrollField(text='import maya.cmds as cmds\n', height=80, wordWrap=True)
        cmds.setParent('..')
        
        def _on_type_changed(val):
            cmds.columnLayout(layout_container, edit=True, visible=(val == 'Load Saved Layout'))
            cmds.columnLayout(snapshot_container, edit=True, visible=(val == 'Snapshot Current Workspace'))
            cmds.columnLayout(script_container, edit=True, visible=(val == 'Custom Python Script'))
            
        cmds.optionMenu(type_menu, edit=True, changeCommand=_on_type_changed)
        
        def _save_new(*_):
            label = cmds.textField(label_fld, query=True, text=True)
            key = cmds.optionMenu(key_menu, query=True, value=True)
            
            action_type = cmds.optionMenu(type_menu, query=True, value=True)
            if action_type == 'Load Saved Layout':
                layout_name = cmds.optionMenu(layout_menu, query=True, value=True)
                cmd_str = 'import maya.mel as mel; mel.eval(\'setNamedPanelLayout "{}"\')'.format(layout_name)
            elif action_type == 'Snapshot Current Workspace':
                snap_id = 'LF_Snap_' + str(uuid.uuid4()).replace('-', '_')
                cmds.panelConfiguration(snap_id)
                mel.eval('updatePanelLayoutFromCurrent "{}"'.format(snap_id))
                config_str = cmds.panelConfiguration(snap_id, query=True, configString=True)
                edit_strs = cmds.panelConfiguration(snap_id, query=True, editStrings=True) or []
                
                cmd_lines = [
                    "import maya.cmds as cmds",
                    "import maya.mel as mel",
                    "layout_name = '{}'".format(snap_id),
                    "if not cmds.panelConfiguration(layout_name, exists=True):",
                    "    cmds.panelConfiguration(layout_name, sceneConfig=False, configString='{}')".format(config_str.replace("'", "\\'"))
                ]
                for es in edit_strs:
                    escaped_es = es.replace('"', '\\"')
                    cmd_lines.append("    pane_str = '{}'".format(escaped_es.replace("'", "\\'")))
                    cmd_lines.append("    mel.eval('panelConfiguration -edit -addPanel false \\\"{0}\\\" \\\"{1}\\\"'.format(pane_str, layout_name))")
                cmd_lines.append('mel.eval(\'setNamedPanelLayout "{}"\'.format(layout_name))')
                cmd_str = "\n".join(cmd_lines)
            else:
                cmd_str = cmds.scrollField(cmd_fld, query=True, text=True)
            
            # Simple conflict resolve
            for entry in _config:
                if entry['key'] == key:
                    cmds.warning("Key '{}' is already in use by '{}'!".format(key, entry['label']))
                    return
            
            cmd_name = 'LayoutForger_Custom_' + str(uuid.uuid4()).replace('-', '_')
            
            new_entry = {
                'id': cmd_name,
                'label': label,
                'key': key,
                'command_name': cmd_name,
                'python_cmd': cmd_str,
                'enabled': True,
                'builtin': False
            }
            
            _config.append(new_entry)
            save_config(_config)
            
            if _hotkeys_enabled:
                register_hotkey(key, cmd_name, cmd_str)
                
            self._build_hotkey_rows()
            cmds.deleteUI(prompt_win)
            
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 180))
        cmds.button(label='Add', command=_save_new, backgroundColor=(0.2, 0.4, 0.2))
        cmds.button(label='Cancel', command=lambda *_: cmds.deleteUI(prompt_win))
        cmds.setParent('..')
        
        cmds.showWindow(prompt_win)

    def _show_edit_cmd_ui(self, idx):
        entry = _config[idx]
        prompt_win = 'LayoutForgerEditCmdWin'
        if cmds.window(prompt_win, exists=True):
            cmds.deleteUI(prompt_win)
            
        cmds.window(prompt_win, title='Edit Command: ' + entry['label'], widthHeight=(400, 320), sizeable=True)
        cmds.columnLayout(adjustableColumn=True, rowSpacing=10, columnAttach=('both', 10))
        
        cmds.text(label='Action Type:', align='left')
        type_menu = cmds.optionMenu()
        cmds.menuItem(label='Load Saved Layout', parent=type_menu)
        cmds.menuItem(label='Snapshot Current Workspace', parent=type_menu)
        cmds.menuItem(label='Custom Python Script', parent=type_menu)
        
        layout_container = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        cmds.text(label='Select Saved Layout:', align='left')
        layout_menu = cmds.optionMenu()
        saved_layouts = []
        for config_node in (cmds.getPanel(allConfigs=True) or []):
            try:
                lbl = cmds.panelConfiguration(config_node, query=True, label=True)
                if lbl:
                    saved_layouts.append(lbl)
                    cmds.menuItem(label=lbl, parent=layout_menu)
            except Exception: pass
        cmds.setParent('..')

        snapshot_container = cmds.columnLayout(adjustableColumn=True, rowSpacing=5, visible=False)
        cmds.text(label='This will capture your exact current Maya window setup\nand OVERWRITE the script for this shortcut.', align='left')
        cmds.setParent('..')
        
        script_container = cmds.columnLayout(adjustableColumn=True, rowSpacing=5)
        cmds.text(label='Python Command for Ctrl+Shift+' + entry['key'].upper() + ':', align='left')
        cmd_fld = cmds.scrollField(text=entry['python_cmd'], height=80, wordWrap=True)
        cmds.setParent('..')
        
        def _on_type_changed(val):
            cmds.columnLayout(layout_container, edit=True, visible=(val == 'Load Saved Layout'))
            cmds.columnLayout(snapshot_container, edit=True, visible=(val == 'Snapshot Current Workspace'))
            cmds.columnLayout(script_container, edit=True, visible=(val == 'Custom Python Script'))
            
        cmds.optionMenu(type_menu, edit=True, changeCommand=_on_type_changed)
        
        # Detect if it's a known layout to select it in the dropdown
        cmd_str = entry['python_cmd']
        if 'setNamedPanelLayout' in cmd_str:
            import re
            m = re.search(r'setNamedPanelLayout\s+"([^"]+)"', cmd_str)
            if m:
                layout_name = m.group(1)
                if layout_name in saved_layouts:
                    cmds.optionMenu(layout_menu, edit=True, value=layout_name)
                    
        # Always default to 'Load Saved Layout' as requested
        cmds.optionMenu(type_menu, edit=True, value='Load Saved Layout')
        _on_type_changed('Load Saved Layout')
        
        def _save_cmd(*_):
            action_type = cmds.optionMenu(type_menu, query=True, value=True)
            if action_type == 'Load Saved Layout':
                layout_name = cmds.optionMenu(layout_menu, query=True, value=True)
                new_cmd = 'import maya.mel as mel; mel.eval(\'setNamedPanelLayout "{}"\')'.format(layout_name)
            elif action_type == 'Snapshot Current Workspace':
                snap_id = 'LF_Snap_' + str(uuid.uuid4()).replace('-', '_')
                cmds.panelConfiguration(snap_id)
                mel.eval('updatePanelLayoutFromCurrent "{}"'.format(snap_id))
                config_str = cmds.panelConfiguration(snap_id, query=True, configString=True)
                edit_strs = cmds.panelConfiguration(snap_id, query=True, editStrings=True) or []
                
                cmd_lines = [
                    "import maya.cmds as cmds",
                    "import maya.mel as mel",
                    "layout_name = '{}'".format(snap_id),
                    "if not cmds.panelConfiguration(layout_name, exists=True):",
                    "    cmds.panelConfiguration(layout_name, sceneConfig=False, configString='{}')".format(config_str.replace("'", "\\'"))
                ]
                for es in edit_strs:
                    escaped_es = es.replace("'", "\\'").replace("\n", " ")
                    cmd_lines.append("    cmds.panelConfiguration(layout_name, edit=True, addPanel=[False, '{}'])".format(escaped_es))
                cmd_lines.append('mel.eval(\'setNamedPanelLayout "{}"\'.format(layout_name))')
                new_cmd = "\n".join(cmd_lines)
            else:
                new_cmd = cmds.scrollField(cmd_fld, query=True, text=True)
                
            entry['python_cmd'] = new_cmd
            save_config(_config)
            
            if entry.get('enabled', True) and _hotkeys_enabled:
                register_hotkey(entry['key'], entry['command_name'], new_cmd)
                
            cmds.deleteUI(prompt_win)
            
        cmds.rowLayout(numberOfColumns=2, columnWidth2=(180, 180))
        cmds.button(label='Save', command=_save_cmd, backgroundColor=(0.2, 0.4, 0.2))
        cmds.button(label='Cancel', command=lambda *_: cmds.deleteUI(prompt_win))
        cmds.setParent('..')
        
        cmds.showWindow(prompt_win)

    def _export_config(self, *_):
        res = cmds.fileDialog2(fileMode=0, fileFilter='JSON (*.json)', caption='Export LayoutForger Config')
        if res and res[0]:
            path = res[0]
            try:
                import json
                with open(path, 'w') as f:
                    json.dump({'hotkeys': _config}, f, indent=4)
                cmds.inViewMessage(amg='<hl>Exported Config:</hl> ' + path, pos='midCenterTop', fade=True)
            except Exception as e:
                cmds.warning('Failed to export config: ' + str(e))

    def _import_config(self, *_):
        res = cmds.fileDialog2(fileMode=1, fileFilter='JSON (*.json)', caption='Import LayoutForger Config')
        if res and res[0]:
            path = res[0]
            try:
                import json
                with open(path, 'r') as f:
                    data = json.load(f)
                    if 'hotkeys' in data:
                        global _config
                        _config = data['hotkeys']
                        save_config(_config)
                        self._disable_all() # Unregister old hotkeys
                        self._enable_all()  # Register new ones
                        self._build_hotkey_rows()
                        cmds.inViewMessage(amg='<hl>Imported Config Successfully!</hl>', pos='midCenterTop', fade=True)
            except Exception as e:
                cmds.warning('Failed to import config: ' + str(e))

    def _delete_entry(self, idx):
        entry = _config[idx]
        res = cmds.confirmDialog(
            title='Delete Shortcut',
            message='Delete shortcut "{}"?'.format(entry['label']),
            button=['Yes', 'Cancel'],
            defaultButton='Cancel', cancelButton='Cancel', dismissString='Cancel')
        if res == 'Yes':
            if entry.get('enabled', True) and _hotkeys_enabled:
                unregister_hotkey(entry['key'])
            del _config[idx]
            save_config(_config)
            self._build_hotkey_rows()

    def _reset_defaults(self, *_):
        res = cmds.confirmDialog(
            title='Reset Defaults',
            message='Reset all shortcuts to defaults? Custom shortcuts will be lost.',
            button=['Yes', 'Cancel'],
            defaultButton='Cancel', cancelButton='Cancel', dismissString='Cancel')
        if res == 'Yes':
            self._disable_all()
            global _config
            _config = [dict(h) for h in _DEFAULT_HOTKEYS]
            save_config(_config)
            self._build_hotkey_rows()

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

    def _on_toggle(self, idx, val):
        entry = _config[idx]
        entry['enabled'] = val
        save_config(_config)
        
        key = entry['key']
        cmd_name = entry['command_name']
        cmd_str = entry['python_cmd']
        label_name = entry['label']
        
        if val:
            register_hotkey(key, cmd_name, cmd_str)
            cmds.inViewMessage(amg='<hl>Enabled:</hl> {} (Shift+{})'.format(label_name, key),
                               pos='midCenterTop', fade=True)
        else:
            unregister_hotkey(key)
            cmds.inViewMessage(amg='<hl>Disabled:</hl> {} (Shift+{})'.format(label_name, key),
                               pos='midCenterTop', fade=True)

    def _enable_all(self, *_):
        for idx, entry in enumerate(_config):
            self._on_toggle(idx, True)
        self._build_hotkey_rows() # Refresh checkboxes

    def _disable_all(self, *_):
        for idx, entry in enumerate(_config):
            self._on_toggle(idx, False)
        self._build_hotkey_rows() # Refresh checkboxes
        # Also clean up maya state just in case
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
            
        # 1. Disable hotkeys and completely scrub Maya's internal shortcut memory
        self._disable_all()
        
        try:
            # Delete all runtime commands we created
            for entry in _config:
                rtc = entry['command_name'] + 'RTC'
                if cmds.runTimeCommand(rtc, exists=True):
                    cmds.runTimeCommand(rtc, edit=True, delete=True)
                    
            # Switch back to Maya_Default and delete our custom set entirely
            if cmds.hotkeySet('LayoutForger_Set', exists=True):
                cmds.hotkeySet('Maya_Default', edit=True, current=True)
                cmds.hotkeySet('LayoutForger_Set', edit=True, delete=True)
                
            # Force Maya to save preferences to disk immediately so it forgets everything
            cmds.savePrefs(hotkeys=True)
        except Exception as e:
            cmds.warning('LayoutForger: Failed to clean Maya hotkey memory: ' + str(e))

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

        # 3. Clean userSetup.py — search both possible locations
        user_app_dir = cmds.internalVar(userAppDir=True)
        docs_maya = os.path.join(
            os.environ.get('USERPROFILE', os.path.expanduser('~')),
            'Documents', 'maya')
        candidate_scripts = [
            os.path.join(docs_maya, 'scripts'),          # where installer writes
            os.path.join(user_app_dir, 'scripts'),        # legacy location
        ]
        _MARKERS = (
            '# --- LayoutForger Auto-Start ---',
            '# --- Anim Shortcuts Auto-Start ---',        # legacy marker
        )
        for scripts_dir in candidate_scripts:
            setup_file = os.path.join(scripts_dir, 'userSetup.py')
            if not os.path.exists(setup_file):
                continue
            try:
                with open(setup_file, 'r') as f:
                    lines = f.readlines()
                skip = False
                cleaned = []
                for line in lines:
                    if any(m in line for m in _MARKERS):
                        skip = True
                    if not skip:
                        cleaned.append(line)
                    if '# ---------------------------------' in line:
                        skip = False
                with open(setup_file, 'w') as f:
                    f.writelines(cleaned)
            except Exception:
                pass

        # 4. Close UI
        if cmds.window(self.win_name, exists=True):
            cmds.deleteUI(self.win_name)

        # 5. Delete installed files & config
        for f in [
            os.path.join(scripts_dir, 'layout_forger.py'),
            os.path.join(user_app_dir, 'prefs', 'icons', 'anim_shortcuts_icon.png'),
            _get_config_path() # Added config deletion
        ]:
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass

        # Removed confirmation dialog per user request


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

    pos += 30
    sub = cmds.text(label='Create custom panel layouts and switch between them\ninstantly using custom hotkeys. Streamline your animation\nworkflow by eliminating tedious menus and keeping your\nworkspace perfectly organized.',
                    align='left', font='obliqueLabelFont')
    cmds.formLayout(form, edit=True, attachForm=[(sub, 'top', pos), (sub, 'left', 14)])

    pos += 80
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
    sign = cmds.text(label='Forge the layout and Enjoy the Flow.  — Baji N', align='left', font='obliqueLabelFont')
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
    cmds.window(win_name, edit=True, widthHeight=(420, pos))
