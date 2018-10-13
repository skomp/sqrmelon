import re
import os
from util import ParseXMLWithIncludes, ScenesPath, SCENE_EXT, ProjectDir


_templates = {}
def Template(templatePath):
    global _templates
    key = os.path.abspath(templatePath).lower()
    if key in _templates:
        return _templates[key]
    assert not _templates, 'Found multiple templates in project, this is currently not supported by the player code.'
    xTemplate = ParseXMLWithIncludes(templatePath)
    _templates[key] = xTemplate
    return xTemplate


_stitches = {}


def readStitch(stitchPath):
    global _stitches
    if stitchPath in _stitches:
        return _stitches[stitchPath]
    with open(stitchPath) as fh:
        text = fh.read()
    _stitches[stitchPath] = text
    return text


shots = []
scenes = []
scenesDir = ScenesPath()

missingUniformsPerShot = []

for scene in os.listdir(scenesDir):
    if not scene.endswith(SCENE_EXT):
        continue
    scenePath = os.path.join(scenesDir, scene)
    sceneDir = os.path.splitext(scenePath)[0]
    xScene = ParseXMLWithIncludes(scenePath)

    templatePath = os.path.join(scenesDir, xScene.attrib['template'])
    templateDir = os.path.splitext(templatePath)[0]
    xTemplate = Template(templatePath)

    requiredUniforms = set()

    for xPass in xTemplate:
        stitches = []
        for xSection in xPass:
            baseDir = sceneDir
            if xSection.tag in ('global', 'shared'):
                baseDir = templateDir
            shaderFile = os.path.join(baseDir, xSection.attrib['path'])
            stitches.append(readStitch(shaderFile))

        # knowing the code for the pass, scan uniforms (that have to be animated)
        localRequiredUniforms = []
        code = '\n'.join(stitches)
        for result in re.finditer('uniform[ \t\r\n]+([a-zA-Z0-9_]+)[ \t\r\n]+([a-zA-Z0-9_]+)(.*?);', code, re.MULTILINE | re.DOTALL):
            typeName = result.group(1)
            varName = result.group(2)
            extras = result.group(3).strip()

            if extras:
                if extras[0] == '[' and extras[1] == ']':
                    extras = extras[2:].strip()
                elif extras[0] == '[' and extras[2] == ']':
                    extras = extras[3:].strip()

            if extras:
                if extras[0] == '=':
                    extras = extras[1:].strip()
                if re.match('[0-9\.]+', extras):
                    extras = ''
                if extras.startswith('vec') or extras.startswith('mat'):
                    i = 0
                    depth = 0
                    while i < len(extras):
                        if extras[i] == '(':
                            depth += 1
                        if extras[i] == ')':
                            depth -= 1
                            if depth == 0:
                                extras = extras[i + 1:].strip()
                                break
                        i += 1

            if extras:
                for varName in extras.split(','):
                    varName = varName.strip()
                    if varName:
                        localRequiredUniforms.append(varName)

            localRequiredUniforms.append(varName)

        # append required uniforms for animationprocessor.py
        if 'uDrone' in localRequiredUniforms:
            localRequiredUniforms.extend(('uDronePos', 'uDroneAngles'))
        if 'uFrustum' in localRequiredUniforms:
            localRequiredUniforms.append('uFovBias')
        if 'uV' in localRequiredUniforms:
            localRequiredUniforms.extend(('uOrigin', 'uAngles'))

        # ignore builtins & uniforms output by animationprocessor.py
        builtins = set(('uVignette', 'uBloom', 'uDrone', 'uV', 'uImages', 'uFrustum', 'uResolution', 'uBeats', 'uSeconds', 'uVisor', 'uBossRings'))
        localRequiredUniforms = set(localRequiredUniforms)
        localRequiredUniforms -= builtins
        # accumulate uniforms to animate
        requiredUniforms |= set(localRequiredUniforms)
    for xShot in xScene:
        if xShot.attrib['enabled'] != 'True':
            continue
        animatedUniforms = set()
        for xChannel in xShot:
            animatedUniforms.add(xChannel.attrib['name'].split('.', 1)[0])
        print scene, xShot.attrib['name']

        missingUniforms = requiredUniforms - animatedUniforms
        if 'uCrystalFlicker' in missingUniforms and scene not in ('IceCave.xml', 'GearIntro.xml'):
            missingUniforms.remove('uCrystalFlicker')
        if 'uBossRingsDist' in missingUniforms and scene not in ('Pillars2.xml',):
            missingUniforms.remove('uBossRingsDist')
        print ' - ' + '\n - '.join(missingUniforms)

        missingUniformsPerShot.append(missingUniforms)

allMissingUniforms = set()
for entry in missingUniformsPerShot:
    allMissingUniforms |= entry
uniformIsInAShot = set()
for uniformName in allMissingUniforms:
    for entry in missingUniformsPerShot:
        if uniformName not in entry:
            uniformIsInAShot.add(uniformName)
neverAnimated = allMissingUniforms - uniformIsInAShot
if neverAnimated:
    print 'Never animated:\n - %s' % '\n'.join(neverAnimated)
