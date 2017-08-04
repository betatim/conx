# conx - a neural network library
#
# Copyright (c) Douglas S. Blank <dblank@cs.brynmawr.edu>
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor,
# Boston, MA 02110-1301  USA

#------------------------------------------------------------------------

import numbers
import operator
from functools import reduce

import numpy as np
import keras
from keras.optimizers import (SGD, RMSprop, Adagrad, Adadelta, Adam, Adamax, Nadam,
                              TFOptimizer)

from .utils import *
#------------------------------------------------------------------------

class BaseLayer():
    ACTIVATION_FUNCTIONS = ('relu', 'sigmoid', 'linear', 'softmax', 'tanh')
    CLASS = None

    def __init__(self, name, *args, **params):
        if not (isinstance(name, str) and len(name) > 0):
            raise Exception('bad layer name: %s' % (name,))
        self.name = name
        self.params = params
        self.args = args
        params["name"] = name
        self.shape = None
        self.vshape = None
        self.visible = True
        self.colormap = None
        self.minmax = None
        self.model = None
        self.decode_model = None
        self.input_names = []
        # used to determine image ranges:
        self.activation = params.get("activation", None) # make a copy, if one
        # set visual shape for display purposes
        if 'vshape' in params:
            vs = params['vshape']
            del params["vshape"] # drop those that are not Keras parameters
            if not valid_vshape(vs):
                raise Exception('bad vshape: %s' % (vs,))
            else:
                self.vshape = vs

        if 'visible' in params:
            visible = params['visible']
            del params["visible"] # drop those that are not Keras parameters
            self.visible = visible

        if 'colormap' in params:
            self.colormap = params['colormap']
            del params["colormap"] # drop those that are not Keras parameters

        if 'minmax' in params:
            self.minmax = params['minmax']
            del params["minmax"] # drop those that are not Keras parameters

        if 'dropout' in params:
            dropout = params['dropout']
            del params["dropout"] # we handle dropout layers
            if dropout == None: dropout = 0
            if not (isinstance(dropout, numbers.Real) and 0 <= dropout <= 1):
                raise Exception('bad dropout rate: %s' % (dropout,))
            self.dropout = dropout
        else:
            self.dropout = 0
        self.incoming_connections = []
        self.outgoing_connections = []

    def __repr__(self):
        return "<%s name='%s'>" % (self.CLASS.__name__, self.name)

    def summary(self):
        print("Name: %s (%s) VShape: %s Dropout: %s" %
              (self.name, self.kind(), self.vshape, self.dropout))
        if len(self.outgoing_connections) > 0:
            print("Connected to:", [layer.name for layer in self.outgoing_connections])

    def kind(self):
        if len(self.incoming_connections) == 0 and len(self.outgoing_connections) == 0:
            return 'unconnected'
        elif len(self.incoming_connections) > 0 and len(self.outgoing_connections) > 0:
            return 'hidden'
        elif len(self.incoming_connections) > 0:
            return 'output'
        else:
            return 'input'

    def make_input_layer_k(self):
        return keras.layers.Input(self.shape, *self.args, **self.params)

    def make_keras_function(self):
        return self.CLASS(*self.args, **self.params)

    def make_keras_functions(self):
        k = self.make_keras_function() # can override
        if self.dropout > 0:
            return [k, keras.layers.Dropout(self.dropout)]
        else:
            return [k]

    def make_image(self, vector, size=25):
        """
        Given an activation name (or function), and an output vector, display
        make and return an image widget.
        """
        from matplotlib import cm
        import PIL
        ## FIXME: grabbing a couple of dimensions
        while len(vector.shape) > 2:
            vector = vector[0]
        if self.vshape != self.shape:
            vector = vector.reshape(self.vshape)
        minmax = self.get_minmax(vector)
        vector = self.scale_output_for_image(vector, minmax)
        if len(vector.shape) == 1:
            vector = vector.reshape((1, vector.shape[0]))
        new_width = vector.shape[0] * size # in, pixels
        new_height = vector.shape[1] * size # in, pixels
        if self.colormap:
            cm_hot = cm.get_cmap(self.colormap)
            vector = cm_hot(vector)
            vector = np.uint8(vector * 255)
            image = PIL.Image.fromarray(vector)
        else:
            image = PIL.Image.fromarray(vector, 'P')
        image = image.resize((new_height, new_width))
        return image

    def scale_output_for_image(self, vector, minmax):
        """
        Given an activation name (or something else) and an output
        vector, scale the vector.
        """
        return rescale_numpy_array(vector, minmax, (0,255), 'uint8')

    def make_dummy_vector(self):
        """
        This is in the easy to use human format (list of lists ...)
        """
        ## FIXME: for pictures give a vector
        v = np.ones(self.shape)
        lo, hi = self.get_minmax(v)
        v *= (lo + hi) / 2.0
        return v.tolist()

    def get_minmax(self, vector):
        if self.minmax:
            return self.minmax
        # ('relu', 'sigmoid', 'linear', 'softmax', 'tanh')
        if self.activation in ["tanh"]:
            return (-1,+1)
        elif self.activation in ["sigmoid", "softmax"]:
            return (0,+1)
        elif self.activation in ["relu"]:
            return (0,vector.max())
        else: # activation in ["linear"] or otherwise
            return (-1,+1)

    def tooltip(self):
        """
        String (with newlines) for describing layer."
        """
        kind = self.kind()
        retval = "Layer: %s (%s)" % (self.name, kind)
        if self.shape:
            retval += "\n shape = %s" % (self.shape, )
        if self.dropout:
            retval += "\n dropout = %s" % self.dropout
        if kind == "input":
            retval += "\n Keras class = Input"
        else:
            retval += "\n Keras class = %s" % self.CLASS.__name__
        for key in self.params:
            if key in ["name"]:
                continue
            retval += "\n %s = %s" % (key, self.params[key])
        return retval

class Layer(BaseLayer):
    """
    For Dense and Input type layers.
    """
    CLASS = keras.layers.Dense
    def __init__(self, name, shape, **params):
        super().__init__(name, **params)
        if not valid_shape(shape):
            raise Exception('bad shape: %s' % (shape,))
        # set layer topology (shape) and number of units (size)
        if isinstance(shape, numbers.Integral):
            self.shape = (shape,)
            self.size = shape
        else:
            # multi-dimensional layer
            self.shape = shape
            self.size = reduce(operator.mul, shape)

        if 'activation' in params:
            act = params['activation']
            if act == None:
                act = 'linear'
            if not (callable(act) or act in Layer.ACTIVATION_FUNCTIONS):
                raise Exception('unknown activation function: %s' % (act,))
            self.activation = act
        self.incoming_connections = []
        self.outgoing_connections = []

    def __repr__(self):
        return "<Layer name='%s', shape=%s, act='%s'>" % (
            self.name, self.shape, self.activation)

    def summary(self):
        print("Name: %s (%s) Shape: %s Size: %d VShape: %s Activation function: %s Dropout: %s" %
              (self.name, self.kind(), self.shape, self.size, self.vshape, self.activation, self.dropout))
        if len(self.outgoing_connections) > 0:
            print("Connected to:", [layer.name for layer in self.outgoing_connections])

    def make_keras_function(self):
        return self.CLASS(self.size, **self.params)

class PictureLayer(Layer):
    def make_image(self, vector):
        """
        Given an activation name (or function), and an output vector, display
        make and return an image widget.
        """
        import PIL
        return PIL.Image.fromarray(vector.astype("uint8")).resize((200,200))

class LSTMLayer(BaseLayer):
    CLASS = keras.layers.LSTM

class Conv2DLayer(BaseLayer):
    CLASS = keras.layers.Conv2D

class MaxPooling2DLayer(BaseLayer):
    CLASS = keras.layers.MaxPooling2D

class FlattenLayer(BaseLayer):
    CLASS = keras.layers.Flatten

DenseLayer = Layer
InputLayer = Layer