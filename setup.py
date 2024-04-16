import kometautils, os

from setuptools import setup, find_packages

with open("README.rst", "r") as f:
    long_descr = f.read()

__version__ = None
if os.path.exists("VERSION"):
    with open("VERSION") as handle:
        for line in handle.readlines():
            line = line.strip()
            if len(line) > 0:
                __version__ = line
                break

with open("requirements.txt", "r") as handle:
    requirements = [i.strip() for i in handle.readlines()]

setup(
    name=kometautils.__package_name__,
    version=__version__,
    description=kometautils.__description__,
    long_description=long_descr,
    url=kometautils.__url__,
    author=kometautils.__author__,
    author_email=kometautils.__email__,
    license=kometautils.__license__,
    packages=find_packages(),
    python_requires=">=3.11",
    keywords=["kometautils"],
    install_requires=requirements,
    project_urls={
        "Documentation": "https://github.com/Kometa-Team/Kometa-Utils",
        "Funding": "https://github.com/sponsors/meisnate12",
        "Source": "https://github.com/Kometa-Team/Kometa-Utils",
        "Issues": "https://github.com/Kometa-Team/Kometa-Utils/issues",
    },
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Libraries",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ]
)
