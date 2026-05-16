"""
Maya 2024+  |  3-Point Arnold Area Light Setup with Orbiting Camera
===================================================================
Select one polygon mesh object, then run this script.

The camera (cam1) is parented to a pivot group that sits exactly at
the object's centroid.  Rotate 'cam1_pivot' in Y (or any axis) to
orbit the camera around the subject.

Light positions use spherical coordinates centred on the object:
  azimuth  0° = +Z (front)  90° = +X (right)  180° = -Z (back)
  elevation 0° = horizon    90° = straight up

Arnold area lights emit along their local -Z axis by default.
If all three lights face the wrong direction, change the aimVector
inside aim_transform_at() from (0, 0, -1) to (0, -1, 0).
"""

import maya.cmds as cmds
import math


def create_three_point_lighting_setup():

    # ── 1. Verify Arnold is available ─────────────────────────────────────
    if not cmds.pluginInfo('mtoa', query=True, loaded=True):
        cmds.error(
            "MtoA (Arnold) plugin is not loaded.\n"
            "Load it via Windows > Settings/Preferences > Plug-in Manager."
        )
        return

    # ── 2. Validate selection ─────────────────────────────────────────────
    sel = cmds.ls(selection=True)
    if not sel:
        cmds.error("Nothing selected – please select a mesh object and run again.")
        return

    obj = sel[0]

    # Resolve shape → transform
    if cmds.objectType(obj) in ('mesh', 'nurbsSurface', 'nurbsCurve'):
        obj = cmds.listRelatives(obj, parent=True)[0]

    shapes = cmds.listRelatives(obj, shapes=True, type='mesh')
    if not shapes:
        cmds.error("'{}' has no polygon mesh shape.".format(obj))
        return

    mesh = shapes[0]

    # ── 3. Find exact centroid via a temporary cluster deformer ───────────
    #
    # Workflow the user specified:
    #   a) select all vertices
    #   b) create a cluster  →  Maya places the handle at the weighted centroid
    #   c) read that world-space position
    #   d) delete the cluster
    #
    cmds.select('{}.vtx[*]'.format(mesh))
    cluster_node, cluster_handle = cmds.cluster(name='_tempCenter_cluster')

    center = cmds.xform(cluster_handle, query=True, worldSpace=True, translation=True)

    cmds.delete(cluster_handle)
    if cmds.objExists(cluster_node):
        cmds.delete(cluster_node)

    cmds.select(clear=True)

    cx, cy, cz = center

    # ── 4. Derive scene-scale distances from the bounding box ─────────────
    bb        = cmds.exactWorldBoundingBox(obj)
    obj_size  = max(bb[3] - bb[0], bb[4] - bb[1], bb[5] - bb[2]) or 1.0

    light_dist = obj_size * 2.5    # radius at which lights are placed
    cam_dist   = obj_size * 3.5    # camera distance from pivot centre
    light_size = obj_size * 0.8    # uniform scale of each area-light quad

    # ── 5. Helpers ────────────────────────────────────────────────────────

    def sphere_to_world(azimuth_deg, elevation_deg, radius):
        """Converts spherical angles + radius to a world-space XYZ position."""
        az = math.radians(azimuth_deg)
        el = math.radians(elevation_deg)
        return (
            cx + radius * math.sin(az) * math.cos(el),
            cy + radius * math.sin(el),
            cz + radius * math.cos(az) * math.cos(el),
        )

    def aim_transform_at(xform, target):
        """
        Rotates `xform` so its local -Z axis points at `target` (world space).

        Strategy: apply a temporary aimConstraint to get the correct euler
        angles, bake them onto the transform's rotate channels, then remove
        the constraint so nothing is left connected.
        """
        loc = cmds.spaceLocator(name='_tempAimLoc')[0]
        cmds.xform(loc, worldSpace=True, translation=list(target))

        con = cmds.aimConstraint(
            loc, xform,
            aimVector=(0, 0, -1),   # Arnold area light emits along local -Z
            upVector=(0, 1, 0),
            worldUpType='scene',
            maintainOffset=False,
        )[0]

        # Query the rotation the constraint computed, then bake + remove it
        rot = cmds.xform(xform, query=True, worldSpace=True, rotation=True)
        cmds.delete(con, loc)
        cmds.xform(xform, worldSpace=True, rotation=rot)

    def make_area_light(name, world_pos, intensity, rgb):
        """
        Creates an Arnold area light (aiAreaLight), positions it at
        `world_pos`, scales it to `light_size`, applies `intensity` and
        `rgb` colour, then aims it at the object centroid.
        """
        shape = cmds.shadingNode('aiAreaLight', asLight=True, name=name + '_shape')
        xform = cmds.listRelatives(shape, parent=True)[0]
        xform = cmds.rename(xform, name)

        cmds.xform(xform, worldSpace=True, translation=list(world_pos))

        for axis in ('X', 'Y', 'Z'):
            cmds.setAttr('{}.scale{}'.format(xform, axis), light_size)

        cmds.setAttr('{}.intensity'.format(shape),  intensity)
        cmds.setAttr('{}.color'.format(shape),      *rgb, type='double3')
        cmds.setAttr('{}.normalize'.format(shape),  1)   # keep intensity
                                                          # independent of size

        aim_transform_at(xform, center)
        return xform

    # ── 6. Create the three lights ────────────────────────────────────────

    # Key light ── front-right, high elevation, warm white
    #   Primary source; typically the brightest of the three.
    key_light = make_area_light(
        'keyLight',
        world_pos  = sphere_to_world(azimuth_deg=45,  elevation_deg=45, radius=light_dist),
        intensity  = 1.0,
        rgb        = (1.0, 0.97, 0.90),
    )

    # Fill light ── front-left, lower elevation, cool tint, softer
    #   Fills shadows cast by the key without fully eliminating them.
    fill_light = make_area_light(
        'fillLight',
        world_pos  = sphere_to_world(azimuth_deg=-45, elevation_deg=20, radius=light_dist * 1.3),
        intensity  = 0.35,
        rgb        = (0.88, 0.93, 1.0),
    )

    # Rim / back light ── behind the subject, high elevation, neutral
    #   Creates a bright edge that separates the subject from the background.
    rim_light = make_area_light(
        'rimLight',
        world_pos  = sphere_to_world(azimuth_deg=180, elevation_deg=55, radius=light_dist),
        intensity  = 0.65,
        rgb        = (1.0, 1.0, 1.0),
    )

    # ── 7. Create camera with a pivot at the object centroid ──────────────
    #
    # Layout inside the pivot group:
    #
    #   cam1_pivot  (world position = object centroid)
    #   └── cam1   (local translate = [0, 0, cam_dist])
    #
    # A Maya camera's default look direction is -Z in local space.
    # At local position (0, 0, +cam_dist) it therefore looks straight back
    # toward local origin (0, 0, 0), which is the pivot / object centre.
    # Rotating cam1_pivot in Y then orbits the camera around the subject.
    #
    pivot = cmds.group(empty=True, name='cam1_pivot')
    cmds.xform(pivot, worldSpace=True, translation=center)

    cam_xform, _cam_shape = cmds.camera(name='cam1')

    cmds.parent(cam_xform, pivot)

    # Reset and set local position after re-parenting
    cmds.setAttr('{}.translateX'.format(cam_xform), 0)
    cmds.setAttr('{}.translateY'.format(cam_xform), 0)
    cmds.setAttr('{}.translateZ'.format(cam_xform), cam_dist)
    cmds.setAttr('{}.rotateX'.format(cam_xform), 0)
    cmds.setAttr('{}.rotateY'.format(cam_xform), 0)
    cmds.setAttr('{}.rotateZ'.format(cam_xform), 0)

    # ── 8. Organise the outliner ──────────────────────────────────────────
    cmds.group(key_light, fill_light, rim_light, name='threePtLights_grp')
    cmds.select(clear=True)

    # ── 9. Summary ────────────────────────────────────────────────────────
    print("=" * 54)
    print("  3-Point Arnold Lighting Setup – done")
    print("  Object  : {}".format(obj))
    print("  Centre  : ({:.3f}, {:.3f}, {:.3f})".format(*center))
    print("  Key     : {}".format(key_light))
    print("  Fill    : {}".format(fill_light))
    print("  Rim     : {}".format(rim_light))
    print("  Camera  : {}  (pivot: {})".format(cam_xform, pivot))
    print("  → Rotate '{}' to orbit the camera.".format(pivot))
    print("=" * 54)


create_three_point_lighting_setup()
