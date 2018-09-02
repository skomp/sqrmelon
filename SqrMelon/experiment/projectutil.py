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


