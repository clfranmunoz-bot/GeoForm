"""Entry point for PyInstaller - absolute imports."""
import sys
import os

# CRITICAL: Load vtk constants hook FIRST before any VTK/PyVista imports
# This injects vtkConstants into vtkmodules.vtkCommonCore so numpy_support.py can find it
import geoform.vtk_constants_hook

# Add the package to path
sys.path.insert(0, os.path.dirname(__file__))

from geoform.__main__ import main

if __name__ == "__main__":
    main()