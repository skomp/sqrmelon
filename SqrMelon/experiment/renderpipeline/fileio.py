import json
from model import Node


def deserializePipeline(filePath):
    with open(filePath) as fileHandle:
        data = json.load(fileHandle)
    data['graph'] = graphFromJson(data)
    return data


def serializePipeline(filePath, graph, uniforms):
    with open(filePath) as fileHandle:
        data = {'graph': graphToJson(graph),
                'uniforms': uniforms}
        json.dump(data, fileHandle, indent=4, sort_keys=True)


def graphFromJson(data):
    Node.idLut.clear()
    nodes = [Node.fromJson(node) for node in data]
    # resolve connections
    for node in nodes:
        for plug in node.inputs:
            for i, connection in enumerate(plug.connections):
                id, portName = connection.split('.', 1)
                plug.connections[i] = Node.idLut[id].findOutput(portName)
        for plug in node.outputs:
            for i, connection in enumerate(plug.connections):
                id, portName = connection.split('.', 1)
                plug.connections[i] = Node.idLut[id].findInput(portName)
    return nodes


def graphToJson(graph):
    Node.idLut.clear()
    return [node.toJson() for node in graph]
