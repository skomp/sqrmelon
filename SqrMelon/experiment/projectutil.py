# TODO: File contains recursive dependency to experiment/render.py, should restructure...
from experiment.renderpipeline.model import EStitchScope
from qtutil import *

PIPELINE_EXT = '.json'
SCENE_EXT = '.json'


def settings():
    return QSettings('PB', 'SqrMelon2')


def projectFolder():
    assert settings().contains('currentproject')
    return str(settings().value('currentproject'))


def pipelineFolder():
    return os.path.join(projectFolder(), 'pipelines')


def iterPipelineNames():
    for name in os.listdir(pipelineFolder()):
        if name.endswith(PIPELINE_EXT):
            yield name[:-len(PIPELINE_EXT)]


def scenesFolder():
    return os.path.join(projectFolder(), 'scenes')


def iterSceneNames():
    for name in os.listdir(scenesFolder()):
        if name.endswith(SCENE_EXT):
            yield name[:-len(SCENE_EXT)]


def pipelineDefaultChannels(pipelineName):
    from render import Pipeline
    return Pipeline.pool(pipelineName).channels


def _iterStitches(pipelineName, scope):
    from render import Pipeline
    for stitchName in Pipeline.pool(pipelineName).iterStitchNames(scope):
        yield stitchName


def iterPublicStitches(pipelineName):
    folder = os.path.join(pipelineFolder(), pipelineName)
    for stitchName in _iterStitches(pipelineName, EStitchScope.Public):
        yield os.path.join(folder, stitchName + '.glsl')


def sceneStitchNames(pipelineName):
    return set(_iterStitches(pipelineName, EStitchScope.Scene))


def iterSceneStitches(sceneName):
    from render import Scene
    folder = os.path.join(scenesFolder(), sceneName)
    for stitchName in Scene.pool(sceneName).pipeline.iterStitchNames(EStitchScope.Scene):
        yield os.path.join(folder, stitchName + '.glsl')


def sceneDefaultChannels(sceneName, includePipelineUniforms=False):
    from render import Scene
    scene = Scene.pool(sceneName)
    if not includePipelineUniforms:
        return scene.channels.copy()
    result = scene.pipeline.channels.copy()
    result.update(scene.channels.copy())
    return result
