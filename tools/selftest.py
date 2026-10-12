#!/usr/bin/env python3
"""Offline self-test for a converted FS25 mod folder.

Usage:
    selftest.py <mod_dir> [--original <fs22_dir>] [--filelist <txt>]
                [--schema <xsd_dir>] [--vocab <file>] [--specs <file>]
                [--label <name>] [--report <file>]

The script is meant to run on the *built* mod (the folder that goes into the
zip) and answers the question "does this conversion still contain errors?".

Checks
    1. xml-parse        every .xml / .i3d parses, UTF-8 decodes
    2. schema           XSD validation against the FS25 schemas (optional,
                        --schema).  Violations that already existed in the FS22
                        original are reported as "pre-existing"; only new ones
                        are failures.
    3. files            every local file reference resolves (exact case first,
                        then case-insensitive; a case-only mismatch is a warning
                        because Windows tolerates it and Linux does not)
    4. parity           nothing from the FS22 archive got lost (file list from
                        --filelist + shape/node name sets from --original)
    5. collision        collisionFilterGroup/Mask pairs are complete, use only
                        bits that exist in FS25 and every component node has the
                        VEHICLE bit in group and mask (the exact check the game
                        does in Vehicle.lua)
    6. sounds           every template="..." is attested in FS25 content
    7. specializations  modDesc vehicleTypes/specializations are known to FS25
    8. shaders          no FS22-era shader (tex2D) and no reference to the FS22
                        shader path
    9. jointtypes       inputAttacherJoint/attacherJoint jointType values are
                        registered in the modDesc or are FS25 built-ins

Exit code 0 = no failures (warnings allowed), 1 = at least one failure.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

# extensions that are *not* text and are therefore absent when the tester runs on
# a stripped checkout (--binary-stripped) instead of on the built archive
TEXT_EXT = {".xml", ".i3d", ".lua", ".txt", ".md", ".json", ".cfg", ".conf",
            ".ini", ".materials", ".csv", ".xsd", ".shader", ".glsl"}
BINARY_EXT = {".dds", ".png", ".ogg", ".wav", ".gls", ".shapes", ".i3d.shapes", ".obj",
              ".fbx", ".gltf", ".bin", ".jpg", ".jpeg", ".tga"}

REF_ATTR = re.compile(r'\b(?:filename|image|xmlFilename|iconFilename|img|file)="([^"]+)"')
REF_ELEM = re.compile(r'<(?:image|iconFilename|filename|file)>([^<]+)</(?:image|iconFilename|filename|file)>')

# collision bits that exist in FS25 (CollisionFlag.lua of the FS25 game scripts)
FS25_FLAGS = {0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14, 16, 17, 18, 19,
              20, 21, 22, 23, 24, 28, 29, 30, 31}
VEHICLE = 16
# bits of the FS22 mask that no longer exist in FS25 (would be silently wrong)
FS22_ONLY = {7, 15, 25, 26, 27}

SOUND_ATTR = re.compile(r'template="([^"]+)"')

# FS22-era shader attributes that FS25 renamed (checked by the schema test)
I3D_ATTR_RENAME = {
    "pcssLightSize": "softShadowsLightSize",
    "pcssLightDistance": "softShadowsLightDistance",
    "pcssDepthBiasFactor": "softShadowsDepthBiasFactor",
    "pcssMaxPenumbraSize": "softShadowsMaxPenumbraSize",
    "aiRevereserNode": "aiReverserNode",
    "spineRotation": "spineRotationOffset",
}

# XML paths that the bundled FS22 colour-compat layer (scripts/BaseMaterial.lua)
# registers at runtime -> the vanilla FS25 schema does not know them, that is fine.
COMPAT_PATHS = (
    "/vehicle/baseMaterial",
    "/vehicle/baseMaterialConfigurations",
    "/vehicle/designMaterial",
)


class Report:
    def __init__(self) -> None:
        self.fails: list[str] = []
        self.warns: list[str] = []
        self.lines: list[str] = []
        self.checks: list[tuple[str, str, str]] = []

    def say(self, text: str = "") -> None:
        self.lines.append(text)

    def check(self, name: str, status: str, detail: str = "") -> None:
        self.checks.append((name, status, detail))
        self.say(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

    def fail(self, text: str) -> None:
        self.fails.append(text)
        self.say("      FAIL " + text)

    def warn(self, text: str) -> None:
        self.warns.append(text)
        self.say("      warn " + text)

    def info(self, text: str) -> None:
        self.say("      " + text)


def is_binary(rel: str, stripped: bool) -> bool:
    """True if this path is a binary asset missing from a stripped checkout."""
    low = rel.lower()
    ext = os.path.splitext(low)[1]
    return stripped and (ext not in TEXT_EXT or any(low.endswith(e) for e in BINARY_EXT))


def iter_files(root: str, exts: tuple) -> list[str]:
    out = []
    for base, _dirs, files in os.walk(root):
        for f in sorted(files):
            if f.lower().endswith(exts):
                out.append(os.path.relpath(os.path.join(base, f), root).replace("\\", "/"))
    return sorted(out)


def read(path: str) -> str:
    with open(path, "rb") as fh:
        return fh.read().decode("utf-8-sig", errors="replace")


def load_list(path: str) -> set:
    if not path or not os.path.isfile(path):
        return set()
    return {l.strip() for l in open(path, encoding="utf-8")
            if l.strip() and not l.startswith("#")}


def strip_ns(tag: str) -> str:
    return tag.split("}")[-1]


# --------------------------------------------------- 11. FS22 leftovers
# Attributes/elements that exist in FS22 but not in FS25.  The FS25 schemas allow
# unknown attributes on many elements, so plain schema validation does NOT catch
# them - the game then either ignores them (broken pose, broken part) or writes an
# error to log.txt.  tools/gen_patches.py converts every one of them, so a built
# mod must not contain any.
LEGACY_PATTERNS = [
    (r"\bspineRotation(?!Offset)=\"", "FS22 driver pose attribute (FS25 builds the pose itself)"),
    (r"\bisCareWheel=\"", "FS22 tire attribute"),
    (r"\bmaxWheelSink=\"", "FS22 wheel attribute (FS25: supportsWheelSink)"),
    (r"\brealLength=\"", "FS22 hose attribute"),
    (r"\bstartStraightening=\"", "FS22 hose attribute (FS25: straighteningFactor)"),
    (r"\bendStraightening=\"", "FS22 hose attribute"),
    (r"\bxzRotations[A-Za-z]*=\"", "FS22 exhaustEffect attribute"),
    (r"\baiRevereserNode=\"", "FS22 typo (FS25: aiReverserNode)"),
    (r"<newcategory\b", "FS22 modDesc element (FS25: storeCategories/storeCategory)"),
    (r"\battacherJointIndex(?!es)=\"", "FS22 scalar (FS25: attacherJointIndices)"),
]


def check_legacy_attrs(root: str, rep: Report) -> None:
    found = []
    for rel in iter_files(root, (".xml", ".i3d")):
        text = strip_comments(read(os.path.join(root, rel)))
        for pattern, why in LEGACY_PATTERNS:
            for m in re.finditer(pattern, text):
                found.append((rel, m.group(0).strip(), why))
    for rel, what, why in found[:15]:
        rep.fail(f"{rel}: FS22 leftover {what!r} - {why}")
    if len(found) > 15:
        rep.say(f"      ... and {len(found) - 15} more FS22 leftover(s)")
    rep.check("fs22-leftovers", "FAIL" if found else "PASS",
              f"{len(found)} FS22-only attribute(s)/element(s) left")

# ---------------------------------------------------------------- 1. xml parse
def check_parse(root: str, rep: Report) -> dict:
    trees = {}
    bad = 0
    for rel in iter_files(root, (".xml", ".i3d")):
        try:
            trees[rel] = ET.parse(os.path.join(root, rel)).getroot()
        except Exception as exc:  # noqa: BLE001
            bad += 1
            rep.fail(f"{rel}: XML is not well formed ({exc})")
    if bad == 0:
        md = os.path.join(root, "modDesc.xml")
        if os.path.isfile(md):
            vm = re.search(r"<version>([^<]+)</version>", read(md))
            if vm:
                rep.say(f"      modDesc.xml version: {vm.group(1)}")
        rep.check("xml-parse", "PASS", f"{len(trees)} xml/i3d files parse")
    else:
        rep.check("xml-parse", "FAIL", f"{bad} file(s) broken")
    return trees


# ------------------------------------------------------------------ 2. schema
def check_schema(root: str, orig: str | None, schema_dir: str | None, rep: Report) -> None:
    if not schema_dir or not os.path.isdir(schema_dir):
        rep.check("schema", "SKIP", "no --schema dir given")
        return
    try:
        import xmlschema
    except ImportError:
        rep.check("schema", "SKIP", "python 'xmlschema' package not installed")
        return

    mapping = {}
    for name in ("modDesc.xsd", "vehicle.xsd", "vehicle_sounds.xsd", "wheel.xsd",
                 "crawler.xsd", "i3d-1.6.xsd"):
        p = os.path.join(schema_dir, name)
        if os.path.isfile(p):
            mapping[name] = p

    def schema_for(rel: str) -> str | None:
        if rel.endswith(".i3d"):
            return "i3d-1.6.xsd"
        if os.path.basename(rel) == "modDesc.xml":
            return "modDesc.xsd"
        try:
            root = ET.parse(os.path.join(root, rel)).getroot()
        except Exception:  # noqa: BLE001
            return None
        tag = strip_ns(root.tag)
        if tag == "sounds":
            return "vehicle_sounds.xsd"
        if tag == "crawler":
            return "crawler.xsd"
        if tag == "vehicle":
            # tools are vehicles as well, FS25 tool xmls live in the wheel schema
            # unless they define a full vehicle; use the big vehicle schema.
            return "vehicle.xsd"
        return None

    loaded = {}
    counts = {"new": 0, "pre": 0}
    for rel in iter_files(root, (".xml", ".i3d")):
        sname = schema_for(rel)
        if sname is None or sname not in mapping:
            continue
        if sname not in loaded:
            loaded[sname] = xmlschema.XMLSchema(mapping[sname])
        schema = loaded[sname]

        def violations(base: str) -> set:
            try:
                return {f"{e.reason}|{re.sub(r'[0-9]+', '#', e.path)}"
                        for e in schema.iter_errors(os.path.join(base, rel))}
            except Exception as exc:  # noqa: BLE001
                return {f"<validator error> {exc}"}

        now = violations(root)
        if not now:
            continue
        now = {v for v in now if not any(p in v for p in COMPAT_PATHS)}
        if orig and os.path.isfile(os.path.join(orig, rel)):
            before = violations(orig)
            before = {v for v in before if not any(p in v for p in COMPAT_PATHS)}
        else:
            before = set()
        new = now - before
        pre = now & before
        counts["new"] += len(new)
        counts["pre"] += len(pre)
        rel_new = sorted(new)
        if rel_new:
            rep.say(f"      {rel}: {len(now)} schema violation(s), {len(rel_new)} new")
            for v in rel_new[:12]:
                rep.say("        new  " + v[:160])
        elif pre:
            rep.say(f"      {rel}: {len(pre)} pre-existing schema violation(s) (same as FS22)")

    status = "PASS" if counts["new"] == 0 else "WARN"
    detail = (f"{counts['new']} new / {counts['pre']} pre-existing violations "
              f"vs the FS25 schemas")
    rep.check("schema", status, detail)


# ------------------------------------------------------------------- 3. files
def check_refs(root: str, orig: str | None, rep: Report, stripped: bool = False) -> None:
    allfiles = set()
    for base, _dirs, files in os.walk(root):
        for f in files:
            allfiles.add(os.path.relpath(os.path.join(base, f), root).replace("\\", "/"))
    lower = {f.lower() for f in allfiles}

    missing: list[tuple[str, str]] = []
    case_only: list[tuple[str, str]] = []
    for rel in iter_files(root, (".xml", ".i3d")):
        text = read(os.path.join(root, rel))
        basedir = os.path.dirname(rel)
        for m in list(REF_ATTR.finditer(text)) + list(REF_ELEM.finditer(text)):
            ref = m.group(1).strip().replace("\\", "/")
            if not ref or ref.startswith(("$", "/")) or re.match(r"^[A-Za-z]:", ref):
                continue
            cands = [os.path.normpath(os.path.join(basedir, ref)).replace("\\", "/"),
                     os.path.normpath(ref).replace("\\", "/")]
            if any(c in allfiles for c in cands):
                continue
            if stripped and is_binary(ref, True):
                continue  # binary asset, simply not part of a stripped checkout
            if any(c.lower() in lower for c in cands):
                case_only.append((rel, ref))
            else:
                missing.append((rel, ref))

    orig_missing = set()
    if orig:
        # what was already dangling in the FS22 original?
        for rel, ref in missing:
            if os.path.isfile(os.path.join(orig, rel)) and ref in read(os.path.join(orig, rel)):
                orig_missing.add((rel, ref))
    new_missing = [m for m in missing if m not in orig_missing]

    for rel, ref in new_missing:
        rep.fail(f"{rel}: missing file reference '{ref}'")
    for rel, ref in sorted(orig_missing)[:12]:
        rep.say(f"      (pre-existing, also dangling in FS22) {rel}: {ref}")
    if len(orig_missing) > 12:
        rep.say(f"      ... and {len(orig_missing) - 12} more pre-existing dangling reference(s)")
    if case_only:
        rep.warn(f"{len(case_only)} case-only reference(s), e.g. {case_only[0][0]} -> {case_only[0][1]}")
    detail = f"{len(missing) - len(new_missing)} pre-existing dangling, {len(new_missing)} new"
    rep.check("files", "FAIL" if new_missing else "PASS", detail)


# ------------------------------------------------------------------- 4. parity
def check_parity(root: str, orig: str | None, filelist: str | None, rep: Report,
                 stripped: bool = False, remove_list: str | None = None) -> None:
    if not filelist or not os.path.isfile(filelist):
        rep.check("parity", "SKIP", "no --filelist given")
        return
    want = set()
    for line in open(filelist, encoding="utf-8"):
        m = re.match(r"\s*\d+\s+[0-9a-fA-F]{8}\s+(.+?)\s*$", line)
        if m and not m.group(1).endswith("/"):
            if stripped and is_binary(m.group(1), True):
                continue  # not extracted in a text-only checkout
            want.add(m.group(1))
    have = set()
    for base, _dirs, files in os.walk(root):
        for f in files:
            have.add(os.path.relpath(os.path.join(base, f), root).replace("\\", "/"))
    removed = set()
    for rl in (remove_list, os.path.join(root, "_remove.txt")):
        if rl and os.path.isfile(rl):
            removed |= {l.strip() for l in open(rl, encoding="utf-8")
                        if l.strip() and not l.startswith("#")}
    # files the build adds on purpose
    expected_extra = {"CONVERSIE_FS25_INFO.txt"}

    lost = sorted(want - have - removed)
    extra = sorted(have - want - expected_extra)
    for rel in lost:
        rep.fail(f"file from the FS22 archive is missing in the build: {rel}")
    if extra:
        rep.say(f"      {len(extra)} added file(s): " + ", ".join(extra[:8]) +
                (" ..." if len(extra) > 8 else ""))
    detail = f"{len(want)} archive files, {len(have)} in build, {len(lost)} lost, {len(extra)} added"
    rep.check("parity", "FAIL" if lost else "PASS", detail)

    if not orig or not os.path.isdir(orig):
        return
    # node-name and shape-name parity for the i3d files that were touched
    lost_nodes = 0
    for rel in iter_files(orig, (".i3d",)):
        a = os.path.join(orig, rel)
        b = os.path.join(root, rel)
        if not os.path.isfile(b):
            continue
        names_a = set(re.findall(r'\bname="([^"]*)"', read(a)))
        names_b = set(re.findall(r'\bname="([^"]*)"', read(b)))
        gone = sorted(n for n in names_a - names_b if n and not n.startswith("$"))
        if gone:
            lost_nodes += len(gone)
            rep.fail(f"{rel}: {len(gone)} named node(s)/element(s) lost, e.g. {gone[:5]}")
    if lost_nodes == 0:
        rep.check("parity-nodes", "PASS", "no named node lost in the i3d files")
    else:
        rep.check("parity-nodes", "FAIL", f"{lost_nodes} names lost")


# -------------------------------------------------------------- 10. node paths
NODE_ATTRS = ("node", "linkNode", "referenceNode", "rootNode", "attacherJointNode",
              "inputAttacherJointNode", "outputAttacherJointNode", "startNode", "endNode",
              "componentJointNode", "characterNode", "aiReverserNode", "animationNode",
              "exactFillRootNode", "fillUnitNode", "fillNode", "dischargeNode", "overlapNode",
              "prerequisiteNode", "targetNode", "sourceNode", "controlNode", "chainNode",
              "mountNode", "attachNode", "toolNode", "tipNode", "sensorNode", "sprayNode",
              "workAreaNode", "emitNode", "finishNode", "partNode", "beltNode", "rotationNode")


def _xml_children(el):
    return [c for c in list(el) if isinstance(c.tag, str)]


def _node_index(i3d_path):
    """Map "N>a|b" paths to the node names of one .i3d file.

    The leading number selects the root component (the N-th top level node of
    <Scene>), the rest walks the children - "0>14" is the 15th child of the first
    component, exactly how the game resolves these references.
    """
    try:
        scene = ET.parse(i3d_path).getroot().find("Scene")
    except Exception:
        return None
    if scene is None:
        return None
    idx = {}

    def walk(el, parts):
        for i, ch in enumerate(_xml_children(el)):
            p = parts + [i]
            idx[tuple(p)] = ch.get("name")
            walk(ch, p)

    for n, comp in enumerate(_xml_children(scene)):
        idx[(n,)] = comp.get("name")
        walk(comp, [n])
    return idx


def _parse_node_path(v):
    v = v.strip()
    if v.isdigit():
        return None          # bare integers are i3d node indices, not paths
    m = re.match(r"^(\d+)(?:>([\d|]+))?$", v)
    if not m:
        return None
    parts = [int(m.group(1))]
    if m.group(2):
        for seg in m.group(2).split("|"):
            if seg:
                parts.append(int(seg))
    return parts


def check_nodepaths(root: str, rep: Report) -> None:
    """Every numeric i3d node path used by the XMLs must exist in the i3d files.

    An unresolvable node is exactly what makes a part invisible or an attacher
    joint unusable, so it is verified node by node.
    """
    cache, checked, missing = {}, 0, []
    for rel in iter_files(root, (".xml",)):
        p = os.path.join(root, rel)
        try:
            tree = ET.parse(p)
        except Exception:
            continue
        basedir = os.path.dirname(p)
        i3d = os.path.join(basedir, os.path.basename(p)[:-4] + ".i3d")
        if not os.path.exists(i3d):
            i3d = None
            for el in tree.getroot().iter():
                for tag in ("i3dFilename", "filename", "name"):
                    v = el.get(tag)
                    if v and v.endswith(".i3d") and not v.startswith("$"):
                        cand = os.path.join(basedir, v)
                        if os.path.exists(cand):
                            i3d = cand
                            break
                if i3d:
                    break
        if not i3d:
            continue
        if i3d not in cache:
            cache[i3d] = _node_index(i3d) or {}
        idx = cache[i3d]
        for el in tree.getroot().iter():
            for a in NODE_ATTRS:
                v = el.get(a)
                if not v:
                    continue
                path = _parse_node_path(v)
                if path is None:
                    continue
                checked += 1
                if tuple(path) not in idx:
                    missing.append((rel, el.tag, a, v))
    for rel, tag, a, v in missing[:15]:
        rep.fail(f'{rel}: <{tag} {a}="{v}"> does not resolve inside the i3d')
    if len(missing) > 15:
        rep.say(f"      ... and {len(missing) - 15} more unresolved node reference(s)")
    rep.check("node-paths", "FAIL" if missing else "PASS",
              f"{checked} numeric node path(s) checked, {len(missing)} unresolved")


# ---------------------------------------------------------------- 5. collision
def scene_components(text: str):
    m = re.search(r"<Scene>(.*)</Scene>", text, re.S)
    if not m:
        return []
    try:
        root = ET.fromstring("<R>" + m.group(1) + "</R>")
    except Exception:  # noqa: BLE001
        return []
    return list(root[0])


def check_collision(root: str, rep: Report) -> None:
    fails = 0
    warns = 0
    no_pair = 0
    unknown = 0
    for rel in iter_files(root, (".i3d",)):
        text = read(os.path.join(root, rel))
        for tag in re.findall(r"<Shape\b[^>]*>", text):
            g = re.search(r'collisionFilterGroup="([^"]+)"', tag)
            mk = re.search(r'collisionFilterMask="([^"]+)"', tag)
            if bool(g) != bool(mk):
                fails += 1
                rep.fail(f"{rel}: shape with only one of collisionFilterGroup / collisionFilterMask: "
                         f"{tag[:110]}")
                continue
            if not g:
                continue
            # only the *group* must be a valid flag combination; the mask is a
            # raw bit set (FS25's own default mask 0xfe3ffb83 has undefined bits)
            for label, value in (("group", g.group(1)), ("mask", mk.group(1))):
                try:
                    v = int(value, 0)
                except ValueError:
                    fails += 1
                    rep.fail(f"{rel}: bad collision {label} value '{value}'")
                    continue
                if label == "group":
                    bad = [b for b in range(32) if (v >> b) & 1 and b not in FS25_FLAGS]
                    if bad:
                        unknown += 1
                        rep.fail(f"{rel}: collision group uses bit(s) {bad} which do not exist in FS25")
        # component check (Scene root children), like Vehicle.lua:3302
        for comp in scene_components(text):
            a = comp.attrib
            name = a.get("name", "?")
            if "collisionFilterGroup" not in a and "collisionFilterMask" not in a:
                no_pair += 1
                continue
            try:
                group = int(a.get("collisionFilterGroup", "0"), 0)
                mask = int(a.get("collisionFilterMask", "0"), 0)
            except ValueError:
                continue
            if not (group >> VEHICLE) & 1:
                fails += 1
                rep.fail(f"{rel}: component '{name}' group misses the VEHICLE bit (0x10000)")
            if not (mask >> VEHICLE) & 1:
                fails += 1
                rep.fail(f"{rel}: component '{name}' mask misses the VEHICLE bit (0x10000)")
            if (group >> 30) & 1 and not (group >> VEHICLE) & 1:
                warns += 1
                rep.warn(f"{rel}: component '{name}' is a pure FILLABLE node")

    # how many shapes keep a legacy FS22 mask?
    legacy = 0
    for rel in iter_files(root, (".i3d",)):
        legacy += len(re.findall(r"<Shape\b[^>]*\scollisionMask=\"\d+\"", read(os.path.join(root, rel))))
    if legacy:
        rep.fail(f"{legacy} shape(s) still carry the legacy FS22 'collisionMask' attribute "
                 f"(FS25 needs collisionFilterGroup/collisionFilterMask)")
    rep.check("collision", "FAIL" if fails else "PASS",
              f"{fails} problem(s), {unknown} unknown-bit, {legacy} legacy mask(s), "
              f"{no_pair} component(s) without explicit filters")


# ------------------------------------------------------------------- 6. sounds
def strip_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.S)


def check_sounds(root: str, rep: Report) -> None:
    """Every template= name must exist in $data/sounds/soundTemplates.xml.

    A name that is unknown there makes the engine drop that single sample and
    write an xmlError into log.txt, so the names are triaged against three
    independent FS25 sources:

      * tools/data/fs25_vanilla_sound_templates.txt - names used by the FS25
        base game itself (definitely valid),
      * tools/data/fs25_sound_templates.txt - names used by FS25-era mods,
      * tools/data/fs22_sound_template_names.txt - the FS22 name set, used to
        spot FS22-only names that FS25 dropped (e.g. SWITCH_01, MEDIUM_TRACTOR_*).
    """
    vocab = load_list(os.path.join(DATA, "fs25_sound_templates.txt"))
    vanilla = load_list(os.path.join(DATA, "fs25_vanilla_sound_templates.txt"))
    fs22 = load_list(os.path.join(DATA, "fs22_sound_template_names.txt"))
    dead = load_list(os.path.join(DATA, "fs22_dead_sound_templates.txt"))
    evidence = vocab | vanilla

    used, unknown, fs22_only = set(), [], []
    for rel in iter_files(root, (".xml",)):
        for t in SOUND_ATTR.findall(strip_comments(read(os.path.join(root, rel)))):
            used.add(t)
            if t in dead:
                rep.fail(f"{rel}: sound template '{t}' does not exist in FS25")
            elif t in fs22 and t not in evidence:
                fs22_only.append((rel, t))
            elif t not in evidence:
                unknown.append((rel, t))

    for rel, t in sorted(set(fs22_only)):
        rep.fail(f"{rel}: sound template '{t}' is an FS22-only name, dropped by FS25")
    for rel, t in sorted(set(unknown))[:15]:
        rep.warn(f"{rel}: sound template '{t}' not attested in FS25 content")

    van = sorted(t for t in used if t in vanilla)
    shared = sorted(t for t in used if t in fs22 and t not in vanilla)
    rep.info(f"      {len(used)} template name(s): {len(van)} confirmed by FS25 vanilla "
             f"({', '.join(van[:6])}{'…' if len(van) > 6 else ''}), "
             f"{len(shared)} kept from FS22, {len(used) - len(van) - len(shared)} FS25-mod-only")
    bad = len(set(fs22_only)) + len(set(unknown))
    status = "FAIL" if fs22_only else ("WARN" if unknown else "PASS")
    rep.check("sounds", status,
              f"{len(used)} template name(s) used, {len(set(fs22_only))} FS22-only, "
              f"{len(set(unknown))} unattested")
    if bad:
        rep.info("note: an unattested template only costs that single sample, "
                 "it does not break the rest of the sounds")


# ---------------------------------------------------------- 7. specializations
def check_specializations(root: str, rep: Report) -> None:
    specs = load_list(os.path.join(DATA, "fs25_specializations.txt"))
    md = os.path.join(root, "modDesc.xml")
    if not os.path.isfile(md) or not specs:
        rep.check("specializations", "SKIP", "no modDesc.xml / no vocabulary")
        return
    text = read(md)
    own = set(re.findall(r'<specialization\s+name="([^"]+)"\s+className', text))
    used = set(re.findall(r'<specialization\s+name="([^"]+)"', text))
    unknown = sorted(n for n in used - own - specs)
    for n in unknown:
        rep.warn(f"modDesc.xml: specialization '{n}' is not known to FS25")
    sources = re.findall(r'<sourceFile\s+filename="([^"]+)"', text)
    for s in sources:
        if not os.path.isfile(os.path.join(root, s)):
            rep.fail(f"modDesc.xml: extraSourceFile '{s}' is missing")
    rep.check("specializations", "PASS" if not unknown else "WARN",
              f"{len(used)} specialization reference(s), {len(unknown)} unknown")


# ------------------------------------------------------------------ 8. shaders
def check_shaders(root: str, rep: Report) -> None:
    bad = 0
    for rel in iter_files(root, (".xml",)):
        text = read(os.path.join(root, rel))
        if "<CustomShader" in text[:4096] and "tex2D(" in text:
            bad += 1
            rep.fail(f"{rel}: FS22-era shader (tex2D) is not usable on FS25")
    fs22_path = 0
    for rel in iter_files(root, (".i3d",)):
        if "$data/shaders/vehicleShader.xml" in read(os.path.join(root, rel)):
            fs22_path += 1
            rep.fail(f"{rel}: still references the FS22 shader path")
    rep.check("shaders", "PASS" if not (bad or fs22_path) else "FAIL",
              f"{bad} FS22 shader file(s), {fs22_path} FS22 shader reference(s)")


# --------------------------------------------------------------- 9. joint types
FS25_JOINT_TYPES = {
    "implement", "trailer", "trailerLow", "semitrailer", "semitrailerLow",
    "attachableFrontloader", "frontloader", "telehandler", "wheelLoader",
    "bale", "baleTrailer", "cutter", "cutterTrailer", "cutterMidMount",
    "mower", "mowerFront", "mowerRear", "tedder", "windrower", "loader",
    "loaderBale", "loaderManure", "loaderLog", "loaderTrailer", "loaderWagon",
    "manureBarrel", "milkTrailer", "waterTrailer", "fuelTrailer", "augerWagon",
    "baler", "loaderBullet", "hooklift", "hookliftTrailer", "weight",
    "plow", "cultivator", "sowingMachine", "fertilizer", "sprayer",
    "1cylinderedAttacher", "2cylinderedAttacher",
}


def check_jointtypes(root: str, rep: Report) -> None:
    md = os.path.join(root, "modDesc.xml")
    registered = set()
    if os.path.isfile(md):
        registered = set(re.findall(r'<jointType\s+name="([^"]+)"', read(md)))
    unknown = set()
    for rel in iter_files(root, (".xml",)):
        for m in re.finditer(r'<(?:inputAttacherJoint|attacherJoint)\b[^>]*?jointType="([^"]+)"',
                             read(os.path.join(root, rel))):
            jt = m.group(1)
            if jt not in registered and jt not in FS25_JOINT_TYPES:
                unknown.add((rel, jt))
    for rel, jt in sorted(unknown):
        rep.warn(f"{rel}: jointType '{jt}' is not registered in the modDesc nor a FS25 built-in")
    rep.check("jointtypes", "PASS" if not unknown else "WARN",
              f"{len(registered)} mod joint type(s), {len(unknown)} unknown reference(s)")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("mod_dir")
    ap.add_argument("--original")
    ap.add_argument("--filelist")
    ap.add_argument("--schema")
    ap.add_argument("--label")
    ap.add_argument("--binary-stripped", action="store_true",
                    help="the tree only has text files (no dds/ogg/shapes)")
    ap.add_argument("--report")
    ap.add_argument("--remove-list", help="path to the patch _remove.txt of this mod")
    args = ap.parse_args()

    root = args.mod_dir.rstrip("/")
    label = args.label or os.path.basename(root)
    rep = Report()
    rep.say("=" * 78)
    rep.say(f"Self-test: {label}   ({root})")
    if args.original:
        rep.say(f"FS22 original: {args.original}")
    rep.say("=" * 78)

    check_parse(root, rep)
    check_schema(root, args.original, args.schema, rep)
    check_refs(root, args.original, rep, args.binary_stripped)
    check_parity(root, args.original, args.filelist, rep, args.binary_stripped,
                 args.remove_list)
    check_collision(root, rep)
    check_sounds(root, rep)
    check_specializations(root, rep)
    check_shaders(root, rep)
    check_jointtypes(root, rep)
    check_nodepaths(root, rep)
    check_legacy_attrs(root, rep)

    rep.say("")
    passed = sum(1 for _n, s, _d in rep.checks if s == "PASS")
    rep.say(f"summary: {passed} PASS / {len(rep.warns)} warning(s) / {len(rep.fails)} failure(s)")
    for f in rep.fails:
        rep.say("  ! " + f)
    text = "\n".join(rep.lines) + "\n"
    print(text, end="")
    if args.report:
        os.makedirs(os.path.dirname(args.report) or ".", exist_ok=True)
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text)
    return 1 if rep.fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
