from setuptools import setup, find_packages

setup(
    name="datashark",
    version="1.0.0",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "typer",
        "rich",
        "openai",
        "chromadb",
    ],
    entry_points={
        "console_scripts": [
            "datashark=datashark.cli:app",
        ],
    },
)
