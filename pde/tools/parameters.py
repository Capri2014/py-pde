'''
This module provides infrastructure for managing classes with parameters. One
aim is to allow easy management of inheritance of parameters.

.. autosummary::
   :nosignatures:

   Parameter
   DeprecatedParameter
   ObsoleteParameter
   Parameterized
   get_all_parameters

.. codeauthor:: David Zwicker <david.zwicker@ds.mpg.de>
'''


import logging
from collections import OrderedDict
from typing import Sequence, Dict, Any, Set, Union  # @UnusedImport

from pde.tools.misc import import_class, hybridmethod



class Parameter():
    """ class representing a single parameter """
    
    def __init__(self, name: str,
                 default_value=None,
                 cls=object,
                 description: str = '',
                 hidden: bool = False):
        """ initialize a parameter 
        
        Args:
            name (str):
                The name of the parameter
            default_value:
                The default value
            cls:
                The type of the parameter, which is used for conversion
            description (str):
                A string describing the impact of this parameter. This
                description appears in the parameter help
            hidden (bool):
                Whether the parameter is hidden in the description summary
        """
        self.name = name
        self.default_value = default_value
        self.cls = cls
        self.description = description
        self.hidden = hidden
        if cls is not object and cls(default_value) != default_value:
            logging.warning('Default value `%s` does not seem to be of type '
                            '`%s`', name, cls.__name__)
    
        
    def __repr__(self):
        return (f'{self.__class__.__name__}(name="{self.name}", default_value='
                f'"{self.default_value}", cls="{self.cls.__name__}", '
                f'description="{self.description}", hidden={self.hidden})')
    __str__ = __repr__
    
    
    def __getstate__(self):
        # replace the object class by its class path 
        return {'name': str(self.name),
                'default_value': self.convert(),
                'cls': object.__module__ + '.' + self.cls.__name__,
                'description': self.description,
                'hidden': self.hidden}
    
        
    def __setstate__(self, state):
        # restore the object from the class path
        state['cls'] = import_class(state['cls'])
        # restore the state
        self.__dict__.update(state)
        
        
    def convert(self, value=None):
        """ converts a `value` into the correct type for this parameter. If
        `value` is not given, the default value is converted.
        
        Note that this does not make a copy of the values, which could lead to
        unexpected effects where the default value is changed by an instance.
        
        Args:
            value: The value to convert
        
        Returns:
            The converted value, which is of type `self.cls`
        """ 
        if value is None:
            value = self.default_value
            
        if self.cls is object:
            return value
        else:
            try:
                return self.cls(value)
            except ValueError:
                raise ValueError(f"Could not convert {value!r} to "
                                 f"{self.cls.__name__} for parameter "
                                 f"'{self.name}'")



class DeprecatedParameter(Parameter):
    """ a parameter that can still be used normally but is deprecated """
    pass



class HideParameter():
    """ a helper class that allows hiding parameters of the parent classes """
    
    
    def __init__(self, name: str):
        """ 
        Args:
            name (str):
                The name of the parameter
        """
        self.name = name



ParameterListType = Sequence[Union[Parameter, HideParameter]]



class Parameterized():
    """ a mixin that manages the parameters of a class """

    parameters_default: ParameterListType = []
    _subclasses: Dict[str, 'Parameterized'] = {}


    def __init__(self, parameters: Dict[str, Any] = None):
        """ initialize the parameters of the object
        
        Args:
            parameters (dict):
                A dictionary of parameters to change the defaults. The allowed
                parameters can be shown by calling 
                :meth:`~Parameterized.show_parameters`.
        """
        self._logger = logging.getLogger(self.__class__.__name__)
        if not hasattr(self, 'parameters'):
            # only set parameters automatically if they are not yet set
            self.parameters = self._parse_parameters(parameters)



    def __init_subclass__(cls, **kwargs):  # @NoSelf
        """ register all subclasses to reconstruct them later """
        # normalize the parameters_default attribute
        if (hasattr(cls, 'parameters_default') and
                isinstance(cls.parameters_default, dict)):
            # default parameters are given as a dictionary
            cls.parameters_default = \
                [Parameter(*args) for args in cls.parameters_default.items()]
        
        # register the subclasses
        super().__init_subclass__(**kwargs)
        cls._subclasses[cls.__name__] = cls
            

    @classmethod        
    def get_parameters(cls, include_hidden: bool = False,
                       include_deprecated: bool = False,
                       sort: bool = True) -> Dict[str, Parameter]:
        """ return a dictionary of parameters that the class supports
        
        Args:
            include_hidden (bool): Include hidden parameters
            include_deprecated (bool): Include deprecated parameters
            sort (bool): Return ordered dictionary with sorted keys
            
        Returns:
            dict: a dictionary of instance of :class:`Parameter` with their
            names as keys.
        """
        parameters: Dict[str, Parameter] = {}
        for cls in reversed(cls.__mro__):
            if hasattr(cls, 'parameters_default'):
                for p in cls.parameters_default:
                    if isinstance(p, HideParameter):
                        if include_hidden:
                            parameters[p.name].hidden = True
                        else:
                            del parameters[p.name]
                    elif (include_deprecated or
                            not isinstance(p, DeprecatedParameter)):
                        parameters[p.name] = p
                        
        if sort:
            parameters = OrderedDict(sorted(parameters.items()))
        return parameters
            
        
    @classmethod    
    def _parse_parameters(cls, parameters: Dict[str, Any] = None,
                          check_validity: bool = True,
                          allow_hidden: bool = True,
                          include_deprecated: bool = False) -> Dict[str, Any]:
        """ parse parameters

        Args:
            parameters (dict):
                A dictionary of parameters that will be parsed. 
            check_validity (bool):
                Determines whether a `ValueError` is raised if there are keys in
                parameters that are not in the defaults. If `False`, additional
                items are simply stored in `self.parameters`
            allow_hidden (bool):
                Allow setting hidden parameters
            include_deprecated (bool):
                Include deprecated parameters
        """
        if parameters is None:
            parameters = {}
        else:
            parameters = parameters.copy()  # do not modify the original
        
        # obtain all possible parameters
        param_objs = cls.get_parameters(include_hidden=allow_hidden,
                                         include_deprecated=include_deprecated)
        
        # initialize parameters with default ones from all parent classes
        result: Dict[str, Any] = {}
        for name, param_obj in param_objs.items():
            if not allow_hidden and param_obj.hidden:
                continue  # skip hidden parameters
            # take value from parameters or set default value
            result[name] = param_obj.convert(parameters.pop(name, None))
                
        # update parameters with the supplied ones
        if check_validity and parameters:
            raise ValueError(f'Parameters `{sorted(parameters.keys())}` were '
                             'provided in instance specific parameters but are '
                             f'not defined for the class `{cls.__name__}`.')
        else:
            result.update(parameters)  # add remaining parameters

        return result
            

    def get_parameter_default(self, name):
        """ return the default value for the parameter with `name` 
        
        Args:
            name (str): The parameter name
        """
        for cls in self.__class__.__mro__:
            if hasattr(cls, 'parameters_default'):
                for p in cls.parameters_default:
                    if isinstance(p, Parameter) and p.name == name:
                        return p.default_value

        raise KeyError(f'Parameter `{name}` is not defined')
        
        
    @classmethod
    def _show_parameters(cls, description: bool = False,
                         sort: bool = False,
                         show_hidden: bool = False,
                         show_deprecated: bool = False,
                         parameter_values: Dict[str, Any] = None):
        """ private method showing all parameters in human readable format
        
        Args:
            description (bool):
                Flag determining whether the parameter description is shown
            sort (bool):
                Flag determining whether the parameters are sorted
            show_hidden (bool):
                Flag determining whether hidden parameters are shown
            show_deprecated (bool):
                Flag determining whether deprecated parameters are shown
            parameter_values (dict):
                A dictionary with values to show. Parameters not in this
                dictionary are shown with their default value.
        
        All flags default to `False`.
        """
        # set the templates for displaying the data 
        if description:
            template = '{name}: {type} = {value!r} ({description})'
            template_object = '{name} = {value!r} ({description})'
        else:
            template = '{name}: {type} = {value!r}'
            template_object = '{name} = {value!r}'
            
        # iterate over all parameters
        params = cls.get_parameters(include_deprecated=show_deprecated,
                                     sort=sort)
        for param in params.values():
            if not show_hidden and param.hidden:
                continue  # skip hidden parameters
            
            # initialize the data to show
            data = {'name': param.name,
                    'type': param.cls.__name__,
                    'description': param.description}
            
            # determine the value to show
            if parameter_values is None:
                data['value'] = param.default_value
            else:
                data['value'] = parameter_values[param.name]
            
            # print the data
            if param.cls is object:
                print((template_object.format(**data)))
            else:
                print((template.format(**data)))
            

    @hybridmethod
    def show_parameters(cls, description: bool = False,  # @NoSelf
                        sort: bool = False,
                        show_hidden: bool = False,
                        show_deprecated: bool = False):
        """ show all parameters in human readable format
        
        Args:
            description (bool):
                Flag determining whether the parameter description is shown
            sort (bool):
                Flag determining whether the parameters are sorted
            show_hidden (bool):
                Flag determining whether hidden parameters are shown
            show_deprecated (bool):
                Flag determining whether deprecated parameters are shown
        
        All flags default to `False`.
        """
        cls._show_parameters(description, sort, show_hidden, show_deprecated)    


    @show_parameters.instancemethod  # type: ignore
    def show_parameters(self, description: bool = False,  # @NoSelf
                        sort: bool = False,
                        show_hidden: bool = False,
                        show_deprecated: bool = False,
                        default_value: bool = False):
        """ show all parameters in human readable format
        
        Args:
            description (bool):
                Flag determining whether the parameter description is shown
            sort (bool):
                Flag determining whether the parameters are sorted
            show_hidden (bool):
                Flag determining whether hidden parameters are shown
            show_deprecated (bool):
                Flag determining whether deprecated parameters are shown
            default_value (bool):
                Flag determining whether the default values or the current
                values are shown
        
        All flags default to `False`.
        """
        self._show_parameters(description, sort, show_hidden, show_deprecated,
                              None if default_value else self.parameters)
        
        

def get_all_parameters(data: str = None) -> Dict[str, Any]:
    """ get a dictionary with all parameters of all registered classes """
    result = {}
    for cls_name, cls in Parameterized._subclasses.items():
        if data is None:
            parameters = set(cls.get_parameters().keys())
        elif data == 'value':
            parameters = {k: v.default_value  # type: ignore
                          for k, v in cls.get_parameters().items()}
        elif data == 'description':
            parameters = {k: v.description  # type: ignore
                          for k, v in cls.get_parameters().items()}
        else:
            raise ValueError(f'Cannot interpret data `{data}`')
        
        result[cls_name] = parameters
    return result
        
                