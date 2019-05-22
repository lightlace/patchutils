import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    #-- Package description
    name="patchutils",
    version="0.0.1",
    author="Petr Tesarik",
    author_email="ptesarik@suse.com",
    description="Patch file handling",
    long_description=long_description,
    url="https://github.com/ptesarik/patchutils",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 2 - Pre-Alpha",
        "License :: OSI Approved :: GNU General Public License v3 or later (GPLv3+)",
        "Operating System :: OS Independent",
    ],
    #-- Python "stand alone" modules
    py_modules = [
        'patchutils',
    ],
)
