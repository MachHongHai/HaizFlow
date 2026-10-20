"""Keep SciPy's native linear-algebra entrypoints in inference engines."""

hiddenimports = [
    "scipy.linalg.cython_blas",
    "scipy.linalg.cython_lapack",
    "scipy.linalg._linalg_pythran",
]
