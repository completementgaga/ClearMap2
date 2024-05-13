# -*- coding: utf-8 -*-
"""
GraphGt
=======

Module provides basic Graph interface to the
`graph_tool <https://graph-tool.skewed.de>`_ library.
"""
__author__ = 'Christoph Kirst <christoph.kirst.ck@gmail.com>'
__license__ = 'GPLv3 - GNU General Public License v3 (see LICENSE)'
__copyright__ = 'Copyright © 2020 by Christoph Kirst'
__webpage__ = 'https://idisco.info'
__download__ = 'https://www.github.com/ChristophKirst/ClearMap2'

import copy

import numpy as np

import graph_tool as gt
import graph_tool.util as gtu
import graph_tool.topology as gtt
import graph_tool.generation as gtg

# fix graph tool saving / loading for very large arrays
import ClearMap.Analysis.Graphs.Graph as grp
from ClearMap.Analysis.Graphs.GraphRendering import mesh_tube
from ClearMap.Analysis.Graphs.type_conversions import dtype_to_gtype, gtype_from_source, vertex_property_map_to_python, \
  edge_property_map_to_python, vertex_property_map_from_python, set_vertex_property_map, edge_property_map_from_python, \
  set_edge_property_map
from ClearMap.Analysis.Graphs.utils import pickler, unpickler, edges_to_connectivity

from ClearMap.Utils.array_utils import remap_array_ranges


gt.gt_io.clean_picklers()
gt.gt_io.libgraph_tool_core.set_pickler(pickler)
gt.gt_io.libgraph_tool_core.set_unpickler(unpickler)


class Graph(grp.AnnotatedGraph):
    """Graph class to handle graph construction and analysis.

    Note
    ----
    This is an interface from ClearMap graphs to graph_tool.
    """
    DEFAULT_N_DIMS = 3

    def __init__(self, name=None, n_vertices=None, edges=None, directed=None,
                 vertex_coordinates=None, vertex_radii=None,
                 edge_coordinates=None, edge_radii=None, edge_geometries=None, shape=None,
                 vertex_labels=None, edge_labels=None, annotation=None,
                 base=None, edge_geometry_type='graph'):

        if base is None:
            base = gt.Graph(directed=directed)
            self.base = base

            # add default graph properties
            self.add_graph_property('shape', None, dtype='object')
            self.add_graph_property('edge_geometry_type', edge_geometry_type, dtype='object')

            super(Graph, self).__init__(name=name, n_vertices=n_vertices, edges=edges, directed=directed,
                                        vertex_coordinates=vertex_coordinates, vertex_radii=vertex_radii,
                                        edge_coordinates=edge_coordinates, edge_radii=edge_radii,
                                        edge_geometries=edge_geometries, shape=shape,
                                        vertex_labels=None, edge_labels=None, annotation=None)
        else:
            self.base = base
            super(Graph, self).__init__(name=name)
        self.__mesh_vertices = None
        self.__mesh_faces = None
        self.__faces_edge_ids = None

    def invalidate_caches(self):
        self.__mesh_vertices = None
        self.__mesh_faces = None
        self.__faces_edge_ids = None

    @property
    def base(self):
        return self._base

    @base.setter
    def base(self, value):
        if not isinstance(value, gt.Graph):
            raise ValueError('Base graph not a graph_tool Graph')
        self._base = value
        self.invalidate_caches()

    @property
    def directed(self):
        return self._base.is_directed()

    @directed.setter
    def directed(self, value):
        self._base.set_directed(value)

    @property
    def is_view(self):
        return isinstance(self.base, gt.GraphView)

    # ## Vertices
    @property
    def n_vertices(self):
        return self._base.num_vertices()

    def vertex(self, vertex):
        if isinstance(vertex, gt.Vertex):
            return vertex
        else:
            return self._base.vertex(vertex)

    def first_vertex(self):
        return self._base.vertices().next()

    @property
    def vertices(self):
        return list(self.base.vertices())

    def vertex_iterator(self):
        return self._base.vertices()

    def vertex_index(self, vertex):
        return int(vertex)

    def vertex_indices(self):
        return np.array(self.vertices, dtype=int)  # FIXME: why not self.base.get_vertices() ?

    def add_vertex(self, n_vertices=None, vertex=None):
        if n_vertices is not None:
            self._base.add_vertex(n_vertices)
        elif isinstance(vertex, int):
            self._base.vertex(vertex, add_missing=True)
        # elif isinstance(vertex, gt.Vertex):
        #     v = self._base.add_vertex(1)
        #     v = vertex  #analysis:ignore
        else:
            raise ValueError('Cannot add vertices.')
        self.invalidate_caches()

    def remove_vertex(self, vertex):
        self._base.remove_vertex(vertex)
        self.invalidate_caches()

    def vertex_property(self, name, vertex=None, as_array=True):
        v_prop = self._base.vertex_properties[name]
        if vertex is not None:
            return v_prop[self.vertex(vertex)]
        else:
            return vertex_property_map_to_python(v_prop, as_array=as_array)

    def vertex_property_map(self, name):
        return self._base.vertex_properties[name]

    @property
    def vertex_properties(self):
        return self._base.vertex_properties.keys()

    def add_vertex_property(self, name, source=None, dtype=None):
        v_prop = vertex_property_map_from_python(source, self, dtype=dtype)
        self._base.vertex_properties[name] = v_prop
        # self.invalidate_caches()  # TODO: check if this is necessary

    def set_vertex_property(self, name, source, vertex=None):
        if name not in self._base.vertex_properties:
            raise ValueError(f'Graph has no vertex property with name {name}!')
        v_prop = self._base.vertex_properties[name]
        if vertex is not None:
            v_prop[vertex] = source
        else:
            set_vertex_property_map(v_prop, source)
        # self.invalidate_caches()  # TODO: check if this is necessary

    def define_vertex_property(self, name, source, vertex=None, dtype=None):
        if name in self.vertex_properties:
            self.set_vertex_property(name, source, vertex=vertex)
        else:
            if vertex is None:
                self.add_vertex_property(name, source, dtype=dtype)
            else:
                dtype = gtype_from_source(source) if dtype is None else dtype
                self.add_vertex_property(name, dtype=dtype)
                self.set_vertex_property(name, source, vertex=vertex)

    def remove_vertex_property(self, name):
        if name not in self._base.vertex_properties:
            raise ValueError(f'Graph has no vertex property with name {name}!')
        del self._base.vertex_properties[name]
        self.invalidate_caches()

    def vertex_degrees(self):
        return self._base.get_out_degrees(self._base.get_vertices())

    def vertex_degree(self, index):
        return self._base.get_out_degrees([index])[0]

    def vertex_out_degrees(self):
        return self._base.get_out_degrees(self._base.get_vertices())

    def vertex_out_degree(self, index):
        return self._base.get_out_degrees([index])[0]

    def vertex_in_degrees(self):
        return self._base.get_in_degrees(self._base.get_vertices())

    def vertex_in_degree(self, index):
        return self._base.get_in_degrees([index])[0]

    def vertex_neighbours(self, index):
        return self._base.get_out_neighbours(index)

    def vertex_out_neighbours(self, index):
        return self._base.get_out_neighbours(index)

    def vertex_in_neighbours(self, index):
        return self._base.get_in_neighbours(index)

    # ## Edges
    @property
    def n_edges(self):
        return self._base.num_edges()

    def edge(self, edge):
        if isinstance(edge, gt.Edge):
            return edge
        elif isinstance(edge, tuple):  # FIXME: what about list ?
            return self._base.edge(*edge)
        elif isinstance(edge, int):
            return gtu.find_edge(self._base, self._base.edge_index, edge)[0]
        else:
            raise ValueError(f'Edge specification {edge} is not valid!')

    def first_edge(self):
        return self._base.edges().next()

    def edge_index(self, edge):
        return self._base.edge_index[self.edge(edge)]

    def edge_indices(self):  # TODO: explain what this does
        p = self.base.edge_index
        return np.array([p[e] for e in self.edge_iterator()], dtype=int)

    def add_edge(self, edge):
        if isinstance(edge, tuple):
            self._base.add_edge(*edge)
        else:
            self._base.add_edge_list(edge)
        self.invalidate_caches()

    def remove_edge(self, edge):
        edge = self.edge(edge)
        self._base.remove_edge(edge)
        self.invalidate_caches()

    @property
    def edges(self):
        return list(self._base.edges())

    def edge_iterator(self):
        return self._base.edges()

    def edge_connectivity(self):
        return self._base.get_edges()[:, :2]

    def edge_property(self, name, edge=None, as_array=True):
        e_prop = self._base.edge_properties[name]
        if edge is not None:
            return e_prop[self.edge(edge)]
        else:
            return edge_property_map_to_python(e_prop, as_array=True)

    def edge_property_map(self, name):
        return self._base.edge_properties[name]

    @property
    def edge_properties(self):
        return self._base.edge_properties.keys()

    def add_edge_property(self, name, source=None, dtype=None):
        p = edge_property_map_from_python(source, self)
        self._base.edge_properties[name] = p
        self.invalidate_caches()

    def set_edge_property(self, name, source, edge=None):
        if name not in self._base.edge_properties:
            raise ValueError(f'Graph has no edge property with name {name}!')
        p = self._base.edge_properties[name]
        if edge is not None:
            p[self.edge(edge)] = source
        else:
            set_edge_property_map(p, source)
        self.invalidate_caches()

    def define_edge_property(self, name, source, edge=None, dtype=None):
        if name in self.edge_properties:
            self.set_edge_property(name, source, edge=edge)
        else:
            if edge is None:
                self.add_edge_property(name, source, dtype=dtype)
            else:
                dtype = gtype_from_source(source) if dtype is None else dtype
                self.add_edge_property(name, dtype=dtype)
                self.set_edge_property(name, source, edge=edge)

    def remove_edge_property(self, name):
        if name not in self.edge_properties:
            raise ValueError(f'Graph does not have edge property with name {name}!')
        del self._base.edge_properties[name]
        self.invalidate_caches()

    def vertex_edges(self, vertex):
        return edges_to_connectivity(self.vertex_edges_iterator(vertex))

    def vertex_out_edges(self, vertex):
        return edges_to_connectivity(self.vertex_out_edges_iterator(vertex))

    def vertex_in_edges(self, vertex):
        return edges_to_connectivity(self.vertex_in_edges_iterator(vertex))

    def vertex_edges_iterator(self, vertex):
        return self._base.vertex(vertex).out_edges()

    def vertex_out_edges_iterator(self, vertex):
        return self._base.vertex(vertex).out_edges()

    def vertex_in_edges_iterator(self, vertex):
        return self._base.vertex(vertex).in_edges()

    # ## Graph properties
    def graph_property(self, name):
        return self._base.graph_properties[name]

    def graph_property_map(self, name):
        return self._base.graph_properties[name]

    @property
    def graph_properties(self):
        return self._base.graph_properties.keys()

    def add_graph_property(self, name, source, dtype=None):
        if dtype is None:
            dtype = 'object'
        gtype = dtype_to_gtype(dtype)
        g_prop = self._base.new_graph_property(gtype)
        g_prop.set_value(source)
        self._base.graph_properties[name] = g_prop
        self.invalidate_caches()

    def set_graph_property(self, name, source):
        if name not in self.graph_properties:
            raise ValueError(f'Graph has no property named {name}!')
        if source is not None:
            self._base.graph_properties[name] = source
        self.invalidate_caches()

    def define_graph_property(self, name, source, dtype=None):
        if name in self.graph_properties:
            self.set_graph_property(name, source)
        else:
            self.add_graph_property(name, source, dtype=dtype)

    def remove_graph_property(self, name):
        if name not in self.graph_properties:
            raise ValueError(f'Graph does not have graph property named {name}!')
        del self._base.graph_properties[name]
        self.invalidate_caches()

    # ## Geometry
    @property
    def shape(self):
        """The shape of the space in which the graph is embedded.

        Returns
        -------
        shape : tuple of int
          The shape of the graph space.
        """
        return self.graph_property('shape')

    @shape.setter
    def shape(self, value):
        self.define_graph_property('shape', value)

    @property
    def ndim(self):
        if self.shape is None:
            return Graph.DEFAULT_N_DIMS
        else:
            return len(self.shape)

    def axis_indices(self, axis=None, as_list=False):
        if axis is None:
            return range(self.ndim)
        axis_to_index = {k: i for i, k in enumerate('xyz')}
        if as_list and not isinstance(axis, (tuple, list)):
            axis = [axis]
        if isinstance(axis, (tuple, list)):
            return [axis_to_index[a] if a in axis_to_index.keys() else a for a in axis]
        else:
            return axis_to_index[axis] if axis in axis_to_index.keys() else axis

    @property
    def has_vertex_coordinates(self):
        return 'coordinates' in self.vertex_properties

    def vertex_coordinates(self, vertex=None, axis=None):
        p = self.vertex_property_map('coordinates')
        if vertex is not None:
            coordinates = p[vertex]
            if axis is None:
                return coordinates
            else:
                indices = self.axis_indices(axis)
                return coordinates[indices]
        else:
            indices = self.axis_indices(axis, as_list=True)
            coordinates = p.get_2d_array(indices)
            if axis is not None and not isinstance(axis, (tuple, list)):
                return coordinates[0]
            else:
                return coordinates.T

    def set_vertex_coordinates(self, coordinates, vertex=None, dtype=float):
        self.define_vertex_property('coordinates', coordinates, vertex=vertex, dtype=dtype)

    # def set_vertex_coordinate(self, vertex, coordinate):
    #     self.define_vertex_property('coordinates', coordinate, vertex=vertex)

    @property
    def has_vertex_radii(self):
        return 'radii' in self.vertex_properties

    def vertex_radii(self, vertex=None):
        return self.vertex_property('radii', vertex=vertex)

    def set_vertex_radii(self, radii, vertex=None):
        self.define_vertex_property('radii', radii, vertex=vertex)

    def set_vertex_radius(self, vertex, radius):
        self.define_vertex_property('radii', radius, vertex=vertex)

    @property
    def has_edge_coordinates(self):
        return 'coordinates' in self.edge_properties

    def edge_coordinates(self, edge=None):
        return self.edge_property('coordinates', edge=edge)

    def set_edge_coordinates(self, coordinates, edge=None):
        self.define_edge_property('coordinates', coordinates, edge=edge)

    @property
    def has_edge_radii(self):
        return 'radii' in self.edge_properties

    def edge_radii(self, edge=None):
        return self.edge_property('radii', edge=edge)

    def set_edge_radii(self, radii, edge=None):
        self.define_edge_property('radii', radii, edge=edge)

    # ## Edge geometry
    @property
    def edge_geometry_type(self):
        """Type for storing edge properties

        Returns
        -------
        type : 'graph' or 'edge'
          'graph' : Stores edge coordinates in a graph property array and
                    start end indices in edges.

          'edge'  : Stores the edge coordinates in variable length vectors in
                    each edge.
        """
        return self.graph_property('edge_geometry_type')

    @edge_geometry_type.setter
    def edge_geometry_type(self, value):
        self.set_edge_geometry_type(value)

    def edge_geometry_property_name(self, name='coordinates', prefix='edge_geometry'):
        return f'{prefix}_{name}'

    @property
    def edge_geometry_property_names(self):
        prefix = self.edge_geometry_property_name(name='')
        if self.edge_geometry_type == 'graph':
            properties = self.graph_properties
        else:
            properties = self.edge_properties
        # return the graph properties that are arrays with n_pixels elements
        return [p for p in properties if p.startswith(prefix) and p != 'edge_geometry_type']

    def edge_geometry_property(self, name):
        name = self.edge_geometry_property_name(name)
        if self.edge_geometry_type == 'graph':
            return self.graph_property(name)
        else:
            return self.edge_property(name)

    @property
    def edge_geometry_properties(self):
        prefix_len = len(self.edge_geometry_property_name(name=''))
        properties = [p[prefix_len:] for p in self.edge_geometry_property_names]
        return properties

    def has_edge_geometry(self, name='coordinates'):
        return self.edge_geometry_property_name(name=name) in self.edge_geometry_property_names

    # edge geometry stored at each edge
    def _edge_geometry_scalar_edge(self, name, edge=None):
        name = self.edge_geometry_property_name(name)
        return self.edge_property(name, edge=edge)

    def _edge_geometry_vector_edge(self, name, edge=None, reshape=True, ndim=None, as_list=True):
        name = self.edge_geometry_property_name(name)
        geometry = self.edge_property(name, edge=edge)
        if reshape:
            if ndim is None:
                ndim = self.ndim
            if edge is None:
                geometry = [g.reshape((-1, ndim), order='A') for g in geometry]
                if as_list:
                    return geometry
                else:
                    return np.vstack(geometry)
            else:
                return geometry.reshape(-1, ndim)
        else:
            return geometry

    def _edge_geometry_indices_edge(self):
        lengths = self.edge_geometry_lengths()
        indices = np.cumsum(lengths)
        indices = np.array([np.hstack([0, indices[:-1]]), indices]).T
        return indices

    def _edge_geometry_edge(self, name, edge=None, reshape=True, ndim=None, as_list=True, return_indices=False):
        if name in ['coordinates', 'mesh']:
            edge_geometry = self._edge_geometry_vector_edge(name, edge=edge, reshape=reshape, ndim=ndim, as_list=as_list)
        else:
            edge_geometry = self._edge_geometry_scalar_edge(name, edge=edge)
        if return_indices:
            indices = self._edge_geometry_indices_edge()
            return edge_geometry, indices
        else:
            return edge_geometry

    def _set_edge_geometry_scalar_edge(self, name, scalars, edge=None, dtype=None):
        name = self.edge_geometry_property_name(name)
        self.define_edge_property(name, scalars, edge=edge, dtype=dtype)

    def _set_edge_geometry_vector_edge(self, name, vectors, indices=None, edge=None):
        name = self.edge_geometry_property_name(name)
        if edge is None:
            if indices is None:
                vectors = [v.reshape(-1, order='A') for v in vectors]
            else:
                vectors = [vectors[s:e].reshape(-1, order='A') for s, e in indices]
        self.define_edge_property(name, vectors, edge=edge, dtype='vector<double>')

    def _set_edge_geometry_edge(self, name, values, indices=None, edge=None):
        if name in ['coordinates', 'mesh']:
            return self._set_edge_geometry_vector_edge(name, values, indices=indices, edge=edge)
        elif name in ['radii']:
            return self._set_edge_geometry_scalar_edge(name, values, edge=edge)
        else:
            return self._set_edge_geometry_scalar_edge(name, values, edge=edge, dtype=object)

    def _remove_edge_geometry_edge(self, name):
        name = self.edge_geometry_property_name(name)
        self.remove_edge_property(name)

    # EDGE GEOMETRY GRAPH
    # edge geometry data stored in a single array, start,end indices stored in edge
    def _edge_geometry_indices_name_graph(self, name='indices'):
        return self.edge_geometry_property_name(name)

    def _edge_geometry_indices_graph(self, edge=None):
        return self.edge_property(self._edge_geometry_indices_name_graph(), edge=edge)

    def _set_edge_geometry_indices_graph(self, indices, edge=None):
        self.set_edge_property(self._edge_geometry_indices_name_graph(), indices, edge=edge)

    def _edge_geometry_graph(self, name, edge=None, return_indices=False, as_list=False):
        name = self.edge_geometry_property_name(name)
        if edge is None:
            values = self.graph_property(name)
            if return_indices or as_list:
                indices = self._edge_geometry_indices_graph()
            if as_list:
                values = [values[start:end] for start, end in indices]
            if return_indices:
                return values, indices
            else:
                return values
        else:
            start, end = self._edge_geometry_indices_graph(edge=edge)
            values = self.graph_property(name)
            return values[start:end]

    def _set_edge_geometry_graph(self, name, values, indices=None, edge=None):
        if edge is not None:
            raise NotImplementedError("Setting individual edge geometries not implemented for 'graph' mode!")
        if isinstance(values, list):
            if indices is None:
                indices = np.cumsum([len(v) for v in values])
                indices = np.array([np.hstack([[0], indices[:-1]]), indices], dtype=int).T
            values = np.vstack(values)
        if indices is not None:
            name_indices = self._edge_geometry_indices_name_graph()
            self.define_edge_property(name_indices, indices, dtype='vector<int64_t>')
        name = self.edge_geometry_property_name(name)
        self.define_graph_property(name, values, dtype='object')

    def _remove_edge_geometry_graph(self, name):
        name = self.edge_geometry_property_name(name)
        if name in self.graph_properties:
            self.remove_graph_property(name)

    def _remove_edge_geometry_indices_graph(self):
        name = self._edge_geometry_indices_name_graph()
        if name in self.edge_properties:
            self.remove_edge_property(name)

    def resize_edge_geometry(self):
        if not self.has_edge_geometry() or self.edge_geometry_type != 'graph':
            return

        # adjust indices
        indices = self._edge_geometry_indices_graph()

        indices_new = np.diff(indices, axis=1)[:, 0]
        indices_new = np.cumsum(indices_new)
        indices_new = np.array([np.hstack([0, indices_new[:-1]]), indices_new]).T
        self._set_edge_geometry_indices_graph(indices_new)

        self._reduce_edge_geometry_properties(indices, indices_new)

    def _reduce_edge_geometry_properties(self, indices, indices_new):
        """
        Remap all properties in self.edge_geometry_properties to the new indices

        For example, if for the edge_geometry_coordinates, which has a shape of
        (n_voxels, 3), the indices would be (n_edges, 2) and the indices_new would be
        (n_edges_new, 2). The function would then remap the coordinates from the old
        indices to the new indices like this:
        for i in range(indices.shape[0]):
          prop_new[indices_new[i, 0]:indices_new[i, 1]] = prop[indices[i, 0]:indices[i, 1]]


        Parameters
        ----------
        indices
        indices_new

        Returns
        -------

        """
        n = indices_new[-1, -1]
        for prop_name in self.edge_geometry_property_names:
            prop = self.graph_property(prop_name)
            shape_new = (n,) + prop.shape[1:]
            prop_new = np.zeros(shape_new, prop.dtype)
            prop_new = remap_array_ranges(prop, prop_new, indices, indices_new)
            self.set_graph_property(prop_name, prop_new)

    def edge_geometry(self, name='coordinates', edge=None, as_list=True, return_indices=False, reshape=True, ndim=None):
        if self.edge_geometry_type == 'graph':
            return self._edge_geometry_graph(name=name, edge=edge, return_indices=return_indices, as_list=as_list)
        else:  # edge geometry type
            return self._edge_geometry_edge(name=name, edge=edge, return_indices=return_indices, as_list=as_list, reshape=reshape, ndim=ndim)

    def set_edge_geometry(self, name, values, indices=None, edge=None):
        if self.edge_geometry_type == 'graph':
            # if coordinates is not None:
            #     self._set_edge_geometry_graph('coordinates', coordinates, indices=indices, edge=edge)
            #     if indices is not None:
            #         indices = None
            # if radii is not None:
            #     self._set_edge_geometry_graph('radii', radii, indices=indices, edge=edge)
            #     if indices is not None:
            #         indices = None
            # if values is not None:
            self._set_edge_geometry_graph(name, values, indices=indices, edge=edge)
        else:
            # if coordinates is not None:
            #     self._set_edge_geometry_edge('coordinates', coordinates, indices=indices, edge=edge)
            # if radii is not None:
            #     self._set_edge_geometry_edge('radii', radii, indices=indices, edge=edge)
            # if values is not None:
            self._set_edge_geometry_edge(name, values, indices=indices, edge=edge)

    def remove_edge_geometry(self, name=None):
        if name is None:
            if self.edge_geometry_type == 'graph':
                self._remove_edge_geometry_indices_graph()
            name = self.edge_geometry_properties
        if not isinstance(name, list):
            name = [name]
        for n in name:
            if self.edge_geometry_type == 'graph':
                self._remove_edge_geometry_graph(name=n)
            else:
                self._remove_edge_geometry_edge(name=n)

    def edge_geometry_indices(self):
        if self.edge_geometry_type == 'graph':
            return self._edge_geometry_indices_graph()
        else:
            return self._edge_geometry_indices_edge()

    def edge_geometry_lengths(self, name='coordinates'):
        if self.edge_geometry_type == 'graph':
            indices = self._edge_geometry_indices_graph()
            return np.diff(indices, axis=1)[:, 0]
        else:
            values = self.edge_geometry(name)
            return np.array([len(v) for v in values], dtype=int)

    def set_edge_geometry_type(self, edge_geometry_type):
        if edge_geometry_type not in ['graph', 'edge']:
            raise ValueError(f"Edge geometry must be 'graph' or 'edge', got '{edge_geometry_type}'!")

        if self.edge_geometry_type == edge_geometry_type:
            return
        else:
            if self.edge_geometry_type == 'graph':  # graph -> edge
                indices = self._edge_geometry_indices_graph()
                for name in self.edge_geometry_property_names:
                    values = self.edge_geometry(name, as_list=False)
                    self._remove_edge_geometry_graph(name)
                    self._set_edge_geometry_edge(name, values, indices=indices)
                self._remove_edge_geometry_indices_graph()
            else:  # self.edge_geometry_type == 'edge': edge -> graph
                for name in self.edge_geometry_property_names:
                    values = self.edge_geometry(name)
                    self._remove_edge_geometry_edge(name)
                    self._set_edge_geometry_graph(name, values)
            self.set_graph_property('edge_geometry_type', edge_geometry_type)
        self.invalidate_caches()

    def is_edge_geometry_consistent(self, verbose=False):
        eg, ei = self.edge_geometry(as_list=False, return_indices=True)
        vc = self.vertex_coordinates()
        ec = self.edge_connectivity()

        # check edge sources
        check = vc[ec[:, 0]] == eg[ei[:, 0]]
        if not np.all(check):
            if verbose:
                errors = np.where(check == False)[0]
                print(f'Found {len(errors)} errors in edge sources at {errors}')
            return False

        # check edge targets
        check = vc[ec[:, 1]] == eg[ei[:, 1]-1]
        if not np.all(check):
            if verbose:
                errors = np.where(check == False)[0]
                print(f'Found {len(errors)} errors in edge targets at {errors}')
            return False

        return True

    def edge_geometry_from_edge_property(self, edge_property_name, edge_geometry_name=None):
        edge_property = self.edge_property(edge_property_name)
        indices = self.edge_geometry_indices()

        shape = (len(indices),) + edge_property.shape[1:]
        edge_geometry = np.zeros(shape, dtype=edge_property.dtype)
        for i, e in zip(indices, edge_property):
            si, ei = i
            edge_geometry[si:ei] = e

        if edge_geometry_name is None:
            edge_geometry_name = edge_property_name

        self.set_edge_geometry(name=edge_geometry_name, values=edge_geometry, indices=indices)

    @property
    def edge_meshes(self, coordinates='coordinates'):
        """
        Returns a mesh triangulation for the geometry of each edge.
        For efficiency purposes, the result is cached.
        """

        if self.__mesh_vertices is None or self.__mesh_faces is None:
            edge_ids = np.arange(self.n_edges)
            self.__mesh_vertices, self.__mesh_faces, self.__faces_edge_ids = (
                mesh_tube(graph=self, coordinates=coordinates, edge_colors=edge_ids))
        return self.__mesh_vertices, self.__mesh_faces, self.__faces_edge_ids

    # ## Label

    # def add_label(self, annotation=None, key='id', value='order'):
    #
    #     # lbl.AnnotationFile
    #     # label points
    #     aba = np.array(io.read(annotation), dtype=int)
    #
    #     # get vertex coordinates
    #     x,y,z = self.vertex_coordinates().T
    #
    #     ids = np.ones(len(x), dtype = bool)
    #     for a,s in zip([x,y,z], aba.shape):
    #         ids = np.logical_and(ids, a >= 0)
    #         ids = np.logical_and(ids, a < s)
    #
    #     # label points
    #     g_ids = np.zeros(len(x), dtype=int)
    #     g_ids[ids] = aba[x[ids], y[ids], z[ids]]
    #
    #     if value is not None:
    #         id_to_order = lbl.getMap(key=key, value=value)
    #         g_order = id_to_order[g_ids]
    #     else:
    #         value = key
    #
    #     self.add_vertex_property(value, g_order)

    # ## Functionality
    def sub_graph(self, vertex_filter=None, edge_filter=None, view=False):
        gv = gt.GraphView(self.base, vfilt=vertex_filter, efilt=edge_filter)
        if view:
            return Graph(base=gv)
        else:
            g = Graph(base=gt.Graph(gv, prune=True))  # create a new pruned graphtool instance to ensure vertices are coninuous
            g.resize_edge_geometry()
            return g

    def view(self, vertex_filter=None, edge_filter=None):
        return gt.GraphView(self.base, vfilt=vertex_filter, efilt=edge_filter)

    def remove_self_loops(self):  # FIXME: substitute custom function
        gt.stats.remove_self_loops(self.base)

    def remove_isolated_vertices(self):
        non_isolated = self.vertex_degrees() > 0
        new_graph = self.sub_graph(vertex_filter=non_isolated)
        self._base = new_graph._base

    def label_components(self, return_vertex_counts=False):
        components, vertex_counts = gtt.label_components(self.base)
        components = np.array(components.a)
        if return_vertex_counts:
            return components, vertex_counts
        else:
            return components

    def largest_component(self, view=False):
        components, counts = self.label_components(return_vertex_counts=True)
        i = np.argmax(counts)
        vertex_filter = components == i
        return self.sub_graph(vertex_filter=vertex_filter, view=view)

    def vertex_coloring(self):
        colors = gtt.sequential_vertex_coloring(self.base)
        colors = vertex_property_map_to_python(colors)
        return colors

    def edge_target_label(self, vertex_label, as_array=True):
        if isinstance(vertex_label, str):
            vertex_label = self.vertex_property(vertex_label)
        if not isinstance(vertex_label, gt.PropertyMap):
            vertex_label = vertex_property_map_from_python(vertex_label, self)
        et = gt.edge_endpoint_property(self.base, vertex_label, endpoint='target')
        return edge_property_map_to_python(et, as_array=as_array)

    def edge_source_label(self, vertex_label, as_array=True):
        if isinstance(vertex_label, str):
            vertex_label = self.vertex_property(vertex_label)
        if not isinstance(vertex_label, gt.PropertyMap):
            vertex_label = vertex_property_map_from_python(vertex_label, self)
        et = gt.edge_endpoint_property(self.base, vertex_label, endpoint='source')
        return edge_property_map_to_python(et, as_array=as_array)

    def remove_isolated_edges(self):
        vertex_degree = self.vertex_degrees()
        vertex_degree = vertex_property_map_from_python(vertex_degree, self)
        es = self.edge_source_label(vertex_degree, as_array=True)
        et = self.edge_target_label(vertex_degree, as_array=True)
        edge_filter = np.logical_not(np.logical_and(es == 1, et == 1))
        new_graph = self.sub_graph(edge_filter=edge_filter)
        self._base = new_graph._base
        self.remove_isolated_vertices()

    def edge_graph(self, return_edge_map=False):
        line_graph, emap = gtg.line_graph(self.base)
        line_graph = Graph(base=line_graph)
        if return_edge_map:
            emap = vertex_property_map_to_python(emap)
            return line_graph, emap
        else:
            return line_graph

    # ## Binary morphological graph operations

    def vertex_propagate(self, label, value, steps=1):
        if value is not None and not hasattr(value, '__len__'):
            value = [value]
        p = vertex_property_map_from_python(label, self)
        for s in range(steps):
            gt.infect_vertex_property(self.base, p, vals=value)
        label = vertex_property_map_to_python(p)
        return label

    def vertex_dilate_binary(self, label, steps=1):
        return self.vertex_propagate(label, value=True, steps=steps)

    def vertex_erode_binary(self, label, steps=1):
        return self.vertex_propagate(label, value=False, steps=steps)

    def vertex_open_binary(self, label, steps=1):
        label = self.vertex_erode_binary(label, steps=steps)
        return self.vertex_dilate_binary(label, steps=steps)

    def vertex_close_binary(self, label, steps=1):
        label = self.vertex_dilate_binary(label, steps=steps)
        return self.vertex_erode_binary(label, steps=steps)

    def expand_vertex_filter(self, vertex_filter, steps=1):
        return self.vertex_dilate_binary(vertex_filter, steps=steps)

    def edge_propagate(self, label, value, steps=1):
        label = np.array(label)
        if steps is None:
            return label
        for s in range(steps):
            edges = label == value
            ec = self.edge_connectivity()
            ec = ec[edges]
            vertices = np.unique(ec)
            for v in vertices:
                for e in self.vertex_edges_iterator(v):
                    i = self.edge_index(e)
                    label[i] = value
        return label

    def edge_dilate_binary(self, label, steps=1):
        return self.edge_propagate(label, value=True, steps=steps)

    def edge_erode_binary(self, label, steps=1):
        return self.edge_propagate(label, value=False, steps=steps)

    def edge_open_binary(self, label, steps=1):
        label = self.edge_erode_binary(label, steps=steps)
        return self.edge_dilate_binary(label, steps=steps)

    def edge_close_binary(self, label, steps=1):
        label = self.edge_dilate_binary(label, steps=steps)
        return self.edge_erode_binary(label, steps=steps)

    ################# MAPPING FUNCTIONS #################

    def vertex_ids_to_connectivity(self, vertex_indices):
        """
        Get the edge connectivity for a set of vertices.
        This will return any edge that has at least one vertex in the set of vertex_indices.

        Parameters
        ----------
        vertex_indices : list of int
            The vertex indices to consider.

        Returns
        -------
        connectivity : np.ndarray
        """
        start_mask, end_mask, connectivity = self.vertex_ids_to_vertex_masks(vertex_indices)
        return connectivity[np.logical_or(start_mask, end_mask)]

    def vertex_ids_to_vertex_masks(self, vertex_indices):
        connectivity = self.edge_connectivity()
        start_mask = np.isin(connectivity[:, 0], vertex_indices)
        end_mask = np.isin(connectivity[:, 1], vertex_indices)
        return start_mask, end_mask, connectivity

    def vertex_indices_to_vectors(self, vertex_indices, coordinates_name='coordinates'):
        """
        Get the edge vectors for a set of vertices.

        Parameters
        ----------
        vertex_indices : list of int
            The vertex indices to consider.
        coordinates_name : str
            The name of the vertex property that contains the coordinates.
            Typically 'coordinates', 'coordinates_atlas', 'coordinates_um'...

        Returns
        -------
        vectors : np.ndarray
        """
        connectivity = self.vertex_ids_to_connectivity(vertex_indices)
        if coordinates_name == 'coordinates':
            coordinates = self.vertex_coordinates()
        else:
            coordinates = self.vertex_property(coordinates_name)
        return np.hstack([coordinates[connectivity[:, 0]], coordinates[connectivity[:, 1]]])

    # FIXME: check if these are ordered as expected
    def vertex_to_edge_property(self, vertex_property, mapping=np.logical_and, vertices=None):
        """
        Converts vertex_property from vertex to edge property

        Parameters
        ----------
        vertex_property : str or np.array
            The name of the vertex property to convert or the vertex property itself
        mapping : function
            The mapping function to apply to the vertex property.
            Typically np.logical_and, np.logical_or, np.mean, np.max, np.sum, ...
        vertices : list of int
            The vertices to consider. If None, all vertices are considered.

        .. warning:: The mapping function should be able to handle numpy arrays of
            the type of the vertex property.

        Returns
        -------
        The edge property (as a numpy array)
        """
        vertex_prop = self.vertex_property(vertex_property) if isinstance(vertex_property, str) else vertex_property
        if vertices is None:
            connectivity = self.edge_connectivity()
        else:
            connectivity = self.vertex_ids_to_connectivity(vertices)
        edge_prop = np.array(mapping(vertex_prop[connectivity[:, 0]], vertex_prop[connectivity[:, 1]]),
                             dtype=vertex_property.dtype)
        return edge_prop

    def vertex_filter_to_edge_filter(self, vertex_filter, mode='both'):
        """
        Converts a vertex filter to an edge filter

        Parameters
        ----------
        vertex_filter : np.array
            The vertex filter to convert
        mode : str
            The mode to apply to map from vertex to edge filter.
            It can be:
                'both': both vertices have to follow the filter
                'either': either vertex has to follow the filter
                 (or the boolean equivalents 'and', 'or')

        Returns
        -------
        The edge filter (as a numpy array)
        """
        mappings = {
            'both': np.logical_and,
            'either': np.logical_or,
            'and': np.logical_and,
            'or': np.logical_or
        }
        connectivity = self.edge_connectivity()
        start_vertex_follows_filter = vertex_filter[connectivity[:, 0]]
        end_vertex_follows_filter = vertex_filter[connectivity[:, 1]]
        try:
            operator = mappings[mode]
        except KeyError:
            raise ValueError(f'Unknown mode {mode}! Choose from {mappings.keys()}')
        edge_filter = operator(start_vertex_follows_filter, end_vertex_follows_filter)
        return edge_filter

    def edge_to_vertex_label(self, edge_label, method='max', as_array=True):
        # TODO: compare implementation with
        #  edge_connectivity = graph.edge_connectivity()
        #  vertex_property_data = np.zeros(graph.n_vertices)
        #  for i in range(edge_connectivity.shape[1]):
        #      vertex_property_data[edge_connectivity[edge_property_data == 1, i]] = 1
        #  if dtype is not None:
        #      vertex_property_data = vertex_property_data.astype(dtype)

        if isinstance(edge_label, str):
            edge_label = self.edge_property(edge_label)
        if not isinstance(edge_label, gt.PropertyMap):
            edge_label = edge_property_map_from_python(edge_label, self)
        vertex_label = gt.incident_edges_op(self.base, 'in', method, edge_label)
        return vertex_property_map_to_python(vertex_label, as_array=as_array)

    def edge_to_vertex_label_or(self, edge_label):
        label = np.zeros(self.n_vertices, dtype=edge_label.dtype)
        ec = self.edge_connectivity()
        # label[ec[:,0]] = edge_label
        # label[ec[:,1]] = np.logical_or(edge_label, label[ec[:,1]])
        ids = np.unique(ec[edge_label].flatten())
        label[ids] = True
        return label

    def vertex_to_edge_label(self, vertex_label, method=None):  # FIXME: use vertex_to_con
        ec = self.edge_connectivity()

        if method is None:
            if vertex_label.dtype == bool:
                label = np.mean([vertex_label[ec[:, 0]], vertex_label[ec[:, 1]]], axis=0) == 1
            else:
                label = np.mean([vertex_label[ec[:, 0]], vertex_label[ec[:, 1]]], axis=0)
        else:
            label = method(vertex_label[ec[:, 0]], vertex_label[ec[:, 1]])

        return label

    # ## Geometric manipulation
    def sub_slice(self, slicing, view=False, coordinates=None):
        valid = self.sub_slice_vertex_filter(slicing, coordinates=coordinates)
        return self.sub_graph(vertex_filter=valid, view=view)

    def _slice_coordinates(self, coordinates, slicing, size):
        import ClearMap.IO.IO as io
        slicing = io.slc.unpack_slicing(slicing, self.ndim)
        valid = np.ones(size, dtype=bool)
        for d, s in enumerate(slicing):
            if isinstance(s, slice):
                if s.start is not None:
                    valid = np.logical_and(valid, s.start <= coordinates[:, d])
                if s.stop is not None:
                    valid = np.logical_and(valid, coordinates[:, d] < s.stop)
            elif isinstance(s, int):
                valid = np.logical_and(valid, coordinates[:, d] == s)
            else:
                raise ValueError(f'Invalid slicing {s} in dimension {d} for sub slicing the graph')
        return valid

    def sub_slice_vertex_filter(self, slicing, coordinates=None):
        if coordinates is None:
            coordinates = self.vertex_coordinates()
        elif isinstance(coordinates, str):
            coordinates = self.vertex_property(coordinates)
        valid = self._slice_coordinates(coordinates, slicing, size=self.n_vertices)
        return valid

    def sub_slice_edge_filter(self, slicing, coordinates=None):
        if coordinates is None:
            coordinates = self.edge_coordinates()
        elif isinstance(coordinates, str):
            coordinates = self.edge_property(coordinates)
        valid = self._slice_coordinates(coordinates, slicing, size=self.n_edges)
        return valid

    def transform_properties(self, transformation,
                             vertex_properties=None,
                             edge_properties=None,
                             edge_geometry_properties=None,
                             verbose=False):
        def properties_to_dict(properties):
            if properties is None:
                properties = {}
            if isinstance(properties, list):
                properties = {n: n for n in properties}
            return properties

        vertex_properties = properties_to_dict(vertex_properties)
        edge_properties = properties_to_dict(edge_properties)
        edge_geometry_properties = properties_to_dict(edge_geometry_properties)

        for p in vertex_properties.keys():
            # if p in self.vertex_properties:
            if verbose:
                print(f'Transforming vertex property: {p} -> {vertex_properties[p]}')
            values = self.vertex_property(p)
            values = transformation(values)
            self.define_vertex_property(vertex_properties[p], values)

        for p in edge_properties.keys():
            # if p in self.edge_properties:
            if verbose:
                print(f'Transforming edge property: {p} -> {edge_properties[p]}')
            values = self.edge_property(p)
            values = transformation(values)
            self.define_edge_property(edge_properties[p], values)

        as_list = self.edge_geometry_type != 'graph'
        for p in edge_geometry_properties.keys():
            # if p in self.edge_geometry_properties:
            if verbose:
                print(f'Transforming edge geometry: {p} -> {edge_geometry_properties[p]}')
            values = self.edge_geometry(p, as_list=as_list)
            if as_list:
                values = [transformation(v) for v in values]
            else:
                values = transformation(values)
            self.set_edge_geometry(edge_geometry_properties[p], values=values)

    # ## Annotation

    def vertex_annotation(self, vertex=None):
        return self.vertex_property('annotation', vertex=vertex)

    def set_vertex_annotation(self, annotation, vertex=None, dtype='int32'):
        self.define_vertex_property('annotation', annotation, vertex=vertex, dtype=dtype)

    def edge_annotation(self, edge=None):
        return self.edge_property('annotation', edge=edge)

    def set_edge_annotation(self, annotation, edge=None, dtype='int32'):
        self.define_edge_property('annotation', annotation, edge=edge, dtype=dtype)

    def annotate_properties(self, annotation,
                            vertex_properties=None,
                            edge_properties=None,
                            edge_geometry_properties=None):
        self.transform_properties(annotation,
                                  vertex_properties=vertex_properties,
                                  edge_properties=edge_properties,
                                  edge_geometry_properties=edge_geometry_properties)

    # ## Generic
    def info(self):
        print(self.__str__())
        self._base.list_properties()

    def save(self, filename):
        self._base.save(filename)

    def load(self, filename):
        self._base = gt.load_graph(filename)

    def copy(self):
        return Graph(name=copy.copy(self.name), base=self.base.copy())


def load(filename):
    g = gt.load_graph(filename)
    return Graph(base=g)


def save(filename, graph):
    graph.save(filename)


###############################################################################
# ## Tests
###############################################################################

def _test():
    import numpy as np
    import ClearMap.Analysis.Graphs.GraphGt as ggt

    from importlib import reload
    reload(ggt)

    g = ggt.Graph('test')

    g.add_vertex(10)

    el = [[1, 3], [2, 5], [6, 7], [7, 9]]
    g.add_edge(el)

    print(g)
    coords = np.random.rand(10,3)
    g.set_vertex_coordinates(coords)

    g.vertex_coordinates()

    # edge geometry
    elen = [3, 4, 5, 6]
    geometry = [np.random.rand(l, 3) for l in elen]

    g.set_edge_geometry(geometry)

    g.edge_geometry()

    g.add_edge_property('test', [3, 4, 5, 6])

    g2 = ggt.Graph('test2')
    g2.add_vertex(10)
    g2.add_edge([[1, 3], [2, 5], [6, 7], [7, 9]])
    g2.edge_geometry_type = 'edge'

    elen = [3, 4, 5, 6]
    geometry = [np.random.rand(l, 3) for l in elen]
    g2.set_edge_geometry(geometry)

    g2.edge_geometry()

    # graph properties
    reload(ggt)
    g = ggt.Graph('test')
    g.add_vertex(10)
    g.add_edge([[1, 3], [2, 5], [6, 7], [7, 9]])

    # scalar vertex property
    g.add_vertex_property('test', np.arange(g.n_vertices))
    print(g.vertex_property('test') == np.arange(g.n_vertices))

    # vector vertex property
    x = np.random.rand(g.n_vertices, 5)
    g.add_vertex_property('vector', x)
    print(np.all(g.vertex_property('vector') == x))

    # vector vertex property with different lengths
    y = [np.arange(i) for i in range(g.n_vertices)]
    g.define_vertex_property('list', y)
    z = g.vertex_property('list', as_array=False)
    print(z == y)

    # edge properties
    x = 10 * np.arange(g.n_edges)
    g.add_edge_property('test', x)
    assert g.edge_property('test') == x

    g.info()

    # filtering / sub-graphs
    v_filter = [True] * 5 + [False] * 5
    s = g.sub_graph(vertex_filter=v_filter)

    p = s.vertex_property_map('test')
    print(p.a)

    p = s.edge_property_map('test')
    print(p.a)

    print(s.vertex_property('list', as_array=False))

    # views
    v_filter = [False] * 5 + [True] * 5
    v = g.sub_graph(vertex_filter=v_filter, view=True)
    print(v.edge_property('test'))
    print(v.vertex_property('list', as_array=False))

    # sub-graphs and edge geometry
    reload(ggt)

    g = ggt.Graph('edge_geometry')
    g.add_vertex(5)
    g.add_edge([[0, 1], [1, 2], [2, 3], [3, 4]])

    geometry = [np.random.rand(l, 3) for l in [3, 4, 5, 6]]
    g.set_edge_geometry(geometry)

    # note te difference !
    s = g.sub_graph(vertex_filter=[False]*2 + [True]*3)
    s.edge_geometry()
    s.edge_geometry(as_list=False)
    s._edge_geometry_indices_graph()

    v = g.sub_graph(vertex_filter=[False]*2 + [True]*3, view=True)
    v.edge_geometry()
    v.edge_geometry(as_list=False)
    v._edge_geometry_indices_graph()

    # vertex expansion
    reload(ggt)
    g = ggt.Graph()
    g.add_vertex(5)
    g.add_edge([[0, 1], [1, 2], [2, 3], [3, 4]])
    vertex_filter = np.array([False, False, True, False, False], dtype='bool')
    expanded = g.expand_vertex_filter(vertex_filter, steps=1)
    print(expanded)

    # test large arrays in graphs
    import numpy as np
    import ClearMap.IO.IO as io
    import ClearMap.Analysis.Graphs.GraphGt as ggt
    reload(ggt)

    g = ggt.Graph('test')
    g.add_vertex(10)

    x = np.zeros(2147483648, dtype='uint8')

    g.define_graph_property('test', x)
    g.save('test.gt')
    # this gives an error when using unmodified graph_tool

    del g
    del x
    import ClearMap.Analysis.Graphs.GraphGt as ggt
    f = ggt.load('test.gt')
    f.info()
    print(f.graph_property('test').shape)

    io.delete_file('test.gt')
