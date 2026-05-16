# Turntable
# By Colin Cheng (With assistance from Claude Code for UI setup and formatting) 
# 
# 
# Run script, select object, adjust attributes in window
# Creates a 3 Point lighting setup with Arnold lights around the object based on vertex attributes.

import maya.cmds as mc
import math

# Class for scene node names 
class variables():
    light_names  = ('keyLight', 'fillLight', 'rimLight')
    lights_grp   = 'threePtlights_grp'
    cam_pivot    = 'cam1_pivot'
    turntable = 'turntable_grp'

# Relative intensity multipliers so the 3-point ratios are preserved
# regardless of what the user types in the Intensity field.
    intensity_ratio = {'keyLight': 1.0, 'fillLight': 0.35, 'rimLight': 0.65}

# Spherical placement per light: (azimuth_deg, elevation_deg, dist_multiplier)
    light_placement = {
        'keyLight':  ( 45,  45, 1.0),
        'fillLight': (-45,  20, 1.3),
        'rimLight':  (180,  55, 1.0),
    }


# Deletes previous setup 

def cleanup_previous_setup():
    to_delete = []

    if mc.objExists(variables.turntable):
        to_delete.append(variables.turntable)
    else:
        for n in variables.light_names:
            if mc.objExists(n):
                to_delete.append(n)

    if to_delete:
        cmds.delete(to_delete)
        print("Turntable: removed previous setup ({}).".format(', '.join(to_delete)))


# Core setup

def create_setup(settings):

    # Validate selection 
    sel = mc.ls(selection=True)
    if not sel:
        mc.error("Turntable: nothing selected – select a mesh object first.")
        return

    obj = sel[0]
    if mc.objectType(obj) in ('mesh', 'nurbsSurface', 'nurbsCurve'):
        obj = mc.listRelatives(obj, parent=True)[0]

    shapes = mc.listRelatives(obj, shapes=True, type='mesh')
    if not shapes:
        mc.error("Turntable: '{}' has no polygon mesh shape.".format(obj))
        return

    mesh = shapes[0]

    # Remove previous rig 
    cleanup_previous_setup()

    # Find center of object via. temporary cluster

    mc.select('{}.vtx[*]'.format(mesh))
    cluster_node, cluster_handle = mc.cluster(name='_tempCenter_cluster')
    center = mc.xform(cluster_handle, query=True, worldSpace=True, translation=True)
    mc.delete(cluster_handle)
    if mc.objExists(cluster_node):
        mc.delete(cluster_node)
    mc.select(clear=True)

    cx, cy, cz = center

    # ── Scale distances from bounding box ────────────────────────────────
    bb       = mc.exactWorldBoundingBox(obj)
    obj_size = max(bb[3]-bb[0], bb[4]-bb[1], bb[5]-bb[2]) or 1.0

    light_dist = obj_size * 2.5
    cam_dist   = obj_size * 3.5
    light_size = obj_size * 0.8

    # Cluster setup to find true center of object 

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
        loc = mc.spaceLocator(name='_tempAimLoc')[0]
        mc.xform(loc, worldSpace=True, translation=list(target))
        con = mc.aimConstraint(
            loc, xform,
            aimVector=(0, 0, -1),
            upVector=(0, 1, 0),
            worldUpType='scene',
            maintainOffset=False,
        )[0]
        rot = mc.xform(xform, query=True, worldSpace=True, rotation=True)
        mc.delete(con, loc)
        mc.xform(xform, worldSpace=True, rotation=rot)

    def make_area_light(name, world_pos, intensity_val):
        xform = mc.createNode('transform', name=name)
        shape = mc.createNode('aiAreaLight', parent=xform, name=name + '_shape')

        mc.xform(xform, worldSpace=True, translation=list(world_pos))
        for axis in ('X', 'Y', 'Z'):
            mc.setAttr('{}.scale{}'.format(xform, axis), light_size)

        r, g, b = settings['color']
        mc.setAttr('{}.color'.format(shape),     r, g, b, type='double3')
        mc.setAttr('{}.intensity'.format(shape), intensity_val)
        mc.setAttr('{}.exposure'.format(shape),  settings['exposure'])
        mc.setAttr('{}.normalize'.format(shape), 1)
        mc.setAttr('{}.aiSpread'.format(shape),    settings['spread'])

        use_temp = settings['use_color_temp']
        mc.setAttr('{}.aiUseColorTemperature'.format(shape), use_temp)
        if use_temp:
            mc.setAttr('{}.aiColorTemperature'.format(shape), settings['temperature'])

        aim_at(xform, center)
        return xform

    # Create three lights 
    base_intensity = settings['intensity']
    lights = []
    for lname in variables.light_names:
        az, el, dist_mult = variables.light_placement[lname]
        pos   = sphere_to_world(az, el, light_dist * dist_mult)
        light = make_area_light(lname, pos, base_intensity * variables.intensity_ratio[lname])
        lights.append(light)

    mc.group(*lights, name=variables.lights_grp)

    # Create camera parented to a pivot at the centroid

    pivot = mc.group(empty=True, name=variables.cam_pivot)
    mc.xform(pivot, worldSpace=True, translation=center)

    cam_name = settings['cam_name'] or 'cam1'
    cam_xform, _cam_shape = mc.camera(name=cam_name)
    mc.parent(cam_xform, pivot)

    for attr, val in [('translateX', 0), ('translateY', 0), ('translateZ', cam_dist),
                      ('rotateX',    0), ('rotateY',    0), ('rotateZ',    0)]:
        mc.setAttr('{}.{}'.format(cam_xform, attr), val)

    #  Keyframe pivot rotation for turntable animation 
    axis = settings['rotation_axis']
    sf   = settings['start_frame']
    ef   = settings['end_frame']

    mc.setKeyframe(pivot, attribute='rotate{}'.format(axis), time=sf, value=0)
    mc.setKeyframe(pivot, attribute='rotate{}'.format(axis), time=ef, value=360)

    mc.selectKey(pivot, attribute='rotate{}'.format(axis), time=(sf, ef))
    mc.keyTangent(inTangentType='linear', outTangentType='linear')

    mc.playbackOptions(minTime=sf, maxTime=ef)
    mc.select(clear=True)
        
    #  Group camera and lights 
    mc.group('threePtlights_grp', 'cam1_pivot', name=variables.turntable)

# UI 

def show_turntable_ui():
    win_id = 'turntableWin'
    if mc.window(win_id, exists=True):
        mc.deleteUI(win_id)

    mc.window(
        win_id,
        title='Turntable',
        sizeable=True,
        resizeToFitChildren=True,
        minimizeButton=True,
        maximizeButton=False,
    )

    mc.columnLayout(adjustableColumn=True, rowSpacing=6, columnOffset=['both', 8])
    mc.separator(height=6, style='none')

    # Section 1 : Light Settings
    mc.frameLayout(
        label=' Light Settings',
        collapsable=True,
        collapse=False,
        marginHeight=10,
        marginWidth=10
    )
    mc.columnLayout(adjustableColumn=True, rowSpacing=6)

    color_ctl = mc.colorSliderGrp(
        label='Color',
        rgb=(1.0, 1.0, 1.0),
        columnWidth=[(1, 120), (2, 30), (3, 80)],
    )
    intensity_ctl = mc.floatSliderGrp(
        label='Intensity',
        value=1.0,
        minValue=0.0, maxValue=10.0,
        fieldMinValue=0.0, fieldMaxValue=9999.0,
        field=True,
        columnWidth=[(1, 120), (2, 60), (3, 80)],
    )
    exposure_ctl = mc.floatSliderGrp(
        label='Exposure',
        value=0.0,
        minValue=-10.0, maxValue=10.0,
        fieldMinValue=-100.0, fieldMaxValue=100.0,
        field=True,
        columnWidth=[(1, 120), (2, 60), (3, 80)],
    )
    use_temp_ctl = mc.checkBoxGrp(
        label='Use Color Temperature',
        value1=False,
        columnWidth=[(1, 120)],
    )
    temp_ctl = mc.intSliderGrp(
        label='Temperature (K)',
        value=6500,
        minValue=1000, maxValue=12000,
        fieldMinValue=800, fieldMaxValue=20000,
        field=True,
        enable=False,
        columnWidth=[(1, 120), (2, 60), (3, 80)],
    )
    spread_ctl = mc.floatSliderGrp(
        label='Spread',
        value=1.0,
        minValue=0.0, maxValue=1.0,
        field=True,
        columnWidth=[(1, 120), (2, 60), (3, 80)],
    )

    def on_temp_toggle(*_):
        enabled = mc.checkBoxGrp(use_temp_ctl, query=True, value1=True)
        mc.intSliderGrp(temp_ctl, edit=True, enable=enabled)

    mc.checkBoxGrp(use_temp_ctl, edit=True, changeCommand=on_temp_toggle)

    mc.setParent('..')  # end columnLayout
    mc.setParent('..')  # end frameLayout

    mc.separator(height=4, style='none')

    # Section 2 : Camera Settings
    mc.frameLayout(
        label=' Camera Settings',
        collapsable=True,
        collapse=False,
        marginHeight=10,
        marginWidth=10
    )
    mc.columnLayout(adjustableColumn=True, rowSpacing=6)

    cam_name_ctl = mc.textFieldGrp(
        label='Camera Name',
        text='cam1',
        columnWidth=[(1, 120), (2, 140)],
    )
    start_ctl = mc.intFieldGrp(
        label='Start Frame',
        numberOfFields=1,
        value1=1,
        columnWidth=[(1, 120), (2, 80)],
    )
    end_ctl = mc.intFieldGrp(
        label='End Frame',
        numberOfFields=1,
        value1=120,
        columnWidth=[(1, 120), (2, 80)],
    )
    axis_ctl = mc.radioButtonGrp(
        label='Rotation Axis',
        labelArray3=['X', 'Y', 'Z'],
        numberOfRadioButtons=3,
        select=2,                          # Y by default
        columnWidth=[(1, 120), (2, 40), (3, 40), (4, 40)],
    )

    mc.setParent('..')
    mc.setParent('..')

    mc.separator(height=6, style='none')

    # Create setup and settings buttons
    def on_create(*_):
        if not mc.pluginInfo('mtoa', query=True, loaded=True):
            mc.confirmDialog(
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
            'color':          tuple(mc.colorSliderGrp(color_ctl,     query=True, rgb=True)),
            'intensity':      mc.floatSliderGrp(intensity_ctl, query=True, value=True),
            'exposure':       mc.floatSliderGrp(exposure_ctl,  query=True, value=True),
            'use_color_temp': mc.checkBoxGrp(use_temp_ctl,     query=True, value1=True),
            'temperature':    mc.intSliderGrp(temp_ctl,        query=True, value=True),
            'spread':         mc.floatSliderGrp(spread_ctl,    query=True, value=True),
            'cam_name':       mc.textFieldGrp(cam_name_ctl,    query=True, text=True),
            'start_frame':    mc.intFieldGrp(start_ctl,        query=True, value1=True),
            'end_frame':      mc.intFieldGrp(end_ctl,          query=True, value1=True),
            'rotation_axis':  axis_map[mc.radioButtonGrp(axis_ctl, query=True, select=True)],
        }

        create_setup(settings)

    mc.button(
        label='Create Setup',
        height=36,
        command=on_create,
        backgroundColor=(0.2, 0.36, 0.2),
    )
    mc.separator(height=8, style='none')

    mc.showWindow(win_id)


show_turntable_ui()
