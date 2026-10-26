"""Runtime hook to inject missing VTK constants into vtkmodules.vtkCommonCore and vtkmodules.util.numpy_support before they are used."""
import sys
import types

# The constants from vtkmodules.util.vtkConstants (the actual VTK 9.x constants)
vtk_constants = {
    'VTK_VOID': 0,
    'VTK_BIT': 1,
    'VTK_CHAR': 2,
    'VTK_SIGNED_CHAR': 15,
    'VTK_UNSIGNED_CHAR': 3,
    'VTK_SHORT': 4,
    'VTK_UNSIGNED_SHORT': 5,
    'VTK_INT': 6,
    'VTK_UNSIGNED_INT': 7,
    'VTK_LONG': 8,
    'VTK_UNSIGNED_LONG': 9,
    'VTK_FLOAT': 10,
    'VTK_DOUBLE': 11,
    'VTK_ID_TYPE': 12,
    'VTK_LONG_LONG': 16,
    'VTK_UNSIGNED_LONG_LONG': 17,
    'VTK_STRING': 13,
    'VTK_OPAQUE': 14,
    'VTK_VARIANT': 20,
    'VTK_OBJECT': 21,
    'VTK_ID_TYPE_IMPL': 12,
}

derived = {
    'VTK_BIT_MIN': 0,
    'VTK_BIT_MAX': 1,
    'VTK_CHAR_MIN': -128,
    'VTK_CHAR_MAX': 127,
    'VTK_UNSIGNED_CHAR_MIN': 0,
    'VTK_UNSIGNED_CHAR_MAX': 255,
    'VTK_SHORT_MIN': -32768,
    'VTK_SHORT_MAX': 32767,
    'VTK_UNSIGNED_SHORT_MIN': 0,
    'VTK_UNSIGNED_SHORT_MAX': 65535,
    'VTK_INT_MIN': -2147483648,
    'VTK_INT_MAX': 2147483647,
    'VTK_LONG_MIN': -2147483648,
    'VTK_LONG_MAX': 2147483647,
    'VTK_FLOAT_MIN': -1.0e+38,
    'VTK_FLOAT_MAX': 1.0e+38,
    'VTK_DOUBLE_MIN': -1.0e+99,
    'VTK_DOUBLE_MAX': 1.0e+99,
}

# Inject into vtkmodules.vtkCommonCore BEFORE any other import
if 'vtkmodules.vtkCommonCore' not in sys.modules:
    import vtkmodules.vtkCommonCore as vtkCommonCore
else:
    vtkCommonCore = sys.modules['vtkmodules.vtkCommonCore']

for name, value in vtk_constants.items():
    if not hasattr(vtkCommonCore, name):
        setattr(vtkCommonCore, name, value)

if not hasattr(vtkCommonCore, '_VTK_INT_MAX'):
    setattr(vtkCommonCore, '_VTK_INT_MAX', 2147483647)
if not hasattr(vtkCommonCore, '_VTK_FLOAT_MAX'):
    setattr(vtkCommonCore, '_VTK_FLOAT_MAX', 1.0e+38)

for name, value in derived.items():
    if not hasattr(vtkCommonCore, name):
        setattr(vtkCommonCore, name, value)

# Create vtkConstants module-like object
vtkConstants_module = types.ModuleType('vtkConstants')
for name, value in vtk_constants.items():
    setattr(vtkConstants_module, name, value)
for name, value in derived.items():
    setattr(vtkConstants_module, name, value)
setattr(vtkConstants_module, '_VTK_INT_MAX', 2147483647)
setattr(vtkConstants_module, '_VTK_FLOAT_MAX', 1.0e+38)

# Inject into vtkCommonCore
setattr(vtkCommonCore, 'vtkConstants', vtkConstants_module)
sys.modules['vtkmodules.vtkCommonCore.vtkConstants'] = vtkConstants_module

# CRITICAL: Import and patch vtkmodules.util.numpy_support RIGHT NOW
# This ensures vtkConstants exists in its namespace before any code uses it
import vtkmodules.util.numpy_support as ns
ns.vtkConstants = vtkConstants_module