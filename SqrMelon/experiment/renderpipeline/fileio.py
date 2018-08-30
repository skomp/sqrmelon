import json
from collections import OrderedDict
from model import Node


def deserializePipeline(filePath):
    with open(filePath) as fileHandle:
        data = json.load(fileHandle, object_pairs_hook=OrderedDict)
    data['graph'] = graphFromJson(data['graph'])
    return data


def serializePipeline(filePath, graph, channels):
    with open(filePath, 'w') as fileHandle:
        data = {'graph': graphToJson(graph),
                'channels': channels}
        json.dump(data, fileHandle, indent=4, sort_keys=True)


def graphFromJson(data):
    Node.idLut.clear()
    nodes = [Node.fromJson(node) for node in data]
    # resolve connections
    for node in nodes:
        for plug in node.inputs:
            for i, connection in enumerate(plug.connections):
                id, portName = connection.split('.', 1)
                plug.connections[i] = Node.idLut[int(id)].findOutput(portName)
        for plug in node.outputs:
            for i, connection in enumerate(plug.connections):
                id, portName = connection.split('.', 1)
                plug.connections[i] = Node.idLut[int(id)].findInput(portName)
    return nodes


def graphToJson(graph):
    Node.idLut.clear()
    return [node.toJson() for node in graph]
