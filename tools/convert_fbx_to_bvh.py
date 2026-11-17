"""Batch convert Auto-Rig Pro / Mixamo FBX animations to CarPi5 VRM-retargeted BVH files.

Run with Blender headless:
    blender -b --python tools/convert_fbx_to_bvh.py
"""

import math
import os
from pathlib import Path
import sys

import bpy
from mathutils import Matrix, Vector


REPO_ROOT = Path(__file__).resolve().parent.parent
REF_BVH = REPO_ROOT / "models" / "bvh" / "idles" / "neutral_idle.bvh"
DOWNLOADS_DIR = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Downloads"
OUT_ROOT = REPO_ROOT / "models" / "bvh"

# (src_subdir, src_filename, dst_subdir, dst_filename, is_ground)
CONVERSION_JOBS = [
    ("Dance Animations", "BubblePop.fbx", "dances", "dance_bubble_pop.bvh", False),
    ("Dance Animations", "HappyDance.fbx", "dances", "dance_happy_dance.bvh", False),
    ("Dance Animations", "LevelUp.fbx", "dances", "dance_level_up.bvh", False),
    ("Dance Animations", "TheDipping.fbx", "dances", "dance_the_dipping.bvh", False),
    ("Emotes Animations", "LadyBow.fbx", "emotions", "pose_lady_bow.bvh", False),
    ("Emotes Animations", "LayingReading.fbx", "idles", "laying_reading.bvh", True),
    ("Emotes Animations", "PolishNails.fbx", "emotions", "pose_polish_nails.bvh", False),
    ("Emotes Animations", "ThanksGentlemenBow.fbx", "emotions", "pose_gentlemen_bow.bvh", False),
    ("Emotes Animations", "TiedUp.fbx", "emotions", "tied_up.bvh", False),
    ("Kids Animations", "GameFrogSitting.fbx", "idles", "sit_frog.bvh", True),
    ("Kids Animations", "GameHopScotch.fbx", "actions", "action_hopscotch.bvh", False),
    ("Kids Animations", "GameSuperman.fbx", "actions", "action_superman.bvh", False),
    ("Kids Animations", "InPlaceAkimboWaiting.fbx", "idles", "idle_akimbo_waiting.bvh", False),
    ("Kids Animations", "LargeStepAcross.fbx", "actions", "action_large_step_across.bvh", False),
    ("Kids Animations", "RunOpenArms.fbx", "actions", "action_run_open_arms.bvh", False),
    ("Kids Animations", "WalkKickingStones.fbx", "actions", "walk_kicking_stones.bvh", False),
    ("Kids Animations", "WalkTipToe.fbx", "actions", "walk_tiptoe.bvh", False),
    ("Movement Animations", "LeftTurn.fbx", "actions", "action_left_turn.bvh", False),
    ("Movement Animations", "RightTurn.fbx", "actions", "action_right_turn.bvh", False),
    ("Movement Animations", "RunToStop.fbx", "actions", "action_run_to_stop.bvh", False),
]

# VRM joint -> (parent_vrm_joint, fbx_bone_candidates, align_rest_dir)
SKELETON_SPEC = [
    ("hips", None, ["root.x", "Hips", "hips", "mixamorig:Hips"], False),
    ("spine", "hips", ["spine_01.x", "Spine", "spine", "mixamorig:Spine"], False),
    ("chest", "spine", ["spine_02.x", "Spine1", "chest", "mixamorig:Spine1"], False),
    ("upperChest", "chest", ["spine_03.x", "Spine2", "upperChest", "mixamorig:Spine2"], False),
    ("neck", "upperChest", ["neck.x", "Neck", "neck", "mixamorig:Neck"], False),
    ("head", "neck", ["head.x", "Head", "head", "mixamorig:Head"], False),
    ("leftShoulder", "upperChest", ["shoulder.l", "LeftShoulder", "mixamorig:LeftShoulder"], True),
    ("leftUpperArm", "leftShoulder", ["arm_stretch.l", "LeftArm", "mixamorig:LeftUpperArm"], True),
    ("leftLowerArm", "leftUpperArm", ["forearm_stretch.l", "LeftForeArm", "mixamorig:LeftLowerArm"], True),
    ("leftHand", "leftLowerArm", ["hand.l", "LeftHand", "mixamorig:LeftHand"], True),
    ("leftThumbProximal", "leftHand", ["thumb1.l", "LeftHandThumb1"], True),
    ("leftThumbIntermediate", "leftThumbProximal", ["thumb2.l", "LeftHandThumb2"], True),
    ("leftThumbDistal", "leftThumbIntermediate", ["thumb3.l", "LeftHandThumb3"], True),
    ("leftIndexProximal", "leftHand", ["index1.l", "LeftHandIndex1"], True),
    ("leftIndexIntermediate", "leftIndexProximal", ["index2.l", "LeftHandIndex2"], True),
    ("leftIndexDistal", "leftIndexIntermediate", ["index3.l", "LeftHandIndex3"], True),
    ("leftMiddleProximal", "leftHand", ["middle1.l", "LeftHandMiddle1"], True),
    ("leftMiddleIntermediate", "leftMiddleProximal", ["middle2.l", "LeftHandMiddle2"], True),
    ("leftMiddleDistal", "leftMiddleIntermediate", ["middle3.l", "LeftHandMiddle3"], True),
    ("leftRingProximal", "leftHand", ["ring1.l", "LeftHandRing1"], True),
    ("leftRingIntermediate", "leftRingProximal", ["ring2.l", "LeftHandRing2"], True),
    ("leftRingDistal", "leftRingIntermediate", ["ring3.l", "LeftHandRing3"], True),
    ("leftLittleProximal", "leftHand", ["pinky1.l", "LeftHandPinky1"], True),
    ("leftLittleIntermediate", "leftLittleProximal", ["pinky2.l", "LeftHandPinky2"], True),
    ("leftLittleDistal", "leftLittleIntermediate", ["pinky3.l", "LeftHandPinky3"], True),
    ("rightShoulder", "upperChest", ["shoulder.r", "RightShoulder", "mixamorig:RightShoulder"], True),
    ("rightUpperArm", "rightShoulder", ["arm_stretch.r", "RightArm", "mixamorig:RightUpperArm"], True),
    ("rightLowerArm", "rightUpperArm", ["forearm_stretch.r", "RightForeArm", "mixamorig:RightLowerArm"], True),
    ("rightHand", "rightLowerArm", ["hand.r", "RightHand", "mixamorig:RightHand"], True),
    ("rightThumbProximal", "rightHand", ["thumb1.r", "RightHandThumb1"], True),
    ("rightThumbIntermediate", "rightThumbProximal", ["thumb2.r", "RightHandThumb2"], True),
    ("rightThumbDistal", "rightThumbIntermediate", ["thumb3.r", "RightHandThumb3"], True),
    ("rightIndexProximal", "rightHand", ["index1.r", "RightHandIndex1"], True),
    ("rightIndexIntermediate", "rightIndexProximal", ["index2.r", "RightHandIndex2"], True),
    ("rightIndexDistal", "rightIndexIntermediate", ["index3.r", "RightHandIndex3"], True),
    ("rightMiddleProximal", "rightHand", ["middle1.r", "RightHandMiddle1"], True),
    ("rightMiddleIntermediate", "rightMiddleProximal", ["middle2.r", "RightHandMiddle2"], True),
    ("rightMiddleDistal", "rightMiddleIntermediate", ["middle3.r", "RightHandMiddle3"], True),
    ("rightRingProximal", "rightHand", ["ring1.r", "RightHandRing1"], True),
    ("rightRingIntermediate", "rightRingProximal", ["ring2.r", "RightHandRing2"], True),
    ("rightRingDistal", "rightRingIntermediate", ["ring3.r", "RightHandRing3"], True),
    ("rightLittleProximal", "rightHand", ["pinky1.r", "RightHandPinky1"], True),
    ("rightLittleIntermediate", "rightLittleProximal", ["pinky2.r", "RightHandPinky2"], True),
    ("rightLittleDistal", "rightLittleIntermediate", ["pinky3.r", "RightHandPinky3"], True),
    ("leftUpperLeg", "hips", ["thigh_stretch.l", "LeftUpLeg", "mixamorig:LeftUpperLeg"], True),
    ("leftLowerLeg", "leftUpperLeg", ["leg_stretch.l", "LeftLeg", "mixamorig:LeftLowerLeg"], True),
    ("leftFoot", "leftLowerLeg", ["foot.l", "LeftFoot", "mixamorig:LeftFoot"], True),
    ("leftToes", "leftFoot", ["toes_01.l", "LeftToeBase", "mixamorig:LeftToes"], True),
    ("rightUpperLeg", "hips", ["thigh_stretch.r", "RightUpLeg", "mixamorig:RightUpperLeg"], True),
    ("rightLowerLeg", "rightUpperLeg", ["leg_stretch.r", "RightLeg", "mixamorig:RightLowerLeg"], True),
    ("rightFoot", "rightLowerLeg", ["foot.r", "RightFoot", "mixamorig:RightFoot"], True),
    ("rightToes", "rightFoot", ["toes_01.r", "RightToeBase", "mixamorig:RightToes"], True),
]

# Blender Z-up -> VRM BVH Y-up change-of-basis matrix
BL_TO_BVH = Matrix(((1.0, 0.0, 0.0), (0.0, 0.0, 1.0), (0.0, -1.0, 0.0))).to_3x3()


def load_reference_vrm_pose():
    """Extract reference rest directions and BVH offsets from neutral_idle.bvh."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_anim.bvh(filepath=str(REF_BVH))
    vrm_arm = bpy.context.active_object

    ref_dirs = {}
    ref_offsets = {}
    for j_name, parent_name, _, _ in SKELETON_SPEC:
        bone = vrm_arm.data.bones.get(j_name)
        if not bone:
            continue
        vec = (vrm_arm.matrix_world.to_3x3() @ (bone.tail_local - bone.head_local)).normalized()
        ref_dirs[j_name] = vec.copy()
        if parent_name and vrm_arm.data.bones.get(parent_name):
            p_bone = vrm_arm.data.bones[parent_name]
            delta_bl = vrm_arm.matrix_world @ bone.head_local - vrm_arm.matrix_world @ p_bone.head_local
        else:
            delta_bl = vrm_arm.matrix_world @ bone.head_local
        delta_bvh = BL_TO_BVH @ delta_bl
        ref_offsets[j_name] = (delta_bvh.x, delta_bvh.y, delta_bvh.z)
    return ref_dirs, ref_offsets


def build_hierarchy_lines(ref_offsets):
    """Build clean BVH HIERARCHY section matching CarPi5 VRM humanoid joints."""
    children = {}
    for j_name, parent_name, _, _ in SKELETON_SPEC:
        children.setdefault(parent_name, []).append(j_name)

    out = ["HIERARCHY"]

    def emit(j_name, depth):
        ind = "  " * depth
        ox, oy, oz = ref_offsets.get(j_name, (0.0, 0.0, 0.0))
        if depth == 0:
            out.append(f"ROOT {j_name}")
            out.append(f"{ind}{{")
            out.append(f"{ind}  OFFSET {ox:.6f} {oy:.6f} {oz:.6f}")
            out.append(f"{ind}  CHANNELS 6 Xposition Yposition Zposition Yrotation Xrotation Zrotation")
        else:
            out.append(f"{ind}JOINT {j_name}")
            out.append(f"{ind}{{")
            out.append(f"{ind}  OFFSET {ox:.6f} {oy:.6f} {oz:.6f}")
            out.append(f"{ind}  CHANNELS 3 Yrotation Xrotation Zrotation")

        kids = children.get(j_name, [])
        if kids:
            for k in kids:
                emit(k, depth + 1)
        else:
            out.append(f"{ind}  End Site")
            out.append(f"{ind}  {{")
            out.append(f"{ind}    OFFSET 0.000000 0.250000 0.000000")
            out.append(f"{ind}  }}")
        out.append(f"{ind}}}")

    emit("hips", 0)
    return out


def convert_single_fbx(fbx_path: Path, dst_path: Path, is_ground: bool, ref_dirs, hierarchy_lines):
    """Import one FBX file in Blender, retarget onto VRM T-pose, and write BVH."""
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.fbx(filepath=str(fbx_path))
    arms = [o for o in bpy.data.objects if o.type == "ARMATURE"]
    if not arms:
        raise RuntimeError(f"No armature found in {fbx_path}")
    fbx_arm = arms[0]
    act = fbx_arm.animation_data.action if fbx_arm.animation_data else None
    if not act:
        raise RuntimeError(f"No action found in {fbx_path}")

    fps = bpy.context.scene.render.fps or 30
    frame_time = 1.0 / float(fps)
    f_start = int(round(act.frame_range[0]))
    f_end = int(round(act.frame_range[1]))

    # Precompute FBX bone rest world matrices & T-pose alignment offsets
    bone_map = {}
    rest_world = {}
    t_to_fbx_rest = {}
    fbx_names = {b.name for b in fbx_arm.data.bones}

    for j_name, _, candidates, align_rest in SKELETON_SPEC:
        match = next((c for c in candidates if c in fbx_names), None)
        if not match:
            continue
        bone_map[j_name] = match
        fb = fbx_arm.data.bones[match]
        rest_world[j_name] = (fbx_arm.matrix_world @ fb.matrix_local).to_3x3().normalized()
        if align_rest and j_name in ref_dirs:
            f_dir = (fbx_arm.matrix_world.to_3x3() @ (fb.tail_local - fb.head_local)).normalized()
            v_dir = ref_dirs[j_name]
            t_to_fbx_rest[j_name] = v_dir.rotation_difference(f_dir).to_matrix()
        else:
            t_to_fbx_rest[j_name] = Matrix.Identity(3)

    hips_fbx_name = bone_map["hips"]
    motion_rows = []
    num_frames = f_end - f_start + 1

    for f in range(f_start, f_end + 1):
        bpy.context.scene.frame_set(f)
        bpy.context.view_layer.update()

        world_delta = {}
        for j_name, parent_name, _, _ in SKELETON_SPEC:
            if j_name not in bone_map:
                world_delta[j_name] = world_delta.get(parent_name, Matrix.Identity(3))
                continue
            pb = fbx_arm.pose.bones[bone_map[j_name]]
            pose_m = (fbx_arm.matrix_world @ pb.matrix).to_3x3().normalized()
            r_anim = pose_m @ rest_world[j_name].transposed()
            world_delta[j_name] = r_anim @ t_to_fbx_rest[j_name]

        # Hips position mapped to CarPi5 BVH Y-up height conventions
        hips_world = fbx_arm.matrix_world @ fbx_arm.pose.bones[hips_fbx_name].head
        if is_ground:
            hips_y_bvh = (hips_world.z - 1.33) * 24.0
        else:
            hips_y_bvh = (hips_world.z - 1.33) * 18.0 + 12.186656
        hips_x_bvh = hips_world.x * 18.0
        hips_z_bvh = -hips_world.y * 18.0

        row = [f"{hips_x_bvh:.5f}", f"{hips_y_bvh:.5f}", f"{hips_z_bvh:.5f}"]
        for j_name, parent_name, _, _ in SKELETON_SPEC:
            r_cur = world_delta[j_name]
            if parent_name:
                r_loc_bl = world_delta[parent_name].transposed() @ r_cur
            else:
                r_loc_bl = r_cur
            r_loc_bvh = BL_TO_BVH @ r_loc_bl @ BL_TO_BVH.transposed()
            # 'Yrotation Xrotation Zrotation' intrinsic == 'ZXY' extrinsic in mathutils
            eul = r_loc_bvh.to_euler("ZXY")
            row.append(f"{math.degrees(eul.y):.4f}")
            row.append(f"{math.degrees(eul.x):.4f}")
            row.append(f"{math.degrees(eul.z):.4f}")
        motion_rows.append(" ".join(row))

    dst_path.parent.mkdir(parents=True, exist_ok=True)
    content = list(hierarchy_lines)
    content.append("MOTION")
    content.append(f"Frames: {num_frames}")
    content.append(f"Frame Time: {frame_time:.6f}")
    content.extend(motion_rows)
    dst_path.write_text("\n".join(content) + "\n", encoding="utf-8")
    return num_frames, fps, dst_path.stat().st_size


def main():
    if not REF_BVH.exists():
        print(f"ERROR: Reference BVH missing: {REF_BVH}")
        sys.exit(1)

    ref_dirs, ref_offsets = load_reference_vrm_pose()
    hierarchy_lines = build_hierarchy_lines(ref_offsets)

    converted = 0
    for src_dir, src_name, dst_dir, dst_name, is_ground in CONVERSION_JOBS:
        src_path = DOWNLOADS_DIR / src_dir / src_name
        dst_path = OUT_ROOT / dst_dir / dst_name
        if not src_path.exists():
            print(f"[SKIP] Missing: {src_path}")
            continue
        frames, fps, sz = convert_single_fbx(src_path, dst_path, is_ground, ref_dirs, hierarchy_lines)
        converted += 1
        print(f"[OK] {src_name:28s} -> {dst_dir}/{dst_name:30s} ({frames}f @ {fps}fps, {sz / 1024:.1f} KB)")

    print(f"\nConverted {converted}/{len(CONVERSION_JOBS)} FBX animations cleanly.")


if __name__ == "__main__":
    main()
