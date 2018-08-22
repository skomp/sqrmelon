import json

from qtutil import *


def settings():
    return QSettings('PB', 'SqrMelon')


def projectFolder():
    assert settings().contains('currentproject')
    return str(settings().value('currentproject'))


def pipelineFolder():
    return os.path.join(projectFolder(), 'pipelines')


def iterPipelineNames():
    for name in os.listdir(projectFolder()):
        if name.endswith('.json'):
            yield name[:-len('.json')]


def scenesFolder():
    return os.path.join(projectFolder(), 'scenes')


def iterSceneNames():
    for name in os.listdir(scenesFolder()):
        if name.endswith('.json'):
            yield name[:-len('.json')]


def _iterStitches(pipelineName, key):
    with open(os.path.join(pipelineFolder(), pipelineName + '.json')) as fh:
        data = json.load(fh)['graph']
    for entry in data:
        if entry['__class__'] == 'Stitch' and entry['scope'] == key:
            yield entry['name']


def publicStitches(pipelineName):
    return set(_iterStitches(pipelineName, 'Public'))


def sceneStitches(sceneName):
    with open(os.path.join(scenesFolder(), sceneName + '.json')) as fh:
        data = json.load(fh)
    pipelineName = data['pipeline']
    return set(_iterStitches(pipelineName, 'Scene'))
