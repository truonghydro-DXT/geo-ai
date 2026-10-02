# setup.py nằm ở thư mục gốc
from setuptools import setup, Extension
from Cython.Build import cythonize
import glob
import os

# --- Thư mục chứa các file Python cần build ---
SOURCE_DIR = "public/algorithm"

# --- Tìm tất cả file .py ---
py_files = [
    f for f in glob.glob(os.path.join(SOURCE_DIR, "*.py"))
    if not f.endswith("__init__.py")
]

print("👉 Danh sách file được build:")
for f in py_files:
    print("  -", f)

# --- Tạo danh sách Extension ---
extensions = [
    Extension(
        name=os.path.splitext(os.path.relpath(f, '.'))[0].replace(os.sep, "."),
        sources=[f],
    )
    for f in py_files
]

setup(
    name="geoai-algorithms",
    ext_modules=cythonize(
        extensions,
        compiler_directives={'language_level': "3"},
        annotate=False
    ),
)
