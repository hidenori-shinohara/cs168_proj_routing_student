import examples.base_node as base_node
from examples.validator import Validator
from examples.watcher import Watcher

# TODO: refactor duplication here. This doesn't work yet
def generate_topology(nx_graph, rand, flood):
    # Setup validators first
    validators = []
    for i in range(num_validators):
        s = Validator.create('val' + str(i), flood)
        validators.append(s)

    def connectAll(nodes):
        visited = []
        for v in nodes:
            for v_inner in nodes:
                if v == v_inner or v_inner in visited:
                    continue
                else:
                    v.linkTo(v_inner)
            visited.append(v)

    connectAll(validators)

    watchers = []
    for node in graph.nodes():
        s = Watcher.create('wat' + str(node), flood)
        watchers.append(s)

    # Now connect
    for edge in graph.edges.data():
        wat1 = watchers[edge[0]]
        wat2 = watchers[edge[1]]
        wat1.linkTo(wat2)

    # Finally connect to validators
    if watchers:
        if not nx.is_connected(graph):
            for cc in nx.connected_components(graph):
                node = cc.pop()
                watchers[node].linkTo(rand.choice(validators))

        else:
            watchers[0].linkTo(validators[0])

    return validators, watchers