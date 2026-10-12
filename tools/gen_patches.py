import os, re, shutil, sys
ROOT='transfer/original'; OUT='transfer/patched'
FIX='transfer/reference/extracted/FS25_ref_FS22ShaderColorFix_v1.2'
CREDIT='-- FS22 shader-color compatibility layer for FS25 (baseMaterial/designMaterial + colorMat*).\n-- Original: "FS22 Shader Color Fix" by Average Enjoyer / Lampovo Project (bundled with permission note; credit kept).\n'

def read(p, enc='utf-8-sig'):
    return open(p, encoding=enc, errors='replace').read()

def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p,'w',encoding='utf-8',newline='').write(s)


def bump_version(s, old, new):
    """Increment the mod version so the fixed build is recognisable in game."""
    return s.replace('<version>%s</version>' % old, '<version>%s</version>' % new)

def transform_moddesc(s, extra_sources, drop_cat=False):
    s = re.sub(r'descVersion="\d+"', 'descVersion="104"', s, count=1)
    # drop moreDesignConfigs specializations
    s = re.sub(r'\s*<specializations>.*?</specializations>\s*', '\n', s, flags=re.S)
    s = re.sub(r'[ \t]*<specialization name="moreDesignConfigs"\s*/>\r?\n', '', s)
    if drop_cat:
        s = re.sub(r'\s*<extraSourceFiles>.*?</extraSourceFiles>\s*', '\n', s, flags=re.S)
        s = re.sub(r'\s*<newcategory[^>]*/>', '', s)
    # register extra source files (rebuild the block: no duplicates)
    s = re.sub(r'\s*<extraSourceFiles>.*?</extraSourceFiles>', '', s, flags=re.S)
    src = ''.join(f'        <sourceFile filename="{f}"/>\n' for f in extra_sources)
    block = f'    <extraSourceFiles>\n{src}    </extraSourceFiles>\n'
    m = re.search(r'([ \t]*<multiplayer[^>]*/>\s*\n)', s)
    if m:
        s = s[:m.end()] + block + s[m.end():]
    else:
        s = s.replace('</modDesc>', block + '</modDesc>')
    return s

# DT pack: keep categorizer (rewritten), add BaseMaterial compat
s = read(f'{ROOT}/FS22_DT_Pack/modDesc.xml')
s = transform_moddesc(s, ['scripts/categorizer.lua', 'scripts/BaseMaterial.lua'])
s = bump_version(s, '1.0.0.2', '1.0.0.4')
s = s.replace('<category>vgtz</category>', '<category>DT_PACK</category>')
write(f'{OUT}/FS22_DT_Pack/modDesc.xml', s)

# T150
s = read(f'{ROOT}/FS22_T150_Gus/modDesc.xml')
s = transform_moddesc(s, ['scripts/BaseMaterial.lua'])
s = bump_version(s, '1.0.0.0', '1.0.0.2')
write(f'{OUT}/FS22_T150_Gus/modDesc.xml', s)

# --- categorizer rewrite (FS25: categoryTypeName is a string) ---
cat = '''-- Custom store category for the DT pack (FS25 port of Dajoor's categorizer).
Categorizer = {}
Categorizer.modFolder = g_currentModDirectory
Categorizer.modDescFile = Categorizer.modFolder .. "modDesc.xml"

local function registerCategories()
    if not fileExists(Categorizer.modDescFile) then
        g_logManager:xmlWarning(Categorizer.modDescFile, "*** Categorizer: no modDesc found!")
        return
    end
    local modDescFile = loadXMLFile("modDesc", Categorizer.modDescFile)
    local i = 0
    while i < 10 do
        local ndx = string.format("modDesc.storeCategories.storeCategory(%d)", i)
        if not hasXMLProperty(modDescFile, ndx) then break end
        local name = getXMLString(modDescFile, ndx .. "#name")
        if name == nil or name == "" then break end
        name = name:upper()
        if g_storeManager:getCategoryByName(name) == nil then
            local title = getXMLString(modDescFile, ndx .. "#title")
            if title == nil or title == "" then title = name end
            title = g_i18n:hasText(title) and g_i18n:getText(title) or title:upper()
            local cattype = getXMLString(modDescFile, ndx .. "#type")
            if cattype == nil or cattype == "" then cattype = "VEHICLE" end
            cattype = cattype:upper()
            local img = getXMLString(modDescFile, ndx .. "#image")
            if img == nil or img == "" then img = getXMLString(modDescFile, ndx .. "#img") end
            local ok, err = pcall(function()
                g_storeManager:addCategory(name, title, img, cattype, Categorizer.modFolder)
            end)
            if not ok then
                g_logManager:xmlWarning(modDescFile, "*** Categorizer: could not add '%s' (%s)", tostring(name), tostring(err))
            end
        end
        i = i + 1
    end
    delete(modDescFile)
end

local function onMissionLoaded()
    registerCategories()
end

g_messageCenter:subscribe(MessageType.MISSION_LOADED, onMissionLoaded)
'''
write(f'{OUT}/FS22_DT_Pack/scripts/categorizer.lua', cat)

# --- bundling of the paint compat layer ---
lua = read(f'{FIX}/src/BaseMaterial.lua', enc='utf-8')
lua = lua.replace('\r\n', '\n')
# guard: the layer is bundled in BOTH mods (and may also be installed as a
# standalone mod) -> register each configuration type only once.
lua = lua.replace('''local function inj_vehicle_init()
    g_vehicleConfigurationManager:addConfigurationType(\"baseMaterial\", g_i18n:getText(\"configuration_baseColor\"), nil, VehicleConfigurationItemColor)
    g_vehicleConfigurationManager:addConfigurationType(\"designMaterial\", g_i18n:getText(\"configuration_designColor\"), nil, VehicleConfigurationItemColor)
    for i = 2, 64 do
        g_vehicleConfigurationManager:addConfigurationType(string.format(\"designMaterial%d\", i), g_i18n:getText(\"configuration_designColor\"), nil, VehicleConfigurationItemColor)
    end
end''', '''local function piw_addConfigType(name)
    if g_vehicleConfigurationManager:getConfigurationIndexByName(name) == nil then
        g_vehicleConfigurationManager:addConfigurationType(name, g_i18n:getText(\"configuration_designColor\"), nil, VehicleConfigurationItemColor)
    end
end

local function inj_vehicle_init()
    piw_addConfigType(\"baseMaterial\")
    piw_addConfigType(\"designMaterial\")
    for i = 2, 64 do
        piw_addConfigType(string.format(\"designMaterial%d\", i))
    end
end''')
assert 'piw_addConfigType' in lua, 'guard insertion failed'
guarded = ('-- FS22 shader-color compatibility layer for FS25 (baseMaterial/designMaterial + colorMat*).\n'
           '-- Original: \"FS22 Shader Color Fix\" by Average Enjoyer / Lampovo Project (credits kept).\n'
           '-- Loaded once even if both converted mods are installed (or the standalone fix mod is present).\n'
           'if PiwFS22ColorFixLoaded == nil then\n'
           '    PiwFS22ColorFixLoaded = true\n'
           + '\n'.join('    ' + line if line.strip() else line for line in lua.split('\n'))
           + '\nend\n')
write(f'{OUT}/FS22_DT_Pack/scripts/BaseMaterial.lua', guarded)
write(f'{OUT}/FS22_T150_Gus/scripts/BaseMaterial.lua', guarded)
shader = read(f'{FIX}/vehicleShader.xml', enc='utf-8')

def fix_xml(s, in_cfg_re=r'(<\w*Material\w*Configurations?\b[^>]*>)(.*?)(</\w*Material\w*Configurations?>)'):
    # inside *Configurations blocks: <material name="X" -> <material materialSlotName="X"
    def repl(m):
        body = re.sub(r'<material\s+name=', '<material materialSlotName=', m.group(2))
        return m.group(1) + body + m.group(3)
    return re.sub(in_cfg_re, repl, s, flags=re.S)

def convert_xml(src, dst):
    s = read(src)
    n = len(re.findall(r'<material\s+name=', s))
    s = fix_xml(s)
    write(dst, s)
    return n

for stem, xmls in [('FS22_DT_Pack', ['DT_75.xml'] + [os.path.join('tools', f) for f in sorted(os.listdir(f'{ROOT}/FS22_DT_Pack/tools')) if f.endswith('.xml')]),
                   ('FS22_T150_Gus', ['150_gus.xml'])]:
    total = 0
    for rel in xmls:
        src = os.path.join(ROOT, stem, rel)
        if 'MaterialConfigurations' in read(src):
            total += convert_xml(src, os.path.join(OUT, stem, rel))
    print(stem, 'material-name attrs converted:', total)

# --- i3d shader references -> mod-local copy ---
def i3d_fix(stem):
    hits = []
    for dirpath, _, files in os.walk(os.path.join(ROOT, stem)):
        for f in files:
            if not f.endswith('.i3d'):
                continue
            p = os.path.join(dirpath, f)
            s = read(p, enc='utf-8')
            if '$data/shaders/vehicleShader.xml' not in s:
                continue
            rel = os.path.relpath(p, os.path.join(ROOT, stem))
            s = s.replace('$data/shaders/vehicleShader.xml', 'shaders/vehicleShader.xml')
            write(os.path.join(OUT, stem, rel), s)
            d = os.path.dirname(os.path.join(OUT, stem, rel))
            write(os.path.join(d, 'shaders', 'vehicleShader.xml'), shader)
            hits.append(rel)
    return hits

print('DT i3ds:', i3d_fix('FS22_DT_Pack'))
print('T150 i3ds:', i3d_fix('FS22_T150_Gus'))
# T150 already has its own shaders/vehicleShader.xml used by the i3d -> refresh it with the fix version
write(f'{OUT}/FS22_T150_Gus/shaders/vehicleShader.xml', shader)

# --- T150: the kapots/* shader files are FS22-era shaders (tex2D) -> unusable on FS25 ---
# Point every reference at the fixed shader and replace the files with it as well.
KAPOTS_SHADERS = ['kapots/shader/customVehicleShader.xml',
                  'kapots/shaders/vehicleShader.xml',
                  'kapots/tex/shaders/vehicleShader.xml',
                  'kapots/tex1/res/shaders/vehicleShader.xml',
                  'kapots/tex1/shederaa/vehicleShader.xml']
t150_i3d = f'{OUT}/FS22_T150_Gus/150_gus.i3d'
s = read(t150_i3d)
for rel in KAPOTS_SHADERS:
    s = s.replace('filename="%s"' % rel, 'filename="shaders/vehicleShader.xml"')
write(t150_i3d, s)
for rel in KAPOTS_SHADERS:
    write(f'{OUT}/FS22_T150_Gus/{rel}', shader)
print('T150 kapots shaders replaced with the fixed one:', len(KAPOTS_SHADERS))

# --- FS22 -> FS25 attribute renames ------------------------------------------
# FS25 renamed a couple of i3d attributes, the old names are simply ignored:
#   pcssLightSize/LightDistance/DepthBiasFactor/MaxPenumbraSize -> softShadows*
#     (verified: 0 pcss* in 227 FS25 i3ds, softShadows* present in vanilla/mod ones)
#   aiRevereserNode -> aiReverserNode   (typo fixed in FS25, vehicle.xsd)
#   spineRotation   -> spineRotationOffset (enterable/characterNode, vehicle.xsd)
# ...and dropped a few FS22-only attributes which are reported by the FS25
# schema validation:
#   tire#isCareWheel, physics#maxWheelSink (FS25: supportsWheelSink),
#   exhaustEffect#xzRotations*, objectChange#centerOfMass, connectionHoses
#   hose#realLength/startStraightening/endStraightening
I3D_ATTR_RENAME = {
    'pcssLightSize': 'softShadowsLightSize',
    'pcssLightDistance': 'softShadowsLightDistance',
    'pcssDepthBiasFactor': 'softShadowsDepthBiasFactor',
    'pcssMaxPenumbraSize': 'softShadowsMaxPenumbraSize',
    'aiRevereserNode': 'aiReverserNode',
}
# attributes that do not exist in FS25 at all -> remove them (the values were
# either unused engine-side or replaced by a different mechanism)
I3D_ATTR_DROP = ('xzRotationsOffset', 'xzRotationsForward', 'xzRotationsBackward',
                 'xzRotationsLeft', 'xzRotationsRight')


def migrate_i3d_attrs(stem):
    changed = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, stem)):
        for f in sorted(files):
            if not f.endswith('.i3d'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), os.path.join(ROOT, stem)).replace('\\', '/')
            base = layered_read(stem, rel)
            new = base
            hits = 0
            for old, repl in I3D_ATTR_RENAME.items():
                if old not in new:
                    continue
                hits += new.count(old)
                new = new.replace(old, repl)
            for attr in I3D_ATTR_DROP:
                if attr not in new:
                    continue
                hits += len(re.findall('\\s' + attr + '="[^"]*"', new))
                new = re.sub('\\s' + attr + '="[^"]*"', '', new)
            if hits:
                write(os.path.join(OUT, stem, rel), new)
                changed.append((rel, hits))
    return changed


# --- FS25 collision filter migration -----------------------------------------
# FS22 stored a single combined mask in the i3d attribute "collisionMask".
# FS25 replaced it by the pair "collisionFilterGroup" + "collisionFilterMask"
# (see <game>/shared/collisionMaskFlags.xml).  A shape without the pair has no
# valid collision filter in FS25 - the game warns
#   "Missing collision filter mask bit 16 (VEHICLE). Please add this bit to
#    component node '...'"
# and the parts stop interacting with the world/other vehicles.
#
# The FS22 mask is translated by role onto the matching FS25 preset:
#   FS22 bit 13 = VEHICLE                  -> preset VEHICLE
#   FS22 bit 27 = TRIGGER_FORK             -> preset FORK
#   FS22 bit 30 = FILLABLE (exact fill)    -> preset EXACT_FILL_ROOT_NODE
#   FS22 bit 20 = TRIGGER_PLAYER           -> preset PLAYER_TRIGGER
#   FS22 bit 23 = TRIGGER_FILLABLE         -> preset FILL_TRIGGER
FS22_BIT_VEHICLE = 13
FS22_BIT_TRIGGER_PLAYER = 20
FS22_BIT_TRIGGER_FILLABLE = 23
FS22_BIT_TRIGGER_FORK = 27
FS22_BIT_FILLABLE = 30

PAIR_VEHICLE = ('0x10004', '0xfe3ffb83')      # group CAMERA_BLOCKING|VEHICLE
PAIR_FORK = ('0x20000', '0xfe3ffb83')         # group VEHICLE_FORK
PAIR_FILL_ROOT = ('0x40000000', '0x20000000')  # group FILLABLE / mask TRIGGER
PAIR_TRIGGER_PLAYER = ('0x20000000', '0x100000')   # TRIGGER / PLAYER
PAIR_TRIGGER_FILL = ('0x20000000', '0x40000000')   # TRIGGER / FILLABLE


def fs25_collision_pair(mask):
    if mask & (1 << FS22_BIT_TRIGGER_FORK):
        return PAIR_FORK
    if mask & (1 << FS22_BIT_FILLABLE):
        return PAIR_FILL_ROOT
    if mask & (1 << FS22_BIT_TRIGGER_PLAYER):
        return PAIR_TRIGGER_PLAYER
    if mask & (1 << FS22_BIT_TRIGGER_FILLABLE) and not mask & (1 << FS22_BIT_VEHICLE):
        return PAIR_TRIGGER_FILL
    return PAIR_VEHICLE


SHAPE_TAG = re.compile(r'<Shape\s([^>]*?)(/?)>')


def migrate_collision_masks(s):
    hits = []

    def repl(m):
        body = m.group(1)
        cm = re.search(r'collisionMask="(\d+)"', body)
        if cm is None or 'collisionFilterGroup' in body:
            return m.group(0)
        mask = int(cm.group(1))
        group, filter_mask = fs25_collision_pair(mask)
        nm = re.search(r'name="([^"]*)"', body)
        hits.append((nm.group(1) if nm else '?', mask, group, filter_mask))
        new_body = body.replace(cm.group(0),
                                'collisionFilterGroup="%s" collisionFilterMask="%s"' % (group, filter_mask))
        return '<Shape %s%s>' % (new_body, m.group(2))

    return SHAPE_TAG.sub(repl, s), hits


def layered_read(stem, rel):
    """Text of a file as it will end up in the build (patched wins over original)."""
    dst = os.path.join(OUT, stem, rel)
    if os.path.exists(dst):
        return read(dst, enc='utf-8')
    return read(os.path.join(ROOT, stem, rel), enc='utf-8')


def migrate_collisions(stem):
    changed = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, stem)):
        for f in sorted(files):
            if not f.endswith('.i3d'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), os.path.join(ROOT, stem)).replace('\\', '/')
            base = layered_read(stem, rel)
            new, hits = migrate_collision_masks(base)
            if hits:
                write(os.path.join(OUT, stem, rel), new)
                changed.append((rel, hits))
    return changed


# --- FS22 -> FS25 XML attribute fixes -----------------------------------------
# The FS25 xml schema (vehicle.xsd / modDesc.xsd) no longer knows these FS22
# attributes.  Verified replacements (FS25 source of truth in the brackets):
#   tire#isCareWheel             -> removed   (FS25: wheelConfiguration#isCareWheelConfiguration)
#   wheel/physics#maxWheelSink   -> supportsWheelSink="true" (Wheels.lua physics paths)
#   exhaustEffect#xzRotations*   -> removed   (not in the FS25 exhaustEffect type)
#   enterable/characterNode#spineRotation -> #spineRotationOffset (vehicle.xsd)
#   connectionHoses hose#realLength -> removed (FS25 uses #length, which the mod has)
#   hose/target#startStraightening -> #straighteningFactor (FS25 attribute name)
#   hose/target#endStraightening   -> removed
#   cylindered dashboard#attacherJointIndex="1 2 3" -> #attacherJointIndices
#       (FS25 reads a vector of indices; Cylindered.lua / Dashboard registration)
# modDesc:
#   <newcategory .../> (FS22) -> <storeCategories><storeCategory .../></storeCategories>
#       which is the FS25 name (modDesc.xsd).  img= becomes image=.
XML_FIX_SIMPLE = [
    (re.compile(r'\s+xzRotations[A-Za-z]*="[^"]*"'), ''),
    (re.compile(r'\s+isCareWheel="[^"]*"'), ''),
    (re.compile(r'maxWheelSink="[^"]*"'), 'supportsWheelSink="true"'),
    (re.compile(r'\s+realLength="[^"]*"'), ''),
    (re.compile(r'startStraightening="'), 'straighteningFactor="'),
    (re.compile(r'\s+endStraightening="[^"]*"'), ''),
    (re.compile(r'spineRotation="'), 'spineRotationOffset="'),
    (re.compile(r'aiRevereserNode='), 'aiReverserNode='),
    (re.compile(r'attacherJointIndex="([^"]*\s[^"]*)"'), r'attacherJointIndices="\1"'),
]


def fix_fs22_attrs(stem):
    changed = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, stem)):
        for f in sorted(files):
            if not f.endswith('.xml'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), os.path.join(ROOT, stem)).replace('\\', '/')
            base = layered_read(stem, rel)
            new = base
            hits = 0
            for pat, repl in XML_FIX_SIMPLE:
                new, n = pat.subn(repl, new)
                hits += n
            m = re.search(r'<newcategory\s+([^>]*?)/>', new)
            if m:
                attrs = re.sub(r'\bimg=', 'image=', m.group(1)).strip()
                new = new.replace(m.group(0),
                                  '<storeCategories>\n        <storeCategory %s/>\n    </storeCategories>' % attrs)
                hits += 1
            if new != base:
                write(os.path.join(OUT, stem, rel), new)
                changed.append((rel, hits))
    return changed


# --- FS25 sound template migration -------------------------------------------
# FS25 only knows the templates listed in $data/sounds/soundTemplates.xml.
# Every FS22 template name that is gone makes SoundManager drop the whole sample
# ("Sound template 'X' was not found"), and for the indexed 'motor(?)' elements
# even the samples after it -> engine/vehicle silence.
# Replacements below are FS25 template names that occur in FS25 content
# (FS25 mod packs, vanilla vehicles); None means "drop the attribute"
# (FS25 vanilla defines motorStart/motorStop without a template).
SOUND_TEMPLATE_MAP = {
    'MEDIUM_TRACTOR_MOTOR_START': None,
    'MEDIUM_TRACTOR_MOTOR_STOP': None,
    'MEDIUM_TRACTOR_MOTOR_IDLE': 'engineMedium',
    'MEDIUM_TRACTOR_MOTOR_OFFLOAD_RUN': 'engineMedium',
    'MEDIUM_TRACTOR_MOTOR_ONLOAD_RUN': 'engineMedium',
    'WATER_SPLASH_01': 'waterSplash01',
    'SWITCH_TURNLIGHT': 'switchTurnlight',
    'TRUCK_ATTACH_01': 'truckAttach',
    'TRUCK_ATTACH_03': 'truckDetach',
    'HONK_NH_TX32': 'hornDefault',
    'HONK_FENDT511C': 'honkFendt511C',
    'switch': 'switch01',
    'defaultHydraulicSound': 'hydraulicOpen02',
    'hydraulicLayerTone': 'hydraulicClose02',
    'HARVESTER_TOOL_WORK': 'harvesterToolWork',
    'forageHarvesterWork': 'combineThreshingSystemLoop',
    'augerBelt': 'harvesterDischargeStartCabin',
    'ROLLBELT_LOOP': 'tracksLoop',
    # FS22 cabin rumble name; FS25 uses the plain 'indoorCabinRumble' template
    # (attested in FS25 mods) and the original sample file is literally
    # sounds/.../indoorCabinRumbleLoop.wav, so this is a 1:1 rename.
    'indoorCabinOldVoice': 'indoorCabinRumble',
    'indoorCabinOldVehicle': 'indoorCabinRumble',
}


def migrate_sounds(s):
    hits = []
    for old, new in SOUND_TEMPLATE_MAP.items():
        attr = 'template="%s"' % old
        if attr not in s:
            continue
        if new is None:
            s = re.sub(r'\s+' + re.escape(attr), '', s)
        else:
            s = s.replace(attr, 'template="%s"' % new)
        hits.append((old, new))
    return s, hits


def migrate_sound_templates(stem):
    changed = []
    for dirpath, _dirs, files in os.walk(os.path.join(ROOT, stem)):
        for f in sorted(files):
            if not f.endswith('.xml'):
                continue
            rel = os.path.relpath(os.path.join(dirpath, f), os.path.join(ROOT, stem)).replace('\\', '/')
            base = layered_read(stem, rel)
            new, hits = migrate_sounds(base)
            if new != base:
                write(os.path.join(OUT, stem, rel), new)
                changed.append((rel, hits))
    return changed


for _stem in ('FS22_DT_Pack', 'FS22_T150_Gus'):
    _attr = migrate_i3d_attrs(_stem)
    print(_stem, 'i3d attributes migrated:', sum(n for _r, n in _attr), _attr)
    _xmlattr = fix_fs22_attrs(_stem)
    print(_stem, 'xml attributes migrated:', sum(n for _r, n in _xmlattr), _xmlattr)
    _coll = migrate_collisions(_stem)
    print(_stem, 'i3d collision filters migrated:', sum(len(h) for _r, h in _coll))
    for _rel, _hits in _coll:
        print('    %s: %d shapes' % (_rel, len(_hits)))
    _snd = migrate_sound_templates(_stem)
    print(_stem, 'xml sound templates migrated:', sum(len(h) for _r, h in _snd))
    for _rel, _hits in _snd:
        print('    %s: %s' % (_rel, ', '.join('%s->%s' % (o, n if n else '(none)') for o, n in _hits)))

# --- _remove.txt ---
write(f'{OUT}/FS22_DT_Pack/_remove.txt', 'scripts/MoreDesignConfigs.lua\n')
write(f'{OUT}/FS22_T150_Gus/_remove.txt', 'scripts/MoreDesignConfigs.lua\n')

# --- repair dangling local texture/image references ---------------------------
# The FS22 authors left a few references to .png files that were never shipped
# (only the .dds with the same name exists, e.g. store icons, kapots textures,
# the A41 radiator normal map).  FS25 refuses to load a missing texture, so point
# every dangling reference at the shipped file with the same name/other extension.
REF_ATTR = re.compile(r'(?P<pre>\b(?:filename|image|xmlFilename|iconFilename|img)=")(?P<path>[^"]+)(?P<post>")')
REF_ELEM = re.compile(r'(?P<pre><(?:image|iconFilename|filename)>)(?P<path>[^<]+)(?P<post></(?:image|iconFilename|filename)>)')


def known_files(mod):
    known = set()
    for line in open(f'{ROOT}/_filelist_{mod}.txt', encoding='utf-8'):
        m = re.match(r'\s*\d+\s+[0-9a-fA-F]{8}\s+(.+?)\s*$', line)
        if m and not m.group(1).endswith('/'):
            known.add(m.group(1))
    for dirpath, _dirs, files in os.walk(os.path.join(OUT, mod)):
        for f in files:
            known.add(os.path.relpath(os.path.join(dirpath, f), os.path.join(OUT, mod)).replace('\\', '/'))
    return known


def repair_refs(mod):
    known = known_files(mod)
    low = {k.lower() for k in known}

    def try_paths(path, basedir):
        for cand in (os.path.normpath(os.path.join(basedir, path)), os.path.normpath(path)):
            c = cand.replace('\\', '/')
            if c in known or c.lower() in low:
                return True
        return False

    def fixed(path, basedir):
        path = path.strip().replace('\\', '/')
        if not path or path.startswith(('$', '/')) or re.match(r'^[A-Za-z]:', path):
            return None
        if try_paths(path, basedir):
            return None
        stem, ext = os.path.splitext(path)
        for alt in ('.dds', '.png'):
            if alt.lower() == ext.lower():
                continue
            cand = stem + alt
            if try_paths(cand, basedir):
                return cand
        return None

    hits = []

    for dirpath, _dirs, files in os.walk(os.path.join(OUT, mod)):
        for f in sorted(files):
            if not f.endswith(('.xml', '.i3d')):
                continue
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, os.path.join(OUT, mod)).replace('\\', '/')
            basedir = os.path.dirname(rel).replace('\\', '/')
            s = read(full)

            def repl(m, _rel=rel):
                new = fixed(m.group('path'), basedir)
                if new:
                    hits.append((_rel, m.group('path'), new))
                    return m.group('pre') + new + m.group('post')
                return m.group(0)

            out = REF_ATTR.sub(repl, s)
            out = REF_ELEM.sub(repl, out)
            if out != s:
                write(full, out)

    for rel, old_ref, new_ref in hits:
        print('    ~ %s: %s -> %s' % (rel, old_ref, new_ref))
    return len(hits)


print('DT dangling refs repaired :', repair_refs('FS22_DT_Pack'))
print('T150 dangling refs repaired:', repair_refs('FS22_T150_Gus'))
