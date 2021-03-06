import itertools
import pprint
from collections import defaultdict

import autonetkit.log as log
import networkx as nx
from ank_utils import unwrap_edges, unwrap_graph, unwrap_nodes
from anm import NmEdge, NmNode

try:
    import cPickle as pickle
except ImportError:
    import pickle

def sn_preflen_to_network(address, prefixlen):
    """Workaround for creating an IPNetwork from an address and a prefixlen
    TODO: check if this is part of netaddr module
    """
    import netaddr
    return netaddr.IPNetwork("%s/%s" % (address, prefixlen))

def fqdn(node):
    return "%s.%s" % (node.label, node.asn)

def name_folder_safe(foldername):
    for illegal_char in [" ", "/", "_", ",", ".", "&amp;", "-", "(", ")"]:
        foldername = foldername.replace(illegal_char, "_")
    # Don't want double _
    while "__" in foldername:
        foldername = foldername.replace("__", "_")
    return foldername

def set_node_default(NmGraph, nbunch = None, **kwargs):
    """Sets all nodes in nbunch to value if key not already set
    Note: this won't apply to future nodes added
    """
    graph = unwrap_graph(NmGraph)
    if nbunch is None:
        nbunch = graph.nodes()
    else:
        nbunch = unwrap_nodes(nbunch)
    for node in nbunch:
        for key, val in kwargs.items():
            if key not in graph.node[node]:
                graph.node[node][key] = val


#TODO: also add ability to copy multiple attributes

#TODO: rename to copy_node_attr_from
def copy_attr_from(overlay_src, overlay_dst, src_attr, dst_attr = None, nbunch = None, type = None, default = None):
    #TODO: add dest format, eg to convert to int
    if not dst_attr:
        dst_attr = src_attr

    graph_src = unwrap_graph(overlay_src)
    graph_dst = unwrap_graph(overlay_dst)
    if not nbunch:
        nbunch = graph_src.nodes()

    for n in nbunch:
        try:
            val = graph_src.node[n].get(src_attr, default)
        except KeyError:
            #TODO: check if because node doesn't exist in dest, or because attribute doesn't exist in graph_src
            log.debug("Unable to copy node attribute %s for %s in %s" % (src_attr, n, overlay_src))
        else:
            #TODO: use a dtype to take an int, float, etc
            if type is float:
                val = float(val)
            elif type is int:
                val = int(val)

            if n in graph_dst:
                graph_dst.node[n][dst_attr] = val

def copy_int_attr_from(overlay_src, overlay_dst, src_attr, dst_attr = None, nbunch = None, type = None, default = None):
    # note; uses high-level API for practicality over raw speed
    if not dst_attr:
        dst_attr = src_attr

    if not nbunch:
        nbunch = overlay_src.nodes()

    for node in nbunch:
        for src_int in node:
            val = src_int.get(src_attr)
            if val is None:
                val = default

            if type is float:
                val = float(val)
            elif type is int:
                val = int(val)

            dst_int = overlay_dst.interface(src_int)
            if dst_int is not None:
                dst_int.set(dst_attr, val)

def copy_edge_attr_from(overlay_src, overlay_dst, src_attr, dst_attr = None, type = None, default = None):
    graph_src = unwrap_graph(overlay_src)
    graph_dst = unwrap_graph(overlay_dst)
    if not dst_attr:
        dst_attr = src_attr

    for src, dst in graph_src.edges():
        try:
            val = graph_src[src][dst].get(src_attr, default)
        except KeyError:
            #TODO: check if because edge doesn't exist in dest, or because attribute doesn't exist in graph_src
            log.debug("Unable to copy edge attribute %s for (%s, %s) in %s" % (src_attr, src, dst, overlay_src))
        else:
            #TODO: use a dtype to take an int, float, etc
            if type is float:
                val = float(val)
            elif type is int:
                val = int(val)
            if graph_dst.has_edge(src, dst):
                graph_dst[src][dst][dst_attr] = val
            else:
                log.debug("Unable to copy edge attribute %s for (%s, %s) not in target graph %s" % (src_attr, src, dst, overlay_dst))

#TODO: make edges own module
def wrap_edges(NmGraph, edges):
    """ wraps edge ids into edge overlay """
    edges = list(edges)
    if not any(len(e) for e in edges):
        return []# each edge tuple is empty

    try:
        # strip out data from (src, dst, data) tuple
        edges = [(s, t) for (s, t, _) in edges]
    except ValueError:
        pass # already of form (src, dst)

    return ( NmEdge(NmGraph._anm, NmGraph._overlay_id, src, dst)
            for src, dst in edges)

def wrap_nodes(NmGraph, nodes):
    """ wraps node id into node overlay """
    return ( NmNode(NmGraph._anm, NmGraph._overlay_id, node)
            for node in nodes)

def in_edges(NmGraph, nodes=None):
    graph = unwrap_graph(NmGraph)
    edges = graph.in_edges(nodes)
    return wrap_edges(NmGraph, edges)

def split(NmGraph, edges, retain = [], id_prepend = ""):
    try:
        retain.lower() #TODO: find more efficient operation to test if string-like
        retain = [retain] # was a string, put into list
    except AttributeError:
        pass # already a list

    graph = unwrap_graph(NmGraph)
    edges = list(unwrap_edges(edges))
    edges_to_add = []
    added_nodes = []
    for (src, dst) in edges:
        if graph.is_directed():
            new_id = "%s%s_%s" % (id_prepend, src, dst)
        else:
            try:
                if float(src) < float(dst):
                    (node_a, node_b) = (src, dst) # numeric ordering
                else:
                    (node_a, node_b) = (dst, src) # numeric ordering
            except ValueError:
                # not numeric, use string sort
                (node_a, node_b) = sorted([src, dst]) # use sorted for consistency
            new_id = "%s%s_%s" % (id_prepend, node_a, node_b)

        interfaces = graph[src][dst]["_interfaces"]
        data = dict( (key, graph[src][dst][key]) for key in retain)
        #TODO: check how this behaves for directed graphs
        src_data = data.copy()
        if src in interfaces:
            src_int_id = interfaces[src]
            src_data['_interfaces'] = {src: src_int_id}
        dst_data = data.copy()
        if dst in interfaces:
            dst_int_id = interfaces[dst]
            dst_data['_interfaces'] = {dst: dst_int_id}
        edges_to_add.append( (src, new_id, src_data))
        edges_to_add.append( (dst, new_id, dst_data))
        added_nodes.append(new_id)

    graph.remove_edges_from(edges)
    graph.add_edges_from(edges_to_add)

    return wrap_nodes(NmGraph, added_nodes)

def explode_nodes(NmGraph, nodes, retain = []):
    """Explodes all nodes in nodes
    TODO: explain better
    TODO: Add support for digraph - check if NmGraph.is_directed()
    """
    log.debug("Exploding nodes")
    try:
        retain.lower()
        retain = [retain] # was a string, put into list
    except AttributeError:
        pass # already a list

    graph = unwrap_graph(NmGraph)
    nodes = unwrap_nodes(nodes)
    added_edges = []
    nodes = list(nodes)
#TODO: if graph is bidirectional, need to explode here too
#TODO: how do we handle explode for multi graphs?
    for node in nodes:
        log.debug("Exploding from %s" % node)
        neighbors = graph.neighbors(node)
        neigh_edge_pairs = ( (s,t) for s in neighbors for t in neighbors if s != t)
        neigh_edge_pairs = list(neigh_edge_pairs)
        edges_to_add = []
        for (src, dst) in neigh_edge_pairs:
            src_to_node_data = dict( (key, graph[src][node][key]) for key in retain)
            node_to_dst_data = dict( (key, graph[node][dst][key]) for key in retain)

            # copy interfaces
            src_int_id = graph[src][node]["_interfaces"][src]
            dst_int_id = graph[node][dst]["_interfaces"][dst]
            src_to_node_data["_interfaces"] = {src: src_int_id, dst: dst_int_id}

            src_to_node_data.update(node_to_dst_data)
            #TODO: handle interfaces for explode
            edges_to_add.append((src, dst, src_to_node_data))

        graph.add_edges_from(edges_to_add)
        added_edges += edges_to_add

        graph.remove_node(node)
    return wrap_edges(NmGraph, added_edges)

def label(NmGraph, nodes):
    return list(NmGraph._anm.node_label(node) for node in nodes)

def connected_subgraphs(NmGraph, nodes):
    nodes = list(unwrap_nodes(nodes))
    graph = unwrap_graph(NmGraph)
    subgraph = graph.subgraph(nodes)
    if not len(subgraph.edges()):
        #print "Nothing to aggregate for %s: no edges in subgraph"
        pass
    total_added_edges = []
    if graph.is_directed():
        component_nodes_list = nx.strongly_connected_components(subgraph)
    else:
        component_nodes_list = nx.connected_components(subgraph)

    wrapped = []
    for component in component_nodes_list:
        wrapped.append(list(wrap_nodes(NmGraph, component)))

    return wrapped

def aggregate_nodes(NmGraph, nodes, retain = []):
    """Combines connected into a single node"""
    try:
        retain.lower()
        retain = [retain] # was a string, put into list
    except AttributeError:
        pass # already a list

    nodes = list(unwrap_nodes(nodes))
    graph = unwrap_graph(NmGraph)
    subgraph = graph.subgraph(nodes)
    if not len(subgraph.edges()):
        #print "Nothing to aggregate for %s: no edges in subgraph"
        pass
    total_added_edges = []
    if graph.is_directed():
        component_nodes_list = nx.strongly_connected_components(subgraph)
    else:
        component_nodes_list = nx.connected_components(subgraph)
    for component_nodes in component_nodes_list:
        if len(component_nodes) > 1:
            base = component_nodes.pop() # choose one base device to retain
            nodes_to_remove = set(component_nodes) # remaining nodes, set for fast membership test
            external_edges = nx.edge_boundary(graph, component_nodes)
            edges_to_add = []
            for src, dst in external_edges:
                # src is the internal node to remove
                if src == base or dst == base:
                    continue # don't alter edges from base
                else:
                    if src in nodes_to_remove:
                        # edge from component to outside
                        interfaces = graph[src][dst]["_interfaces"]
                        dst_int_id = interfaces[dst]
                        data = dict( (key, graph[src][dst][key]) for key in retain)
                        data['_interfaces'] = {dst: dst_int_id}
                        edges_to_add.append((base, dst, data))
                        if graph.is_directed():
                            # other direction
                            #TODO: check which data should be copied
                            dst_data = dict( (key, graph[src][dst][key]) for key in retain)
                            dst_data['_interfaces'] = {dst: dst_int_id}
                            edges_to_add.append((dst, base, dst_data))
                    else:
                        # edge from outside into component
                        interfaces = graph[dst][src]["_interfaces"]
                        src_int_id = interfaces[src]
                        data = dict( (key, graph[dst][src][key]) for key in retain)
                        data['_interfaces'] = {src: src_int_id}
                        edges_to_add.append((base, src, data))
                        if graph.is_directed():
                            # other direction
                            #TODO: check which data should be copied
                            dst_data = dict( (key, graph[src][dst][key]) for key in retain)
                            dst_data['_interfaces'] = {src: src_int_id}
                            edges_to_add.append((src, base, dst_data))

            graph.add_edges_from(edges_to_add)
            total_added_edges += edges_to_add
            graph.remove_nodes_from(nodes_to_remove)

    return wrap_edges(NmGraph, total_added_edges)

# chain of two or more nodes

def most_frequent(iterable):
    """returns most frequent item in iterable"""
# from http://stackoverflow.com/q/1518522
    g = itertools.groupby
    try:
        return max(g(sorted(iterable)), key=lambda(x, v):(len(list(v)),-iterable.index(x)))[0]
    except ValueError, e:
        log.warning("Unable to calculate most_frequent, %s" % e)
        return None

def neigh_most_frequent(NmGraph, node, attribute, attribute_graph = None, allow_none = False):
    """Used to explicitly force most frequent - useful if integers such as ASN which would otherwise return mean"""
    #TODO: rename to median?
    graph = unwrap_graph(NmGraph)
    if attribute_graph:
        attribute_graph = unwrap_graph(attribute_graph)
    else:
        attribute_graph = graph # use input graph
    node = unwrap_nodes(node)
    values = [attribute_graph.node[n].get(attribute) for n in graph.neighbors(node)]
    values = sorted(values)
    if not allow_none:
        values = [v for v in values if v is not None]
    return most_frequent(values)


def neigh_average(NmGraph, node, attribute, attribute_graph = None):
    """ averages out attribute from neighbors in specified NmGraph
    attribute_graph is the graph to read the attribute from
    if property is numeric, then return mean
        else return most frequently occuring value
    """
    graph = unwrap_graph(NmGraph)
    if attribute_graph:
        attribute_graph = unwrap_graph(attribute_graph)
    else:
        attribute_graph = graph # use input graph
    node = unwrap_nodes(node)
    values = [attribute_graph.node[n].get(attribute) for n in graph.neighbors(node)]
#TODO: use neigh_attr
    try:
        values = [float(val) for val in values]
        return sum(values)/len(values)
    except ValueError:
        return most_frequent(values)

def neigh_attr(NmGraph, node, attribute, attribute_graph = None):
    #TODO: tidy up parameters to take attribute_graph first, and then evaluate if attribute_graph set, if not then use attribute_graph as attribute
#TODO: explain how NmGraph and attribute_graph work, eg for G_ip and G_phy
    graph = unwrap_graph(NmGraph)
    node = unwrap_nodes(node)
    if attribute_graph:
        attribute_graph = unwrap_graph(attribute_graph)
    else:
        attribute_graph = graph # use input graph

    #Only look at nodes which exist in attribute_graph
    neighs = (n for n in graph.neighbors(node))
    valid_nodes = (n for n in neighs if n in attribute_graph)
    return (attribute_graph.node[node].get(attribute) for node in valid_nodes)

def neigh_equal(NmGraph, node, attribute, attribute_graph = None):
    """Boolean, True if neighbors in NmGraph all have same attribute in attribute_graph"""
    neigh_attrs = neigh_attr(NmGraph, node, attribute, attribute_graph)
    return len(set(neigh_attrs)) == 1

def unique_attr(NmGraph, attribute):
    graph = unwrap_graph(NmGraph)
    return set(graph.node[node].get(attribute) for node in graph)

def groupby(attribute, nodes):
    """Takes a group of nodes and returns a generator of (attribute, nodes) for each attribute value
    A simple wrapped around itertools.groupby that creates a lambda for the attribute
    """
    import itertools
    keyfunc = lambda x: x.get(attribute)
    nodes = sorted(nodes, key = keyfunc)
    return itertools.groupby(nodes, key = keyfunc)

def boundary_nodes(graph, nodes):
    # TODO: move to utils
#TODO: use networkx boundary nodes directly: does the same thing
    """ returns nodes at boundary of G based on edge_boundary from networkx """
    graph = unwrap_graph(graph)
    nodes = list(nodes)
    nbunch = list(unwrap_nodes(nodes))
    # find boundary
    b_edges = nx.edge_boundary(graph, nbunch)  # boundary edges
    internal_nodes = [s for (s, t) in b_edges]
    assert(all(n in nbunch for n in internal_nodes))  # check internal

    return wrap_nodes(graph, internal_nodes)
