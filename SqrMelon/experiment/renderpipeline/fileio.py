import json
from model import Node
from experiment.serializable import serializeObjects, deserializeObjects


def deserializeGraph(fileHandle):
    data = json.load(fileHandle)['graph']
    return [node for node in deserializeObjects(data) if isinstance(node, Node)]


def serializeGraph(graph, fileHandle):
    data = {'graph': serializeObjects(graph)}
    json.dump(data, fileHandle, indent=4, sort_keys=True)
