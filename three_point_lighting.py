"""
Maya 2024+  |  Turntable – 3-Point Arnold Area Light Setup
===========================================================
Select one polygon mesh object, open the Turntable UI, and click
'Create Setup'.  Re-running the setup automatically removes the
previous rig first.

Spherical coordinate convention for light placement:
  azimuth  0° = +Z (front)  90° = +X (right)  180° = -Z (back)
  elevation 0° = horizon    90° = straight up

Arnold area lights emit along local -Z.  If lights face the wrong
way, change aimVector=(0,0,-1) to (0,-1,0) inside aim_at().
"""

import maya.cmds as cmds
import math

# ── Scene-node names used by this rig ─────────────────────────────────────────
class variables():
    LIGHT_NAMES  = ('keyLight', 'fillLight', 'rimLight')
    LIGHTS_GRP   = 'threePtLights_grp'
    CAM_PIVOT    = 'cam1_pivot'

# Relative intensity multipliers so the 3-point ratios are preserved
# regardless of what the user types in the Intensity field.
    INTENSITY_RATIO = {'keyLight': 1.0, 'fillLight': 0.35, 'rimLight': 0.65}

# Spherical placement per light: (azimuth_deg, elevation_deg, dist_multiplier)
    LIGHT_PLACEMENT = {
        'keyLight':  ( 45,  45, 1.0),
        'fillLight': (-45,  20, 1.3),
        'rimLight':  (180,  55, 1.0),
    }


# ── Cleanup ───────────────────────────────────────────────────────────────────

def cleanup_previous_setup():
    """Delete any nodes from a previous run of this script."""
    to_delete = []

    if cmds.objExists(LIGHTS_GRP):
        to_delete.append(LIGHTS_GRP)
    else:
        for n in LIGHT_NAMES:
            if cmds.objExists(n):
                to_delete.append(n)

    if cmds.objExists(CAM_PIVOT):
        to_delete.append(CAM_PIVOT)

    if to_delete:
        cmds.delete(to_delete)
        print("Turntable: removed previous setup ({}).".format(', '.join(to_delete)))


# ── Core setup ────────────────────────────────────────────────────────────────

def create_setup(settings):
    """
    Build the 3-point lighting rig and camera from a settings dict.

    Expected keys
    -------------
    color           (r, g, b) floats 0-1
    intensity       float  – key-light base; fill/rim are scaled automatically
    exposure        float  – applied equally to all three lights
    use_color_temp  bool
    temperature     int    – Kelvin, used when use_color_temp is True
    spread          float  0-1
    cam_name        str
    start_frame     int
    end_frame       int
    rotation_axis   'X', 'Y', or 'Z'
    """

    # ── Validate selection ────────────────────────────────────────────────
    sel = cmds.ls(selection=True)
    if not sel:
        cmds.error("Turntable: nothing selected – select a mesh object first.")
        return

    obj = sel[0]
    if cmds.objectType(obj) in ('mesh', 'nurbsSurface', 'nurbsCurve'):
        obj = cmds.listRelatives(obj, parent=True)[0]

    shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
    if not shapes:
        cmds.error("Turntable: '{}' has no polygon mesh shape.".format(obj))
        return

    mesh = shapes[0]

    # ── Remove previous rig ───────────────────────────────────────────────
    cleanup_previous_setup()

    # ── Find centroid via temporary cluster ───────────────────────────────
    #
    #   a) select all vertices
    #   b) cluster() places its handle at the weighted centroid of the verts
    #   c) read world-space translation of the handle
    #   d) delete handle + deformer node
    #
    cmds.select('{}.vtx[*]'.format(mesh))
    cluster_node, cluster_handle = cmds.cluster(name='_tempCenter_cluster')
    center = cmds.xform(cluster_handle, query=True, worldSpace=True, translation=True)
    cmds.delete(cluster_handle)
    if cmds.objExists(cluster_node):
        cmds.delete(cluster_node)
    cmds.select(clear=True)

    cx, cy, cz = center

    # ── Scale distances from bounding box ────────────────────────────────
    bb       = cmds.exactWorldBoundingBox(obj)
    obj_size = max(bb[3]-bb[0], bb[4]-bb[1], bb[5]-bb[2]) or 1.0

    light_dist = obj_size * 2.5
    cam_dist   = obj_size * 3.5
    light_size = obj_size * 0.8

    # ── Helpers ───────────────────────────────────────────────────────────

    def sphere_to_world(az_deg, el_deg, radius):
        az = math.radians(az_deg)
        el = math.radians(el_deg)
        return (
            cx + radius * math.sin(az) * math.cos(el),
            cy + radius * math.sin(el),
            cz + radius * math.cos(az) * math.cos(el),
        )

    def aim_at(xform, target):
        """Point xform's local -Z axis at target (world space), no constraints left."""
        loc = cmds.spaceLocator(name='_tempAimLoc')[0]
        cmds.xform(loc, worldSpace=True, translation=list(target))
        con = cmds.aimConstraint(
            loc, xform,
            aimVector=(0, 0, -1),
            upVector=(0, 1, 0),
            worldUpType='scene',
            maintainOffset=False,
        )[0]
        rot = cmds.xform(xform, query=True, worldSpace=True, rotation=True)
        cmds.delete(con, loc)
        cmds.xform(xform, worldSpace=True, rotation=rot)

    def make_area_light(name, world_pos, intensity_val):
        xform = cmds.createNode('transform', name=name)
        shape = cmds.createNode('aiAreaLight', parent=xform, name=name + '_shape')

        cmds.xform(xform, worldSpace=True, translation=list(world_pos))
        for axis in ('X', 'Y', 'Z'):
            cmds.setAttr('{}.scale{}'.format(xform, axis), light_size)

        r, g, b = settings['color']
        cmds.setAttr('{}.color'.format(shape),     r, g, b, type='double3')
        cmds.setAttr('{}.intensity'.format(shape), intensity_val)
        cmds.setAttr('{}.exposure'.format(shape),  settings['exposure'])
        cmds.setAttr('{}.normalize'.format(shape), 1)
        cmds.setAttr('{}.aiSpread'.format(shape),    settings['spread'])

        use_temp = settings['use_color_temp']
        cmds.setAttr('{}.aiUseColorTemperature'.format(shape), use_temp)
        if use_temp:
            cmds.setAttr('{}.aiColorTemperature'.format(shape), settings['temperature'])

        aim_at(xform, center)
        return xform

    # ── Create three lights ───────────────────────────────────────────────
    base_intensity = settings['intensity']
    lights = []
    for lname in LIGHT_NAMES:
        az, el, dist_mult = LIGHT_PLACEMENT[lname]
        pos   = sphere_to_world(az, el, light_dist * dist_mult)
        light = make_area_light(lname, pos, base_intensity * INTENSITY_RATIO[lname])
        lights.append(light)

    cmds.group(*lights, name=LIGHTS_GRP)

    # ── Create camera parented to a pivot at the centroid ─────────────────
    #
    #   cam1_pivot  (world position = object centroid)
    #   └── <cam>  (local Z = +cam_dist → camera's default -Z looks at pivot)
    #
    pivot = cmds.group(empty=True, name=CAM_PIVOT)
    cmds.xform(pivot, worldSpace=True, translation=center)

    cam_name = settings['cam_name'] or 'cam1'
    cam_xform, _cam_shape = cmds.camera(name=cam_name)
    cmds.parent(cam_xform, pivot)

    for attr, val in [('translateX', 0), ('translateY', 0), ('translateZ', cam_dist),
                      ('rotateX',    0), ('rotateY',    0), ('rotateZ',    0)]:
        cmds.setAttr('{}.{}'.format(cam_xform, attr), val)

    # ── Keyframe pivot rotation for turntable animation ───────────────────
    axis = settings['rotation_axis']
    sf   = settings['start_frame']
    ef   = settings['end_frame']

    cmds.setKeyframe(pivot, attribute='rotate{}'.format(axis), time=sf, value=0)
    cmds.setKeyframe(pivot, attribute='rotate{}'.format(axis), time=ef, value=360)

    cmds.selectKey(pivot, attribute='rotate{}'.format(axis), time=(sf, ef))
    cmds.keyTangent(inTangentType='linear', outTangentType='linear')

    cmds.playbackOptions(minTime=sf, maxTime=ef)
    cmds.select(clear=True)

    print("=" * 54)
    print("  Turntable setup complete")
    print("  Object : {}".format(obj))
    print("  Centre : ({:.3f}, {:.3f}, {:.3f})".format(*center))
    print("  Camera : {}  pivot: {}".format(cam_xform, pivot))
    print("  Anim   : frames {} – {} on rotate{}  (360°)".format(sf, ef, axis))
    print("=" * 54)


# ── UI ────────────────────────────────────────────────────────────────────────

def show_turntable_ui():
    win_id = 'turntableWin'
    if cmds.window(win_id, exists=True):
        cmds.deleteUI(win_id)

    cmds.window(
        win_id,
        title='Turntable',
        sizeable=True,
        resizeToFitChildren=True,
        minimizeButton=True,
        maximizeButton=False,
    )

    cmds.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=['both', 8])
    cmds.separator(height=6, style='none')

    # ── Section 1 : Light Settings ────────────────────────────────────────
    cmds.frameLayout(
        label=' Light Settings',
        collapsable=True,
        collapse=False,
        marginHeight=10,
        marginWidth=10
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6)

    color_ctl = cmds.colorSliderGrp(
        label='Color',
        rgb=(1.0, 1.0, 1.0),
        columnWidth=[(1, 120), (2, 30), (3, 80)],
    )
    intensity_ctl = cmds.floatSliderGrp(
        label='Intensity',
        value=1.0,
        minValue=0.0, maxValue=10.0,
        fieldMinValue=0.0, fieldMaxValue=9999.0,
        field=True,
        columnWidth=[(1, 120), (2, 60), (3, 80)],
    )
    exposure_ctl = cmds.floatSliderGrp(
        label='Exposure',
        value=0.0,
        minValue=-10.0, maxValue=10.0,
        fieldMinValue=-100.0, fieldMaxValue=100.0,
        field=True,
        columnWidth=[(1, 120), (2, 60), (3, 80)],
    )
    use_temp_ctl = cmds.checkBoxGrp(
        label='Use Color Temperature',
        value1=False,
        columnWidth=[(1, 120)],
    )
    temp_ctl = cmds.intSliderGrp(
        label='Temperature (K)',
        value=6500,
        minValue=1000, maxValue=12000,
        fieldMinValue=800, fieldMaxValue=20000,
        field=True,
        enable=False,
        columnWidth=[(1, 120), (2, 60), (3, 80)],
    )
    spread_ctl = cmds.floatSliderGrp(
        label='Spread',
        value=1.0,
        minValue=0.0, maxValue=1.0,
        field=True,
        columnWidth=[(1, 120), (2, 60), (3, 80)],
    )

    def on_temp_toggle(*_):
        enabled = cmds.checkBoxGrp(use_temp_ctl, query=True, value1=True)
        cmds.intSliderGrp(temp_ctl, edit=True, enable=enabled)

    cmds.checkBoxGrp(use_temp_ctl, edit=True, changeCommand=on_temp_toggle)

    cmds.setParent('..')  # end columnLayout
    cmds.setParent('..')  # end frameLayout

    cmds.separator(height=4, style='none')

    # ── Section 2 : Camera Settings ───────────────────────────────────────
    cmds.frameLayout(
        label=' Camera Settings',
        collapsable=True,
        collapse=False,
        marginHeight=10,
        marginWidth=10
    )
    cmds.columnLayout(adjustableColumn=True, rowSpacing=6)

    cam_name_ctl = cmds.textFieldGrp(
        label='Camera Name',
        text='cam1',
        columnWidth=[(1, 120), (2, 140)],
    )
    start_ctl = cmds.intFieldGrp(
        label='Start Frame',
        numberOfFields=1,
        value1=1,
        columnWidth=[(1, 120), (2, 80)],
    )
    end_ctl = cmds.intFieldGrp(
        label='End Frame',
        numberOfFields=1,
        value1=120,
        columnWidth=[(1, 120), (2, 80)],
    )
    axis_ctl = cmds.radioButtonGrp(
        label='Rotation Axis',
        labelArray3=['X', 'Y', 'Z'],
        numberOfRadioButtons=3,
        select=2,                          # Y by default
        columnWidth=[(1, 120), (2, 40), (3, 40), (4, 40)],
    )

    cmds.setParent('..')
    cmds.setParent('..')

    cmds.separator(height=6, style='none')

    # ── Create button ─────────────────────────────────────────────────────
    def on_create(*_):
        if not cmds.pluginInfo('mtoa', query=True, loaded=True):
            cmds.confirmDialog(
                title='Arnold Not Loaded',
                message=(
                    'MtoA (Arnold) plugin is not loaded.\n'
                    'Load it via Windows > Settings/Preferences > Plug-in Manager.'
                ),
                button=['OK'],
            )
            return

        axis_map = {1: 'X', 2: 'Y', 3: 'Z'}

        settings = {
            'color':          tuple(cmds.colorSliderGrp(color_ctl,     query=True, rgb=True)),
            'intensity':      cmds.floatSliderGrp(intensity_ctl, query=True, value=True),
            'exposure':       cmds.floatSliderGrp(exposure_ctl,  query=True, value=True),
            'use_color_temp': cmds.checkBoxGrp(use_temp_ctl,     query=True, value1=True),
            'temperature':    cmds.intSliderGrp(temp_ctl,        query=True, value=True),
            'spread':         cmds.floatSliderGrp(spread_ctl,    query=True, value=True),
            'cam_name':       cmds.textFieldGrp(cam_name_ctl,    query=True, text=True),
            'start_frame':    cmds.intFieldGrp(start_ctl,        query=True, value1=True),
            'end_frame':      cmds.intFieldGrp(end_ctl,          query=True, value1=True),
            'rotation_axis':  axis_map[cmds.radioButtonGrp(axis_ctl, query=True, select=True)],
        }

        create_setup(settings)

    cmds.button(
        label='Create Setup',
        height=36,
        command=on_create,
        backgroundColor=(0.2, 0.36, 0.2),
    )
    cmds.separator(height=8, style='none')

    cmds.showWindow(win_id)


show_turntable_ui()
